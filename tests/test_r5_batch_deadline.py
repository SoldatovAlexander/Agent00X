from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from app_contracts.executor import ExecutionResult, ExecutionStatus
from app_contracts.brainbooster_target_profile import PINNED_CONTENT_DIGEST, PINNED_TREE
from app_contracts.r5_attempt_ledger import SQLiteR5AttemptLedger
from app_contracts.r5_execution import R5ExecutionRecord
from scripts import run_r5_batch_cli
from scripts.r5_batch_selection import select_first_five_attempts
from scripts.run_r5_preregistered_batch import run_first_five_r5_attempts
from scripts.run_r5_batch_cli import (
    MAX_R5_BATCH_SECONDS,
    R5BatchDeadlineExceeded,
    _DeadlineWorkerFactory,
    _batch_deadline,
    _print_summary,
    _require_deadline_support,
)
from app_contracts.r5_local_model_preflight import R5LocalModelMetadata


class _FakeSignalAPI:
    SIGALRM = 14
    ITIMER_REAL = 0

    def __init__(self):
        self.handler = "prior-handler"
        self.timer = (0.0, 0.0)
        self.timer_calls: list[tuple[int, float]] = []

    def getitimer(self, _which):
        return self.timer

    def setitimer(self, which, value):
        self.timer_calls.append((which, value))
        self.timer = (value, 0.0)

    def getsignal(self, _signum):
        return self.handler

    def signal(self, _signum, handler):
        old = self.handler
        self.handler = handler
        return old


