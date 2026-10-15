#!/usr/bin/env python3
"""Audit OCI index-to-manifest identity in memory with bounded output."""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from typing import Callable, TextIO

from scripts import stream_pinned_verifier_image as pinned


_MARKER_CODES = {
    "LOCAL_IMAGE_SAVE_FAILED": 10,
    "LOCAL_IMAGE_SAVE_TIMEOUT": 11,
    "LOCAL_IMAGE_SAVE_LAUNCH_FAILED": 12,
    "LOCAL_IMAGE_STREAM_SIZE_MISMATCH": 13,
    "OCI_ARCHIVE_INVALID": 14,
    "OCI_ARCHIVE_STRUCTURE_INVALID": 15,
    "OCI_INDEX_ABSENT": 16,
    "OCI_INDEX_INVALID": 17,
    "OCI_INDEX_ENTRY_COUNT_MISMATCH": 18,
    "OCI_MANIFEST_BLOB_INVALID": 19,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def audit_oci_index(
    archive: bytes,
    *,
    image_id: str = pinned.IMAGE_ID,
    stream_size: int = pinned.STREAM_SIZE,
    output: TextIO = sys.stdout,
) -> int:
    if not isinstance(archive, bytes) or len(archive) != stream_size:
        return _emit("LOCAL_IMAGE_STREAM_SIZE_MISMATCH", output)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            members = tar.getmembers()
            if len(members) > 128:
                return _emit("OCI_ARCHIVE_STRUCTURE_INVALID", output)
            member_map = {member.name: member for member in members}
            if len(member_map) != len(members):
                return _emit("OCI_ARCHIVE_STRUCTURE_INVALID", output)
            index_member = member_map.get("index.json")
            if index_member is None:
                return _emit("OCI_INDEX_ABSENT", output)
            if not index_member.isfile() or index_member.size > 65536:
                return _emit("OCI_INDEX_INVALID", output)
            index_file = tar.extractfile(index_member)
            if index_file is None:
                return _emit("OCI_INDEX_INVALID", output)
            try:
                index = json.loads(index_file.read(65537))
            except json.JSONDecodeError:
                return _emit("OCI_INDEX_INVALID", output)
            if not isinstance(index, dict):
                return _emit("OCI_INDEX_INVALID", output)
            manifests = index.get("manifests")
            if not isinstance(manifests, list):
                return _emit("OCI_INDEX_INVALID", output)
            if len(manifests) != 1:
                return _emit("OCI_INDEX_ENTRY_COUNT_MISMATCH", output)
            descriptor = manifests[0]
            if not isinstance(descriptor, dict):
                return _emit("OCI_INDEX_INVALID", output)
            digest = descriptor.get("digest")
            size = descriptor.get("size")
            if (
                not isinstance(digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
                or type(size) is not int
                or size < 0
            ):
                return _emit("OCI_INDEX_INVALID", output)
            blob_path = "blobs/sha256/" + digest.split(":", 1)[1]
            blob_member = member_map.get(blob_path)
            if (
                blob_member is None
                or not blob_member.isfile()
                or blob_member.size != size
                or blob_member.size > stream_size
            ):
                return _emit("OCI_MANIFEST_BLOB_INVALID", output)
            blob_file = tar.extractfile(blob_member)
            if blob_file is None:
                return _emit("OCI_MANIFEST_BLOB_INVALID", output)
            hasher = hashlib.sha256()
            for chunk in iter(lambda: blob_file.read(1024 * 1024), b""):
                hasher.update(chunk)
            blob_matches = "sha256:" + hasher.hexdigest() == digest
            output.write(
                "OCI_ARCHIVE_FACTS|index_present=true|index_valid=true|entry_count=1|"
                "target_digest_matches_image_id="
                f"{str(digest == image_id).lower()}|"
                f"manifest_blob_hash_matches={str(blob_matches).lower()}\n"
            )
            if not blob_matches:
                return _MARKER_CODES["OCI_MANIFEST_BLOB_INVALID"]
            return 0
    except (tarfile.TarError, OSError, ValueError, TypeError):
        return _emit("OCI_ARCHIVE_INVALID", output)


def audit_local_archive(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    try:
        saved = runner(
            ("/usr/local/bin/docker", "image", "save", pinned.IMAGE_ID),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _emit("LOCAL_IMAGE_SAVE_TIMEOUT", output)
    except Exception:
        return _emit("LOCAL_IMAGE_SAVE_LAUNCH_FAILED", output)
    if saved.returncode != 0:
        return _emit("LOCAL_IMAGE_SAVE_FAILED", output)
    return audit_oci_index(saved.stdout, output=output)


if __name__ == "__main__":
    raise SystemExit(audit_local_archive())
