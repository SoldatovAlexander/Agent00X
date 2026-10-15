"""Create a standalone, exact-stage snapshot from a stable SQLite WAL source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

from .durable_stage import SQLiteStagedArtifactStore

_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_DIGEST_PREFIX = "sha256:"


class WalStageSnapshotError(ValueError):
    """A WAL-backed stage snapshot could not be safely produced."""


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_SOURCE_BYTES:
                    raise ValueError
                digest.update(chunk)
        return digest.hexdigest(), size
    except Exception:
        raise WalStageSnapshotError("wal stage snapshot: source is unavailable") from None


def _source_path(value: Path | str) -> Path:
    try:
        path = Path(value)
        if (
            not path.is_absolute()
            or ".." in path.parts
            or path.is_symlink()
            or not path.is_file()
            or path.resolve(strict=True) != path
            or path.with_name(path.name + "-journal").exists()
        ):
            raise ValueError
        return path
    except Exception:
        raise WalStageSnapshotError("wal stage snapshot: source is unavailable") from None


def _destination_path(value: Path | str, source: Path) -> Path:
    try:
        path = Path(value)
        parent = path.parent
        if (
            not path.is_absolute()
            or ".." in path.parts
            or path.name in ("", ".", "..")
            or path.is_symlink()
            or path.exists()
            or not parent.is_dir()
            or parent.is_symlink()
            or parent.resolve(strict=True) != parent
            or path == source
            or path in {
                source.with_name(source.name + "-wal"),
                source.with_name(source.name + "-shm"),
            }
        ):
            raise ValueError
        return path
    except Exception:
        raise WalStageSnapshotError(
            "wal stage snapshot: destination is unavailable"
        ) from None


def _source_manifest(source: Path) -> tuple[tuple[str, str, int], ...]:
    items: list[tuple[str, str, int]] = []
    total = 0
    try:
        for suffix in ("", "-wal", "-shm"):
            path = source if not suffix else source.with_name(source.name + suffix)
            if not path.exists():
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError
            digest, size = _file_digest(path)
            total += size
            if total > _MAX_SOURCE_BYTES:
                raise ValueError
            items.append((path.name, digest, size))
        if not items or items[0][0] != source.name:
            raise ValueError
        return tuple(items)
    except Exception:
        raise WalStageSnapshotError("wal stage snapshot: source is unavailable") from None


def _copy_exact(source: Path, destination: Path) -> None:
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_stream:
            shutil.copyfileobj(input_stream, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        raise WalStageSnapshotError("wal stage snapshot: source changed during copy") from None


def _integrity_check(connection: sqlite3.Connection) -> None:
    try:
        result = connection.execute("PRAGMA integrity_check").fetchall()
        if result != [("ok",)]:
            raise ValueError
    except Exception:
        raise WalStageSnapshotError("wal stage snapshot: SQLite integrity check failed") from None


def _digest_manifest(manifest: tuple[tuple[str, str, int], ...]) -> str:
    value = [
        {"name": name, "sha256": digest, "size": size}
        for name, digest, size in manifest
    ]
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def snapshot_wal_stage(
    source_database: Path | str,
    staged_change_digest: str,
    destination_database: Path | str,
) -> dict:
    """Copy a consistent SQLite snapshot without opening or mutating the source DB."""

    source = _source_path(source_database)
    destination = _destination_path(destination_database, source)
    if (
        type(staged_change_digest) is not str
        or len(staged_change_digest) != len(_DIGEST_PREFIX) + 64
        or not staged_change_digest.startswith(_DIGEST_PREFIX)
        or any(character not in "0123456789abcdef" for character in staged_change_digest[7:])
    ):
        raise WalStageSnapshotError("wal stage snapshot: staged digest is invalid")

    manifest = _source_manifest(source)
    temporary_directory: Path | None = None
    descriptor = -1
    try:
        temporary_directory = Path(
            tempfile.mkdtemp(prefix=".agent00x-wal-stage-", dir=destination.parent)
        )
        os.chmod(temporary_directory, 0o700)
        snapshot_source = temporary_directory / source.name
        for name, expected_digest, _size in manifest:
            original = source if name == source.name else source.with_name(name)
            copied = temporary_directory / name
            _copy_exact(original, copied)
            copied_digest, _copied_size = _file_digest(copied)
            if copied_digest != expected_digest:
                raise WalStageSnapshotError(
                    "wal stage snapshot: source changed during copy"
                )
        if _source_manifest(source) != manifest:
            raise WalStageSnapshotError("wal stage snapshot: source changed during copy")

        destination_temp = temporary_directory / "standalone.sqlite3"
        descriptor = os.open(
            destination_temp,
            os.O_RDWR | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(descriptor)
        descriptor = -1
        source_connection: sqlite3.Connection | None = None
        destination_connection: sqlite3.Connection | None = None
        try:
            source_uri = snapshot_source.resolve(strict=True).as_uri() + "?mode=ro"
            source_connection = sqlite3.connect(
                source_uri, timeout=5.0, isolation_level=None, uri=True
            )
            destination_connection = sqlite3.connect(
                str(destination_temp), timeout=5.0, isolation_level=None
            )
            try:
                _integrity_check(source_connection)
                journal = destination_connection.execute(
                    "PRAGMA journal_mode=DELETE"
                ).fetchone()
                destination_connection.execute("PRAGMA synchronous=FULL")
                if not journal or journal[0] != "delete":
                    raise WalStageSnapshotError(
                        "wal stage snapshot: standalone journal mode unavailable"
                    )
                source_connection.backup(destination_connection, pages=256)
                destination_connection.commit()
                journal = destination_connection.execute(
                    "PRAGMA journal_mode=DELETE"
                ).fetchone()
                if not journal or journal[0] != "delete":
                    raise WalStageSnapshotError(
                        "wal stage snapshot: standalone journal mode unavailable"
                    )
                _integrity_check(destination_connection)
            finally:
                if destination_connection is not None:
                    destination_connection.close()
                if source_connection is not None:
                    source_connection.close()
        except WalStageSnapshotError:
            raise
        except Exception:
            raise WalStageSnapshotError(
                "wal stage snapshot: SQLite backup failed"
            ) from None

        os.chmod(destination_temp, 0o600)
        if (
            destination_temp.with_name(destination_temp.name + "-wal").exists()
            or destination_temp.with_name(destination_temp.name + "-shm").exists()
        ):
            raise WalStageSnapshotError(
                "wal stage snapshot: standalone database is not quiescent"
            )
        with destination_temp.open("rb") as database_file:
            os.fsync(database_file.fileno())
        try:
            with SQLiteStagedArtifactStore(destination_temp, read_only=True) as store:
                artifact = store.load(staged_change_digest)
        except Exception:
            raise WalStageSnapshotError(
                "wal stage snapshot: staged artifact validation failed"
            ) from None
        if _source_manifest(source) != manifest:
            raise WalStageSnapshotError("wal stage snapshot: source changed during copy")

        destination_hash, destination_size = _file_digest(destination_temp)
        try:
            os.link(destination_temp, destination)
        except Exception:
            raise WalStageSnapshotError(
                "wal stage snapshot: no-overwrite publish failed"
            ) from None
        if (
            destination.with_name(destination.name + "-wal").exists()
            or destination.with_name(destination.name + "-shm").exists()
            or _file_digest(destination)[0] != destination_hash
            or _source_manifest(source) != manifest
        ):
            raise WalStageSnapshotError(
                "wal stage snapshot: final verification failed"
            )
        try:
            with SQLiteStagedArtifactStore(destination, read_only=True) as store:
                final_artifact = store.load(staged_change_digest)
        except Exception:
            raise WalStageSnapshotError(
                "wal stage snapshot: final artifact readback failed"
            ) from None
        if final_artifact != artifact:
            raise WalStageSnapshotError(
                "wal stage snapshot: final artifact readback failed"
            )
        if os.name != "nt":
            try:
                parent_fd = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
            except OSError:
                raise WalStageSnapshotError(
                    "wal stage snapshot: destination durability check failed"
                ) from None
        return {
            "schema": "wal-stage-snapshot-evidence/v1",
            "status": "snapshotted",
            "staged_change_digest": staged_change_digest,
            "artifact_digest": artifact.artifact_digest,
            "source_snapshot_sha256": _digest_manifest(manifest),
            "destination_sha256": destination_hash,
            "destination_bytes": destination_size,
            "source_unchanged": True,
            "overwrite": False,
        }
    except WalStageSnapshotError:
        raise
    except Exception:
        raise WalStageSnapshotError("wal stage snapshot: operation failed") from None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_directory is not None:
            try:
                shutil.rmtree(temporary_directory)
            except OSError:
                pass
        # A published destination is retained as evidence, even after a later check fails.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a standalone exact-digest snapshot of a SQLite WAL stage."
    )
    parser.add_argument("source_database")
    parser.add_argument("staged_change_digest")
    parser.add_argument("destination_database")
    args = parser.parse_args(argv)
    try:
        evidence = snapshot_wal_stage(
            args.source_database,
            args.staged_change_digest,
            args.destination_database,
        )
    except WalStageSnapshotError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("wal stage snapshot: operation failed", file=sys.stderr)
        return 2
    print(json.dumps(evidence, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0
