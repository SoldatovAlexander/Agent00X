"""Create a byte-identical, no-overwrite copy of a quiescent observer journal.

This is local evidence retention only. It does not prove collector completeness,
tamper resistance, cross-host durability, or that the journal contains no
unknown secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from .observation_store import SQLiteObservationStore

_MAX_DATABASE_BYTES = 64 * 1024 * 1024
_RUN_ID = re.compile(r"run-[a-z0-9-]{8,64}\Z")


class ObserverCopyError(ValueError):
    """An observer journal copy could not be safely completed."""


def _has_sidecars(path: Path) -> bool:
    return any(
        candidate.exists() or candidate.is_symlink()
        for candidate in (
            path.with_name(path.name + "-wal"),
            path.with_name(path.name + "-shm"),
        )
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
            or not 0 < path.stat().st_size <= _MAX_DATABASE_BYTES
            or _has_sidecars(path)
        ):
            raise ValueError
        return path
    except Exception:
        raise ObserverCopyError("observer copy: source is unavailable") from None


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
            or not os.access(parent, os.W_OK)
            or path == source
            or _has_sidecars(path)
        ):
            raise ValueError
        return path
    except Exception:
        raise ObserverCopyError("observer copy: destination is unavailable") from None


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
        raise ObserverCopyError("observer copy: file verification failed") from None


def _validated_journal(path: Path, run_id: str) -> tuple[tuple, tuple]:
    try:
        with SQLiteObservationStore(path) as store:
            events = store.events()
            checkpoints = store.checkpoints()
        if (
            not events
            or any(event.get("run_id") != run_id for event in events)
            or [event.get("sequence") for event in events] != list(range(len(events)))
        ):
            raise ValueError
        return events, checkpoints
    except Exception:
        raise ObserverCopyError("observer copy: journal validation failed") from None


def copy_observer_evidence(
    source_database: Path | str,
    run_id: str,
    destination_database: Path | str,
) -> dict:
    """Copy one exact, validated observer run without overwriting evidence."""

    source = _validated_source(source_database)
    destination = _validated_destination(destination_database, source)
    if type(run_id) is not str or _RUN_ID.fullmatch(run_id) is None:
        raise ObserverCopyError("observer copy: run id is invalid")

    source_events, source_checkpoints = _validated_journal(source, run_id)
    source_hash = _file_sha256(source)
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".agent00x-observer-copy-",
            suffix=".sqlite3",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        os.close(descriptor)
        descriptor = -1
        shutil.copyfile(source, temporary)
        with temporary.open("rb") as copied_file:
            os.fsync(copied_file.fileno())

        if _has_sidecars(temporary) or _file_sha256(temporary) != source_hash:
            raise ObserverCopyError("observer copy: byte verification failed")
        copied_events, copied_checkpoints = _validated_journal(temporary, run_id)
        if (copied_events, copied_checkpoints) != (source_events, source_checkpoints):
            raise ObserverCopyError("observer copy: journal readback mismatch")
        if _has_sidecars(source) or _file_sha256(source) != source_hash:
            raise ObserverCopyError("observer copy: source changed during copy")

        try:
            os.link(temporary, destination)
        except Exception:
            raise ObserverCopyError("observer copy: no-overwrite publish failed") from None

        if _has_sidecars(destination) or _file_sha256(destination) != source_hash:
            raise ObserverCopyError("observer copy: final file verification failed")
        final_events, final_checkpoints = _validated_journal(destination, run_id)
        if (final_events, final_checkpoints) != (source_events, source_checkpoints):
            raise ObserverCopyError("observer copy: final journal readback failed")
        return {
            "schema": "observer-copy-evidence/v1",
            "status": "copied",
            "run_id": run_id,
            "event_count": len(source_events),
            "checkpoint_count": len(source_checkpoints),
            "database_file_sha256": source_hash,
            "database_bytes": destination.stat().st_size,
            "overwrite": False,
        }
    except ObserverCopyError:
        raise
    except Exception:
        raise ObserverCopyError("observer copy: operation failed") from None
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy one exact observer run to a new local evidence path."
    )
    parser.add_argument("source_database")
    parser.add_argument("run_id")
    parser.add_argument("destination_database")
    args = parser.parse_args(argv)
    try:
        evidence = copy_observer_evidence(
            args.source_database, args.run_id, args.destination_database
        )
    except ObserverCopyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("observer copy: operation failed", file=sys.stderr)
        return 2
    print(json.dumps(evidence, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
