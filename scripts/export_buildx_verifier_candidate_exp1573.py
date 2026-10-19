#!/usr/bin/env python3
"""One-shot offline Buildx export and in-memory identity check (EXP-1573)."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_contracts.brainbooster_target_profile import (  # noqa: E402
    TARGET_RUNTIME_IMAGE_ID,
    VERIFIER_CONTEXT_MODULES,
    VERIFIER_CONTEXT_SCHEMA_FILES,
)
from scripts.audit_portable_verifier_image_exp1350 import (  # noqa: E402
    InvalidChain,
    OutputLimitExceeded,
    _bounded_process_output,
    parse_portable_archive,
)
from scripts.export_verify_portable_image_exp1529 import DIFF_IDS  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
IMAGE_TAG = "agent00x-verifier:exp-1573-buildx"
PYTHON_BASE_REF = "python:3.11.16-slim@sha256:174bec68e0451bffabbb08c7d5d21c6b253f772d81d52b9558af97bb3159b761"
PLATFORM = "linux/amd64"
TIMEOUT_SECONDS = 300
MAX_ARCHIVE_BYTES = 640 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_CONTROL_OUTPUT_BYTES = 256
EXPECTED_USER = "65532:65532"
EXPECTED_ENTRYPOINT = ["python3", "-m", "app_contracts.verifier_container_entrypoint"]
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONTAINER_ID = re.compile(rb"[0-9a-f]{64}\n?\Z")

_CODES = {
    "OPT_IN_REQUIRED": 10,
    "PREFLIGHT_FAILED": 11,
    "CONTAINER_CREATE_FAILED": 12,
    "DEPENDENCY_COPY_FAILED": 13,
    "EXPORT_FAILED": 14,
    "EXPORT_LIMIT": 15,
    "EXPORT_TIMEOUT": 16,
    "ARCHIVE_INVALID": 17,
    "CLEANUP_FAILED": 18,
    "EXPORT_DIAGNOSTIC_LIMIT": 19,
    "BUILDX_EXPORT_CONFIRMED": 0,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


class DiagnosticOutputLimitExceeded(Exception):
    pass


def _bounded_build_export(command: tuple[str, ...], *, max_bytes: int,
                          max_stderr_bytes: int, timeout: float,
                          env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    """Capture bounded archive stdout and bounded diagnostic stderr."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, env=env
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise OSError
    selector = selectors.DefaultSelector()
    streams = {process.stdout: "stdout", process.stderr: "stderr"}
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": max_bytes, "stderr": max_stderr_bytes}
    deadline = time.monotonic() + timeout
    try:
        for stream in streams:
            selector.register(stream, selectors.EVENT_READ)
        while streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            events = selector.select(remaining)
            if not events:
                raise subprocess.TimeoutExpired(command, timeout)
            for key, _ in events:
                stream = key.fileobj
                kind = streams[stream]
                chunk = os.read(stream.fileno(), min(65536, limits[kind] + 1 - len(captured[kind])))
                if not chunk:
                    selector.unregister(stream)
                    del streams[stream]
                    continue
                captured[kind].extend(chunk)
                if len(captured[kind]) > limits[kind]:
                    if kind == "stderr":
                        raise DiagnosticOutputLimitExceeded
                    raise OutputLimitExceeded
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        returncode = process.wait(timeout=remaining)
        return subprocess.CompletedProcess(
            command, returncode, bytes(captured["stdout"]), bytes(captured["stderr"])
        )
    except (OutputLimitExceeded, DiagnosticOutputLimitExceeded, subprocess.TimeoutExpired):
        process.kill()
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()


def _export_failure_reason(stderr: bytes) -> str:
    """Map bounded, untrusted Buildx stderr to a fixed marker category."""
    text = stderr.decode("utf-8", errors="replace").lower()
    if "builder" in text and ("not found" in text or "no such builder" in text):
        return "builder_unsupported"
    if "exporter" in text and any(
        phrase in text for phrase in ("not supported", "unsupported", "unknown")
    ):
        return "exporter_unsupported"
    if any(phrase in text for phrase in ("failed to calculate checksum", "no such file or directory", "input not found")):
        return "missing_input"
    if any(phrase in text for phrase in ("network is unreachable", "network access", "network is disabled")):
        return "network_dependency"
    if any(phrase in text for phrase in ("permission denied", "operation not permitted")):
        return "permission_denied"
    if "failed to solve" in text or "solve failed" in text:
        return "solver_failed"
    return "unknown"


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def _env(config_dir: str) -> dict[str, str]:
    return {
        "DOCKER_CONFIG": config_dir,
        "DOCKER_HOST": DOCKER_HOST,
        "LANG": "C",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }


