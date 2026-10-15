from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.observation_store import SQLiteObservationStore
from app_contracts.observer_copy import (
    ObserverCopyError,
    copy_observer_evidence,
    main,
)


def _event(event_id: str, sequence: int) -> dict:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "tool_requested",
        "process_id": "process-observer-copy",
        "run_id": "run-observer-copy-001",
        "branch_id": "branch-main",
        "task_id": "task-observer-copy",
        "agent_id": "agent-worker",
        "sequence": sequence,
        "occurred_at": "2026-10-12T12:00:00Z",
        "recorded_at": "2026-10-12T12:00:01Z",
        "classification": "internal",
        "redaction_status": "complete",
    }


def _checkpoint() -> dict:
    return {
        "schema_version": 1,
        "checkpoint_id": "checkpoint-observer-copy-001",
        "kind": "tool_call",
        "process_id": "process-observer-copy",
        "run_id": "run-observer-copy-001",
        "branch_id": "branch-main",
        "agent_id": "agent-worker",
        "trigger_event_id": "event-observer-copy-001",
        "event_cursor": 0,
        "state_ref": "artifact://states/observer-copy-001",
        "completeness": "complete",
        "restore_mode": "simulation",
        "created_at": "2026-10-12T12:00:02Z",
    }


class ObserverCopyTests(unittest.TestCase):
    run_id = "run-observer-copy-001"

    def _source(self, root: Path) -> tuple[Path, bytes]:
        source = root / "source.sqlite3"
        with SQLiteObservationStore(source) as store:
            store.append(_event("event-observer-copy-001", 0))
            store.record_checkpoint(_checkpoint())
            store.append(_event("event-observer-copy-002", 1))
        return source, source.read_bytes()

    def test_copy_is_exact_no_overwrite_and_reopens_same_run(self):
        with tempfile.TemporaryDirectory(prefix="observer-copy-success-") as temporary:
            root = Path(temporary).resolve()
            source, source_bytes = self._source(root)
            destination = root / "retained.sqlite3"

            evidence = copy_observer_evidence(source, self.run_id, destination)

            self.assertEqual(destination.read_bytes(), source_bytes)
            self.assertEqual(evidence["schema"], "observer-copy-evidence/v1")
            self.assertEqual(evidence["status"], "copied")
            self.assertEqual(evidence["run_id"], self.run_id)
            self.assertEqual(evidence["event_count"], 2)
            self.assertEqual(evidence["checkpoint_count"], 1)
            self.assertEqual(
                evidence["database_file_sha256"], hashlib.sha256(source_bytes).hexdigest()
            )
            self.assertEqual(evidence["database_bytes"], len(source_bytes))
            self.assertFalse(evidence["overwrite"])
            with SQLiteObservationStore(destination) as reopened:
                self.assertEqual(len(reopened.events()), 2)
                self.assertEqual(reopened.checkpoints(), (_checkpoint(),))

    def test_invalid_run_existing_destination_and_sidecars_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="observer-copy-invalid-") as temporary:
            root = Path(temporary).resolve()
            source, source_bytes = self._source(root)
            destination = root / "retained.sqlite3"
            with self.assertRaisesRegex(ObserverCopyError, "run id is invalid"):
                copy_observer_evidence(source, "wrong-run", destination)
            destination.write_bytes(b"preserve")
            with self.assertRaisesRegex(ObserverCopyError, "destination is unavailable"):
                copy_observer_evidence(source, self.run_id, destination)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(destination.read_bytes(), b"preserve")
            destination.unlink()
            source.with_name(source.name + "-wal").write_bytes(b"active")
            with self.assertRaisesRegex(ObserverCopyError, "source is unavailable"):
                copy_observer_evidence(source, self.run_id, destination)
            self.assertFalse(destination.exists())

    def test_journal_with_foreign_run_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory(prefix="observer-copy-foreign-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            with SQLiteObservationStore(source) as store:
                store.append(_event("event-observer-copy-001", 0))
            with self.assertRaisesRegex(ObserverCopyError, "journal validation failed"):
                copy_observer_evidence(source, "run-another-run-001", root / "copy.sqlite3")
            self.assertFalse((root / "copy.sqlite3").exists())

    def test_copy_failure_redacts_exception_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory(prefix="observer-copy-redaction-") as temporary:
            root = Path(temporary).resolve()
            source, _ = self._source(root)
            destination = root / "retained.sqlite3"
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch(
                "app_contracts.observer_copy.shutil.copyfile",
                side_effect=OSError("secret=PRIVATE-CANARY"),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                status = main([str(source), self.run_id, str(destination)])
            self.assertEqual(status, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "observer copy: operation failed\n")
            self.assertNotIn("PRIVATE-CANARY", stderr.getvalue())
            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".agent00x-observer-copy-*.sqlite3")), [])

    def test_cli_emits_fixed_metadata_without_local_paths_or_event_payload(self):
        with tempfile.TemporaryDirectory(prefix="observer-copy-cli-") as temporary:
            root = Path(temporary).resolve()
            source, _ = self._source(root)
            destination = root / "retained.sqlite3"
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = main([str(source), self.run_id, str(destination)])
            self.assertEqual(status, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertNotIn(str(source), stdout.getvalue())
            self.assertNotIn(str(destination), stdout.getvalue())
            self.assertNotIn("event-observer-copy-001", stdout.getvalue())
            self.assertEqual(json.loads(stdout.getvalue())["run_id"], self.run_id)


if __name__ == "__main__":
    unittest.main()
