from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import ExecutionRequest, ExecutionResult, ExecutionStatus


class ExecutionRecordTests(unittest.TestCase):
    def test_request_is_an_immutable_local_preparation_record(self):
        request = ExecutionRequest(
            process_id="process-local-001",
            task_id="task-local-001",
            repository_id="fixture-repository",
            base_commit="fixture-base-001",
            snapshot_path=Path("fixtures/repository/project"),
            allowed_commands=frozenset({"python3"}),
            declared_change_paths=("calculator.py",),
            test_command=("python3", "-m", "unittest"),
        )

        self.assertEqual(request.test_timeout_seconds, 30)
        with self.assertRaises(FrozenInstanceError):
            request.process_id = "process-replaced"  # type: ignore[misc]

    def test_result_has_only_bounded_prepared_or_failure_metadata(self):
        prepared = ExecutionResult(
            status=ExecutionStatus.PREPARED,
            prepared_change_id="staged-local-001",
            patch_digest="a" * 64,
            evidence_digest="b" * 64,
            verification_digest="c" * 64,
        )
        failed = ExecutionResult(status=ExecutionStatus.FAILED, failure_code="worker-failed")

        self.assertEqual(prepared.status, ExecutionStatus.PREPARED)
        self.assertEqual(failed.status, ExecutionStatus.FAILED)
        self.assertEqual(failed.failure_code, "worker-failed")
        with self.assertRaises(FrozenInstanceError):
            failed.status = ExecutionStatus.PREPARED  # type: ignore[misc]
        self.assertNotIn("prompt", ExecutionResult.__dataclass_fields__)
        self.assertNotIn("credential", ExecutionRequest.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
