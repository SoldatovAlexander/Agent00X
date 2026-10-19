#!/usr/bin/env python3
"""Validate the pinned OCI subset from one bounded Docker image save."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import PurePosixPath
from pathlib import Path
import tempfile
import sys
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import export_verify_portable_image_exp1529 as pinned
from scripts.audit_portable_verifier_image_exp1350 import (
    MAX_ARCHIVE_BYTES,
    InvalidChain,
    OutputLimitExceeded,
    _bounded_process_output,
    parse_portable_archive,
)


_CODES = {
    "OPT_IN_REQUIRED": 10,
    "IMAGE_SAVE_FAILED": 11,
    "IMAGE_SAVE_SIZE_LIMIT": 12,
    "IMAGE_SAVE_TIMEOUT": 13,
    "OCI_SUBSET_INVALID": 14,
    "OCI_SUBSET_CONFIRMED": 0,
}
_DIGEST_PREFIX = "sha256:"
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _digest(data: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def _descriptor_name(descriptor: object, members: dict[str, tarfile.TarInfo]) -> tuple[str, bytes]:
    if not isinstance(descriptor, dict):
        raise InvalidChain("oci-index-descriptor")
    digest = descriptor.get("digest")
    size = descriptor.get("size")
    if not isinstance(digest, str) or len(digest) != 71 or not digest.startswith(_DIGEST_PREFIX):
        raise InvalidChain("oci-index-descriptor")
    if type(size) is not int or size < 0 or size > MAX_ARCHIVE_BYTES:
        raise InvalidChain("oci-index-descriptor")
    name = "blobs/sha256/" + digest[len(_DIGEST_PREFIX):]
    member = members.get(name)
    if member is None or not member.isfile() or member.size != size:
        raise InvalidChain("oci-index-descriptor")
    return name, digest.encode("ascii")


def _read_member(tar: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    stream = tar.extractfile(member)
    if stream is None:
        raise InvalidChain("archive-members")
    payload = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(payload) != member.size or len(payload) > MAX_ARCHIVE_BYTES:
        raise InvalidChain("archive-members")
    return payload


def make_oci_subset(archive: bytes) -> bytes:
    """Build a memory-only OCI tar from reachable regular members."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
            records = source.getmembers()
            if not 0 < len(records) <= 128:
                raise InvalidChain("archive-members")
            members = {member.name: member for member in records}
            if len(members) != len(records):
                raise InvalidChain("archive-members")
            for name, member in members.items():
                path = PurePosixPath(name)
                if (
                    not name or "\\" in name or path.is_absolute()
                    or path.as_posix() != name
                    or any(part in {"", ".", ".."} for part in path.parts)
                ):
                    raise InvalidChain("archive-members")

            index_member = members.get("index.json")
            if index_member is None or not index_member.isfile():
                raise InvalidChain("oci-index-header")
            index_raw = _read_member(source, index_member)
            try:
                index = json.loads(index_raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise InvalidChain("oci-index-header") from None
            if not isinstance(index, dict) or index.get("schemaVersion") != 2:
                raise InvalidChain("oci-index-header")
            manifests = index.get("manifests")
            if not isinstance(manifests, list) or len(manifests) != 1:
                raise InvalidChain("oci-index-manifest-list")

            selected = {"index.json": index_raw}
            manifest_name, manifest_digest = _descriptor_name(manifests[0], members)
            manifest_raw = _read_member(source, members[manifest_name])
            if _digest(manifest_raw).encode("ascii") != manifest_digest:
                raise InvalidChain("oci-index-descriptor")
            selected[manifest_name] = manifest_raw
            try:
                manifest = json.loads(manifest_raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise InvalidChain("oci-manifest") from None
            if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2:
                raise InvalidChain("oci-manifest")

            descriptors = [manifest.get("config")]
            layers = manifest.get("layers")
            if not isinstance(layers, list):
                raise InvalidChain("oci-layers")
            descriptors.extend(layers)
            for descriptor in descriptors:
                blob_name, expected_digest = _descriptor_name(descriptor, members)
                blob = _read_member(source, members[blob_name])
                if _digest(blob).encode("ascii") != expected_digest:
                    raise InvalidChain("oci-layers")
                selected[blob_name] = blob

        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as target:
            for name, payload in sorted(selected.items()):
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                target.addfile(info, io.BytesIO(payload))
        subset = output.getvalue()
        if not subset or len(subset) > MAX_ARCHIVE_BYTES:
            raise InvalidChain("archive-format")
        return subset
    except InvalidChain:
        raise
    except Exception:
        raise InvalidChain("archive-format") from None


def run_once(
    *,
    runner: Runner = _bounded_process_output,
    output: TextIO = sys.stdout,
    temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory,
) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        return _emit(output, "OPT_IN_REQUIRED", _CODES["OPT_IN_REQUIRED"])
    try:
        with temporary_directory(prefix="agent00x-exp1540-docker-config-") as config_dir:
            result = runner(
                (pinned.DOCKER_EXECUTABLE, "image", "save", pinned.IMAGE_TAG),
                max_bytes=MAX_ARCHIVE_BYTES,
                timeout=pinned.TIMEOUT_SECONDS,
                env={"DOCKER_CONFIG": str(config_dir), "PATH": "/usr/local/bin:/usr/bin:/bin"},
            )
    except OutputLimitExceeded:
        return _emit(output, "IMAGE_SAVE_SIZE_LIMIT", _CODES["IMAGE_SAVE_SIZE_LIMIT"])
    except subprocess.TimeoutExpired:
        return _emit(output, "IMAGE_SAVE_TIMEOUT", _CODES["IMAGE_SAVE_TIMEOUT"])
    except Exception:
        return _emit(output, "IMAGE_SAVE_FAILED", _CODES["IMAGE_SAVE_FAILED"])
    if result.returncode != 0 or type(result.stdout) is not bytes:
        return _emit(output, "IMAGE_SAVE_FAILED", _CODES["IMAGE_SAVE_FAILED"])

    try:
        subset = make_oci_subset(result.stdout)
        facts = parse_portable_archive(
            subset,
            expected_config_digest=pinned.CONFIG_DIGEST,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=pinned.DIFF_IDS,
            expected_repo_tag=pinned.IMAGE_TAG,
            max_archive_bytes=MAX_ARCHIVE_BYTES,
        )
    except InvalidChain as exc:
        digest_suffix = (
            f"|expected_config={pinned.CONFIG_DIGEST}|observed_config={exc.observed_digest}"
            if exc.observed_digest is not None
            else ""
        )
        return _emit(
            output,
            f"OCI_SUBSET_INVALID|stage={exc.stage}{digest_suffix}",
            _CODES["OCI_SUBSET_INVALID"],
        )
    except Exception:
        return _emit(output, "OCI_SUBSET_INVALID|stage=archive-validation", _CODES["OCI_SUBSET_INVALID"])

    output.write(
        "OCI_SUBSET_CONFIRMED|legacy=unverified|"
        f"archive_bytes={len(subset)}|manifest={facts.portable_manifest_digest}|"
        f"config={facts.config_digest}|platform={facts.os_name}/{facts.architecture}|"
        f"diff_ids={','.join(facts.diff_ids)}|repo_tag={facts.repo_tags[0]}\n"
    )
    return _CODES["OCI_SUBSET_CONFIRMED"]


if __name__ == "__main__":
    raise SystemExit(run_once())