class R5BatchDeadlineTests(unittest.TestCase):
    def _ledger(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        ledger = SQLiteR5AttemptLedger.create(
            Path(temporary.name) / "attempts.sqlite3",
            allowed_attempt_ids=tuple(
                item.attempt_id for item in select_first_five_attempts()
            ),
        )
        self.addCleanup(ledger.close)
        return ledger

    @staticmethod
    def _collaborators():
        class Worker:
            def propose(self, _input):
                return None

        class Verifier:
            def verify(self, _input):
                return None

        class Sandbox:
            def create(self, *_args, **_kwargs):
                return None

        class Stage:
            def save(self, *_args, **_kwargs):
                return None

            def load(self, *_args, **_kwargs):
                return None

        return Worker(), Verifier(), Sandbox(), Stage()

    def _run_coordinator(self, ledger, worker_factory, attempt_executor):
        _worker, verifier, sandbox, stage = self._collaborators()
        return run_first_five_r5_attempts(
            object(), ledger,
            worker_factory=worker_factory,
            verifier=verifier,
            sandbox_backend=sandbox,
            stage_sink=stage,
            attempt_executor=attempt_executor,
        )

    def test_deadline_is_finite_and_timer_is_always_disarmed_and_restored(self):
        self.assertEqual(MAX_R5_BATCH_SECONDS, 2_400)
        api = _FakeSignalAPI()
        with self.assertRaises(R5BatchDeadlineExceeded):
            with _batch_deadline(17, signal_api=api):
                self.assertEqual(api.timer[0], 17.0)
                api.handler(api.SIGALRM, None)

        self.assertEqual(api.timer_calls, [(api.ITIMER_REAL, 17.0), (api.ITIMER_REAL, 0.0)])
        self.assertEqual(api.handler, "prior-handler")
        self.assertEqual(api.timer, (0.0, 0.0))

    def test_refuses_to_overwrite_an_existing_process_timer(self):
        api = _FakeSignalAPI()
        api.timer = (5.0, 0.0)
        with self.assertRaisesRegex(run_r5_batch_cli.R5BatchCLIError, "deadline unavailable"):
            _require_deadline_support(api)
        self.assertEqual(api.timer_calls, [])
        self.assertEqual(api.handler, "prior-handler")

    def test_factory_stops_before_starting_a_new_attempt_after_deadline(self):
        attempts = []
        factory = _DeadlineWorkerFactory(
            lambda attempt: attempts.append(attempt) or object(),
            deadline=10.0,
        )
        with patch.object(run_r5_batch_cli.time, "monotonic", side_effect=(9.0, 10.0)):
            first = factory("R5-001")
            with self.assertRaises(R5BatchDeadlineExceeded):
                factory("R5-002")

        self.assertIsNotNone(first)
        self.assertEqual(attempts, ["R5-001"])
        self.assertTrue(factory.expired)

    def test_expiry_before_claim_leaves_every_attempt_pending(self):
        ledger = self._ledger()
        worker_factory = _DeadlineWorkerFactory(
            lambda _attempt: self.fail("expired attempt must not construct Worker"),
            deadline=10.0,
        )
        result_record = self._run_coordinator(
            ledger, worker_factory, lambda *_args, **_kwargs: self.fail("not dispatched")
        )
        self.assertEqual(result_record.status, "stopped-preflight")
        self.assertTrue(all(record.state == "PENDING" for record in ledger.records()))

    def test_inflight_deadline_stops_as_unknown_and_is_not_replayed(self):
        ledger = self._ledger()
        api = _FakeSignalAPI()
        with _batch_deadline(17, signal_api=api):
            def expire_inflight(*_args, **_kwargs):
                api.handler(api.SIGALRM, None)

            result_record = self._run_coordinator(
                ledger,
                lambda _attempt: self._collaborators()[0],
                expire_inflight,
            )
        self.assertEqual(result_record.status, "stopped-unknown")
        self.assertEqual(ledger.get("R5-001").state, "UNKNOWN")
        self.assertTrue(all(
            ledger.get(f"R5-{index:03d}").state == "PENDING"
            for index in range(2, 6)
        ))

    def test_expiry_between_attempts_does_not_claim_or_replace_next_id(self):
        ledger = self._ledger()
        selected_ids = []
        worker_factory = _DeadlineWorkerFactory(
            lambda attempt: selected_ids.append(attempt.attempt_id)
            or self._collaborators()[0],
            deadline=10.0,
        )
        times = iter((9.0, 10.0))

        def success(attempt, _snapshot, **_kwargs):
            return R5ExecutionRecord(
                attempt.attempt_id,
                attempt.input_digest,
                ExecutionResult(status=ExecutionStatus.VERIFIED),
            )

        with patch.object(run_r5_batch_cli.time, "monotonic", side_effect=lambda: next(times)):
            result_record = self._run_coordinator(ledger, worker_factory, success)
        self.assertEqual(result_record.status, "stopped-preflight")
        self.assertEqual(selected_ids, ["R5-001"])
        self.assertEqual(ledger.get("R5-001").state, "COMPLETED")
        self.assertEqual(ledger.get("R5-002").state, "PENDING")

    def test_batch_deadline_support_requires_main_thread_signal_timer(self):
        api = _FakeSignalAPI()
        with patch.object(run_r5_batch_cli.threading, "current_thread", return_value=object()):
            with self.assertRaisesRegex(run_r5_batch_cli.R5BatchCLIError, "deadline unavailable"):
                _require_deadline_support(api)
        self.assertEqual(api.timer_calls, [])

    def test_operator_summary_displays_exact_post_confirmation_deadline(self):
        output = StringIO()
        _print_summary(
            output,
            "EXP-1070",
            R5LocalModelMetadata("0.40.3", "qwen2.5-coder:7b", "a" * 64, 1),
            available_bytes=1024 * 1024 * 1024,
            snapshot_origin="github_codeload_archive",
            snapshot_tree_oid=PINNED_TREE,
            snapshot_content_digest=PINNED_CONTENT_DIGEST,
        )
        self.assertIn('"batch_deadline_seconds_after_confirmation":2400', output.getvalue())
        self.assertIn(f'"tree":"{PINNED_TREE}"', output.getvalue())
        self.assertIn(
            f'"snapshot_content_digest":"{PINNED_CONTENT_DIGEST}"',
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