def _run_control(runner: Runner, args: tuple[str, ...], env: dict[str, str], *,
                 timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
    return runner(args, max_bytes=MAX_CONTROL_OUTPUT_BYTES, timeout=timeout, env=env)


def _prepare_context(context: Path) -> str:
    package_dir = context / "src" / "app_contracts"
    schema_dir = context / "schemas"
    package_dir.mkdir(parents=True)
    schema_dir.mkdir()
    (context / "target-python").mkdir()
    for rel in (
        Path("containers/verifier/Dockerfile"),
        Path("containers/target-runtime/requirements.lock"),
    ):
        destination = context / ("Dockerfile" if rel.name == "Dockerfile" else "requirements.lock")
        destination.write_bytes((ROOT / rel).read_bytes())
    for filename in VERIFIER_CONTEXT_MODULES:
        (package_dir / filename).write_bytes(
            (ROOT / "src" / "app_contracts" / filename).read_bytes()
        )
    for filename in VERIFIER_CONTEXT_SCHEMA_FILES:
        (schema_dir / filename).write_bytes((ROOT / "schemas" / filename).read_bytes())

    digest = hashlib.sha256()
    identity = [context / "Dockerfile", context / "requirements.lock"]
    identity.extend(sorted(package_dir.iterdir(), key=lambda item: item.name))
    identity.extend(sorted(schema_dir.iterdir(), key=lambda item: item.name))
    for path in identity:
        digest.update(path.relative_to(context).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _read_archive_config(archive: bytes) -> tuple[str, dict[str, object]]:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            members_list = tar.getmembers()
            if not 0 < len(members_list) <= 128:
                raise ValueError
            members = {item.name: item for item in members_list}
            if len(members) != len(members_list):
                raise ValueError
            for name, member in members.items():
                path = PurePosixPath(name.rstrip("/") if member.isdir() else name)
                if (not name or "\\" in name or path.is_absolute()
                        or path.as_posix() != name.rstrip("/")
                        or any(part in {"", ".", ".."} for part in path.parts)
                        or not (member.isfile() or member.isdir())):
                    raise ValueError
            manifest_member = members.get("manifest.json")
            if manifest_member is None or not manifest_member.isfile() or manifest_member.size > 65536:
                raise ValueError
            manifest_stream = tar.extractfile(manifest_member)
            if manifest_stream is None:
                raise ValueError
            manifests = json.loads(manifest_stream.read(65537))
            if not isinstance(manifests, list) or len(manifests) != 1:
                raise ValueError
            record = manifests[0]
            if (not isinstance(record, dict) or record.get("RepoTags") != [IMAGE_TAG]
                    or record.get("Layers") is None or not isinstance(record.get("Layers"), list)
                    or len(record["Layers"]) != len(DIFF_IDS)):
                raise ValueError
            config_name = record.get("Config")
            if not isinstance(config_name, str) or config_name not in members:
                raise ValueError
            config_member = members[config_name]
            if not config_member.isfile() or config_member.size > 1_048_576:
                raise ValueError
            config_stream = tar.extractfile(config_member)
            if config_stream is None:
                raise ValueError
            config_raw = config_stream.read(1_048_577)
            if len(config_raw) != config_member.size or len(config_raw) > 1_048_576:
                raise ValueError
            config_digest = "sha256:" + hashlib.sha256(config_raw).hexdigest()
            config = json.loads(config_raw)
            if not isinstance(config, dict):
                raise ValueError
            runtime = config.get("config")
            rootfs = config.get("rootfs")
            if (config.get("os") != "linux" or config.get("architecture") != "amd64"
                    or not isinstance(runtime, dict)
                    or runtime.get("User") != EXPECTED_USER
                    or runtime.get("Entrypoint") != EXPECTED_ENTRYPOINT
                    or not isinstance(rootfs, dict) or rootfs.get("type") != "layers"
                    or rootfs.get("diff_ids") != list(DIFF_IDS)):
                raise ValueError
        facts = parse_portable_archive(
            archive,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=DIFF_IDS,
            expected_repo_tag=IMAGE_TAG,
            max_archive_bytes=MAX_ARCHIVE_BYTES,
        )
        return facts.config_digest, config
    except Exception:
        raise InvalidChain("archive-validation") from None


def run_once(*, runner: Runner = _bounded_process_output,
             build_runner=_bounded_build_export,
             output: TextIO = sys.stdout,
             temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        return _emit(output, "OPT_IN_REQUIRED", _CODES["OPT_IN_REQUIRED"])

    container_id: str | None = None
    cleanup_ok = True
    archive: bytes | None = None
    code_digest = ""
    with temporary_directory(prefix="agent00x-exp1573-context-") as context_name, \
            temporary_directory(prefix="agent00x-exp1573-docker-config-") as config_name:
        context = Path(context_name)
        env = _env(config_name)
        try:
            code_digest = _prepare_context(context)
            preflight = _run_control(
                runner,
                (DOCKER, "--host=" + DOCKER_HOST, "image", "inspect", "--format", "{{.Id}}", TARGET_RUNTIME_IMAGE_ID),
                env,
            )
            base_preflight = _run_control(
                runner,
                (DOCKER, "--host=" + DOCKER_HOST, "image", "inspect", "--format", "{{.Id}}", PYTHON_BASE_REF),
                env,
            )
        except Exception:
            return _emit(output, "PREFLIGHT_FAILED", _CODES["PREFLIGHT_FAILED"])
        if preflight.returncode != 0 or preflight.stdout != (TARGET_RUNTIME_IMAGE_ID + "\n").encode("ascii"):
            return _emit(output, "PREFLIGHT_FAILED", _CODES["PREFLIGHT_FAILED"])
        if (base_preflight.returncode != 0
                or _DIGEST.fullmatch(base_preflight.stdout.decode("ascii", errors="ignore").strip()) is None):
            return _emit(output, "PREFLIGHT_FAILED", _CODES["PREFLIGHT_FAILED"])

        created = False
        failure: tuple[str, int] | None = None
        try:
            result = _run_control(
                runner,
                (DOCKER, "--host=" + DOCKER_HOST, "create", TARGET_RUNTIME_IMAGE_ID),
                env,
            )
            if result.returncode != 0 or _CONTAINER_ID.fullmatch(result.stdout) is None:
                failure = ("CONTAINER_CREATE_FAILED", _CODES["CONTAINER_CREATE_FAILED"])
            else:
                container_id = result.stdout.decode("ascii").strip()
                created = True
                copied = _run_control(
                    runner,
                    (DOCKER, "--host=" + DOCKER_HOST, "cp", f"{container_id}:/opt/target-python/.", str(context / "target-python")),
                    env,
                    timeout=60,
                )
                if copied.returncode != 0:
                    failure = ("DEPENDENCY_COPY_FAILED", _CODES["DEPENDENCY_COPY_FAILED"])
                else:
                    command = (
                        DOCKER, "--host=" + DOCKER_HOST, "buildx", "build", "--builder", "default",
                        "--platform=linux/amd64", "--pull=false", "--network=none", "--no-cache",
                        "--provenance=false", "--progress=quiet", "--build-arg", "SOURCE_DATE_EPOCH=0",
                        "--tag", IMAGE_TAG,
                        "--output", "type=docker,dest=-", str(context),
                    )
                    built = build_runner(
                        command,
                        max_bytes=MAX_ARCHIVE_BYTES,
                        max_stderr_bytes=MAX_DIAGNOSTIC_BYTES,
                        timeout=TIMEOUT_SECONDS,
                        env=env,
                    )
                    if type(built.stdout) is not bytes:
                        failure = (
                            "EXPORT_FAILED|reason=invalid_stdout",
                            _CODES["EXPORT_FAILED"],
                        )
                    elif built.returncode != 0:
                        stderr = built.stderr if type(built.stderr) is bytes else b""
                        reason = _export_failure_reason(stderr)
                        if reason == "unknown":
                            marker = (
                                "EXPORT_FAILED|reason=unclassified_stderr"
                                f"|exit={built.returncode}|stderr_bytes={len(stderr)}"
                            )
                        else:
                            marker = (
                                f"EXPORT_FAILED|reason={reason}"
                                f"|exit={built.returncode}|stderr_bytes={len(stderr)}"
                            )
                        failure = (
                            marker,
                            _CODES["EXPORT_FAILED"],
                        )
                    else:
                        archive = built.stdout
        except OutputLimitExceeded:
            failure = ("EXPORT_LIMIT", _CODES["EXPORT_LIMIT"])
        except DiagnosticOutputLimitExceeded:
            failure = (
                "EXPORT_DIAGNOSTIC_LIMIT",
                _CODES["EXPORT_DIAGNOSTIC_LIMIT"],
            )
        except subprocess.TimeoutExpired:
            failure = ("EXPORT_TIMEOUT", _CODES["EXPORT_TIMEOUT"])
        except Exception:
            failure = (
                "EXPORT_FAILED|reason=runner_error",
                _CODES["EXPORT_FAILED"],
            )
        finally:
            if created and container_id is not None:
                try:
                    removed = _run_control(
                        runner,
                        (DOCKER, "--host=" + DOCKER_HOST, "rm", "--force", container_id),
                        env,
                    )
                    cleanup_ok = removed.returncode == 0
                except Exception:
                    cleanup_ok = False

    if not cleanup_ok:
        return _emit(output, "CLEANUP_FAILED", _CODES["CLEANUP_FAILED"])
    if failure is not None:
        return _emit(output, failure[0], failure[1])
    if archive is None:
        return _emit(output, "EXPORT_FAILED", _CODES["EXPORT_FAILED"])
    try:
        config_digest, _ = _read_archive_config(archive)
    except InvalidChain:
        return _emit(output, "ARCHIVE_INVALID", _CODES["ARCHIVE_INVALID"])
    output.write(
        "BUILDX_EXPORT_CONFIRMED|"
        f"archive_bytes={len(archive)}|config={config_digest}|code={code_digest}\n"
    )
    return _CODES["BUILDX_EXPORT_CONFIRMED"]


if __name__ == "__main__":
    raise SystemExit(run_once())
