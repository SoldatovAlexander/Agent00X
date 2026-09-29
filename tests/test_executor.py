from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import (
    ExecutionError,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ProposalWorker,
    WorkerInput,
    WorkerProposal,
    validate_worker_proposal,
)


def valid_request(**overrides) -> ExecutionRequest:
    fields = {
        "process_id": "process-local-001",
        "task_id": "task-local-001",
        "repository_id": "fixture-repository",
        "base_commit": "fixture-base-001",
        "snapshot_path": (ROOT / "fixtures/repository/project").resolve(),
        "allowed_commands": frozenset({"python3"}),
        "declared_change_paths": ("calculator.py",),
        "test_command": ("python3", "-m", "unittest"),
    }
    fields.update(overrides)
    return ExecutionRequest(**fields)


class ExecutionRecordTests(unittest.TestCase):
    def test_request_is_an_immutable_local_preparation_record(self):
        request = valid_request()

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

    def test_request_rejects_invalid_identity_values_without_echoing_them(self):
        for field in ("process_id", "task_id", "repository_id", "base_commit"):
            for value in (None, 42, "", "  ", " leading", "trailing ", "unsafe\nvalue"):
                with self.subTest(field=field, value=repr(value)):
                    with self.assertRaisesRegex(
                        ExecutionError,
                        "^execution request: identity field is invalid$",
                    ) as raised:
                        valid_request(**{field: value})
                    self.assertNotIn("unsafe", str(raised.exception))

    def test_worker_contract_exposes_task_metadata_and_text_changes_only(self):
        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.received = task
                return WorkerProposal((("calculator.py", "def add(a, b): return a + b\n"),))

        fake = FakeWorker()
        task = WorkerInput(
            process_id="process-local-001",
            task_id="task-local-001",
            repository_id="fixture-repository",
            base_commit="fixture-base-001",
            declared_change_paths=("calculator.py",),
        )
        proposal = fake.propose(task)
        self.assertIs(fake.received, task)
        self.assertEqual(proposal.changes[0][0], "calculator.py")
        self.assertTrue(isinstance(fake, ProposalWorker))
        self.assertEqual(
            set(WorkerInput.__dataclass_fields__),
            {"process_id", "task_id", "repository_id", "base_commit", "declared_change_paths"},
        )
        self.assertEqual(set(WorkerProposal.__dataclass_fields__), {"changes"})

    def test_worker_proposal_validator_rejects_malformed_values_without_echo(self):
        malformed = (
            None,
            {"changes": (("calculator.py", "secret-content"),)},
            WorkerProposal(()),
            WorkerProposal([("calculator.py", "content")]),
            WorkerProposal(((None, "content"),)),
            WorkerProposal((("calculator.py", object()),)),
            WorkerProposal((("calculator.py", "content"), object())),
        )
        for proposal in malformed:
            with self.subTest(proposal=type(proposal).__name__):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution proposal: shape is invalid$"
                ) as raised:
                    validate_worker_proposal(proposal, valid_request())
                self.assertNotIn("secret-content", str(raised.exception))

    def test_worker_proposal_validator_returns_detached_immutable_record(self):
        original = WorkerProposal((("calculator.py", "safe content"),))
        validated = validate_worker_proposal(original, valid_request())
        self.assertEqual(validated, original)
        self.assertIsNot(validated, original)

    def test_worker_proposal_validator_enforces_scope_and_normalized_path_uniqueness(self):
        for changes in (
            (("../calculator.py", "content"),),
            (("/tmp/calculator.py", "content"),),
            (("other.py", "content"),),
            (("calculator.py", "one"), ("calculator.py", "two")),
        ):
            with self.subTest(changes=tuple(path for path, _ in changes)):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution proposal: scope is invalid$"
                ):
                    validate_worker_proposal(WorkerProposal(changes), valid_request())

    def test_worker_proposal_validator_enforces_file_count_and_utf8_size_limits(self):
        paths = tuple(f"file-{index}.py" for index in range(21))
        request = valid_request(declared_change_paths=paths)
        proposal = WorkerProposal(tuple((path, "x") for path in paths))
        with self.assertRaisesRegex(
            ExecutionError, "^execution proposal: limits exceeded$"
        ):
            validate_worker_proposal(proposal, request)

        total_paths = tuple(f"total-{index}.py" for index in range(10))
        total_request = valid_request(declared_change_paths=total_paths)
        total_proposal = WorkerProposal(tuple((path, "x" * 100_000) for path in total_paths))
        with self.assertRaisesRegex(
            ExecutionError, "^execution proposal: limits exceeded$"
        ):
            validate_worker_proposal(total_proposal, total_request)

        oversized = WorkerProposal((("calculator.py", "x" * 100_001),))
        with self.assertRaisesRegex(
            ExecutionError, "^execution proposal: limits exceeded$"
        ):
            validate_worker_proposal(oversized, valid_request())

        invalid_unicode = WorkerProposal((("calculator.py", "\ud800"),))
        with self.assertRaisesRegex(
            ExecutionError, "^execution proposal: content is invalid$"
        ):
            validate_worker_proposal(invalid_unicode, valid_request())

    def test_request_rejects_invalid_snapshot_and_change_paths(self):
        invalid_snapshots = ("/tmp/repository", Path("."), Path("/"), Path("/tmp/../escape"))
        for value in invalid_snapshots:
            with self.subTest(snapshot=value):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: snapshot path is invalid$"
                ):
                    valid_request(snapshot_path=value)

        for value in ("", ".", "../escape.py", "/tmp/file.py", "a//b.py", "a/./b.py", "a\\b.py"):
            with self.subTest(change_path=value):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: declared paths are invalid$"
                ):
                    valid_request(declared_change_paths=(value,))

    def test_request_rejects_malformed_test_command_and_limits(self):
        for command in ("python3 -m unittest", (), ("python3", ""), ("sh", "-c", "true")):
            with self.subTest(command=command):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: test command is invalid$"
                ):
                    valid_request(test_command=command)

        for timeout in (0, -1, 301, True, 1.5):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: test timeout is invalid$"
                ):
                    valid_request(test_timeout_seconds=timeout)

    def test_request_rejects_invalid_command_allowlist(self):
        for allowed_commands in (set(), frozenset(), frozenset({"python3 -m"}), frozenset({""})):
            with self.subTest(allowed_commands=allowed_commands):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: command allowlist is invalid$"
                ):
                    valid_request(allowed_commands=allowed_commands)


if __name__ == "__main__":
    unittest.main()
