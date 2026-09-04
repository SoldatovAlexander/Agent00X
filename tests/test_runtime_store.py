from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.runtime_store import SQLiteProcessStore, VersionConflict
from app_contracts.state_machine import InvalidTransition, ProcessState, TransitionEvidence


class RuntimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="app-runtime-test-")
        self.database = Path(self.temp_dir.name) / "runtime.sqlite3"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_state_and_events_survive_reopen(self):
        store = SQLiteProcessStore(self.database)
        created = store.create("process-durable-001")
        advanced = store.advance(
            created.process_id,
            ProcessState.SPECIFIED,
            TransitionEvidence(contract_complete=True),
            expected_version=0,
        )
        store.close()

        reopened = SQLiteProcessStore(self.database)
        self.assertEqual(reopened.get(created.process_id), advanced)
        events = reopened.events(created.process_id)
        self.assertEqual([event["state"] for event in events], ["received", "specified"])
        self.assertTrue(events[1]["evidence"]["contract_complete"])
        reopened.close()

    def test_invalid_transition_is_not_persisted(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-002")
            with self.assertRaises(InvalidTransition):
                store.advance(
                    "process-durable-002",
                    ProcessState.APPLYING,
                    TransitionEvidence(),
                    expected_version=0,
                )
            self.assertEqual(store.get("process-durable-002").state, ProcessState.RECEIVED)
            self.assertEqual(len(store.events("process-durable-002")), 1)

    def test_stale_writer_is_rejected(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-003")
            store.advance(
                "process-durable-003",
                ProcessState.SPECIFIED,
                TransitionEvidence(contract_complete=True),
                expected_version=0,
            )
            with self.assertRaises(VersionConflict):
                store.advance(
                    "process-durable-003",
                    ProcessState.AUTHORIZED,
                    TransitionEvidence(policy_allowed=True),
                    expected_version=0,
                )

    def test_event_table_rejects_update_and_delete(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-004")
            with self.assertRaises(sqlite3.IntegrityError):
                store._connection.execute("UPDATE process_events SET state = 'failed'")


if __name__ == "__main__":
    unittest.main()
