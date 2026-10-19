#!/usr/bin/env python3
"""Check the pinned verifier's portable OCI content chain in one local save."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import selectors
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TextIO

from scripts import stream_pinned_verifier_image as pinned


CONFIG_DIGEST = "sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IMAGE_TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")
_GZIP_TYPES = {
    "application/vnd.oci.image.layer.v1.tar+gzip",
    "application/vnd.docker.image.rootfs.diff.tar.gzip",
}
_TAR_TYPES = {"application/vnd.oci.image.layer.v1.tar"}
_CODES = {
    "PORTABLE_IMAGE_CHAIN_CONFIRMED": 0,
    "OPT_IN_REQUIRED": 10,
    "LOCAL_IMAGE_SAVE_FAILED": 11,
    "LOCAL_IMAGE_STREAM_SIZE_MISMATCH": 12,
    "PORTABLE_IMAGE_CHAIN_INVALID": 13,
}
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_LAYER_BYTES = 512 * 1024 * 1024


class InvalidChain(Exception):
    """An archive link or content digest is missing or inconsistent."""

    def __init__(self, stage: str = "archive-validation", *,
                 layer_index: int | None = None,
                 observed_digest: str | None = None,
                 safe_detail: str | None = None,
                 archive_format_fact: str | None = None,
                 legacy_config_fact: str | None = None,
                 oci_config_fact: str | None = None,
                 oci_manifest_fact: str | None = None) -> None:
        self.stage = stage if stage in _FAILURE_STAGES else "archive-validation"
        self.safe_detail = safe_detail if safe_detail in _SAFE_FAILURE_DETAILS else None
        self.archive_format_fact = (
            archive_format_fact
            if archive_format_fact in {"oci+docker-legacy", "oci", "docker-legacy", "unclassified"}
            else None
        )
        self.legacy_config_fact = (
            legacy_config_fact
            if legacy_config_fact in {"daemon-match", "daemon-mismatch", "absent", "unclassified"}
            else None
        )
        self.oci_config_fact = (
            oci_config_fact
            if oci_config_fact in {"daemon-match", "daemon-mismatch", "absent", "unclassified"}
            else None
        )
        self.oci_manifest_fact = (
            oci_manifest_fact
            if oci_manifest_fact in {"daemon-match", "daemon-mismatch", "absent", "unclassified"}
            else None
        )
        self.layer_index = layer_index if type(layer_index) is int and 0 <= layer_index < 16 else None
        self.observed_digest = (
            observed_digest
            if isinstance(observed_digest, str) and _DIGEST.fullmatch(observed_digest)
            else None
        )
        super().__init__(self.stage)


_FAILURE_STAGES = frozenset({
    "expected-facts", "archive-layout", "archive-members", "archive-format",
    "oci-index-header", "oci-index-manifest-list", "oci-index-descriptor",
    "oci-index-reference", "oci-index-annotations-invalid",
    "oci-index-ref-name-mismatch", "oci-index-ref-name-unbound",
    "oci-manifest", "image-config", "oci-layers",
    "docker-manifest", "docker-config", "docker-layer-member",
    "docker-layer-size-limit", "docker-layer-diff-id-mismatch",
    "daemon-config-digest-mismatch", "daemon-image-id-mismatch",
    "daemon-platform-mismatch",
    "daemon-diff-id-mismatch",
    "archive-validation",
})
_SAFE_FAILURE_DETAILS = frozenset({"config-name-matches-content", "config-name-mismatches-content"})


class OutputLimitExceeded(Exception):
    """The child emitted more than the allowed bounded archive size."""


@dataclass(frozen=True)
class PortableImageFacts:
    archive_format: str
    portable_manifest_digest: str | None
    config_digest: str
    os_name: str
    architecture: str
    diff_ids: tuple[str, ...]
    repo_tags: tuple[str, ...]


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require(condition: bool) -> None:
    if not condition:
        raise InvalidChain


def _read(tar: tarfile.TarFile, members: dict[str, tarfile.TarInfo],
          name: str, limit: int) -> bytes:
    _require(isinstance(name, str) and not name.startswith("/"))
    _require(all(part not in {"", ".", ".."} for part in name.split("/")))
    member = members.get(name)
    _require(member is not None and member.isfile() and 0 <= member.size <= limit)
    stream = tar.extractfile(member)
    _require(stream is not None)
    data = stream.read(limit + 1)
    _require(len(data) == member.size)
    return data


def _json(data: bytes) -> object:
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidChain from exc


def _descriptor_blob(tar: tarfile.TarFile,
                     members: dict[str, tarfile.TarInfo], descriptor: object,
                     limit: int) -> bytes:
    _require(isinstance(descriptor, dict))
    digest = descriptor.get("digest")
    size = descriptor.get("size")
    _require(isinstance(digest, str) and _DIGEST.fullmatch(digest) is not None)
    _require(type(size) is int and 0 <= size <= limit)
    data = _read(tar, members, "blobs/sha256/" + digest[7:], limit)
    _require(len(data) == size and _digest(data) == digest)
    return data


def _layer_diff_id(data: bytes, media_type: str,
                   max_uncompressed_bytes: int) -> tuple[str, int]:
    if media_type in _TAR_TYPES:
        _require(len(data) <= max_uncompressed_bytes)
        return _digest(data), len(data)
    _require(media_type in _GZIP_TYPES)
    hasher = hashlib.sha256()
    total = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(chunk)
                _require(total <= max_uncompressed_bytes)
                hasher.update(chunk)
    except (OSError, EOFError) as exc:
        raise InvalidChain from exc
    return "sha256:" + hasher.hexdigest(), total


def _legacy_layer_diff_id(data: bytes,
                          max_uncompressed_bytes: int) -> tuple[str, int]:
    """Docker-save compatibility entries omit media type; detect gzip safely."""
    media_type = (
        "application/vnd.docker.image.rootfs.diff.tar.gzip"
        if data.startswith(b"\x1f\x8b")
        else "application/vnd.oci.image.layer.v1.tar"
    )
    return _layer_diff_id(data, media_type, max_uncompressed_bytes)


def parse_portable_archive(
    archive: bytes,
    *,
    expected_config_digest: str,
    expected_os: str,
    expected_architecture: str,
    expected_diff_ids: tuple[str, ...],
    expected_repo_tag: str | None,
    max_archive_bytes: int = 128 * 1024 * 1024,
    max_uncompressed_layer_bytes: int = MAX_EXPANDED_LAYER_BYTES,
) -> PortableImageFacts:
    """Validate one OCI or Docker-legacy image archive against daemon facts.

    Docker's legacy `manifest.json` is not an OCI manifest and receives no
    portable manifest digest. Raw member names and JSON are never returned.
    """
    stage = "expected-facts"
    try:
        _require(type(max_archive_bytes) is int and max_archive_bytes > 0)
        _require(type(max_uncompressed_layer_bytes) is int and max_uncompressed_layer_bytes >= 0)
        _require(type(archive) is bytes and 0 < len(archive) <= max_archive_bytes)
        _require(isinstance(expected_config_digest, str) and _DIGEST.fullmatch(expected_config_digest) is not None)
        _require(expected_os in {"linux", "windows"})
        _require(expected_architecture in {"amd64", "arm64", "386", "arm", "ppc64le", "s390x"})
        _require(
            isinstance(expected_diff_ids, tuple)
            and len(expected_diff_ids) > 0
            and all(isinstance(value, str) and _DIGEST.fullmatch(value) is not None for value in expected_diff_ids)
        )
        if expected_repo_tag is None:
            expected_ref_name = None
        else:
            _require(isinstance(expected_repo_tag, str) and expected_repo_tag and "\n" not in expected_repo_tag)
            _require("@" not in expected_repo_tag and ":" in expected_repo_tag)
            expected_ref_name = expected_repo_tag.rsplit(":", 1)[1]
            _require(_IMAGE_TAG.fullmatch(expected_ref_name) is not None)

        stage = "archive-layout"
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            stage = "archive-members"
            records = tar.getmembers()
            _require(0 < len(records) <= 128)
            members = {record.name: record for record in records}
            _require(len(members) == len(records))
            normalized_names: set[str] = set()
            for name, record in members.items():
                _require(isinstance(name, str) and bool(name) and "\\" not in name)
                normalized_name = name[:-1] if record.isdir() and name.endswith("/") else name
                _require(bool(normalized_name) and normalized_name not in normalized_names)
                normalized_names.add(normalized_name)
                path = PurePosixPath(normalized_name)
                _require(
                    not path.is_absolute()
                    and path.as_posix() == normalized_name
                    and all(part not in {"", ".", ".."} for part in path.parts)
                )
                if record.isdir():
                    _require(record.size == 0)
                else:
                    _require(record.isfile() and 0 <= record.size <= max_archive_bytes)

            def read_member(name: str, limit: int) -> bytes:
                _require(isinstance(name, str) and not name.startswith("/"))
                path = PurePosixPath(name)
                _require(path.as_posix() == name and all(part not in {"", ".", ".."} for part in path.parts))
                record = members.get(name)
                _require(record is not None and record.isfile() and 0 <= record.size <= limit)
                stream = tar.extractfile(record)
                _require(stream is not None)
                data = stream.read(limit + 1)
                _require(len(data) == record.size)
                return data

            stage = "archive-format"
            has_oci_index = "index.json" in members
            has_legacy_manifest = "manifest.json" in members
            _require(has_oci_index or has_legacy_manifest)
            if has_oci_index:
                stage = "oci-index-header"
                index = _json(read_member("index.json", 65536))
                _require(isinstance(index, dict) and index.get("schemaVersion") == 2)
                stage = "oci-index-manifest-list"
                descriptors = index.get("manifests")
                _require(isinstance(descriptors, list) and len(descriptors) == 1)
                stage = "oci-index-descriptor"
                manifest_descriptor = descriptors[0]
                _require(isinstance(manifest_descriptor, dict))
                stage = "oci-index-reference"
                annotations = manifest_descriptor.get("annotations", {})
                if not isinstance(annotations, dict):
                    raise InvalidChain("oci-index-annotations-invalid")
                ref_name = "org.opencontainers.image.ref.name"
                if ref_name in annotations:
                    actual_ref_name = annotations.get(ref_name)
                    if (
                        expected_repo_tag is None
                        or (
                            actual_ref_name != expected_ref_name
                            and actual_ref_name != expected_repo_tag
                        )
                    ):
                        raise InvalidChain("oci-index-ref-name-mismatch")
                else:
                    if not has_legacy_manifest:
                        raise InvalidChain("oci-index-ref-name-unbound")
                manifest_digest = manifest_descriptor.get("digest")
                stage = "oci-manifest"
                manifest_raw = _descriptor_blob(tar, members, manifest_descriptor, 65536)
                _require(_digest(manifest_raw) == manifest_digest)
                manifest = _json(manifest_raw)
                _require(isinstance(manifest, dict) and manifest.get("schemaVersion") == 2)
                config_descriptor = manifest.get("config")
                _require(isinstance(config_descriptor, dict))
                config_digest = config_descriptor.get("digest")
                stage = "image-config"
                config_raw = _descriptor_blob(tar, members, config_descriptor, 1048576)
                config = _json(config_raw)
                _require(isinstance(config, dict))
                rootfs = config.get("rootfs")
                _require(isinstance(rootfs, dict) and rootfs.get("type") == "layers")
                diff_ids = rootfs.get("diff_ids")
                layers = manifest.get("layers")
                _require(isinstance(layers, list) and len(layers) == len(expected_diff_ids))
                stage = "oci-layers"
                expanded_total = 0
                for descriptor, expected_diff_id in zip(layers, expected_diff_ids):
                    _require(isinstance(descriptor, dict))
                    layer = _descriptor_blob(tar, members, descriptor, max_archive_bytes)
                    actual_diff_id, expanded_size = _layer_diff_id(
                        layer,
                        descriptor.get("mediaType"),
                        max_uncompressed_layer_bytes - expanded_total,
                    )
                    expanded_total += expanded_size
                    _require(actual_diff_id == expected_diff_id)
                if has_legacy_manifest:
                    stage = "docker-manifest"
                    records_json = _json(read_member("manifest.json", 65536))
                    _require(isinstance(records_json, list) and len(records_json) == 1)
                    legacy_record = records_json[0]
                    _require(
                        isinstance(legacy_record, dict)
                        and set(legacy_record) == {"Config", "RepoTags", "Layers"}
                    )
                    repo_tags = legacy_record.get("RepoTags")
                    if expected_repo_tag is None:
                        _require(repo_tags is None)
                    else:
                        _require(isinstance(repo_tags, list) and repo_tags == [expected_repo_tag])
                    config_name = legacy_record.get("Config")
                    _require(isinstance(config_name, str))
                    stage = "docker-config"
                    legacy_config_raw = read_member(config_name, 1048576)
                    _require(_digest(legacy_config_raw) == config_digest)
                    legacy_config = _json(legacy_config_raw)
                    _require(
                        isinstance(legacy_config, dict)
                        and legacy_config.get("os") == expected_os
                        and legacy_config.get("architecture") == expected_architecture
                    )
                    legacy_rootfs = legacy_config.get("rootfs")
                    _require(
                        isinstance(legacy_rootfs, dict)
                        and legacy_rootfs.get("type") == "layers"
                        and legacy_rootfs.get("diff_ids") == list(expected_diff_ids)
                    )
                    legacy_layers = legacy_record.get("Layers")
                    _require(
                        isinstance(legacy_layers, list)
                        and len(legacy_layers) == len(expected_diff_ids)
                    )
                    stage = "docker-layers"
                    for layer_index, (layer_name, expected_diff_id) in enumerate(
                        zip(legacy_layers, expected_diff_ids)
                    ):
                        stage = "docker-layer-member"
                        layer = read_member(layer_name, max_archive_bytes)
                        stage = "docker-layer-size-limit"
                        actual_diff_id, expanded_size = _legacy_layer_diff_id(
                            layer, max_uncompressed_layer_bytes - expanded_total
                        )
                        expanded_total += expanded_size
                        stage = "docker-layer-diff-id-mismatch"
                        if actual_diff_id != expected_diff_id:
                            raise InvalidChain(
                                "docker-layer-diff-id-mismatch",
                                layer_index=layer_index,
                            )
                    archive_format = "oci+docker-legacy"
                else:
                    archive_format = "oci"
            else:
                stage = "docker-manifest"
                records_json = _json(read_member("manifest.json", 65536))
                _require(isinstance(records_json, list) and len(records_json) == 1)
                record = records_json[0]
                _require(isinstance(record, dict) and set(record) == {"Config", "RepoTags", "Layers"})
                repo_tags = record.get("RepoTags")
                if expected_repo_tag is None:
                    _require(repo_tags is None)
                else:
                    _require(isinstance(repo_tags, list) and repo_tags == [expected_repo_tag])
                config_name = record.get("Config")
                _require(isinstance(config_name, str))
                stage = "docker-config"
                config_raw = read_member(config_name, 1048576)
                config_digest = _digest(config_raw)
                config = _json(config_raw)
                _require(isinstance(config, dict))
                rootfs = config.get("rootfs")
                _require(isinstance(rootfs, dict) and rootfs.get("type") == "layers")
                diff_ids = rootfs.get("diff_ids")
                layers = record.get("Layers")
                _require(isinstance(layers, list) and len(layers) == len(expected_diff_ids))
                stage = "docker-layers"
                expanded_total = 0
                for layer_index, (layer_name, expected_diff_id) in enumerate(
                    zip(layers, expected_diff_ids)
                ):
                    stage = "docker-layer-member"
                    layer = read_member(layer_name, max_archive_bytes)
                    stage = "docker-layer-size-limit"
                    actual_diff_id, expanded_size = _legacy_layer_diff_id(
                        layer, max_uncompressed_layer_bytes - expanded_total
                    )
                    expanded_total += expanded_size
                    stage = "docker-layer-diff-id-mismatch"
                    if actual_diff_id != expected_diff_id:
                        raise InvalidChain(
                            "docker-layer-diff-id-mismatch",
                            layer_index=layer_index,
                        )
                manifest_digest = None
                archive_format = "docker-legacy"

            stage = "daemon-facts"
            if config_digest != expected_config_digest:
                raise InvalidChain(
                    "daemon-config-digest-mismatch",
                    observed_digest=config_digest,
                )
            if config.get("os") != expected_os or config.get("architecture") != expected_architecture:
                raise InvalidChain("daemon-platform-mismatch")
            if diff_ids != list(expected_diff_ids):
                raise InvalidChain("daemon-diff-id-mismatch")
            return PortableImageFacts(
                archive_format=archive_format,
                portable_manifest_digest=manifest_digest,
                config_digest=config_digest,
                os_name=expected_os,
                architecture=expected_architecture,
                diff_ids=expected_diff_ids,
                repo_tags=() if expected_repo_tag is None else (expected_repo_tag,),
            )
    except InvalidChain as exc:
        failure_stage = exc.stage if exc.stage != "archive-validation" else stage
        raise InvalidChain(
            failure_stage,
            layer_index=exc.layer_index,
            observed_digest=exc.observed_digest,
        ) from None
    except Exception:
        raise InvalidChain(stage) from None


def audit_archive(archive: bytes, *, manifest_digest: str = pinned.IMAGE_ID,
                  config_digest: str = CONFIG_DIGEST,
                  diff_ids: tuple[str, ...] = pinned.DIFF_IDS,
                  stream_size: int = pinned.STREAM_SIZE,
                  os_name: str = pinned.OS, architecture: str = pinned.ARCH,
                  output: TextIO = sys.stdout) -> int:
    if not isinstance(archive, bytes) or len(archive) != stream_size:
        output.write("LOCAL_IMAGE_STREAM_SIZE_MISMATCH\n")
        return _CODES["LOCAL_IMAGE_STREAM_SIZE_MISMATCH"]
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            all_members = tar.getmembers()
            _require(len(all_members) <= 128)
            members = {member.name: member for member in all_members}
            _require(len(members) == len(all_members))
            index = _json(_read(tar, members, "index.json", 65536))
            _require(isinstance(index, dict) and index.get("schemaVersion") == 2)
            manifests = index.get("manifests")
            _require(isinstance(manifests, list) and len(manifests) == 1)
            manifest_descriptor = manifests[0]
            _require(isinstance(manifest_descriptor, dict))
            _require(manifest_descriptor.get("digest") == manifest_digest)
            manifest = _json(_descriptor_blob(tar, members, manifest_descriptor, 65536))
            _require(isinstance(manifest, dict) and manifest.get("schemaVersion") == 2)
            config_descriptor = manifest.get("config")
            _require(isinstance(config_descriptor, dict))
            _require(config_descriptor.get("digest") == config_digest)
            config_bytes = _descriptor_blob(tar, members, config_descriptor, 1048576)
            config = _json(config_bytes)
            _require(isinstance(config, dict))
            rootfs = config.get("rootfs")
            _require(isinstance(rootfs, dict) and rootfs.get("type") == "layers")
            _require(config.get("os") == os_name and config.get("architecture") == architecture)
            _require(rootfs.get("diff_ids") == list(diff_ids))
            layers = manifest.get("layers")
            _require(isinstance(layers, list) and len(layers) == len(diff_ids))
            expanded_total = 0
            for descriptor, expected_diff_id in zip(layers, diff_ids):
                _require(isinstance(descriptor, dict))
                layer_data = _descriptor_blob(tar, members, descriptor, stream_size)
                actual_diff_id, expanded_size = _layer_diff_id(
                    layer_data,
                    descriptor.get("mediaType"),
                    MAX_EXPANDED_LAYER_BYTES - expanded_total,
                )
                expanded_total += expanded_size
                _require(actual_diff_id == expected_diff_id)
    except (InvalidChain, tarfile.TarError, OSError, ValueError, TypeError):
        output.write("PORTABLE_IMAGE_CHAIN_INVALID\n")
        return _CODES["PORTABLE_IMAGE_CHAIN_INVALID"]
    output.write("PORTABLE_IMAGE_CHAIN_CONFIRMED\n")
    return _CODES["PORTABLE_IMAGE_CHAIN_CONFIRMED"]


def _bounded_process_output(command: tuple[str, ...], *, max_bytes: int,
                            timeout: float,
                            env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    """Capture one child's stdout incrementally, never beyond max_bytes."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, bufsize=0, env=env)
    if process.stdout is None:
        process.kill()
        process.wait()
        raise OSError
    captured = bytearray()
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            events = selector.select(remaining)
            if not events:
                raise subprocess.TimeoutExpired(command, timeout)
            chunk = os.read(process.stdout.fileno(), min(1024 * 1024, max_bytes + 1 - len(captured)))
            if not chunk:
                selector.unregister(process.stdout)
                break
            captured.extend(chunk)
            if len(captured) > max_bytes:
                raise OutputLimitExceeded
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        returncode = process.wait(timeout=remaining)
        return subprocess.CompletedProcess(command, returncode, bytes(captured), None)
    except (OutputLimitExceeded, subprocess.TimeoutExpired):
        process.kill()
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()


def audit_local_image(output: TextIO = sys.stdout) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return _CODES["OPT_IN_REQUIRED"]
    try:
        result = _bounded_process_output(
            ("/usr/local/bin/docker", "image", "save", pinned.IMAGE_ID),
            max_bytes=MAX_ARCHIVE_BYTES,
            timeout=60,
        )
    except OutputLimitExceeded:
        output.write("LOCAL_IMAGE_STREAM_SIZE_MISMATCH\n")
        return _CODES["LOCAL_IMAGE_STREAM_SIZE_MISMATCH"]
    except Exception:
        output.write("LOCAL_IMAGE_SAVE_FAILED\n")
        return _CODES["LOCAL_IMAGE_SAVE_FAILED"]
    if result.returncode != 0:
        output.write("LOCAL_IMAGE_SAVE_FAILED\n")
        return _CODES["LOCAL_IMAGE_SAVE_FAILED"]
    return audit_archive(result.stdout, output=output)


if __name__ == "__main__":
    raise SystemExit(audit_local_image())
