#!/usr/bin/env python3
"""Build a deterministic source archive for the one-shot verifier host.

The archive is emitted only to stdout. Its manifest and archive digest are
reported to stderr so a caller can pipe the bytes to a separately authorized
destination without writing an intermediate file.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
from dataclasses import dataclass
from typing import BinaryIO, TextIO


ROOT = Path(__file__).resolve().parents[1]
_FIXED_FILES = (
    "scripts/serve_ephemeral_signed_verifier_https.py",
    "requirements-verifier-host.txt",
    "schemas/checkpoint.schema.json",
    "schemas/observation-event.schema.json",
)
_APP_PACKAGE = "src/app_contracts"
_APP_PACKAGE_NAME = "app_contracts"
_VERIFIER_HOST_ROOT_MODULES = (
    "app_contracts",
    "app_contracts.signed_verifier_http_service",
    "app_contracts.signed_verifier_service",
)
_MAX_MEMBERS = 128
_MAX_MEMBER_BYTES = 1_048_576
_MAX_SOURCE_BYTES = 8_388_608
_MAX_ARCHIVE_BYTES = 10_485_760
_MANIFEST_NAME = "MANIFEST.json"
_FAILURE = "verifier host bundle: build failed\n"
_EXPECTED_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class BundleBuildError(ValueError):
    """The fixed verifier-host source bundle cannot be built safely."""


@dataclass(frozen=True)
class _SourceMember:
    name: str
    data: bytes


def _ensure_no_symlink_path(root: Path, relative_name: str) -> None:
    current = root
    for part in Path(relative_name).parts:
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError


def _read_regular_file(root: Path, relative_name: str) -> bytes:
    candidate = root / relative_name
    try:
        _ensure_no_symlink_path(root, relative_name)
        before = candidate.lstat()
        if not stat.S_ISREG(before.st_mode) or candidate.is_symlink():
            raise ValueError
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size > _MAX_MEMBER_BYTES
            ):
                raise ValueError
            chunks: list[bytes] = []
            remaining = _MAX_MEMBER_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > _MAX_MEMBER_BYTES or len(data) != opened.st_size:
                raise ValueError
            return data
        finally:
            os.close(descriptor)
    except Exception:
        raise BundleBuildError(_FAILURE) from None


def _module_name_for_path(relative_path: str) -> str:
    parts = list(Path(relative_path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join((_APP_PACKAGE_NAME, *parts))


def _app_module_index(root: Path) -> dict[str, str]:
    package_root = root / _APP_PACKAGE
    try:
        _ensure_no_symlink_path(root, _APP_PACKAGE)
        info = package_root.lstat()
        if not stat.S_ISDIR(info.st_mode) or package_root.is_symlink():
            raise ValueError
        module_index: dict[str, str] = {}
        for directory, dirnames, filenames in os.walk(
            package_root, topdown=True, followlinks=False
        ):
            current = Path(directory)
            dirnames.sort()
            filenames.sort()
            for dirname in dirnames:
                child = current / dirname
                child_info = child.lstat()
                if stat.S_ISLNK(child_info.st_mode) or not stat.S_ISDIR(
                    child_info.st_mode
                ):
                    raise ValueError
            for filename in filenames:
                candidate = current / filename
                candidate_info = candidate.lstat()
                if stat.S_ISLNK(candidate_info.st_mode):
                    raise ValueError
                if not filename.endswith(".py"):
                    continue
                if not stat.S_ISREG(candidate_info.st_mode):
                    raise ValueError
                relative_name = candidate.relative_to(root).as_posix()
                module_name = _module_name_for_path(
                    candidate.relative_to(package_root).as_posix()
                )
                if module_name in module_index:
                    raise ValueError
                module_index[module_name] = relative_name
        return module_index
    except Exception:
        raise BundleBuildError(_FAILURE) from None


def _local_import_targets(
    tree: ast.Module,
    *,
    package: str,
    module_index: dict[str, str],
) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name == _APP_PACKAGE_NAME or name.startswith(
                    _APP_PACKAGE_NAME + "."
                ):
                    if name not in module_index:
                        raise ValueError
                    targets.add(name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = importlib.util.resolve_name("." * node.level + base, package)
            if base != _APP_PACKAGE_NAME and not base.startswith(
                _APP_PACKAGE_NAME + "."
            ):
                continue
            if base not in module_index:
                raise ValueError
            targets.add(base)
            if node.module is None or base == _APP_PACKAGE_NAME:
                for alias in node.names:
                    candidate = base + "." + alias.name
                    if candidate in module_index:
                        targets.add(candidate)
    return targets


def _module_parents(name: str, module_index: dict[str, str]) -> set[str]:
    parts = name.split(".")
    return {
        ".".join(parts[:position])
        for position in range(1, len(parts) + 1)
        if ".".join(parts[:position]) in module_index
    }


def _collect_app_modules(root: Path) -> list[_SourceMember]:
    try:
        module_index = _app_module_index(root)
        pending = list(_VERIFIER_HOST_ROOT_MODULES)
        included: set[str] = set()
        while pending:
            module_name = pending.pop()
            if module_name in included:
                continue
            relative_name = module_index.get(module_name)
            if relative_name is None:
                raise ValueError
            source = _read_regular_file(root, relative_name)
            tree = ast.parse(source.decode("utf-8"), filename=relative_name)
            package = (
                module_name
                if Path(relative_name).name == "__init__.py"
                else module_name.rpartition(".")[0]
            )
            imports = _local_import_targets(
                tree,
                package=package,
                module_index=module_index,
            )
            included.add(module_name)
            for imported_name in imports:
                pending.extend(_module_parents(imported_name, module_index) - included)

        if len(included) + len(_FIXED_FILES) > _MAX_MEMBERS:
            raise ValueError
        members = [
            _SourceMember(module_index[name], _read_regular_file(root, module_index[name]))
            for name in sorted(included)
        ]
        if sum(len(member.data) for member in members) > _MAX_SOURCE_BYTES:
            raise ValueError
        return members
    except BundleBuildError:
        raise
    except Exception:
        raise BundleBuildError(_FAILURE) from None


def _collect_members(project_root: str | os.PathLike[str]) -> list[_SourceMember]:
    try:
        root = Path(project_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError
        members = [
            _SourceMember(name, _read_regular_file(root, name))
            for name in _FIXED_FILES
        ]
        members.extend(_collect_app_modules(root))
        members.sort(key=lambda member: member.name)
        names = [member.name for member in members]
        if (
            len(names) != len(set(names))
            or len(members) > _MAX_MEMBERS
            or sum(len(member.data) for member in members) > _MAX_SOURCE_BYTES
            or any(
                len(member.data) > _MAX_MEMBER_BYTES
                or not _is_allowed_name(member.name)
                for member in members
            )
        ):
            raise ValueError
        return members
    except BundleBuildError:
        raise
    except Exception:
        raise BundleBuildError(_FAILURE) from None


def _is_allowed_name(name: str) -> bool:
    return (
        name in _FIXED_FILES
        or (
            name.startswith(_APP_PACKAGE + "/")
            and name.endswith(".py")
            and "\\" not in name
            and ".." not in Path(name).parts
        )
    )


def _tar_info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}
    return info


def build_bundle(
    project_root: str | os.PathLike[str] = ROOT,
) -> tuple[bytes, str, int, int]:
    """Return archive bytes, archive digest, source member count and byte size."""

    members = _collect_members(project_root)
    source_bytes = sum(len(member.data) for member in members)
    manifest = {
        "schema": "agent00x-verifier-host-source-bundle/v1",
        "files": [
            {
                "path": member.name,
                "size": len(member.data),
                "sha256": hashlib.sha256(member.data).hexdigest(),
            }
            for member in members
        ],
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    if len(manifest_bytes) > 65_536:
        raise BundleBuildError(_FAILURE) from None
    archive_buffer = io.BytesIO()
    try:
        with tarfile.open(
            fileobj=archive_buffer, mode="w", format=tarfile.USTAR_FORMAT
        ) as archive:
            for member in members:
                archive.addfile(
                    _tar_info(member.name, len(member.data)),
                    io.BytesIO(member.data),
                )
            archive.addfile(
                _tar_info(_MANIFEST_NAME, len(manifest_bytes)),
                io.BytesIO(manifest_bytes),
            )
        archive_bytes = archive_buffer.getvalue()
    except Exception:
        raise BundleBuildError(_FAILURE) from None
    if (
        not archive_bytes
        or len(archive_bytes) > _MAX_ARCHIVE_BYTES
        or _MANIFEST_NAME in {member.name for member in members}
    ):
        raise BundleBuildError(_FAILURE) from None
    return (
        archive_bytes,
        hashlib.sha256(archive_bytes).hexdigest(),
        len(members),
        source_bytes,
    )


def main(
    argv: object | None = None,
    *,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
    project_root: str | os.PathLike[str] = ROOT,
) -> int:
    output = sys.stdout.buffer if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    try:
        arguments = sys.argv[1:] if argv is None else argv
        if type(arguments) not in {list, tuple} or any(
            type(argument) is not str for argument in arguments
        ):
            raise BundleBuildError(_FAILURE)
        expected_digest = None
        if arguments:
            if (
                len(arguments) != 2
                or arguments[0] != "--expected-sha256"
                or _EXPECTED_DIGEST.fullmatch(arguments[1]) is None
            ):
                raise BundleBuildError(_FAILURE)
            expected_digest = arguments[1]
        archive, digest, count, source_bytes = build_bundle(project_root)
        if expected_digest is not None and expected_digest != "sha256:" + digest:
            raise BundleBuildError(_FAILURE)
        output.write(archive)
        output.flush()
        metadata = {
            "schema": "agent00x-verifier-host-bundle-report/v1",
            "bundle_sha256": "sha256:" + digest,
            "member_count": count,
            "source_bytes": source_bytes,
        }
        errors.write(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n"
        )
        errors.flush()
        return 0
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        try:
            errors.write(_FAILURE)
            errors.flush()
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
