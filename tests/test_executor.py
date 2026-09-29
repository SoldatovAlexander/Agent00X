from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import (
    ExecutionError,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    IndependentVerifier,
    ProposalWorker,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    WorkerInput,
    WorkerProposal,
    ExecutorSandboxBackend,
    run_local_execution,
    validate_worker_proposal,
)
from app_contracts.validator import ContractValidationError
from app_contracts.repository_process import prepare_change
from app_contracts.digests import sha256_digest


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


class AcceptingVerifier:
    def __init__(self):
        self.calls = 0

    def verify(self, prepared: VerifierInput) -> VerifierResult:
        self.calls += 1
        self.received = prepared
        return VerifierResult(
            process_id=prepared.process_id,
            verifier_id="test-verifier",
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
        )


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

    def test_verifier_contract_is_separate_and_explicitly_local(self):
        class FakeVerifier:
            def verify(self, prepared: VerifierInput) -> VerifierResult:
                self.received = prepared
                return VerifierResult(
                    process_id=prepared.process_id,
                    verifier_id="test-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        verifier = FakeVerifier()
        prepared = VerifierInput(
            process_id="process-local-001",
            patch_digest="sha256:" + "a" * 64,
            evidence_digest="sha256:" + "b" * 64,
            verification_digest="sha256:" + "c" * 64,
            verified_contents_digest="sha256:" + "d" * 64,
        )
        result = verifier.verify(prepared)
        self.assertTrue(isinstance(verifier, IndependentVerifier))
        self.assertEqual(verifier.received.evidence_origin, "local_test")
        self.assertEqual(result.verdict, VerifierVerdict.PASS)
        self.assertEqual(result.evidence_origin, "local_test")
        self.assertEqual(
            set(VerifierInput.__dataclass_fields__),
            {
                "process_id", "patch_digest", "evidence_digest", "verification_digest",
                "verified_contents_digest", "evidence_origin",
            },
        )
        self.assertNotIn("credential", VerifierInput.__dataclass_fields__)

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

    def test_local_coordinator_calls_worker_once_and_returns_prepared_digests(self):
        class FakeWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                self.task = task
                content = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                self.content = content + "\n\ndef subtract(a, b):\n    return a - b\n"
                return WorkerProposal((("calculator.py", self.content),))

        worker = FakeWorker()
        with patch(
            "app_contracts.executor.prepare_change", wraps=prepare_change
        ) as prepare_call:
            verifier = AcceptingVerifier()
            result = run_local_execution(
                valid_request(test_command=("python3", "-c", "print('ok')")),
                worker,
                verifier=verifier,
            )

        self.assertEqual(worker.calls, 1)
        prepare_call.assert_called_once()
        self.assertEqual(worker.task.declared_change_paths, ("calculator.py",))
        self.assertEqual(result.status, ExecutionStatus.VERIFIED)
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(result.prepared_change_id, "staged-local-001")
        self.assertTrue(result.patch_digest.startswith("sha256:"))
        self.assertTrue(result.evidence_digest.startswith("sha256:"))
        self.assertTrue(result.verification_digest.startswith("sha256:"))
        self.assertTrue(result.verified_contents_digest.startswith("sha256:"))
        self.assertTrue(all(len(digest.removeprefix("sha256:")) == 64 for digest in (
            result.patch_digest,
            result.evidence_digest,
            result.verification_digest,
            result.verified_contents_digest,
        )))
        self.assertEqual(
            result.verified_contents_digest,
            sha256_digest((("calculator.py", worker.content),)),
        )
        self.assertEqual(verifier.received.patch_digest, result.patch_digest)
        self.assertEqual(verifier.received.evidence_digest, result.evidence_digest)
        self.assertEqual(verifier.received.verification_digest, result.verification_digest)
        self.assertEqual(
            verifier.received.verified_contents_digest, result.verified_contents_digest
        )
        self.assertEqual(verifier.received.evidence_origin, "local_test")
        self.assertEqual(result.verifier_result.verifier_id, "test-verifier")
        self.assertNotIn("approval", ExecutionResult.__dataclass_fields__)
        self.assertNotIn("publishable", ExecutionResult.__dataclass_fields__)

    def test_local_coordinator_returns_no_success_when_preparation_fails(self):
        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                return WorkerProposal((("calculator.py", "invalid but different"),))

        request = valid_request(test_command=("python3", "-c", "raise SystemExit(1)"))
        with self.assertRaisesRegex(
            ContractValidationError,
            "^verification failed; staged change was not created$",
        ):
            run_local_execution(request, FakeWorker(), verifier=AcceptingVerifier())

    def test_local_coordinator_closes_injected_sandbox_on_worker_failure(self):
        class TrackingBackend:
            def __init__(self):
                self.closed = 0

            def create(self, snapshot: Path, allowed_commands: set[str]):
                from app_contracts.sandbox import LocalProcessSandbox

                sandbox = LocalProcessSandbox(snapshot, allowed_commands)
                backend = self

                class Session:
                    snapshot = sandbox.snapshot
                    workspace = sandbox.workspace

                    def run(self, argv, timeout_seconds=30):
                        return sandbox.run(argv, timeout_seconds)

                    def close(self):
                        backend.closed += 1
                        sandbox.close()

                return Session()

        class FailingWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                raise RuntimeError("injected worker failure")

        backend = TrackingBackend()
        with self.assertRaisesRegex(RuntimeError, "^injected worker failure$"):
            run_local_execution(
                valid_request(), FailingWorker(), verifier=AcceptingVerifier(),
                sandbox_backend=backend,
            )
        self.assertEqual(backend.closed, 1)
        self.assertIsInstance(backend, ExecutorSandboxBackend)

    def test_malformed_sandbox_session_fails_before_worker_and_attempts_cleanup(self):
        class MalformedBackend:
            def __init__(self):
                self.session_closed = False

            def create(self, snapshot: Path, allowed_commands: set[str]):
                backend = self

                class Session:
                    workspace = snapshot

                    def run(self, argv, timeout_seconds=30):
                        raise AssertionError("must not run")

                    def close(self):
                        backend.session_closed = True

                return Session()

        class CountingWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                return WorkerProposal((("calculator.py", "unused"),))

        backend = MalformedBackend()
        worker = CountingWorker()
        with self.assertRaisesRegex(
            ExecutionError, "^execution sandbox: session is invalid$"
        ):
            run_local_execution(
                valid_request(), worker, verifier=AcceptingVerifier(), sandbox_backend=backend
            )
        self.assertEqual(worker.calls, 0)
        self.assertTrue(backend.session_closed)

    def test_preparation_metadata_must_match_request_bindings(self):
        class FakeBackend:
            def create(self, snapshot: Path, allowed_commands: set[str]):
                class Session:
                    workspace = snapshot

                    def __init__(self):
                        self.snapshot = snapshot

                    def run(self, argv, timeout_seconds=30):
                        raise AssertionError("preparation is mocked")

                    def close(self):
                        pass

                return Session()

        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                return WorkerProposal((("calculator.py", "replacement"),))

        request = valid_request()
        base_staged = {
            "process_id": request.process_id,
            "repository_id": request.repository_id,
            "base_commit": request.base_commit,
            "staged_change_id": "staged-local-001",
            "patch_digest": "sha256:" + "a" * 64,
            "evidence_digest": "sha256:" + "b" * 64,
            "verification_digest": "sha256:" + "c" * 64,
        }
        for field, replacement in (
            ("process_id", "process-foreign"),
            ("repository_id", "repository-foreign"),
            ("base_commit", "commit-foreign"),
        ):
            staged = dict(base_staged, **{field: replacement})
            with self.subTest(field=field), patch(
                "app_contracts.executor.prepare_change",
                return_value=SimpleNamespace(staged_change=staged),
            ):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution preparation: binding mismatch$"
                ):
                    run_local_execution(
                        request, FakeWorker(), verifier=AcceptingVerifier(),
                        sandbox_backend=FakeBackend(),
                    )

    def test_worker_cannot_replace_declared_test_command(self):
        class TrackingBackend:
            def __init__(self):
                self.commands = []

            def create(self, snapshot: Path, allowed_commands: set[str]):
                from app_contracts.sandbox import LocalProcessSandbox

                sandbox = LocalProcessSandbox(snapshot, allowed_commands)
                backend = self

                class Session:
                    snapshot = sandbox.snapshot
                    workspace = sandbox.workspace

                    def run(self, argv, timeout_seconds=30):
                        backend.commands.append(tuple(argv))
                        return sandbox.run(argv, timeout_seconds)

                    def close(self):
                        sandbox.close()

                return Session()

        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                proposal = WorkerProposal((("calculator.py", "replacement"),))
                self.proposed_command = ("sh", "-c", "touch injected")
                return proposal

        command = ("python3", "-c", "print('declared-only')")
        backend = TrackingBackend()
        worker = FakeWorker()
        run_local_execution(
            valid_request(test_command=command), worker, verifier=AcceptingVerifier(),
            sandbox_backend=backend,
        )
        self.assertEqual(backend.commands, [command])
        self.assertNotEqual(backend.commands[0], worker.proposed_command)

    def test_missing_or_aliased_verifier_is_denied_before_sandbox_creation(self):
        class Backend:
            def __init__(self):
                self.calls = 0

            def create(self, snapshot: Path, allowed_commands: set[str]):
                self.calls += 1
                raise AssertionError("sandbox must not be created")

        class DualRole:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                return WorkerProposal((("calculator.py", "unused"),))

            def verify(self, prepared: VerifierInput) -> VerifierResult:
                return VerifierResult(
                    process_id=prepared.process_id,
                    verifier_id="aliased",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        for verifier, expected in (
            (None, "execution verifier: collaborator is invalid"),
            (object(), "execution verifier: collaborator is invalid"),
        ):
            backend = Backend()
            with self.subTest(expected=expected), self.assertRaisesRegex(
                ExecutionError, f"^{expected}$"
            ):
                run_local_execution(
                    valid_request(), DualRole(), verifier=verifier, sandbox_backend=backend
                )
            self.assertEqual(backend.calls, 0)

        backend = Backend()
        dual_role = DualRole()
        with self.assertRaisesRegex(
            ExecutionError, "^execution verifier: collaborator is aliased$"
        ):
            run_local_execution(
                valid_request(), dual_role, verifier=dual_role, sandbox_backend=backend
            )
        self.assertEqual(backend.calls, 0)

    def test_only_explicit_verifier_pass_returns_verified_result(self):
        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                return WorkerProposal((("calculator.py", original + "\n# local change\n"),))

        class ReturningVerifier:
            def __init__(self, verdict):
                self.verdict = verdict

            def verify(self, prepared: VerifierInput) -> VerifierResult:
                return VerifierResult(
                    process_id=prepared.process_id,
                    verifier_id="test-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=self.verdict,
                )

        for verdict in (VerifierVerdict.FAIL, VerifierVerdict.BLOCKED, "unknown"):
            with self.subTest(verdict=verdict):
                result = run_local_execution(
                    valid_request(test_command=("python3", "-c", "print('ok')")),
                    FakeWorker(),
                    verifier=ReturningVerifier(verdict),
                )
                self.assertEqual(result.status, ExecutionStatus.FAILED)
                self.assertIsNone(result.prepared_change_id)
                self.assertEqual(result.failure_code, "verifier-not-pass")
                self.assertTrue(result.evidence_digest.startswith("sha256:"))
                self.assertNotIn("approval", ExecutionResult.__dataclass_fields__)

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
