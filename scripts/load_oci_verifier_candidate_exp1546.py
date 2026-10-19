#!/usr/bin/env python3
"""Load one verified OCI subset under a new local candidate tag, once."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
import tempfile
from typing import Callable, TextIO

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import export_verify_oci_subset_exp1540 as source
from scripts.audit_portable_verifier_image_exp1350 import (
    MAX_ARCHIVE_BYTES,
    InvalidChain,
    OutputLimitExceeded,
    _bounded_process_output,
    parse_portable_archive,
)


DOCKER = "/usr/local/bin/docker"
SOURCE_TAG = "agent00x-verifier:exp-1521-e6fb28b"
IMAGE_TAG = "agent00x-verifier:exp-1546-oci-candidate"
OCI_CONFIG_DIGEST = "sha256:8fd288eaae140b2ba5acbf70aa3e18db0d54c724c0a20e5a65080d214966eaeb"
OS_NAME = "linux"
ARCHITECTURE = "amd64"
DIFF_IDS = source.pinned.DIFF_IDS
USER = "65532:65532"
ENTRYPOINT = ("python3", "-m", "app_contracts.verifier_container_entrypoint")
LOAD_TIMEOUT_SECONDS = 90
INSPECT_TIMEOUT_SECONDS = 15
INSPECT_MAX_BYTES = 16384
_CODES = {
    "OPT_IN_REQUIRED": 10,
    "IMAGE_SAVE_FAILED": 11,
    "IMAGE_SAVE_SIZE_LIMIT": 12,
    "IMAGE_SAVE_TIMEOUT": 13,
    "OCI_SUBSET_INVALID": 14,
    "OCI_LOAD_FAILED": 15,
    "POST_LOAD_INSPECT_FAILED": 16,
    "OCI_LOAD_FACTS_MISMATCH": 17,
    "OCI_LOAD_CONFIRMED": 0,
}
SaveRunner = Callable[..., subprocess.CompletedProcess[bytes]]
LoadRunner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def prepare_tagged_oci_archive(archive: bytes, *, config_digest: str = OCI_CONFIG_DIGEST,
                               diff_ids: tuple[str, ...] = DIFF_IDS,
                               repo_tag: str = IMAGE_TAG) -> bytes:
    """Extract, retag and validate a memory-only OCI archive."""
    subset = source.make_oci_subset(archive)
    with tarfile.open(fileobj=io.BytesIO(subset), mode="r:*") as current:
        files = {
            member.name: current.extractfile(member).read()
            for member in current.getmembers()
            if member.isfile()
        }
    index = json.loads(files["index.json"])
    descriptor = index["manifests"][0]
    annotations = descriptor.setdefault("annotations", {})
    if not isinstance(annotations, dict):
        raise InvalidChain("oci-index-annotations-invalid")
    annotations["org.opencontainers.image.ref.name"] = repo_tag.rsplit(":", 1)[1]
    files["index.json"] = json.dumps(index, separators=(",", ":")).encode("utf-8")
    files["oci-layout"] = b'{"imageLayoutVersion":"1.0.0"}'

    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as target:
        for name, payload in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            target.addfile(info, io.BytesIO(payload))
    candidate = output.getvalue()
    if not candidate or len(candidate) > MAX_ARCHIVE_BYTES:
        raise InvalidChain("archive-format")
    parse_portable_archive(
        candidate,
        expected_config_digest=config_digest,
        expected_os=OS_NAME,
        expected_architecture=ARCHITECTURE,
        expected_diff_ids=diff_ids,
        expected_repo_tag=repo_tag,
        max_archive_bytes=MAX_ARCHIVE_BYTES,
    )
    return candidate


def _parse_inspect(payload: bytes) -> tuple[str, str, str, tuple[str, ...], str, tuple[str, ...]]:
    try:
        parts = payload.decode("ascii").strip().split("|", 5)
        if len(parts) != 6:
            raise ValueError
        image_id, os_name, architecture, raw_diff_ids, user, raw_entrypoint = parts
        diff_ids = json.loads(raw_diff_ids)
        entrypoint = json.loads(raw_entrypoint)
        if (
            not isinstance(diff_ids, list)
            or not all(isinstance(item, str) and item.startswith("sha256:") and len(item) == 71 for item in diff_ids)
            or not isinstance(entrypoint, list)
            or not all(isinstance(item, str) for item in entrypoint)
        ):
            raise ValueError
        return image_id, os_name, architecture, tuple(diff_ids), user, tuple(entrypoint)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise InvalidChain("archive-validation") from None


def run_once(*, save_runner: SaveRunner = _bounded_process_output,
             load_runner: LoadRunner = subprocess.run,
             inspect_runner: SaveRunner = _bounded_process_output,
             output: TextIO = sys.stdout,
             temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        return _emit(output, "OPT_IN_REQUIRED", _CODES["OPT_IN_REQUIRED"])
    try:
        with temporary_directory(prefix="agent00x-exp1546-docker-config-") as config_dir:
            env = {"DOCKER_CONFIG": str(config_dir), "PATH": "/usr/local/bin:/usr/bin:/bin"}
            saved = save_runner(
                (DOCKER, "image", "save", SOURCE_TAG),
                max_bytes=MAX_ARCHIVE_BYTES,
                timeout=60,
                env=env,
            )
    except OutputLimitExceeded:
        return _emit(output, "IMAGE_SAVE_SIZE_LIMIT", _CODES["IMAGE_SAVE_SIZE_LIMIT"])
    except subprocess.TimeoutExpired:
        return _emit(output, "IMAGE_SAVE_TIMEOUT", _CODES["IMAGE_SAVE_TIMEOUT"])
    except Exception:
        return _emit(output, "IMAGE_SAVE_FAILED", _CODES["IMAGE_SAVE_FAILED"])
    if saved.returncode != 0 or type(saved.stdout) is not bytes:
        return _emit(output, "IMAGE_SAVE_FAILED", _CODES["IMAGE_SAVE_FAILED"])

    try:
        candidate = prepare_tagged_oci_archive(
            saved.stdout,
            config_digest=OCI_CONFIG_DIGEST,
            diff_ids=DIFF_IDS,
            repo_tag=IMAGE_TAG,
        )
    except InvalidChain as exc:
        return _emit(output, f"OCI_SUBSET_INVALID|stage={exc.stage}", _CODES["OCI_SUBSET_INVALID"])
    except Exception:
        return _emit(output, "OCI_SUBSET_INVALID|stage=archive-validation", _CODES["OCI_SUBSET_INVALID"])

    with tempfile.TemporaryDirectory(prefix="agent00x-exp1546-load-config-") as config_dir:
        env = {"DOCKER_CONFIG": config_dir, "PATH": "/usr/local/bin:/usr/bin:/bin"}
        try:
            loaded = load_runner(
                (DOCKER, "image", "load"), input=candidate,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=LOAD_TIMEOUT_SECONDS, check=False, env=env,
            )
        except Exception:
            return _emit(output, "OCI_LOAD_FAILED", _CODES["OCI_LOAD_FAILED"])
        if loaded.returncode != 0:
            return _emit(output, "OCI_LOAD_FAILED", _CODES["OCI_LOAD_FAILED"])

        inspect_template = "{{.Id}}|{{.Os}}|{{.Architecture}}|{{json .RootFS.Layers}}|{{.Config.User}}|{{json .Config.Entrypoint}}"
        try:
            inspected = inspect_runner(
                (DOCKER, "image", "inspect", "--format", inspect_template, IMAGE_TAG),
                max_bytes=INSPECT_MAX_BYTES,
                timeout=INSPECT_TIMEOUT_SECONDS,
                env=env,
            )
        except Exception:
            return _emit(output, "POST_LOAD_INSPECT_FAILED", _CODES["POST_LOAD_INSPECT_FAILED"])
    if inspected.returncode != 0 or type(inspected.stdout) is not bytes:
        return _emit(output, "POST_LOAD_INSPECT_FAILED", _CODES["POST_LOAD_INSPECT_FAILED"])
    try:
        facts = _parse_inspect(inspected.stdout)
    except InvalidChain:
        return _emit(output, "POST_LOAD_INSPECT_FAILED", _CODES["POST_LOAD_INSPECT_FAILED"])
    expected = (OCI_CONFIG_DIGEST, OS_NAME, ARCHITECTURE, DIFF_IDS, USER, ENTRYPOINT)
    if facts != expected:
        return _emit(output, "OCI_LOAD_FACTS_MISMATCH", _CODES["OCI_LOAD_FACTS_MISMATCH"])
    output.write(
        "OCI_LOAD_CONFIRMED|"
        f"config={facts[0]}|platform={facts[1]}/{facts[2]}|"
        f"diff_ids={','.join(facts[3])}|user={facts[4]}|"
        f"entrypoint={' '.join(facts[5])}|tag={IMAGE_TAG}\n"
    )
    return _CODES["OCI_LOAD_CONFIRMED"]


if __name__ == "__main__":
    raise SystemExit(run_once())
