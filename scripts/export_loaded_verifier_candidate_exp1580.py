#!/usr/bin/env python3
"""Build/load/save one locally pinned verifier candidate (EXP-1580)."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
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
from scripts.export_buildx_verifier_candidate_exp1573 import (  # noqa: E402
    DiagnosticOutputLimitExceeded,
    _bounded_build_export,
    _export_failure_reason,
)
from scripts.export_verify_portable_image_exp1529 import DIFF_IDS  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
IMAGE_TAG = "agent00x-verifier:exp-1580"
EXP1586_IMAGE_TAG = "agent00x-verifier:exp-1586"
EXP1587_IMAGE_TAG = "agent00x-verifier:exp-1587"
EXP1590_IMAGE_TAG = "agent00x-verifier:exp-1590"
EXP1593_IMAGE_TAG = "agent00x-verifier:exp-1593"
EXP1603_IMAGE_TAG = "agent00x-verifier:exp-1603"
EXP1607_IMAGE_TAG = "agent00x-verifier:exp-1607"
EXP1616_IMAGE_TAG = "agent00x-verifier:exp-1616"
EXP1619_IMAGE_TAG = "agent00x-verifier:exp-1619"
EXP1621_IMAGE_TAG = "agent00x-verifier:exp-1621"
EXP1623_IMAGE_TAG = "agent00x-verifier:exp-1623"
EXP1625_IMAGE_TAG = "agent00x-verifier:exp-1625"
EXP1627_IMAGE_TAG = "agent00x-verifier:exp-1627"
EXP1630_IMAGE_TAG = "agent00x-verifier:exp-1630"
EXP1632_IMAGE_TAG = "agent00x-verifier:exp-1632"
EXP1658_IMAGE_TAG = "agent00x-verifier:exp-1658"
EXP1681_IMAGE_TAG = "agent00x-verifier:exp-1681"
_ALLOWED_IMAGE_TAGS = frozenset({
    IMAGE_TAG, EXP1586_IMAGE_TAG, EXP1587_IMAGE_TAG, EXP1590_IMAGE_TAG,
    EXP1593_IMAGE_TAG, EXP1603_IMAGE_TAG, EXP1607_IMAGE_TAG, EXP1616_IMAGE_TAG,
    EXP1619_IMAGE_TAG, EXP1621_IMAGE_TAG, EXP1623_IMAGE_TAG, EXP1625_IMAGE_TAG,
    EXP1627_IMAGE_TAG,
    EXP1630_IMAGE_TAG,
    EXP1632_IMAGE_TAG,
    EXP1658_IMAGE_TAG,
    EXP1681_IMAGE_TAG,
})
PYTHON_BASE_REF = "python:3.11.16-slim@sha256:174bec68e0451bffabbb08c7d5d21c6b253f772d81d52b9558af97bb3159b761"
PLATFORM = "linux/amd64"
MAX_ARCHIVE_BYTES = 640 * 1024 * 1024
MAX_CONTROL_OUTPUT_BYTES = 8192
MAX_DIAGNOSTIC_BYTES = 64 * 1024
TIMEOUT_SECONDS = 300
EXPECTED_USER = "65532:65532"
EXPECTED_ENTRYPOINT = ["python3", "-m", "app_contracts.verifier_container_entrypoint"]
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONTAINER_ID = re.compile(rb"[0-9a-f]{64}\n?\Z")
_BUILDX_PLUGIN_CANDIDATES = (
    "/Users/aleksandrsoldatov/.docker/cli-plugins/docker-buildx",
    "/usr/local/lib/docker/cli-plugins/docker-buildx",
    "/usr/local/libexec/docker/cli-plugins/docker-buildx",
    "/usr/lib/docker/cli-plugins/docker-buildx",
    "/usr/libexec/docker/cli-plugins/docker-buildx",
)


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def _cleanup_failure_marker(*, container_ok: bool, tag_ok: bool,
                            container_id: str | None) -> str:
    resources: list[str] = []
    if not container_ok:
        resource = "copy_container"
        if container_id is not None and re.fullmatch(r"[0-9a-f]{64}", container_id):
            resource += ":" + container_id
        resources.append(resource)
    if not tag_ok:
        resources.append("verifier_tag")
    return "CLEANUP_FAILED|resources=" + ",".join(resources)


def _prepare_isolated_buildx_plugin(
    config_dir: str,
    *,
    candidates: tuple[str, ...] = _BUILDX_PLUGIN_CANDIDATES,
    is_executable: Callable[[str], bool] | None = None,
    user_local_path: str = "/Users/aleksandrsoldatov/.docker/cli-plugins/docker-buildx",
) -> None:
    if is_executable is None:
        is_executable = lambda path: Path(path).is_file() and os.access(path, os.X_OK)
    matches = [path for path in candidates if is_executable(path)]
    if len(matches) != 1:
        raise RuntimeError("buildx-plugin-candidate-count")
    if matches[0] != user_local_path:
        return
    plugin_dir = Path(config_dir) / "cli-plugins"
    plugin_dir.mkdir(mode=0o700, exist_ok=True)
    link = plugin_dir / "docker-buildx"
    if link.exists() or link.is_symlink():
        raise RuntimeError("buildx-plugin-link-exists")
    link.symlink_to(user_local_path)


def _env(config_dir: str) -> dict[str, str]:
    _prepare_isolated_buildx_plugin(config_dir)
    return {
        "DOCKER_CONFIG": config_dir,
        "DOCKER_HOST": DOCKER_HOST,
        "LANG": "C",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }


def _control(runner, args: tuple[str, ...], env: dict[str, str], *, timeout: float = 30):
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
    files = [context / "Dockerfile", context / "requirements.lock"]
    files.extend(sorted(package_dir.iterdir(), key=lambda item: item.name))
    files.extend(sorted(schema_dir.iterdir(), key=lambda item: item.name))
    for path in files:
        digest.update(path.relative_to(context).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _inspect_tuple(data: bytes) -> tuple[str, int, tuple[str, ...]] | None:
    try:
        image_id, os_name, architecture, size_text, layer_json = data.decode("ascii").rstrip("\n").split("|", 4)
        layers = json.loads(layer_json)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if (
        _DIGEST.fullmatch(image_id) is None
        or os_name != "linux"
        or architecture != "amd64"
        or not size_text.isdecimal()
        or not isinstance(layers, list)
        or any(not isinstance(layer, str) or _DIGEST.fullmatch(layer) is None for layer in layers)
    ):
        return None
    return image_id, int(size_text), tuple(layers)


def _archive_identity_relation_facts(
    archive: bytes, inspected_id: str
) -> tuple[str, str, str, str]:
    """Return only fixed format and config-ID relations; never raw archive data."""
    archive_format = "unclassified"
    legacy_fact = "unclassified"
    oci_fact = "unclassified"
    oci_manifest_fact = "unclassified"
    has_index = False
    has_legacy = False
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            rows = tar.getmembers()
            members = {row.name: row for row in rows}
            has_index = "index.json" in members
            has_legacy = "manifest.json" in members
            archive_format = (
                "oci+docker-legacy" if has_index and has_legacy
                else "oci" if has_index
                else "docker-legacy" if has_legacy
                else "unclassified"
            )

            def read(name: str, limit: int) -> bytes | None:
                member = members.get(name)
                if member is None or not member.isfile() or member.size > limit:
                    return None
                stream = tar.extractfile(member)
                if stream is None:
                    return None
                data = stream.read(limit + 1)
                return data if len(data) == member.size else None

            if has_legacy:
                raw_manifest = read("manifest.json", 65536)
                manifest = json.loads(raw_manifest) if raw_manifest is not None else None
                if isinstance(manifest, list) and len(manifest) == 1 and isinstance(manifest[0], dict):
                    config_name = manifest[0].get("Config")
                    if isinstance(config_name, str):
                        config_raw = read(config_name, 1_048_576)
                        if config_raw is not None:
                            digest = "sha256:" + hashlib.sha256(config_raw).hexdigest()
                            legacy_fact = "daemon-match" if digest == inspected_id else "daemon-mismatch"

            if has_index:
                raw_index = read("index.json", 65536)
                index = json.loads(raw_index) if raw_index is not None else None
                manifests = index.get("manifests") if isinstance(index, dict) else None
                if isinstance(manifests, list) and len(manifests) == 1 and isinstance(manifests[0], dict):
                    manifest_digest = manifests[0].get("digest")
                    if isinstance(manifest_digest, str) and _DIGEST.fullmatch(manifest_digest):
                        oci_manifest_fact = (
                            "daemon-match" if manifest_digest == inspected_id
                            else "daemon-mismatch"
                        )
                        manifest_raw = read(
                            "blobs/sha256/" + manifest_digest.removeprefix("sha256:"),
                            65536,
                        )
                        manifest = json.loads(manifest_raw) if manifest_raw is not None else None
                        config_desc = manifest.get("config") if isinstance(manifest, dict) else None
                        config_digest = config_desc.get("digest") if isinstance(config_desc, dict) else None
                        config_size = config_desc.get("size") if isinstance(config_desc, dict) else None
                        if (
                            isinstance(config_digest, str)
                            and _DIGEST.fullmatch(config_digest)
                            and type(config_size) is int
                            and 0 <= config_size <= 1_048_576
                        ):
                            config_raw = read(
                                "blobs/sha256/" + config_digest.removeprefix("sha256:"),
                                1_048_576,
                            )
                            if config_raw is not None and len(config_raw) == config_size:
                                content_digest = "sha256:" + hashlib.sha256(config_raw).hexdigest()
                                oci_fact = (
                                    "daemon-match"
                                    if config_digest == inspected_id and content_digest == inspected_id
                                    else "daemon-mismatch"
                                )
    except Exception:
        pass
    if not has_legacy:
        legacy_fact = "absent"
    if not has_index:
        oci_fact = "absent"
        oci_manifest_fact = "absent"
    return archive_format, legacy_fact, oci_fact, oci_manifest_fact


def _validate_archive(
    archive: bytes,
    inspected_id: str,
    *,
    image_tag: str = IMAGE_TAG,
    expected_diff_ids: tuple[str, ...] = DIFF_IDS,
    require_portable_manifest: bool = False,
):
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            rows = tar.getmembers()
            if not 0 < len(rows) <= 128:
                raise InvalidChain("archive-layout")
            members = {member.name: member for member in rows}
            if len(members) != len(rows):
                raise InvalidChain("archive-members")
            for name, member in members.items():
                path = PurePosixPath(name.rstrip("/") if member.isdir() else name)
                if (
                    not name
                    or "\\" in name
                    or path.is_absolute()
                    or path.as_posix() != name.rstrip("/")
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or not (member.isfile() or member.isdir())
                ):
                    raise InvalidChain("archive-layout")
            manifest_member = members.get("manifest.json")
            if manifest_member is None or not manifest_member.isfile() or manifest_member.size > 65536:
                raise InvalidChain("docker-manifest")
            manifest_stream = tar.extractfile(manifest_member)
            if manifest_stream is None:
                raise InvalidChain("docker-manifest")
            try:
                manifests = json.loads(manifest_stream.read(65537))
            except Exception:
                raise InvalidChain("docker-manifest") from None
            if not isinstance(manifests, list) or len(manifests) != 1:
                raise InvalidChain("docker-manifest")
            record = manifests[0]
            if (
                not isinstance(record, dict)
                or record.get("RepoTags") != [image_tag]
                or not isinstance(record.get("Layers"), list)
                or len(record["Layers"]) != len(expected_diff_ids)
            ):
                raise InvalidChain("docker-manifest")
            config_name = record.get("Config")
            if not isinstance(config_name, str) or config_name not in members:
                raise InvalidChain("docker-config")
            config_member = members[config_name]
            if not config_member.isfile() or config_member.size > 1_048_576:
                raise InvalidChain("docker-config")
            config_stream = tar.extractfile(config_member)
            if config_stream is None:
                raise InvalidChain("docker-config")
            config_raw = config_stream.read(1_048_577)
            if len(config_raw) != config_member.size or len(config_raw) > 1_048_576:
                raise InvalidChain("docker-config")
            config_digest = "sha256:" + hashlib.sha256(config_raw).hexdigest()
            try:
                config = json.loads(config_raw)
            except Exception:
                raise InvalidChain("docker-config") from None
            runtime = config.get("config") if isinstance(config, dict) else None
            rootfs = config.get("rootfs") if isinstance(config, dict) else None
            if (
                config.get("os") != "linux"
                or config.get("architecture") != "amd64"
            ):
                raise InvalidChain("daemon-platform-mismatch")
            if (
                not isinstance(runtime, dict)
                or runtime.get("User") != EXPECTED_USER
                or runtime.get("Entrypoint") != EXPECTED_ENTRYPOINT
                or not isinstance(rootfs, dict)
                or rootfs.get("type") != "layers"
            ):
                raise InvalidChain("docker-config")
            if rootfs.get("diff_ids") != list(expected_diff_ids):
                raise InvalidChain("daemon-diff-id-mismatch")
        facts = parse_portable_archive(
            archive,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=expected_diff_ids,
            expected_repo_tag=image_tag,
            max_archive_bytes=MAX_ARCHIVE_BYTES,
        )
        if require_portable_manifest and facts.portable_manifest_digest is None:
            raise InvalidChain("archive-format")
        if inspected_id not in {facts.config_digest, facts.portable_manifest_digest}:
            archive_facts = _archive_identity_relation_facts(archive, inspected_id)
            safe_detail = (
                "config-name-matches-content"
                if config_name == config_digest.removeprefix("sha256:") + ".json"
                else "config-name-mismatches-content"
            )
            raise InvalidChain(
                "daemon-image-id-mismatch", safe_detail=safe_detail,
                archive_format_fact=archive_facts[0],
                legacy_config_fact=archive_facts[1],
                oci_config_fact=archive_facts[2],
                oci_manifest_fact=archive_facts[3],
            )
        return facts
    except InvalidChain as exc:
        raise InvalidChain(
            exc.stage, safe_detail=exc.safe_detail,
            archive_format_fact=exc.archive_format_fact,
            legacy_config_fact=exc.legacy_config_fact,
            oci_config_fact=exc.oci_config_fact,
            oci_manifest_fact=exc.oci_manifest_fact,
        ) from None
    except tarfile.TarError:
        raise InvalidChain("archive-layout") from None
    except Exception:
        raise InvalidChain("archive-validation") from None


def run_once(*, runner=_bounded_process_output, save_runner=_bounded_build_export,
             output: TextIO = sys.stdout,
             temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory,
             build_runner=None,
             image_tag: str = IMAGE_TAG,
             retain_tag: bool = False,
             dynamic_diff_ids: bool = False,
             require_portable_manifest: bool = False) -> int:
    if build_runner is None:
        if runner is _bounded_process_output:
            build_runner = _bounded_build_export
        else:
            def build_runner(command, *, max_bytes, max_stderr_bytes, timeout, env):
                del max_stderr_bytes
                return runner(command, max_bytes=max_bytes, timeout=timeout, env=env)

    if image_tag not in _ALLOWED_IMAGE_TAGS:
        return _emit(output, "IMAGE_TAG_NOT_ALLOWLISTED", 23)
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        return _emit(output, "OPT_IN_REQUIRED", 10)

    tag_creation_possible = False
    container_id: str | None = None
    container_cleanup_attempted = False
    tag_cleanup_ok = True
    container_cleanup_ok = True
    result_marker = "CANDIDATE_INCOMPLETE"
    result_code = 11
    code_digest = ""
    archive: bytes | None = None
    inspected: tuple[str, int, tuple[str, ...]] | None = None
    with temporary_directory(prefix="agent00x-exp1580-context-") as context_name, \
            temporary_directory(prefix="agent00x-exp1580-docker-config-") as config_name:
        context = Path(context_name)
        try:
            env = _env(config_name)
            code_digest = _prepare_context(context)
            tag_check = _control(
                runner,
                (DOCKER, "--host=" + DOCKER_HOST, "image", "ls", "--filter", "reference=" + image_tag, "--format", "{{.Repository}}:{{.Tag}}"),
                env,
            )
            target = _control(
                runner,
                (DOCKER, "--host=" + DOCKER_HOST, "image", "inspect", "--format", "{{.Id}}", TARGET_RUNTIME_IMAGE_ID),
                env,
            )
            base = _control(
                runner,
                (DOCKER, "--host=" + DOCKER_HOST, "image", "inspect", "--format", "{{.Id}}", PYTHON_BASE_REF),
                env,
            )
        except Exception:
            return _emit(output, "PREFLIGHT_FAILED", 11)
        if (
            tag_check.returncode != 0
            or tag_check.stdout != b""
            or target.returncode != 0
            or target.stdout != (TARGET_RUNTIME_IMAGE_ID + "\n").encode("ascii")
            or base.returncode != 0
            or _DIGEST.fullmatch(base.stdout.decode("ascii", errors="ignore").strip()) is None
        ):
            return _emit(output, "PREFLIGHT_FAILED", 11)

        try:
            created = _control(
                runner,
                (DOCKER, "--host=" + DOCKER_HOST, "create", TARGET_RUNTIME_IMAGE_ID),
                env,
            )
            if created.returncode != 0 or _CONTAINER_ID.fullmatch(created.stdout) is None:
                result_marker, result_code = "CONTAINER_CREATE_FAILED", 12
            else:
                container_id = created.stdout.decode("ascii").strip()
                copied = _control(
                    runner,
                    (DOCKER, "--host=" + DOCKER_HOST, "cp", f"{container_id}:/opt/target-python/.", str(context / "target-python")),
                    env,
                    timeout=60,
                )
                if copied.returncode != 0:
                    result_marker, result_code = "DEPENDENCY_COPY_FAILED", 13
                else:
                    container_cleanup_attempted = True
                    try:
                        removed = _control(
                            runner,
                            (DOCKER, "--host=" + DOCKER_HOST, "rm", "--force", container_id),
                            env,
                        )
                    except Exception:
                        container_cleanup_ok = False
                    else:
                        if removed.returncode != 0:
                            container_cleanup_ok = False
                        else:
                            container_id = None
                            command = (
                                DOCKER, "--host=" + DOCKER_HOST, "buildx", "build", "--builder", "default",
                                "--platform=" + PLATFORM, "--pull=false", "--network=none", "--no-cache",
                                "--provenance=false", "--progress=quiet", "--build-arg", "SOURCE_DATE_EPOCH=0",
                                "--tag", image_tag, "--load", str(context),
                            )
                            tag_creation_possible = True
                            built = build_runner(
                                command,
                                max_bytes=MAX_CONTROL_OUTPUT_BYTES,
                                max_stderr_bytes=MAX_DIAGNOSTIC_BYTES,
                                timeout=TIMEOUT_SECONDS,
                                env=env,
                            )
                            if built.returncode != 0:
                                stderr = built.stderr if type(built.stderr) is bytes else b""
                                reason = _export_failure_reason(stderr)
                                exit_code = built.returncode if type(built.returncode) is int else "unknown"
                                result_marker = (
                                    f"BUILD_FAILED|reason={reason}|exit={exit_code}"
                                    f"|stderr_bytes={len(stderr)}"
                                )
                                result_code = 14
                            else:
                                inspected_result = _control(
                                    runner,
                                    (DOCKER, "--host=" + DOCKER_HOST, "image", "inspect", "--format", "{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|{{json .RootFS.Layers}}", image_tag),
                                    env,
                                )
                                inspected = _inspect_tuple(inspected_result.stdout) if inspected_result.returncode == 0 else None
                                if (
                                    inspected is None
                                    or (
                                        not dynamic_diff_ids
                                        and inspected[2] != tuple(DIFF_IDS)
                                    )
                                    or not 1 <= len(inspected[2]) <= 32
                                ):
                                    result_marker, result_code = "IMAGE_FACTS_MISMATCH", 15
                                else:
                                    saved = save_runner(
                                        (DOCKER, "--host=" + DOCKER_HOST, "image", "save", "--platform=" + PLATFORM, image_tag),
                                        max_bytes=MAX_ARCHIVE_BYTES,
                                        max_stderr_bytes=MAX_DIAGNOSTIC_BYTES,
                                        timeout=TIMEOUT_SECONDS,
                                        env=env,
                                    )
                                    if saved.returncode != 0 or type(saved.stdout) is not bytes:
                                        result_marker, result_code = "IMAGE_SAVE_FAILED", 16
                                    else:
                                        archive = saved.stdout
                                        try:
                                            facts = _validate_archive(
                                                archive,
                                                inspected[0],
                                                image_tag=image_tag,
                                                expected_diff_ids=(
                                                    inspected[2]
                                                    if dynamic_diff_ids
                                                    else tuple(DIFF_IDS)
                                                ),
                                                require_portable_manifest=require_portable_manifest,
                                            )
                                        except InvalidChain as invalid:
                                            result_marker = f"ARCHIVE_INVALID|stage={invalid.stage}"
                                            if invalid.safe_detail is not None:
                                                result_marker += f"|fact={invalid.safe_detail}"
                                            if invalid.archive_format_fact is not None:
                                                result_marker += f"|archive={invalid.archive_format_fact}"
                                            if invalid.legacy_config_fact is not None:
                                                result_marker += f"|legacy-config={invalid.legacy_config_fact}"
                                            if invalid.oci_config_fact is not None:
                                                result_marker += f"|oci-config={invalid.oci_config_fact}"
                                            if invalid.oci_manifest_fact is not None:
                                                result_marker += f"|oci-manifest={invalid.oci_manifest_fact}"
                                            result_code = 17
                                        else:
                                            manifest_digest = facts.portable_manifest_digest
                                            if require_portable_manifest and manifest_digest is None:
                                                result_marker, result_code = "ARCHIVE_INVALID", 17
                                            else:
                                                result_marker = (
                                                    f"PORTABLE_ARCHIVE_CONFIRMED|manifest={manifest_digest or 'none'}"
                                                    f"|config={facts.config_digest}|size={inspected[1]}"
                                                    f"|layers={len(inspected[2])}|archive_bytes={len(archive)}"
                                                    f"|code={code_digest}"
                                                )
                                                result_code = 0
        except OutputLimitExceeded:
            result_marker, result_code = "OUTPUT_LIMIT", 18
        except DiagnosticOutputLimitExceeded:
            result_marker, result_code = "DIAGNOSTIC_LIMIT", 19
        except subprocess.TimeoutExpired:
            result_marker, result_code = "OPERATION_TIMEOUT", 20
        except Exception:
            result_marker, result_code = "OPERATION_FAILED", 21
        finally:
            if container_id is not None and not container_cleanup_attempted:
                try:
                    container_cleanup_attempted = True
                    removed = _control(
                        runner,
                        (DOCKER, "--host=" + DOCKER_HOST, "rm", "--force", container_id),
                        env,
                    )
                    container_cleanup_ok = removed.returncode == 0
                except Exception:
                    container_cleanup_ok = False
            if tag_creation_possible and not retain_tag:
                try:
                    tag_state = _control(
                        runner,
                        (DOCKER, "--host=" + DOCKER_HOST, "image", "ls", "--filter", "reference=" + image_tag, "--format", "{{.Repository}}:{{.Tag}}"),
                        env,
                    )
                    if tag_state.returncode != 0:
                        tag_cleanup_ok = False
                    elif tag_state.stdout == b"":
                        tag_cleanup_ok = True
                    elif tag_state.stdout == (image_tag + "\n").encode("ascii"):
                        removed = _control(
                            runner,
                            (DOCKER, "--host=" + DOCKER_HOST, "image", "rm", image_tag),
                            env,
                        )
                        tag_cleanup_ok = removed.returncode == 0
                    else:
                        tag_cleanup_ok = False
                except Exception:
                    tag_cleanup_ok = False

    if not tag_cleanup_ok or not container_cleanup_ok:
        return _emit(
            output,
            _cleanup_failure_marker(
                container_ok=container_cleanup_ok,
                tag_ok=tag_cleanup_ok,
                container_id=container_id,
            ),
            22,
        )
    return _emit(output, result_marker, result_code)


if __name__ == "__main__":
    raise SystemExit(run_once())
