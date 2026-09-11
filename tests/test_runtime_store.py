from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.runtime_store import ProcessNotFound, SQLiteProcessStore, VersionConflict
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

    def test_naive_timestamps_rejected_before_any_write(self):
        naive = datetime(2026, 9, 4, 12, 0)
        with SQLiteProcessStore(self.database) as store:
            with self.assertRaisesRegex(ContractValidationError, "timezone-aware") as raised:
                store.create("process-durable-009", now=naive)
            self.assertNotIn("2026-09-04", str(raised.exception))
            with self.assertRaises(ProcessNotFound):
                store.get("process-durable-009")
            store.create("process-durable-009")
            with self.assertRaises(ContractValidationError):
                store.advance(
                    "process-durable-009", ProcessState.SPECIFIED,
                    TransitionEvidence(contract_complete=True), expected_version=0, now=naive,
                )
            with self.assertRaises(ContractValidationError):
                store.append_audit_event(
                    "process-durable-009", actor_id="agent-worker-001",
                    event_type="gateway.request", input_digest="sha256:" + "e" * 64,
                    result="denied", reason_codes=("write-or-unknown-denied",), now=naive,
                )
            self.assertEqual(store.get("process-durable-009").version, 0)
            self.assertEqual(len(store.events("process-durable-009")), 1)
            self.assertEqual(store.audit_events("process-durable-009"), [])

    def test_aware_non_utc_timestamp_is_accepted(self):
        tz = timezone(timedelta(hours=3))
        with SQLiteProcessStore(self.database) as store:
            record = store.create("process-durable-010", now=datetime(2026, 9, 4, 12, 0, tzinfo=tz))
            self.assertTrue(record.updated_at.endswith("Z"))

    def test_readback_mutation_cannot_alter_event_history(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-011")
            store.advance(
                "process-durable-011",
                ProcessState.SPECIFIED,
                TransitionEvidence(contract_complete=True),
                expected_version=0,
            )
            first_read = store.events("process-durable-011")
            first_read[1]["evidence"]["contract_complete"] = False
            first_read[1]["evidence"]["forged"] = True
            first_read[1]["state"] = "failed"
            second_read = store.events("process-durable-011")
            self.assertTrue(second_read[1]["evidence"]["contract_complete"])
            self.assertNotIn("forged", second_read[1]["evidence"])
            self.assertEqual(second_read[1]["state"], "specified")
            self.assertEqual([event["sequence"] for event in second_read], [0, 1])
            with self.assertRaises(InvalidTransition) as raised:
                store.advance(
                    "process-durable-011",
                    ProcessState.APPLYING,
                    TransitionEvidence(),
                    expected_version=1,
                )
            self.assertNotIn("contract_complete", str(raised.exception))

    def test_audit_records_are_isolated_per_process(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-012")
            store.create("process-durable-013")
            store.append_audit_event(
                "process-durable-012", actor_id="agent-worker-001",
                event_type="gateway.request", input_digest="sha256:" + "a" * 64,
                result="allowed", reason_codes=("internal-read-only",),
            )
            store.append_audit_event(
                "process-durable-013", actor_id="agent-worker-002",
                event_type="gateway.request", input_digest="sha256:" + "b" * 64,
                result="denied", reason_codes=("write-or-unknown-denied",),
            )
            store.append_audit_event(
                "process-durable-012", actor_id="agent-worker-001",
                event_type="gateway.request", input_digest="sha256:" + "c" * 64,
                result="denied", reason_codes=("tainted-content",),
            )
            own = store.audit_events("process-durable-012")
            self.assertEqual([event["input_digest"] for event in own], ["sha256:" + "a" * 64, "sha256:" + "c" * 64])
            self.assertTrue(all(event["actor_id"] == "agent-worker-001" for event in own))
            other = store.audit_events("process-durable-013")
            self.assertEqual(len(other), 1)
            self.assertNotIn("sha256:" + "b" * 64, [event["input_digest"] for event in own])
            with self.assertRaises(ProcessNotFound):
                store.audit_events("process-unknown-999")
            with self.assertRaises(ProcessNotFound):
                store.events("process-unknown-999")

    def test_malformed_reason_batches_leave_history_untouched(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-014")
            store.append_audit_event(
                "process-durable-014", actor_id="agent-worker-001",
                event_type="gateway.request", input_digest="sha256:" + "a" * 64,
                result="allowed", reason_codes=("internal-read-only",),
            )
            baseline = store.audit_events("process-durable-014")
            malformed = (
                (["nested"],),
                ({"code": "denied"},),
                (b"bytes",),
                (True,),
                ("ok", 42),
            )
            for codes in malformed:
                with self.subTest(codes=type(codes[0]).__name__):
                    with self.assertRaises(ContractValidationError):
                        store.append_audit_event(
                            "process-durable-014", actor_id="agent-worker-001",
                            event_type="gateway.request", input_digest="sha256:" + "b" * 64,
                            result="denied", reason_codes=codes,
                        )
            self.assertEqual(store.audit_events("process-durable-014"), baseline)
            readable = store.audit_events("process-durable-014")[0]
            self.assertEqual(readable["reason_codes"], ["internal-read-only"])
            self.assertEqual(readable["result"], "allowed")

    def test_malformed_expected_version_rejects_without_mutation(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-015")
            for bad in (True, False, 1.0, "0", None, -1):
                with self.subTest(version=bad):
                    with self.assertRaisesRegex(VersionConflict, "expected version"):
                        store.advance(
                            "process-durable-015",
                            ProcessState.SPECIFIED,
                            TransitionEvidence(contract_complete=True),
                            expected_version=bad,
                        )
            record = store.get("process-durable-015")
            self.assertEqual((record.state, record.version), (ProcessState.RECEIVED, 0))
            self.assertEqual(len(store.events("process-durable-015")), 1)
            advanced = store.advance(
                "process-durable-015",
                ProcessState.SPECIFIED,
                TransitionEvidence(contract_complete=True),
                expected_version=0,
            )
            self.assertEqual((advanced.state, advanced.version), (ProcessState.SPECIFIED, 1))
            self.assertEqual(len(store.events("process-durable-015")), 2)

    def test_malformed_process_id_creates_no_record(self):
        with SQLiteProcessStore(self.database) as store:
            for bad in (None, 123, "", ["process-durable-016"]):
                with self.subTest(process_id=type(bad).__name__):
                    with self.assertRaisesRegex(
                        ContractValidationError, "^runtime: process ID is invalid$"
                    ):
                        store.create(bad)
            with self.assertRaises(ProcessNotFound):
                store.get("process-durable-016")
            record = store.create("process-durable-016")
            self.assertEqual(record.version, 0)

    def test_malformed_audit_fields_denied_without_mutation(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-017")
            cases = (
                {"actor_id": None}, {"actor_id": ""},
                {"event_type": 123}, {"input_digest": None},
                {"result": []}, {"result": ""},
            )
            for override in cases:
                with self.subTest(override=override):
                    kwargs = {
                        "actor_id": "agent-worker-001",
                        "event_type": "gateway.request",
                        "input_digest": "sha256:" + "a" * 64,
                        "result": "denied",
                    }
                    kwargs.update(override)
                    with self.assertRaisesRegex(
                        ContractValidationError, "^audit: event field is invalid$"
                    ):
                        store.append_audit_event(
                            "process-durable-017", reason_codes=("denied",), **kwargs
                        )
            self.assertEqual(store.audit_events("process-durable-017"), [])

    def test_non_sequence_reason_containers_denied_without_history_change(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-018")
            containers = (
                {"code": "denied"},
                {"denied"},
                frozenset({"denied"}),
                (code for code in ("denied",)),
            )
            for codes in containers:
                with self.subTest(container=type(codes).__name__):
                    with self.assertRaises(ContractValidationError):
                        store.append_audit_event(
                            "process-durable-018", actor_id="agent-worker-001",
                            event_type="gateway.request", input_digest="sha256:" + "a" * 64,
                            result="denied", reason_codes=codes,
                        )
            self.assertEqual(store.audit_events("process-durable-018"), [])

    def test_malformed_lookup_id_denied_on_all_read_paths(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-019")
            for bad in (None, 123, "", ["process-durable-019"]):
                with self.subTest(process_id=type(bad).__name__):
                    for read in (
                        store.get,
                        store.events,
                        store.audit_events,
                    ):
                        with self.assertRaisesRegex(
                            ContractValidationError, "^runtime: process ID is invalid$"
                        ):
                            read(bad)
            with self.assertRaises(ProcessNotFound):
                store.get("process-absent-001")
            with self.assertRaises(ProcessNotFound):
                store.events("process-absent-001")
            with self.assertRaises(ProcessNotFound):
                store.audit_events("process-absent-001")
            self.assertEqual(store.get("process-durable-019").version, 0)

    def test_event_table_rejects_update_and_delete(self):
        with SQLiteProcessStore(self.database) as store:
            store.create("process-durable-004")
            with self.assertRaises(sqlite3.IntegrityError):
                store._connection.execute("UPDATE process_events SET state = 'failed'")


if __name__ == "__main__":
    unittest.main()
