from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import sqlite3
import unittest

from app_contracts.r5_attempt_ledger import (
    R5AttemptLedgerError,
    SQLiteR5AttemptLedger,
)
from app_contracts.repository_process import SAFE_TARGET_TEST_FAILURE_CODES


ATTEMPTS = ("R5-001", "R5-002", "R5-003", "R5-004", "R5-005")
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class R5AttemptLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "attempts.sqlite3"

    def create(self) -> SQLiteR5AttemptLedger:
        return SQLiteR5AttemptLedger.create(
            self.path, allowed_attempt_ids=ATTEMPTS
        )

    def test_claim_is_committed_then_completes_once_without_raw_content(self) -> None:
        with self.create() as ledger:
            ledger.claim("R5-001", DIGEST_A)
            self.assertEqual(ledger.get("R5-001").state, "CLAIMED")
            ledger.complete(
                "R5-001", result_digest=DIGEST_B, outcome="verified"
            )
            record = ledger.get("R5-001")
            self.assertEqual(record.state, "COMPLETED")
            self.assertEqual(record.input_digest, DIGEST_A)
            self.assertEqual(record.result_digest, DIGEST_B)
            self.assertEqual(record.outcome, "verified")
            self.assertEqual(record.reason_code, "none")
            rendered = repr(ledger.records())
            self.assertNotIn("prompt", rendered.lower())
            self.assertNotIn("response", rendered.lower())

        reopened = SQLiteR5AttemptLedger.open_existing(self.path)
        with reopened:
            self.assertEqual(reopened.get("R5-001").state, "COMPLETED")
            with self.assertRaises(R5AttemptLedgerError):
                reopened.claim("R5-001", DIGEST_A)

    def test_claim_survives_reopen_as_spent_if_process_stops(self) -> None:
        ledger = self.create()
        ledger.claim("R5-002", DIGEST_A)
        ledger.close()

        reopened = SQLiteR5AttemptLedger.open_existing(self.path)
        with reopened:
            self.assertEqual(reopened.get("R5-002").state, "CLAIMED")
            with self.assertRaises(R5AttemptLedgerError):
                reopened.claim("R5-002", DIGEST_A)
            reopened.mark_unknown("R5-002", reason_code="interrupted")
            self.assertEqual(reopened.get("R5-002").state, "UNKNOWN")
            with self.assertRaises(R5AttemptLedgerError):
                reopened.complete(
                    "R5-002", result_digest=DIGEST_B, outcome="verified"
                )

    def test_event_history_is_append_only(self) -> None:
        with self.create() as ledger:
            ledger.claim("R5-001", DIGEST_A)
            ledger.complete(
                "R5-001", result_digest=DIGEST_B, outcome="verified"
            )
        connection = sqlite3.connect(self.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE attempts SET attempt_id='R5-002' WHERE attempt_id='R5-001'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM attempt_events")
        finally:
            connection.close()

    def test_unknown_requires_claim_and_fixed_reason(self) -> None:
        with self.create() as ledger:
            with self.assertRaises(R5AttemptLedgerError):
                ledger.mark_unknown("R5-003", reason_code="interrupted")
            ledger.claim("R5-003", DIGEST_A)
            with self.assertRaises(R5AttemptLedgerError):
                ledger.mark_unknown("R5-003", reason_code="raw exception text")
            ledger.mark_unknown(
                "R5-003", reason_code="result-unavailable", result_digest=DIGEST_B
            )
            self.assertEqual(ledger.get("R5-003").reason_code, "result-unavailable")

    def test_unknown_accepts_only_fixed_redacted_phase_codes(self) -> None:
        phase_codes = (
            "input-validation-error",
            "executor-uncaught-error",
            "result-validation-error",
            "executor-request-rejected",
            "executor-worker-rejected",
            "executor-sandbox-rejected",
            "executor-snapshot-rejected",
            "executor-preparation-rejected",
            "executor-verifier-rejected",
            "executor-stage-rejected",
            "executor-marker-unmapped",
            "executor-value-error",
            "executor-type-error",
            "executor-os-error",
            "executor-runtime-error",
            "executor-key-error",
            "executor-attribute-error",
            "executor-workspace-error",
            "executor-contract-invalid",
            "executor-test-result-malformed",
        )
        with self.create() as ledger:
            ledger.extend_allowed_attempt_ids(
                tuple(
                    f"R5-{number:03d}"
                    for number in range(6, 6 + len(phase_codes) + 1)
                )
            )
            phase_attempts = ATTEMPTS + tuple(
                f"R5-{number:03d}"
                for number in range(6, 6 + len(phase_codes) - len(ATTEMPTS))
            )
            for attempt_id, reason_code in zip(phase_attempts, phase_codes):
                ledger.claim(attempt_id, DIGEST_A)
                ledger.mark_unknown(attempt_id, reason_code=reason_code)
                self.assertEqual(ledger.get(attempt_id).state, "UNKNOWN")
                self.assertEqual(ledger.get(attempt_id).reason_code, reason_code)
            invalid_attempt = f"R5-{6 + len(phase_codes) - len(ATTEMPTS):03d}"
            ledger.claim(invalid_attempt, DIGEST_A)
            with self.assertRaises(R5AttemptLedgerError):
                ledger.mark_unknown(invalid_attempt, reason_code="private exception text")

    def test_completed_execution_failure_accepts_allowlisted_safe_reason(self) -> None:
        with self.create() as ledger:
            ledger.claim("R5-001", DIGEST_A)
            ledger.complete(
                "R5-001",
                result_digest=DIGEST_B,
                outcome="failed",
                reason_code="target-tests-failed",
            )
            self.assertEqual(
                ledger.get("R5-001").reason_code, "target-tests-failed"
            )
            with self.assertRaises(R5AttemptLedgerError):
                ledger.complete(
                    "R5-002",
                    result_digest=DIGEST_B,
                    outcome="failed",
                    reason_code="unbounded-private-detail",
                )

    def test_target_test_reason_codes_are_fixed_completed_failure_reasons(self) -> None:
        base_reasons = (
            "target-tests-failed",
            "target-test-readiness-exit",
            "target-test-readiness-timeout",
            "target-test-malformed-status",
            "target-test-malformed-no-write",
            "target-test-overflow-status",
            "target-test-overflow-no-write",
            "target-test-sqlite-range-status",
            "target-test-sqlite-range-no-write",
            "target-test-valid-status",
            "target-test-valid-body",
            "target-test-valid-row",
        )
        reasons = base_reasons + tuple(
            sorted(SAFE_TARGET_TEST_FAILURE_CODES - set(base_reasons))
        )
        with self.create() as ledger:
            additional_ids = tuple(
                f"R5-{number:03d}" for number in range(6, 6 + len(reasons))
            )
            ledger.extend_allowed_attempt_ids(additional_ids)
            for attempt_id, reason_code in zip(additional_ids, reasons):
                ledger.claim(attempt_id, DIGEST_A)
                ledger.complete(
                    attempt_id,
                    result_digest=DIGEST_B,
                    outcome="failed",
                    reason_code=reason_code,
                )
                self.assertEqual(ledger.get(attempt_id).reason_code, reason_code)

    def test_only_exact_first_five_can_be_enrolled(self) -> None:
        with self.assertRaises(R5AttemptLedgerError):
            SQLiteR5AttemptLedger.create(
                self.path, allowed_attempt_ids=("R5-001", "R5-002")
            )
        self.assertFalse(self.path.exists())

    def test_extension_appends_later_ids_without_changing_terminal_history(self) -> None:
        ledger = self.create()
        ledger.claim("R5-001", DIGEST_A)
        ledger.mark_unknown("R5-001", reason_code="pipeline-error")
        before = ledger._connection.execute(
            "SELECT event_id,attempt_id,state,input_digest,result_digest,outcome,reason_code "
            "FROM attempt_events ORDER BY event_id"
        ).fetchall()
        additions = tuple(f"R5-{number:03d}" for number in range(6, 101))

        updated = ledger.extend_allowed_attempt_ids(additions)

        self.assertEqual(len(updated), 100)
        self.assertEqual(updated[:5], ATTEMPTS)
        self.assertEqual(updated[5:], additions)
        self.assertEqual(ledger.get("R5-001").state, "UNKNOWN")
        self.assertEqual(ledger.get("R5-001").reason_code, "pipeline-error")
        self.assertEqual(ledger.get("R5-002").state, "PENDING")
        self.assertEqual(ledger.get("R5-100").state, "PENDING")
        after = ledger._connection.execute(
            "SELECT event_id,attempt_id,state,input_digest,result_digest,outcome,reason_code "
            "FROM attempt_events ORDER BY event_id"
        ).fetchall()
        self.assertEqual(after, before)
        ledger.close()

        reopened = SQLiteR5AttemptLedger.open_existing(self.path)
        with reopened:
            self.assertEqual(len(reopened.records()), 100)
            with self.assertRaises(R5AttemptLedgerError):
                reopened.claim("R5-001", DIGEST_B)

    def test_extension_rejects_overlap_earlier_and_noncanonical_ids_atomically(self) -> None:
        with self.create() as ledger:
            for invalid in (
                ("R5-005",),
                ("R5-004", "R5-006"),
                ("R5-007", "R5-006"),
                ("R5-101",),
            ):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(R5AttemptLedgerError):
                        ledger.extend_allowed_attempt_ids(invalid)
            self.assertEqual(tuple(record.attempt_id for record in ledger.records()), ATTEMPTS)

    def test_duplicate_and_malformed_claims_are_rejected(self) -> None:
        with self.create() as ledger:
            with self.assertRaises(R5AttemptLedgerError):
                ledger.claim("R5-101", DIGEST_A)
            with self.assertRaises(R5AttemptLedgerError):
                ledger.claim("R5-001", "not-a-digest")
            ledger.claim("R5-004", DIGEST_A)
            with self.assertRaises(R5AttemptLedgerError):
                ledger.claim("R5-004", DIGEST_A)

    def test_existing_destination_and_symlink_are_not_overwritten(self) -> None:
        self.path.write_bytes(b"preserve")
        with self.assertRaises(R5AttemptLedgerError):
            self.create()
        self.assertEqual(self.path.read_bytes(), b"preserve")

        link = Path(self.temporary.name) / "linked.sqlite3"
        target = Path(self.temporary.name) / "target.sqlite3"
        target.write_bytes(b"preserve-target")
        link.symlink_to(target)
        with self.assertRaises(R5AttemptLedgerError):
            SQLiteR5AttemptLedger.create(link, allowed_attempt_ids=ATTEMPTS)
        self.assertEqual(target.read_bytes(), b"preserve-target")

    def test_concurrent_claim_has_exactly_one_winner(self) -> None:
        first = self.create()
        second = SQLiteR5AttemptLedger.open_existing(self.path)
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def claim(ledger: SQLiteR5AttemptLedger) -> None:
            barrier.wait()
            try:
                ledger.claim("R5-005", DIGEST_A)
                result = "claimed"
            except R5AttemptLedgerError:
                result = "rejected"
            with lock:
                outcomes.append(result)

        workers = [
            threading.Thread(target=claim, args=(first,)),
            threading.Thread(target=claim, args=(second,)),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
        first.close()
        second.close()

        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertCountEqual(outcomes, ["claimed", "rejected"])
        with SQLiteR5AttemptLedger.open_existing(self.path) as reopened:
            self.assertEqual(reopened.get("R5-005").state, "CLAIMED")


if __name__ == "__main__":
    unittest.main()
