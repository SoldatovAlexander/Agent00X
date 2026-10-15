from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from app_contracts.executor import ExecutionResult, ExecutionStatus
from app_contracts.r5_attempt_ledger import SQLiteR5AttemptLedger
from app_contracts.r5_execution import R5ExecutionError, R5ExecutionRecord
from scripts.r5_batch_selection import select_first_five_attempts, select_r5_attempts
from scripts.run_r5_preregistered_batch import (
    R5BatchResult,
    _result_digest,
    run_first_five_r5_attempts,
)


ATTEMPTS = ("R5-001", "R5-002", "R5-003", "R5-004", "R5-005")


class R5PreregisteredBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ledger_path = Path(self.temporary.name) / "r5-attempts.sqlite3"
        self.ledger = SQLiteR5AttemptLedger.create(
            self.ledger_path, allowed_attempt_ids=ATTEMPTS
        )
        self.addCleanup(self.ledger.close)
        self.selected = select_first_five_attempts()
        self.calls: list[str] = []

    @staticmethod
    def _collaborators():
        class Worker:
            def propose(self, _input):
                raise AssertionError("fake executor owns the result")

        class Verifier:
            def verify(self, _input):
                raise AssertionError("fake executor owns the result")

        class Sandbox:
            def create(self, *_args, **_kwargs):
                raise AssertionError("fake executor owns the result")

        class Stage:
            def save(self, *_args, **_kwargs):
                raise AssertionError("fake executor owns the result")

            def load(self, *_args, **_kwargs):
                raise AssertionError("fake executor owns the result")

        return Worker(), Verifier(), Sandbox(), Stage()

    def invoke(
        self,
        attempt_executor,
        *,
        worker_factory=None,
        selected_attempts=None,
        continue_after_failed=False,
    ):
        _worker, verifier, sandbox, stage = self._collaborators()
        if worker_factory is None:
            worker_factory = lambda _item: self._collaborators()[0]
        return run_first_five_r5_attempts(
            object(),
            self.ledger,
            worker_factory=worker_factory,
            verifier=verifier,
            sandbox_backend=sandbox,
            stage_sink=stage,
            attempt_executor=attempt_executor,
            selected_attempts=selected_attempts,
            continue_after_failed=continue_after_failed,
        )

    def test_runs_exact_five_in_order_and_records_fixed_outcomes(self) -> None:
        workers = []

        def worker_factory(_item):
            worker = self._collaborators()[0]
            workers.append(worker)
            return worker

        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            terminal_outcomes = {
                "R5-002": ("blocked", "target_test_outcome_unknown"),
                "R5-003": ("denied", "publication_not_authorized"),
                "R5-004": ("clarification_required", "conflicting_requirements"),
            }
            if item.attempt_id in terminal_outcomes:
                terminal_outcome, reason_code = terminal_outcomes[item.attempt_id]
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    worker_terminal_outcome=terminal_outcome,
                    worker_terminal_reason_code=reason_code,
                )
            else:
                result = ExecutionResult(status=ExecutionStatus.VERIFIED)
            return R5ExecutionRecord(item.attempt_id, item.input_digest, result)

        result = self.invoke(execute, worker_factory=worker_factory)
        self.assertIs(type(result), R5BatchResult)
        self.assertEqual(result.status, "complete")
        self.assertEqual(self.calls, list(ATTEMPTS))
        self.assertEqual(len({id(worker) for worker in workers}), 5)
        self.assertEqual(tuple(record.attempt_id for record in result.records), ATTEMPTS)
        self.assertEqual(
            tuple(record.outcome for record in result.records),
            ("verified", "blocked", "denied", "needs_input", "verified"),
        )
        self.assertTrue(all(record.result_digest for record in result.records))
        self.assertTrue(all(self.ledger.get(attempt).state == "COMPLETED" for attempt in ATTEMPTS))

    def test_unknown_exception_spends_id_stops_batch_and_never_retries(self) -> None:
        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            if item.attempt_id == "R5-003":
                raise RuntimeError("do not persist this exception text")
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        result = self.invoke(execute)
        self.assertEqual(result.status, "stopped-unknown")
        self.assertEqual(self.calls, ["R5-001", "R5-002", "R5-003"])
        self.assertEqual(self.ledger.get("R5-003").state, "UNKNOWN")
        self.assertEqual(self.ledger.get("R5-003").reason_code, "pipeline-error")
        self.assertEqual(self.ledger.get("R5-004").state, "PENDING")
        self.assertEqual(self.ledger.get("R5-005").state, "PENDING")
        self.assertNotIn("do not persist", repr(result))

        self.calls.clear()
        resumed = self.invoke(execute)
        self.assertEqual(resumed.status, "stopped-unknown")
        self.assertEqual(self.calls, [])

    def test_r5_phase_error_is_persisted_redacted_and_never_retried(self) -> None:
        marker = "private phase detail"

        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            if item.attempt_id == "R5-001":
                error = R5ExecutionError("executor-contract-invalid")
                error.args = (marker,)
                raise error
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        result = self.invoke(execute)
        self.assertEqual(result.status, "stopped-unknown")
        self.assertEqual(self.calls, ["R5-001"])
        self.assertEqual(self.ledger.get("R5-001").state, "UNKNOWN")
        self.assertEqual(
            self.ledger.get("R5-001").reason_code, "executor-contract-invalid"
        )
        self.assertNotIn(marker, repr(result))
        self.ledger.close()
        self.ledger = SQLiteR5AttemptLedger.open_existing(self.ledger_path)
        self.addCleanup(self.ledger.close)
        self.calls.clear()

        resumed = self.invoke(execute)
        self.assertEqual(resumed.status, "stopped-unknown")
        self.assertEqual(self.calls, [])

    def test_completed_batch_reopen_does_not_repeat_calls(self) -> None:
        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        first = self.invoke(execute)
        self.assertEqual(first.status, "complete")
        self.assertEqual(self.calls, list(ATTEMPTS))
        self.ledger.close()
        self.ledger = SQLiteR5AttemptLedger.open_existing(self.ledger_path)
        self.addCleanup(self.ledger.close)
        self.calls.clear()

        second = self.invoke(execute)
        self.assertEqual(second.status, "complete")
        self.assertEqual(self.calls, [])

    def test_failed_result_stops_before_constructing_or_claiming_later_workers(self) -> None:
        constructed: list[str] = []

        def worker_factory(item):
            constructed.append(item.attempt_id)
            return self._collaborators()[0]

        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(status=ExecutionStatus.FAILED),
            )

        result = self.invoke(execute, worker_factory=worker_factory)
        self.assertEqual(result.status, "stopped-failed")
        self.assertEqual(self.calls, ["R5-001"])
        self.assertEqual(constructed, ["R5-001"])
        self.assertEqual(self.ledger.get("R5-001").state, "COMPLETED")
        self.assertEqual(self.ledger.get("R5-001").outcome, "failed")
        for attempt_id in ATTEMPTS[1:]:
            self.assertEqual(self.ledger.get(attempt_id).state, "PENDING")

        self.calls.clear()
        resumed = self.invoke(execute, worker_factory=worker_factory)
        self.assertEqual(resumed.status, "stopped-failed")
        self.assertEqual(self.calls, [])
        self.assertEqual(constructed, ["R5-001"])

    def test_opt_in_continues_new_ids_after_terminal_failure_without_replay(self) -> None:
        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            failure_code = (
                "target-test-sqlite-range-status"
                if item.attempt_id == "R5-001"
                else None
            )
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(
                    status=(
                        ExecutionStatus.FAILED
                        if failure_code is not None
                        else ExecutionStatus.VERIFIED
                    ),
                    failure_code=failure_code,
                ),
            )

        result = self.invoke(
            execute,
            selected_attempts=self.selected,
            continue_after_failed=True,
        )
        self.assertEqual(result.status, "complete-with-failures")
        self.assertEqual(self.calls, list(ATTEMPTS))
        self.assertEqual(
            self.ledger.get("R5-001").reason_code, "target-test-sqlite-range-status"
        )
        self.assertTrue(
            all(self.ledger.get(attempt_id).state == "COMPLETED" for attempt_id in ATTEMPTS)
        )

        self.calls.clear()
        resumed = self.invoke(
            execute,
            selected_attempts=self.selected,
            continue_after_failed=True,
        )
        self.assertEqual(resumed.status, "complete-with-failures")
        self.assertEqual(self.calls, [])

    def test_continue_after_failed_requires_explicit_selected_ids(self) -> None:
        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        with self.assertRaises(ValueError):
            self.invoke(execute, continue_after_failed=True)
        self.assertEqual(self.calls, [])

    def test_failed_result_persists_only_allowlisted_execution_failure_code(self) -> None:
        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    failure_code="sandbox-create-failed",
                ),
            )

        result = self.invoke(execute)

        self.assertEqual(result.status, "stopped-failed")
        record = self.ledger.get("R5-001")
        self.assertEqual(record.outcome, "failed")
        self.assertEqual(record.reason_code, "sandbox-create-failed")
        self.assertEqual(result.records[0].reason_code, "sandbox-create-failed")
        self.assertEqual(self.ledger.get("R5-002").state, "PENDING")

    def test_invalid_returned_worker_proposal_is_a_fixed_completed_failure(self) -> None:
        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    failure_code="worker-proposal-invalid",
                ),
            )

        result = self.invoke(execute)

        self.assertEqual(result.status, "stopped-failed")
        record = self.ledger.get("R5-001")
        self.assertEqual(record.state, "COMPLETED")
        self.assertEqual(record.outcome, "failed")
        self.assertEqual(record.reason_code, "worker-proposal-invalid")
        self.assertEqual(result.records[0].reason_code, "worker-proposal-invalid")
        self.assertEqual(self.ledger.get("R5-002").state, "PENDING")

    def test_unknown_failure_code_is_redacted_and_uses_generic_reason(self) -> None:
        marker = "private-runtime-detail-not-for-evidence"

        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    failure_code=marker,
                ),
            )

        result = self.invoke(execute)

        self.assertEqual(self.ledger.get("R5-001").reason_code, "execution-failed")
        self.assertNotIn(marker, repr(result))
        self.assertNotIn(marker, repr(self.ledger.records()))

    def test_result_digest_binds_only_the_projected_failure_reason(self) -> None:
        item = self.selected[0]
        sandbox_failure = R5ExecutionRecord(
            item.attempt_id,
            item.input_digest,
            ExecutionResult(
                status=ExecutionStatus.FAILED,
                failure_code="sandbox-create-failed",
            ),
        )
        verifier_failure = R5ExecutionRecord(
            item.attempt_id,
            item.input_digest,
            ExecutionResult(
                status=ExecutionStatus.FAILED,
                failure_code="verifier-failed",
            ),
        )

        self.assertNotEqual(
            _result_digest(sandbox_failure, reason_code="sandbox-create-failed"),
            _result_digest(verifier_failure, reason_code="verifier-failed"),
        )
        with self.assertRaises(ValueError):
            _result_digest(sandbox_failure, reason_code="private-error-detail")

    def test_digest_mismatch_from_executor_becomes_unknown_and_stops(self) -> None:
        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                "sha256:" + "0" * 64,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        result = self.invoke(execute)
        self.assertEqual(result.status, "stopped-unknown")
        self.assertEqual(self.calls, ["R5-001"])
        self.assertEqual(self.ledger.get("R5-001").state, "UNKNOWN")
        self.assertEqual(self.ledger.get("R5-002").state, "PENDING")

    def test_report_repr_contains_no_prompt_or_candidate(self) -> None:
        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        result = self.invoke(execute)
        rendered = repr(result)
        self.assertIn("attempt_count=5", rendered)
        self.assertNotIn("Исправь наблюдаемый", rendered)
        self.assertNotIn("backend/routes.py", rendered)

    def test_reused_single_attempt_worker_is_rejected_before_claim(self) -> None:
        shared_worker = self._collaborators()[0]
        worker_factory = lambda _item: shared_worker

        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        result = self.invoke(execute, worker_factory=worker_factory)
        self.assertEqual(result.status, "stopped-preflight")
        self.assertEqual(self.calls, ["R5-001"])
        self.assertEqual(self.ledger.get("R5-001").state, "COMPLETED")
        self.assertEqual(self.ledger.get("R5-002").state, "PENDING")

    def test_explicit_pending_subset_skips_prior_unknown_without_replaying_it(self) -> None:
        self.ledger.claim("R5-001", self.selected[0].input_digest)
        self.ledger.mark_unknown("R5-001", reason_code="pipeline-error")
        selected = select_r5_attempts(("R5-002", "R5-003"))

        def execute(item, _snapshot, **_kwargs):
            self.calls.append(item.attempt_id)
            return R5ExecutionRecord(
                item.attempt_id,
                item.input_digest,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        result = self.invoke(execute, selected_attempts=selected)
        self.assertEqual(result.status, "complete")
        self.assertEqual(self.calls, ["R5-002", "R5-003"])
        self.assertEqual(self.ledger.get("R5-001").state, "UNKNOWN")
        self.assertEqual(self.ledger.get("R5-001").reason_code, "pipeline-error")
        self.assertEqual(self.ledger.get("R5-004").state, "PENDING")


if __name__ == "__main__":
    unittest.main()
