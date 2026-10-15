#!/usr/bin/env python3
"""Audit the exact pinned Docker save archive entirely in process memory."""

from __future__ import annotations

import hashlib
import gzip
import io
import json
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
    "ARCHIVE_INVALID": 14,
    "ARCHIVE_STRUCTURE_INVALID": 15,
    "MANIFEST_INVALID": 16,
    "MANIFEST_ENTRY_COUNT_MISMATCH": 17,
    "MANIFEST_CONFIG_PATH_INVALID": 18,
    "MANIFEST_REPOTAGS_PRESENT": 19,
    "MANIFEST_LAYERS_INVALID": 20,
    "MANIFEST_LAYER_COUNT_MISMATCH": 21,
    "MANIFEST_LAYER_PATH_INVALID": 22,
    "CONFIG_ID_MISMATCH": 23,
    "DIFF_IDS_MISMATCH": 24,
    "LAYER_DIGEST_MISMATCH": 25,
    "ARCHIVE_CONFIRMED": 0,
}

Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def _safe_archive_path(path: object) -> bool:
    if not isinstance(path, str) or not path or path.startswith("/"):
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def inspect_archive(
    archive: bytes,
    *,
    image_id: str = pinned.IMAGE_ID,
    descriptor_digest: str | None = None,
    emit_config_digest: bool = False,
    diff_ids: tuple[str, ...] = pinned.DIFF_IDS,
    stream_size: int = pinned.STREAM_SIZE,
    output: TextIO = sys.stdout,
) -> int:
    """Validate manifest, config identity, ordered DiffIDs and layer contents."""
    if not isinstance(archive, bytes) or len(archive) != stream_size:
        return _emit("LOCAL_IMAGE_STREAM_SIZE_MISMATCH", output)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            members = tar.getmembers()
            if len(members) > 128:
                return _emit("ARCHIVE_STRUCTURE_INVALID", output)
            member_by_name = {member.name: member for member in members}
            if len(member_by_name) != len(members):
                return _emit("ARCHIVE_STRUCTURE_INVALID", output)
            manifest_member = member_by_name.get("manifest.json")
            if (
                manifest_member is None
                or not manifest_member.isfile()
                or manifest_member.size > 65536
            ):
                return _emit("MANIFEST_INVALID", output)
            manifest_file = tar.extractfile(manifest_member)
            if manifest_file is None:
                return _emit("MANIFEST_INVALID", output)
            try:
                manifest = json.loads(manifest_file.read(65537))
            except json.JSONDecodeError:
                return _emit("MANIFEST_INVALID", output)

            if not isinstance(manifest, list):
                return _emit("MANIFEST_INVALID", output)
            if len(manifest) != 1:
                return _emit("MANIFEST_ENTRY_COUNT_MISMATCH", output)
            entry = manifest[0]
            if not isinstance(entry, dict):
                return _emit("MANIFEST_INVALID", output)
            config_name = entry.get("Config")
            if not _safe_archive_path(config_name):
                return _emit("MANIFEST_CONFIG_PATH_INVALID", output)
            if entry.get("RepoTags") is not None:
                return _emit("MANIFEST_REPOTAGS_PRESENT", output)
            layers = entry.get("Layers")
            if (
                not isinstance(layers, list)
            ):
                return _emit("MANIFEST_LAYERS_INVALID", output)
            if len(layers) != len(diff_ids):
                return _emit("MANIFEST_LAYER_COUNT_MISMATCH", output)
            if not all(_safe_archive_path(path) for path in layers):
                return _emit("MANIFEST_LAYER_PATH_INVALID", output)
            if len(set(layers)) != len(layers):
                return _emit("MANIFEST_LAYER_PATH_INVALID", output)

            config_member = member_by_name.get(config_name)
            if (
                config_member is None
                or not config_member.isfile()
                or config_member.size > 1_048_576
            ):
                return _emit("ARCHIVE_STRUCTURE_INVALID", output)
            config_file = tar.extractfile(config_member)
            if config_file is None:
                return _emit("ARCHIVE_STRUCTURE_INVALID", output)
            config_bytes = config_file.read(1_048_577)
            config_digest = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
            try:
                config = json.loads(config_bytes)
            except json.JSONDecodeError:
                return _emit("CONFIG_ID_MISMATCH", output)
            rootfs = config.get("rootfs") if isinstance(config, dict) else None
            actual_diff_ids = rootfs.get("diff_ids") if isinstance(rootfs, dict) else None
            if (
                not isinstance(actual_diff_ids, list)
                or not all(
                    isinstance(value, str)
                    and value.startswith("sha256:")
                    and len(value) == 71
                    and all(character in "0123456789abcdef" for character in value[7:])
                    for value in actual_diff_ids
                )
            ):
                return _emit("DIFF_IDS_MISMATCH", output)

            raw_layers_match_config = len(actual_diff_ids) == len(layers)
            uncompressed_layers_match_config = len(actual_diff_ids) == len(layers)
            gzip_layer_count = 0
            for index, layer_path in enumerate(layers):
                layer_member = member_by_name.get(layer_path)
                if (
                    layer_member is None
                    or not layer_member.isfile()
                    or layer_member.size > stream_size
                ):
                    return _emit("ARCHIVE_STRUCTURE_INVALID", output)
                layer_file = tar.extractfile(layer_member)
                if layer_file is None:
                    return _emit("ARCHIVE_STRUCTURE_INVALID", output)
                prefix = layer_file.read(2)
                layer_file.seek(0)
                raw_digest = hashlib.sha256()
                for chunk in iter(lambda: layer_file.read(1024 * 1024), b""):
                    raw_digest.update(chunk)
                raw_actual_digest = "sha256:" + raw_digest.hexdigest()
                normalized_digest = hashlib.sha256()
                if prefix == b"\x1f\x8b":
                    gzip_layer_count += 1
                    layer_file.seek(0)
                    with gzip.GzipFile(fileobj=layer_file, mode="rb") as decompressed:
                        for chunk in iter(lambda: decompressed.read(1024 * 1024), b""):
                            normalized_digest.update(chunk)
                else:
                    layer_file.seek(0)
                    for chunk in iter(lambda: layer_file.read(1024 * 1024), b""):
                        normalized_digest.update(chunk)
                normalized_actual_digest = "sha256:" + normalized_digest.hexdigest()
                if index >= len(actual_diff_ids):
                    raw_layers_match_config = False
                    uncompressed_layers_match_config = False
                else:
                    raw_layers_match_config &= raw_actual_digest == actual_diff_ids[index]
                    uncompressed_layers_match_config &= (
                        normalized_actual_digest == actual_diff_ids[index]
                    )

            config_hash_matches_pin = config_digest == image_id
            config_filename_stem_matches_hash = (
                config_name.rsplit("/", 1)[-1].removesuffix(".json")
                == hashlib.sha256(config_bytes).hexdigest()
            )
            diff_ids_match_pin = actual_diff_ids == list(diff_ids)
            if not config_hash_matches_pin:
                output.write(
                    "ARCHIVE_FACTS|config_hash_matches_pin=false|"
                    f"config_filename_stem_matches_hash={str(config_filename_stem_matches_hash).lower()}|"
                    f"diff_ids_match_pin={str(diff_ids_match_pin).lower()}|"
                    "raw_layers_match_diff_ids="
                    f"{str(raw_layers_match_config).lower()}|"
                    "uncompressed_layers_match_diff_ids="
                    f"{str(uncompressed_layers_match_config).lower()}|"
                    f"gzip_layer_count={gzip_layer_count}"
                    + (
                        "|descriptor_digest_matches_pin="
                        f"{str(descriptor_digest == image_id).lower()}|"
                        "config_hash_matches_descriptor="
                        f"{str(config_digest == descriptor_digest).lower()}"
                        if descriptor_digest is not None
                        else ""
                    )
                    + (
                        "|archive_config_digest=" + config_digest
                        if emit_config_digest
                        else ""
                    )
                    + "\n"
                )
                return _MARKER_CODES["CONFIG_ID_MISMATCH"]
            if not diff_ids_match_pin:
                return _emit("DIFF_IDS_MISMATCH", output)
            if not uncompressed_layers_match_config:
                return _emit("LAYER_DIGEST_MISMATCH", output)
    except (tarfile.TarError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return _emit("ARCHIVE_INVALID", output)

    output.write(
        f"ARCHIVE_CONFIRMED|{image_id}|{stream_size}|{len(diff_ids)}|"
        f"config_sha256={image_id}|"
        "config_filename_stem_matches_hash="
        f"{str(config_filename_stem_matches_hash).lower()}|"
        "repo_tags=null\n"
    )
    return _MARKER_CODES["ARCHIVE_CONFIRMED"]


def audit_local_archive(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    command = ("/usr/local/bin/docker", "image", "save", pinned.IMAGE_ID)
    try:
        result = runner(command, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        return _emit("LOCAL_IMAGE_SAVE_TIMEOUT", output)
    except Exception:
        return _emit("LOCAL_IMAGE_SAVE_LAUNCH_FAILED", output)
    if result.returncode != 0:
        return _emit("LOCAL_IMAGE_SAVE_FAILED", output)
    return inspect_archive(result.stdout, output=output)


def main() -> int:
    return audit_local_archive()


if __name__ == "__main__":
    raise SystemExit(main())
