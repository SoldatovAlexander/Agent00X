#!/usr/bin/env python3
"""Convert the pinned OCI content into one checked Docker archive and load it."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path
import sys
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import export_verify_oci_subset_exp1540 as source
from scripts.audit_portable_verifier_image_exp1350 import (
    MAX_ARCHIVE_BYTES,
    MAX_EXPANDED_LAYER_BYTES,
    InvalidChain,
    OutputLimitExceeded,
    _bounded_process_output,
    _layer_diff_id,
    parse_portable_archive,
)


DOCKER = "/usr/local/bin/docker"
SOURCE_TAG = "agent00x-verifier:exp-1521-e6fb28b"
IMAGE_TAG = "agent00x-verifier:exp-1549-oci-candidate"
CONFIG_DIGEST = "sha256:8fd288eaae140b2ba5acbf70aa3e18db0d54c724c0a20e5a65080d214966eaeb"
OS_NAME = "linux"
ARCHITECTURE = "amd64"
DIFF_IDS = source.pinned.DIFF_IDS
MAX_DOCKER_ARCHIVE_BYTES = MAX_EXPANDED_LAYER_BYTES + 1_048_576
USER = "65532:65532"
ENTRYPOINT = ("python3", "-m", "app_contracts.verifier_container_entrypoint")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GZIP_TYPES = {
    "application/vnd.oci.image.layer.v1.tar+gzip",
    "application/vnd.docker.image.rootfs.diff.tar.gzip",
}
_TAR_TYPES = {"application/vnd.oci.image.layer.v1.tar"}
_CODES = {
    "OPT_IN_REQUIRED": 10,
    "IMAGE_SAVE_FAILED": 11,
    "IMAGE_SAVE_SIZE_LIMIT": 12,
    "IMAGE_SAVE_TIMEOUT": 13,
    "DOCKER_ARCHIVE_INVALID": 14,
    "DOCKER_LOAD_FAILED": 15,
    "POST_LOAD_INSPECT_FAILED": 16,
    "DOCKER_LOAD_FACTS_MISMATCH": 17,
    "DOCKER_LOAD_CONFIRMED": 0,
}
SaveRunner = Callable[..., subprocess.CompletedProcess[bytes]]
LoadRunner = Callable[..., subprocess.CompletedProcess[bytes]]


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def _read_blob(tar: tarfile.TarFile, members: dict[str, tarfile.TarInfo],
               descriptor: object) -> tuple[str, bytes]:
    if not isinstance(descriptor, dict):
        raise InvalidChain("oci-index-descriptor")
    digest = descriptor.get("digest")
    size = descriptor.get("size")
    if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
        raise InvalidChain("oci-index-descriptor")
    if type(size) is not int or not 0 <= size <= MAX_ARCHIVE_BYTES:
        raise InvalidChain("oci-index-descriptor")
    name = "blobs/sha256/" + digest[7:]
    member = members.get(name)
    if member is None or not member.isfile() or member.size != size:
        raise InvalidChain("oci-index-descriptor")
    stream = tar.extractfile(member)
    if stream is None:
        raise InvalidChain("archive-members")
    raw = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) != size or _digest(raw) != digest:
        raise InvalidChain("oci-index-descriptor")
    return digest, raw


def _expand_layer(raw: bytes, media_type: object, remaining: int) -> bytes:
    if media_type in _TAR_TYPES:
        if len(raw) > remaining:
            raise InvalidChain("oci-layers")
        return raw
    if media_type not in _GZIP_TYPES:
        raise InvalidChain("oci-layers")
    expanded = bytearray()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
            while True:
                chunk = stream.read(min(1024 * 1024, remaining + 1 - len(expanded)))
                if not chunk:
                    break
                expanded.extend(chunk)
                if len(expanded) > remaining:
                    raise InvalidChain("oci-layers")
    except InvalidChain:
        raise
    except (OSError, EOFError):
        raise InvalidChain("oci-layers") from None
    return bytes(expanded)


def make_docker_archive(archive: bytes, *, config_digest: str = CONFIG_DIGEST,
                        diff_ids: tuple[str, ...] = DIFF_IDS,
                        repo_tag: str = IMAGE_TAG) -> bytes:
    """Convert only descriptor-verified OCI blobs to a checked legacy archive."""
    subset = source.make_oci_subset(archive)
    try:
        with tarfile.open(fileobj=io.BytesIO(subset), mode="r:*") as tar:
            records = tar.getmembers()
            members = {member.name: member for member in records}
            if len(records) != len(members) or "index.json" not in members:
                raise InvalidChain("archive-members")
            index_raw_stream = tar.extractfile(members["index.json"])
            if index_raw_stream is None:
                raise InvalidChain("oci-index-header")
            index = json.loads(index_raw_stream.read(65537))
            if not isinstance(index, dict) or index.get("schemaVersion") != 2:
                raise InvalidChain("oci-index-header")
            descriptors = index.get("manifests")
            if not isinstance(descriptors, list) or len(descriptors) != 1:
                raise InvalidChain("oci-index-manifest-list")
            _, manifest_raw = _read_blob(tar, members, descriptors[0])
            manifest = json.loads(manifest_raw)
            if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2:
                raise InvalidChain("oci-manifest")
            config_hash, config_raw = _read_blob(tar, members, manifest.get("config"))
            if config_hash != config_digest:
                raise InvalidChain("daemon-config-digest-mismatch", observed_digest=config_hash)
            config = json.loads(config_raw)
            if not isinstance(config, dict):
                raise InvalidChain("image-config")
            if config.get("os") != OS_NAME or config.get("architecture") != ARCHITECTURE:
                raise InvalidChain("daemon-platform-mismatch")
            rootfs = config.get("rootfs")
            if not isinstance(rootfs, dict) or rootfs.get("type") != "layers":
                raise InvalidChain("image-config")
            if rootfs.get("diff_ids") != list(diff_ids):
                raise InvalidChain("daemon-diff-id-mismatch")
            descriptors = manifest.get("layers")
            if not isinstance(descriptors, list) or len(descriptors) != len(diff_ids):
                raise InvalidChain("oci-layers")

            layer_files: dict[str, bytes] = {}
            total_expanded = 0
            layer_names = []
            for index_number, (descriptor, expected_diff_id) in enumerate(zip(descriptors, diff_ids)):
                _, compressed_or_tar = _read_blob(tar, members, descriptor)
                media_type = descriptor.get("mediaType") if isinstance(descriptor, dict) else None
                layer = _expand_layer(
                    compressed_or_tar,
                    media_type,
                    MAX_EXPANDED_LAYER_BYTES - total_expanded,
                )
                total_expanded += len(layer)
                if _digest(layer) != expected_diff_id:
                    raise InvalidChain("oci-layers")
                name = f"layers/{index_number:02d}/layer.tar"
                layer_names.append(name)
                layer_files[name] = layer

        config_name = config_digest[7:] + ".json"
        manifest_json = [{"Config": config_name, "RepoTags": [repo_tag], "Layers": layer_names}]
        files = {
            "manifest.json": json.dumps(manifest_json, separators=(",", ":")).encode("utf-8"),
            config_name: config_raw,
            **layer_files,
        }
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as target:
            for name, payload in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                target.addfile(info, io.BytesIO(payload))
        docker_archive = output.getvalue()
        if not docker_archive or len(docker_archive) > MAX_DOCKER_ARCHIVE_BYTES:
            raise InvalidChain("archive-format")
        parse_portable_archive(
            docker_archive,
            expected_config_digest=config_digest,
            expected_os=OS_NAME,
            expected_architecture=ARCHITECTURE,
            expected_diff_ids=diff_ids,
            expected_repo_tag=repo_tag,
            max_archive_bytes=MAX_DOCKER_ARCHIVE_BYTES,
        )
        return docker_archive
    except InvalidChain:
        raise
    except Exception:
        raise InvalidChain("archive-format") from None


def _parse_inspect(payload: bytes) -> tuple[str, str, str, tuple[str, ...], str, tuple[str, ...]]:
    try:
        fields = payload.decode("ascii").strip().split("|", 5)
        if len(fields) != 6:
            raise ValueError
        image_id, os_name, architecture, raw_diff_ids, user, raw_entrypoint = fields
        diff_ids = json.loads(raw_diff_ids)
        entrypoint = json.loads(raw_entrypoint)
        if (
            _DIGEST.fullmatch(image_id) is None
            or not isinstance(diff_ids, list)
            or not all(isinstance(value, str) and _DIGEST.fullmatch(value) for value in diff_ids)
            or not isinstance(entrypoint, list)
            or not all(isinstance(value, str) for value in entrypoint)
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
        with temporary_directory(prefix="agent00x-exp1549-save-config-") as config_dir:
            env = {"DOCKER_CONFIG": str(config_dir), "PATH": "/usr/local/bin:/usr/bin:/bin"}
            saved = save_runner((DOCKER, "image", "save", SOURCE_TAG),
                                max_bytes=MAX_ARCHIVE_BYTES, timeout=60, env=env)
    except OutputLimitExceeded:
        return _emit(output, "IMAGE_SAVE_SIZE_LIMIT", _CODES["IMAGE_SAVE_SIZE_LIMIT"])
    except subprocess.TimeoutExpired:
        return _emit(output, "IMAGE_SAVE_TIMEOUT", _CODES["IMAGE_SAVE_TIMEOUT"])
    except Exception:
        return _emit(output, "IMAGE_SAVE_FAILED", _CODES["IMAGE_SAVE_FAILED"])
    if saved.returncode != 0 or type(saved.stdout) is not bytes:
        return _emit(output, "IMAGE_SAVE_FAILED", _CODES["IMAGE_SAVE_FAILED"])
    try:
        docker_archive = make_docker_archive(
            saved.stdout,
            config_digest=CONFIG_DIGEST,
            diff_ids=DIFF_IDS,
            repo_tag=IMAGE_TAG,
        )
    except InvalidChain as exc:
        return _emit(output, f"DOCKER_ARCHIVE_INVALID|stage={exc.stage}", _CODES["DOCKER_ARCHIVE_INVALID"])
    except Exception:
        return _emit(output, "DOCKER_ARCHIVE_INVALID|stage=archive-validation", _CODES["DOCKER_ARCHIVE_INVALID"])

    with temporary_directory(prefix="agent00x-exp1549-load-config-") as config_dir:
        env = {"DOCKER_CONFIG": str(config_dir), "PATH": "/usr/local/bin:/usr/bin:/bin"}
        try:
            loaded = load_runner((DOCKER, "image", "load"), input=docker_archive,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 timeout=90, check=False, env=env)
        except Exception:
            return _emit(output, "DOCKER_LOAD_FAILED", _CODES["DOCKER_LOAD_FAILED"])
        if loaded.returncode != 0:
            return _emit(output, "DOCKER_LOAD_FAILED", _CODES["DOCKER_LOAD_FAILED"])
        template = "{{.Id}}|{{.Os}}|{{.Architecture}}|{{json .RootFS.Layers}}|{{.Config.User}}|{{json .Config.Entrypoint}}"
        try:
            inspected = inspect_runner((DOCKER, "image", "inspect", "--format", template, IMAGE_TAG),
                                       max_bytes=16384, timeout=15, env=env)
        except Exception:
            return _emit(output, "POST_LOAD_INSPECT_FAILED", _CODES["POST_LOAD_INSPECT_FAILED"])
    if inspected.returncode != 0 or type(inspected.stdout) is not bytes:
        return _emit(output, "POST_LOAD_INSPECT_FAILED", _CODES["POST_LOAD_INSPECT_FAILED"])
    try:
        facts = _parse_inspect(inspected.stdout)
    except InvalidChain:
        return _emit(output, "POST_LOAD_INSPECT_FAILED", _CODES["POST_LOAD_INSPECT_FAILED"])
    if facts != (CONFIG_DIGEST, OS_NAME, ARCHITECTURE, DIFF_IDS, USER, ENTRYPOINT):
        return _emit(output, "DOCKER_LOAD_FACTS_MISMATCH", _CODES["DOCKER_LOAD_FACTS_MISMATCH"])
    output.write(
        "DOCKER_LOAD_CONFIRMED|"
        f"config={facts[0]}|platform={facts[1]}/{facts[2]}|"
        f"diff_ids={','.join(facts[3])}|user={facts[4]}|"
        f"entrypoint={' '.join(facts[5])}|tag={IMAGE_TAG}\n"
    )
    return _CODES["DOCKER_LOAD_CONFIRMED"]


if __name__ == "__main__":
    raise SystemExit(run_once())
