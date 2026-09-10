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
from app_contracts.validator import ContractValidationError


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

    def test_stale_writer_leaves_no_partial_state_or_audit(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-005")
            store.append_audit_event(
                "process-durable-005", actor_id="agent-worker-001", event_type="decision_proposed",
                input_digest="sha256:" + "a" * 64, result="recorded", reason_codes=("recorded",),
            )
            store.advance(
                "process-durable-005",
                ProcessState.SPECIFIED,
                TransitionEvidence(contract_complete=True),
                expected_version=0,
            )
            events_before = store.events("process-durable-005")
            audit_before = store.audit_events("process-durable-005")
            with self.assertRaises(VersionConflict):
                store.advance(
                    "process-durable-005",
                    ProcessState.AUTHORIZED,
                    TransitionEvidence(policy_allowed=True),
                    expected_version=0,
                )
            record = store.get("process-durable-005")
            self.assertEqual((record.state, record.version), (ProcessState.SPECIFIED, 1))
            self.assertEqual(store.events("process-durable-005"), events_before)
            self.assertEqual(store.audit_events("process-durable-005"), audit_before)
            advanced = store.advance(
                "process-durable-005",
                ProcessState.AUTHORIZED,
                TransitionEvidence(policy_allowed=True),
                expected_version=1,
            )
            self.assertEqual((advanced.state, advanced.version), (ProcessState.AUTHORIZED, 2))
            self.assertEqual(
                [event["sequence"] for event in store.events("process-durable-005")], [0, 1, 2]
            )
            self.assertEqual(store.audit_events("process-durable-005"), audit_before)

    def test_caller_mutation_does_not_alter_stored_audit_event(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-006")
            reason_codes = ["recorded", "slow-path"]
            store.append_audit_event(
                "process-durable-006", actor_id="agent-worker-001", event_type="decision_proposed",
                input_digest="sha256:" + "b" * 64, result="recorded", reason_codes=reason_codes,
            )
            reason_codes.append("forged-after-write")
            reason_codes[0] = "rewritten"
            first_read = store.audit_events("process-durable-006")
            self.assertEqual(first_read[0]["reason_codes"], ["recorded", "slow-path"])
            first_read[0]["reason_codes"].append("forged-after-read")
            first_read[0]["actor_id"] = "rewritten"
            second_read = store.audit_events("process-durable-006")
            self.assertEqual(second_read[0]["reason_codes"], ["recorded", "slow-path"])
            self.assertEqual(second_read[0]["actor_id"], "agent-worker-001")

    def test_malformed_reason_codes_rejected_without_audit_write(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-007")
            for bad in (({"nested": "caller-value-001"},), (42,), (None,), (), ("x" * 129,)):
                with self.subTest(codes=bad):
                    with self.assertRaisesRegex(
                        ContractValidationError, "reason code is invalid"
                    ) as raised:
                        store.append_audit_event(
                            "process-durable-007", actor_id="agent-worker-001",
                            event_type="gateway.request", input_digest="sha256:" + "c" * 64,
                            result="denied", reason_codes=bad,
                        )
                    self.assertNotIn("caller-value-001", str(raised.exception))
            self.assertEqual(store.audit_events("process-durable-007"), [])
            store.append_audit_event(
                "process-durable-007", actor_id="agent-worker-001",
                event_type="gateway.request", input_digest="sha256:" + "c" * 64,
                result="denied", reason_codes=["write-or-unknown-denied"],
            )
            self.assertEqual(
                store.audit_events("process-durable-007")[0]["reason_codes"],
                ["write-or-unknown-denied"],
            )

    def test_tuple_reason_codes_are_stored_detached(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-008")
            store.append_audit_event(
                "process-durable-008", actor_id="agent-worker-001",
                event_type="gateway.request", input_digest="sha256:" + "d" * 64,
                result="allowed", reason_codes=("internal-read-only",),
            )
            first_read = store.audit_events("process-durable-008")
            self.assertEqual(first_read[0]["reason_codes"], ["internal-read-only"])
            first_read[0]["reason_codes"].append("forged-after-read")
            self.assertEqual(
                store.audit_events("process-durable-008")[0]["reason_codes"],
                ["internal-read-only"],
            )
            with self.assertRaises(ContractValidationError):
                store.append_audit_event(
                    "process-durable-008", actor_id="agent-worker-001",
                    event_type="gateway.request", input_digest="sha256:" + "d" * 64,
                    result="denied", reason_codes="not-a-sequence",
                )
            self.assertEqual(len(store.audit_events("process-durable-008")), 1)

    def test_event_table_rejects_update_and_delete(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-004")
            with self.assertRaises(sqlite3.IntegrityError):
                store._connection.execute("UPDATE process_events SET state = 'failed'")


if __name__ == "__main__":
    unittest.main()
