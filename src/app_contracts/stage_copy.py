"""Create a byte-identical, exact-digest copy of a quiescent SQLite stage.

This is a local evidence-copy helper. A copy on the same volume is not a
cross-host backup, replication, power-loss proof, or production durability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .durable_stage import SQLiteStagedArtifactStore

_DIGEST_PREFIX = "sha256:"
_MAX_DATABASE_BYTES = 64 * 1024 * 1024


class StageCopyError(ValueError):
    """A stage copy could not be safely completed."""


def _has_sqlite_sidecars(path: Path) -> bool:
    return (
        path.with_name(path.name + "-wal").exists()
        or path.with_name(path.name + "-shm").exists()
    )


def _validated_source(value: Path | str) -> Path:
    try:
        path = Path(value)
        resolved = path.resolve(strict=True)
        if (
            not path.is_absolute()
            or ".." in path.parts
            or path.is_symlink()
            or not path.is_file()
            or resolved != path
            or path.stat().st_size > _MAX_DATABASE_BYTES
            or _has_sqlite_sidecars(path)
        ):
            raise ValueError
        return path
    except Exception:
        raise StageCopyError("stage copy: source is unavailable") from None


def _validated_destination(value: Path | str, source: Path) -> Path:
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
        ):
            raise ValueError
        return path
    except Exception:
        raise StageCopyError("stage copy: destination is unavailable") from None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        raise StageCopyError("stage copy: file verification failed") from None


def copy_staged_evidence(
    source_database: Path | str,
    staged_change_digest: str,
    destination_database: Path | str,
) -> dict:
    """Copy one validated stage DB to a new path without overwriting either file."""

    source = _validated_source(source_database)
    destination = _validated_destination(destination_database, source)
    if (
        type(staged_change_digest) is not str
        or len(staged_change_digest) != len(_DIGEST_PREFIX) + 64
        or not staged_change_digest.startswith(_DIGEST_PREFIX)
        or any(character not in "0123456789abcdef" for character in staged_change_digest[7:])
    ):
        raise StageCopyError("stage copy: staged digest is invalid")

    try:
        with SQLiteStagedArtifactStore(source, read_only=True) as store:
            source_artifact = store.load(staged_change_digest)
    except Exception:
        raise StageCopyError("stage copy: source stage is invalid") from None

    source_hash = _file_sha256(source)
    descriptor = -1
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".agent00x-stage-copy-", suffix=".sqlite3", dir=destination.parent
        )
        temporary = Path(temporary_name)
        os.close(descriptor)
        descriptor = -1
        shutil.copyfile(source, temporary)
        with temporary.open("rb") as copied_file:
            os.fsync(copied_file.fileno())

        if (
            _has_sqlite_sidecars(temporary)
            or _file_sha256(temporary) != source_hash
        ):
            raise StageCopyError("stage copy: byte verification failed")
        try:
            with SQLiteStagedArtifactStore(temporary, read_only=True) as store:
                copied_artifact = store.load(staged_change_digest)
        except Exception:
            raise StageCopyError("stage copy: destination stage is invalid") from None
        if copied_artifact != source_artifact:
            raise StageCopyError("stage copy: stage readback mismatch")

        if _has_sqlite_sidecars(source) or _file_sha256(source) != source_hash:
            raise StageCopyError("stage copy: source changed during copy")

        try:
            os.link(temporary, destination)
        except Exception:
            raise StageCopyError("stage copy: no-overwrite publish failed") from None

        destination_hash = _file_sha256(destination)
        if (
            destination_hash != source_hash
            or _has_sqlite_sidecars(source)
            or _file_sha256(source) != source_hash
        ):
            raise StageCopyError("stage copy: final file verification failed")
        with SQLiteStagedArtifactStore(destination, read_only=True) as store:
            final_artifact = store.load(staged_change_digest)
        if final_artifact != source_artifact:
            raise StageCopyError("stage copy: final stage readback failed")
        return {
            "schema": "stage-copy-evidence/v1",
            "status": "copied",
            "staged_change_digest": staged_change_digest,
            "artifact_digest": source_artifact.artifact_digest,
            "database_file_sha256": destination_hash,
            "database_bytes": destination.stat().st_size,
            "overwrite": False,
        }
    except StageCopyError:
        raise
    except Exception:
        raise StageCopyError("stage copy: operation failed") from None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        # Once linked, the destination is evidence and is never removed here.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy one exact verified SQLite stage to a new local evidence path."
    )
    parser.add_argument("source_database")
    parser.add_argument("staged_change_digest")
    parser.add_argument("destination_database")
    args = parser.parse_args(argv)
    try:
        evidence = copy_staged_evidence(
            args.source_database,
            args.staged_change_digest,
            args.destination_database,
        )
    except StageCopyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("stage copy: operation failed", file=sys.stderr)
        return 2
    print(json.dumps(evidence, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
