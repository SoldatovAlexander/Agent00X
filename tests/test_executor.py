from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
import ast
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
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
    WorkerTerminalOutcome,
    ExecutorSandboxBackend,
    _build_verifier_input,
    _read_pinned_snapshot_files,
    run_local_execution,
    validate_worker_proposal,
)
from app_contracts.validator import ContractValidationError
from app_contracts.observation_store import ObservationStore, ObservationStoreError
from app_contracts.repository_process import prepare_change
from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
)
from app_contracts.pinned_snapshot import (
    SNAPSHOT_DIGEST_CANONICALIZATION,
    PinnedSnapshot,
    compute_snapshot_tree_digest,
    export_local_commit_tree,
    open_local_repository,
)
from app_contracts.remote_snapshot_workspace import (
    materialize_github_snapshot,
)
import app_contracts.executor as executor_module


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


@contextmanager
def pinned_test_request(**overrides):
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        source_repository = temporary_root / "source-repository"
        shutil.copytree(ROOT / "fixtures/repository/project", source_repository)
        subprocess.run(
            ["git", "init", "--quiet", str(source_repository)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(source_repository), "add", "-A"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git", "-C", str(source_repository), "-c", "user.name=Executor Test",
                "-c", "user.email=executor@example.invalid", "commit", "--quiet", "-m",
                "fixture snapshot",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        repository = open_local_repository(source_repository)
        commit_oid = subprocess.run(
            ["git", "-C", str(source_repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        lease = export_local_commit_tree(repository, commit_oid, temporary_root)
        try:
            snapshot_path = lease.path
            fields = {
                "process_id": "process-local-001",
                "task_id": "task-local-001",
                "repository_id": "fixture-repository",
                "base_commit": commit_oid,
                "snapshot_path": snapshot_path,
                "allowed_commands": frozenset({"python3"}),
                "declared_change_paths": ("calculator.py",),
                "test_command": ("python3", "-m", "unittest"),
                "pinned_snapshot": PinnedSnapshot(
                    repository_id="fixture-repository",
                    commit_oid=commit_oid,
                    tree_digest=compute_snapshot_tree_digest(snapshot_path),
                    snapshot_path=snapshot_path,
                ),
            }
            fields.update(overrides)
            yield ExecutionRequest(**fields)
        finally:
            lease.close()


class AcceptingVerifier:
    def __init__(self):
        self.calls = 0

    def verify(self, prepared: VerifierInput) -> VerifierResult:
        self.calls += 1
        self.received = prepared
        return VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id="test-verifier",
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
        )


class RemoteSnapshotExecutionTests(unittest.TestCase):
    @staticmethod
    def make_snapshot(
        path: Path,
        content: bytes,
        *,
        evidence_origin: str = "github_rest_api_claim",
    ) -> GitHubSnapshotContents:
        path.mkdir(parents=True, exist_ok=True)
        (path / "calculator.py").write_bytes(content)
        (path / "calculator.py").chmod(0o644)
        digest = compute_snapshot_tree_digest(path)
        git_oid = hashlib.sha1(
            b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        ).hexdigest()
        blob = GitHubBlobClaim(
            path="calculator.py",
            mode="100644",
            sha=git_oid,
            size=len(content),
            content=content,
            content_digest=sha256_bytes(content),
            evidence_origin=evidence_origin,
        )
        claim = GitHubSnapshotClaim(
            owner="fixture-owner",
            repository="fixture-repository",
            commit_oid="a" * 40,
            tree_oid="b" * 40,
            content_digest=digest,
            evidence_origin=evidence_origin,
        )
        return GitHubSnapshotContents(claim=claim, files=(blob,))

    class FakeBackend:
        def __init__(
            self,
            replay_returncode=0,
            *,
            target_returncode=0,
            target_stdout="",
            target_stderr="",
        ):
            self.temporary_directories = []
            self.sessions = []
            self.commands = []
            self.closed_workspace_contents = []
            self.closed_snapshot_contents = []
            self.replay_returncode = replay_returncode
            self.target_returncode = target_returncode
            self.target_stdout = target_stdout
            self.target_stderr = target_stderr

        def create(self, snapshot: Path, allowed_commands: set[str]):
            from app_contracts.sandbox import CommandResult

            temporary = tempfile.TemporaryDirectory()
            self.temporary_directories.append(temporary)
            root = Path(temporary.name)
            copied_snapshot = root / "snapshot"
            workspace = root / "workspace"
            shutil.copytree(snapshot, copied_snapshot)
            shutil.copytree(snapshot, workspace)
            for path in (workspace, *workspace.rglob("*")):
                path.chmod(path.stat().st_mode | 0o200)
            backend = self

            class Session:
                def __init__(self):
                    self.index = len(backend.sessions) + 1
                    self.snapshot = copied_snapshot
                    self.workspace = workspace
                    self.closed = False

                def run(self, argv, timeout_seconds=30):
                    backend.commands.append((tuple(argv), timeout_seconds, self.index))
                    if self.index == 2:
                        backend.replayed_content = (
                            workspace / "calculator.py"
                        ).read_text(encoding="utf-8")
                    return CommandResult(
                        tuple(argv),
                        backend.replay_returncode if self.index == 2 else backend.target_returncode,
                        "REPLAY-OUTPUT-CANARY" if self.index == 2 else backend.target_stdout,
                        "REPLAY-ERROR-CANARY" if self.index == 2 else backend.target_stderr,
                    )

                def close(self):
                    backend.closed_workspace_contents.append(
                        (workspace / "calculator.py").read_text(encoding="utf-8")
                    )
                    backend.closed_snapshot_contents.append(
                        (copied_snapshot / "calculator.py").read_text(encoding="utf-8")
                    )
                    self.closed = True
                    temporary.cleanup()

            session = Session()
            self.sessions.append(session)
            return session

    def test_allowlisted_target_test_failure_reaches_only_fixed_cli_marker(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "remote-snapshot"
            base = b"def add(left, right):\n    return left + right\n"
            remote_snapshot = self.make_snapshot(snapshot_path, base)
            request = ExecutionRequest(
                process_id="process-target-test-category",
                task_id="task-target-test-category",
                repository_id="fixture-owner/fixture-repository",
                base_commit=remote_snapshot.claim.commit_oid,
                snapshot_path=snapshot_path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-c", "pass"),
                remote_snapshot=remote_snapshot,
            )

            class FakeWorker:
                def propose(self, _worker_input):
                    return WorkerProposal((("calculator.py", base.decode() + "# candidate\n"),))

            stdout_canary = "PRIVATE-STDOUT-CANARY"
            stderr_canary = "PRIVATE-STDERR-CANARY"
            backend = self.FakeBackend(
                target_returncode=1,
                target_stdout=(
                    stdout_canary + "\nagent00x:test-failure:valid-row\n"
                ),
                target_stderr=stderr_canary,
            )
            result = run_local_execution(
                request,
                FakeWorker(),
                verifier=AcceptingVerifier(),
                sandbox_backend=backend,
            )

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "target-test-valid-row")
        from app_contracts import worker_cli

        evidence = worker_cli._remote_execution_evidence(result)
        self.assertEqual(evidence["failure_code"], "target-test-valid-row")
        serialized = json.dumps(evidence) + repr(result)
        self.assertNotIn(stdout_canary, serialized)
        self.assertNotIn(stderr_canary, serialized)

    def test_remote_claim_is_bound_to_worker_verifier_and_execution_result(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "remote-snapshot"
            base = b"def add(left, right):\n    return left + right\n"
            remote_snapshot = self.make_snapshot(snapshot_path, base)
            request = ExecutionRequest(
                process_id="process-remote-001",
                task_id="task-remote-001",
                repository_id="fixture-owner/fixture-repository",
                base_commit=remote_snapshot.claim.commit_oid,
                snapshot_path=snapshot_path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-m", "unittest"),
                remote_snapshot=remote_snapshot,
            )

            class FakeWorker:
                received = None
                content = None

                def propose(self, worker_input: WorkerInput) -> WorkerProposal:
                    self.received = worker_input
                    self.content = base.decode() + "\n# proposed\n"
                    return WorkerProposal(
                        (("calculator.py", self.content),)
                    )

            worker = FakeWorker()
            verifier = AcceptingVerifier()
            backend = self.FakeBackend()
            result = run_local_execution(
                request, worker, verifier=verifier, sandbox_backend=backend
            )
            expected_claim_digest = sha256_digest(
                {
                    "canonicalization": "github-rest-snapshot-claim/v1",
                    "owner": remote_snapshot.claim.owner,
                    "repository": remote_snapshot.claim.repository,
                    "commit_oid": remote_snapshot.claim.commit_oid,
                    "tree_oid": remote_snapshot.claim.tree_oid,
                    "content_digest": remote_snapshot.claim.content_digest,
                    "full_snapshot": remote_snapshot.claim.full_snapshot,
                    "selected_paths": remote_snapshot.claim.selected_paths,
                    "evidence_origin": "github_rest_api_claim",
                }
            )

            self.assertEqual(result.status, ExecutionStatus.VERIFIED)
            self.assertEqual(result.snapshot_origin, "github_rest_api_claim")
            self.assertEqual(result.snapshot_tree_digest, remote_snapshot.claim.content_digest)
            self.assertEqual(result.snapshot_claim_digest, expected_claim_digest)
            self.assertRegex(result.verifier_result.replay_result_digest, r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(worker.received.snapshot_origin, "github_rest_api_claim")
            self.assertEqual(worker.received.snapshot_claim_digest, expected_claim_digest)
            self.assertFalse(hasattr(worker.received, "snapshot_files"))
            self.assertEqual(verifier.received.snapshot_claim_digest, expected_claim_digest)
            self.assertEqual(
                verifier.received.snapshot_files,
                (("calculator.py", "100644", base),),
            )
            self.assertEqual(len(backend.sessions), 2)
            self.assertIsNot(backend.sessions[0], backend.sessions[1])
            self.assertNotEqual(backend.sessions[0].workspace, backend.sessions[1].workspace)
            self.assertTrue(all(session.closed for session in backend.sessions))
            self.assertEqual(
                backend.commands,
                [
                    (request.test_command, request.test_timeout_seconds, 1),
                    (request.test_command, request.test_timeout_seconds, 2),
                ],
            )
            self.assertEqual(backend.replayed_content, worker.content)
            expected_replay_digest = sha256_digest(
                (
                    "github-remote-replay-v1",
                    request.repository_id,
                    request.base_commit,
                    remote_snapshot.claim.content_digest,
                    expected_claim_digest,
                    request.test_command,
                    request.test_timeout_seconds,
                    verifier.received.verified_contents_digest,
                    0,
                )
            )
            self.assertEqual(
                verifier.received.replay_result_digest,
                expected_replay_digest,
            )
            from app_contracts.publication_seed import build_publication_seed

            seed = build_publication_seed(request, result)
            self.assertEqual(seed.snapshot_origin, "github_rest_api_claim")
            self.assertEqual(seed.snapshot_tree_digest, result.snapshot_tree_digest)
            self.assertEqual(seed.snapshot_claim_digest, result.snapshot_claim_digest)

    def test_codeload_archive_origin_flows_through_worker_verifier_and_seed(self):
        from app_contracts.publication_seed import build_publication_seed

        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "archive-snapshot"
            base = b"def add(left, right):\n    return left + right\n"
            remote_snapshot = self.make_snapshot(
                snapshot_path,
                base,
                evidence_origin="github_codeload_archive",
            )
            request = ExecutionRequest(
                process_id="process-archive-001",
                task_id="task-archive-001",
                repository_id="fixture-owner/fixture-repository",
                base_commit=remote_snapshot.claim.commit_oid,
                snapshot_path=snapshot_path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-m", "unittest"),
                remote_snapshot=remote_snapshot,
            )

            class ArchiveWorker:
                received = None

                def propose(self, worker_input: WorkerInput) -> WorkerProposal:
                    self.received = worker_input
                    return WorkerProposal(
                        (("calculator.py", base.decode() + "\n# archive proposal\n"),)
                    )

            worker = ArchiveWorker()
            result = run_local_execution(
                request,
                worker,
                verifier=AcceptingVerifier(),
                sandbox_backend=self.FakeBackend(),
            )
            expected_claim_digest = sha256_digest(
                {
                    "canonicalization": "github-codeload-snapshot-claim/v1",
                    "owner": remote_snapshot.claim.owner,
                    "repository": remote_snapshot.claim.repository,
                    "commit_oid": remote_snapshot.claim.commit_oid,
                    "tree_oid": remote_snapshot.claim.tree_oid,
                    "content_digest": remote_snapshot.claim.content_digest,
                    "full_snapshot": True,
                    "selected_paths": None,
                    "evidence_origin": "github_codeload_archive",
                }
            )
            self.assertEqual(result.status, ExecutionStatus.VERIFIED)
            self.assertEqual(result.snapshot_origin, "github_codeload_archive")
            self.assertEqual(result.snapshot_claim_digest, expected_claim_digest)
            self.assertEqual(worker.received.snapshot_origin, "github_codeload_archive")
            self.assertEqual(worker.received.snapshot_claim_digest, expected_claim_digest)
            seed = build_publication_seed(request, result)
            self.assertEqual(seed.snapshot_origin, "github_codeload_archive")
            self.assertEqual(seed.snapshot_claim_digest, expected_claim_digest)

    def test_signed_client_remains_audit_only_before_durable_stage(self):
        from datetime import timedelta
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from app_contracts.signed_verifier_client import (
            SignedVerifierClient,
            SignedVerifierHTTPSTransport,
        )
        from app_contracts.signed_verifier_service import (
            VerifierProfile,
            handle_signed_verifier_invocation,
        )
        from app_contracts.signed_verifier_protocol import (
            parse_signed_verifier_invocation,
        )
        from app_contracts.verifier_trust_enrollment import (
            build_signed_verifier_trust_enrollment,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "remote-snapshot"
            base = b"def add(left, right):\n    return left + right\n"
            remote_snapshot = self.make_snapshot(snapshot_path, base)
            profile = VerifierProfile(
                repository_id="fixture-owner/fixture-repository",
                base_commit=remote_snapshot.claim.commit_oid,
                snapshot_tree_digest=remote_snapshot.claim.content_digest,
                snapshot_file_count=len(remote_snapshot.files),
                allowed_change_paths=("calculator.py",),
                test_command=("python3", "-m", "unittest"),
                test_timeout_seconds=30,
                verifier_image_id="sha256:" + "1" * 64,
                verifier_code_digest="sha256:" + "2" * 64,
                signer_key_id="synthetic-executor-client-v1",
            )
            signing_key = Ed25519PrivateKey.generate()
            public_key = signing_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            authority_key = Ed25519PrivateKey.generate()
            authority_public_key = authority_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            verifier_endpoint = "https://verifier.example.com/v1/verify"
            worker_host_id = "synthetic-worker-host-exp683"
            verifier_host_id = "synthetic-verifier-host-exp683"
            now = datetime.now(timezone.utc).replace(microsecond=0)
            enrollment_bytes = build_signed_verifier_trust_enrollment(
                enrollment_id="synthetic-enrollment-exp683",
                authority_key_id="synthetic-authority-exp683",
                endpoint_url=verifier_endpoint,
                verifier_id=profile.expected_verifier_id,
                verifier_profile_digest=profile.profile_digest,
                verifier_key_id=profile.signer_key_id,
                verifier_public_key=public_key,
                worker_host_id=worker_host_id,
                verifier_host_id=verifier_host_id,
                host_separation_evidence_digest="sha256:" + "4" * 64,
                signing_key=authority_key,
                issued_at=now,
                expires_at=now + timedelta(hours=1),
            )

            class PassingRemoteVerifier:
                def verify(self, prepared: VerifierInput) -> VerifierResult:
                    return VerifierResult(
                        process_id=prepared.process_id,
                        base_commit=prepared.base_commit,
                        snapshot_tree_digest=prepared.snapshot_tree_digest,
                        replay_result_digest=prepared.replay_result_digest,
                        verifier_id=profile.expected_verifier_id,
                        patch_digest=prepared.patch_digest,
                        evidence_digest=prepared.evidence_digest,
                        verification_digest=prepared.verification_digest,
                        verified_contents_digest=prepared.verified_contents_digest,
                        verdict=VerifierVerdict.PASS,
                    )

            class FakeHTTPSResponse:
                status = 200

                def __init__(self, body: bytes):
                    self.body = body
                    self.closed = False

                def getheader(self, name):
                    return "application/json" if name == "Content-Type" else None

                def read(self, limit):
                    return self.body[:limit]

                def close(self):
                    self.closed = True

            class FakeHTTPSConnection:
                def __init__(self):
                    self.calls = 0
                    self.closed = False

                def configure(self, host, *, port, timeout, context):
                    self.configuration = (host, port, timeout, context)
                    return self

                def request(self, method, path, *, body, headers):
                    self.calls += 1
                    if (method, path) != ("POST", "/v1/verify"):
                        raise AssertionError("unexpected verifier route")
                    invocation_bytes = body
                    invocation = parse_signed_verifier_invocation(invocation_bytes)
                    if invocation.verifier_profile_digest != profile.profile_digest:
                        raise AssertionError("client sent an unexpected profile")
                    self.response = FakeHTTPSResponse(handle_signed_verifier_invocation(
                        invocation_bytes,
                        profile=profile,
                        verifier=PassingRemoteVerifier(),
                        signing_key=signing_key,
                        issued_at=datetime.now(timezone.utc),
                    ))

                def getresponse(self):
                    return self.response

                def close(self):
                    self.closed = True

            class NoTouchStage:
                save_calls = 0
                load_calls = 0

                def save(self, artifact):
                    self.save_calls += 1
                    raise AssertionError("untrusted verifier must not stage")

                def load(self, digest):
                    self.load_calls += 1
                    raise AssertionError("untrusted verifier must not stage")

            connection = FakeHTTPSConnection()
            transport = SignedVerifierHTTPSTransport(
                verifier_endpoint,
                connection_factory=lambda host, *, port, timeout, context: connection.configure(
                    host, port=port, timeout=timeout, context=context
                ),
            )
            client = SignedVerifierClient.from_trust_enrollment(
                profile,
                transport,
                enrollment_bytes,
                trusted_authority_keys={
                    "synthetic-authority-exp683": authority_public_key
                },
                expected_endpoint_url=verifier_endpoint,
                expected_worker_host_id=worker_host_id,
                expected_verifier_host_id=verifier_host_id,
                now=now,
            )
            stage = NoTouchStage()
            worker_content = base.decode() + "\n# signed client integration\n"

            class FakeWorker:
                def propose(self, _worker_input: WorkerInput) -> WorkerProposal:
                    return WorkerProposal((("calculator.py", worker_content),))

            with materialize_github_snapshot(remote_snapshot) as workspace:
                request = ExecutionRequest(
                    process_id="process-signed-client-audit-only",
                    task_id="task-signed-client-audit-only",
                    repository_id="fixture-owner/fixture-repository",
                    base_commit=remote_snapshot.claim.commit_oid,
                    snapshot_path=workspace.path,
                    allowed_commands=frozenset({"python3"}),
                    declared_change_paths=("calculator.py",),
                    test_command=("python3", "-m", "unittest"),
                    test_timeout_seconds=30,
                    remote_snapshot=remote_snapshot,
                    remote_workspace=workspace,
                )
                result = run_local_execution(
                    request,
                    FakeWorker(),
                    verifier=client,
                    sandbox_backend=self.FakeBackend(),
                    stage_sink=stage,
                )

            self.assertEqual(connection.calls, 1)
            self.assertEqual(result.status, ExecutionStatus.FAILED)
            self.assertEqual(result.failure_code, "verifier-trust-unestablished")
            self.assertTrue(result.verifier_signature_valid)
            self.assertFalse(result.verifier_independent_host_trust_established)
            self.assertEqual(
                result.verifier_attestation_key_id, profile.signer_key_id
            )
            self.assertEqual(
                result.verifier_attestation_profile_digest, profile.profile_digest
            )
            enrollment_digest = sha256_bytes(enrollment_bytes)
            self.assertEqual(
                result.verifier_trust_enrollment_digest, enrollment_digest
            )
            self.assertEqual((stage.save_calls, stage.load_calls), (0, 0))
            from app_contracts import worker_cli

            evidence = worker_cli._remote_execution_evidence(result)
            self.assertEqual(
                evidence["verifier_attestation"]["trust_enrollment_digest"],
                enrollment_digest,
            )
            self.assertEqual(evidence["failure_code"], "verifier-trust-unestablished")
            self.assertNotIn("'signature':", repr(evidence))
            self.assertNotIn("public_key", repr(evidence))

    def test_remote_replay_failure_closes_both_sessions_before_verifier(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "remote-snapshot"
            base = b"def add(left, right):\n    return left + right\n"
            remote_snapshot = self.make_snapshot(snapshot_path, base)
            request = ExecutionRequest(
                process_id="process-remote-replay-fail",
                task_id="task-remote-replay-fail",
                repository_id="fixture-owner/fixture-repository",
                base_commit=remote_snapshot.claim.commit_oid,
                snapshot_path=snapshot_path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-m", "unittest"),
                remote_snapshot=remote_snapshot,
            )

            class FakeWorker:
                def propose(self, worker_input: WorkerInput) -> WorkerProposal:
                    return WorkerProposal(
                        (("calculator.py", base.decode() + "\n# proposed\n"),)
                    )

            verifier = AcceptingVerifier()
            backend = self.FakeBackend(replay_returncode=1)
            result = run_local_execution(
                request, FakeWorker(), verifier=verifier, sandbox_backend=backend
            )
            self.assertEqual(result.status, ExecutionStatus.FAILED)
            self.assertEqual(result.failure_code, "verification-replay-failed")
            self.assertEqual(verifier.calls, 0)
            self.assertEqual(len(backend.sessions), 2)
            self.assertTrue(all(session.closed for session in backend.sessions))
            serialized = repr(result)
            self.assertNotIn("REPLAY-OUTPUT-CANARY", serialized)
            self.assertNotIn("REPLAY-ERROR-CANARY", serialized)

    def test_remote_claim_mismatch_and_default_backend_fail_before_worker(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            outer = Path(temporary_directory)
            snapshot_path = outer / "materialized"
            actual = b"actual bytes\n"
            claimed = b"different claimed bytes\n"
            snapshot = self.make_snapshot(outer / "claim-source", claimed)
            snapshot_path.mkdir()
            (snapshot_path / "calculator.py").write_bytes(actual)
            (snapshot_path / "calculator.py").chmod(0o644)
            request = ExecutionRequest(
                process_id="process-remote-002",
                task_id="task-remote-002",
                repository_id="fixture-owner/fixture-repository",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=snapshot_path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-m", "unittest"),
                remote_snapshot=snapshot,
            )

            class CountingWorker:
                calls = 0

                def propose(self, worker_input: WorkerInput) -> WorkerProposal:
                    self.calls += 1
                    return WorkerProposal((("calculator.py", "unused\n"),))

            worker = CountingWorker()
            backend = self.FakeBackend()
            with self.assertRaisesRegex(
                ExecutionError, "^execution sandbox: explicit remote backend is required$"
            ):
                run_local_execution(
                    request, worker, verifier=AcceptingVerifier()
                )
            self.assertEqual(worker.calls, 0)

            with self.assertRaisesRegex(
                ExecutionError, "^execution snapshot: claim mismatch$"
            ):
                run_local_execution(
                    request,
                    worker,
                    verifier=AcceptingVerifier(),
                    sandbox_backend=backend,
                )
            self.assertEqual(worker.calls, 0)
            self.assertTrue(backend.sessions[0].closed)

            (snapshot_path / "calculator.py").unlink()
            (snapshot_path / "calculator.py").symlink_to(
                outer / "claim-source" / "calculator.py"
            )
            with self.assertRaisesRegex(
                ExecutionError, "^execution snapshot: claim mismatch$"
            ):
                run_local_execution(
                    request,
                    worker,
                    verifier=AcceptingVerifier(),
                    sandbox_backend=self.FakeBackend(),
                )
            self.assertEqual(worker.calls, 0)

            with self.assertRaisesRegex(
                ExecutionError, "^execution request: remote snapshot binding is invalid$"
            ):
                run_local_execution(
                    replace(request, repository_id="different-owner/different-repository"),
                    worker,
                    verifier=AcceptingVerifier(),
                    sandbox_backend=self.FakeBackend(),
                )
            with self.assertRaisesRegex(
                ExecutionError, "^execution request: remote snapshot binding is invalid$"
            ):
                run_local_execution(
                    replace(
                        request,
                        pinned_snapshot=PinnedSnapshot(
                            repository_id=request.repository_id,
                            commit_oid=request.base_commit,
                            tree_digest=snapshot.claim.content_digest,
                            snapshot_path=snapshot_path,
                        ),
                    ),
                    worker,
                    verifier=AcceptingVerifier(),
                    sandbox_backend=self.FakeBackend(),
                )
            self.assertEqual(worker.calls, 0)

    def test_tampered_remote_snapshot_is_scanned_before_backend_or_worker(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "remote-snapshot"
            original = b"def add(left, right):\n    return left + right\n"
            snapshot = self.make_snapshot(snapshot_path, original)
            request = ExecutionRequest(
                process_id="process-remote-secret-001",
                task_id="task-remote-secret-001",
                repository_id="fixture-owner/fixture-repository",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=snapshot_path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-m", "unittest"),
                remote_snapshot=snapshot,
            )
            suspicious = b'password = "synthetic-password-value"\n'
            blob = snapshot.files[0]
            object.__setattr__(blob, "content", suspicious)
            object.__setattr__(blob, "size", len(suspicious))
            object.__setattr__(
                blob,
                "sha",
                hashlib.sha1(
                    b"blob " + str(len(suspicious)).encode("ascii") + b"\0" + suspicious
                ).hexdigest(),
            )
            object.__setattr__(blob, "content_digest", sha256_bytes(suspicious))
            object.__setattr__(
                snapshot.claim,
                "content_digest",
                sha256_digest(
                    {
                        "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
                        "files": [
                            {
                                "path": blob.path,
                                "content_digest": blob.content_digest,
                                "mode": blob.mode,
                            }
                        ],
                    }
                ),
            )

            class CountingWorker:
                calls = 0

                def propose(self, worker_input: WorkerInput) -> WorkerProposal:
                    self.calls += 1
                    return WorkerProposal((("calculator.py", "unused\n"),))

            worker = CountingWorker()
            backend = self.FakeBackend()
            with self.assertRaisesRegex(
                ExecutionError, "^execution request: remote snapshot is invalid$"
            ) as raised:
                run_local_execution(
                    request,
                    worker,
                    verifier=AcceptingVerifier(),
                    sandbox_backend=backend,
                )
            self.assertNotIn(suspicious.decode().strip(), str(raised.exception))
            self.assertEqual(worker.calls, 0)
            self.assertEqual(backend.sessions, [])

    def test_remote_worker_failure_preserves_claim_identity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "remote-snapshot"
            snapshot = self.make_snapshot(snapshot_path, b"synthetic source\n")
            request = ExecutionRequest(
                process_id="process-remote-failed-001",
                task_id="task-remote-failed-001",
                repository_id="fixture-owner/fixture-repository",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=snapshot_path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-m", "unittest"),
                remote_snapshot=snapshot,
            )

            class FailingWorker:
                def propose(self, worker_input: WorkerInput) -> WorkerProposal:
                    raise RuntimeError("synthetic worker failure")

            result = run_local_execution(
                request,
                FailingWorker(),
                verifier=AcceptingVerifier(),
                sandbox_backend=self.FakeBackend(),
            )

            expected_claim_digest = sha256_digest(
                {
                    "canonicalization": "github-rest-snapshot-claim/v1",
                    "owner": snapshot.claim.owner,
                    "repository": snapshot.claim.repository,
                    "commit_oid": snapshot.claim.commit_oid,
                    "tree_oid": snapshot.claim.tree_oid,
                    "content_digest": snapshot.claim.content_digest,
                    "full_snapshot": snapshot.claim.full_snapshot,
                    "selected_paths": snapshot.claim.selected_paths,
                    "evidence_origin": "github_rest_api_claim",
                }
            )
            self.assertEqual(result.status, ExecutionStatus.FAILED)
            self.assertEqual(result.failure_code, "worker-failed")
            self.assertEqual(result.snapshot_origin, "github_rest_api_claim")
            self.assertEqual(result.snapshot_tree_digest, snapshot.claim.content_digest)
            self.assertEqual(result.snapshot_claim_digest, expected_claim_digest)

    def test_remote_workspace_lease_runs_and_caller_cleanup_covers_all_outcomes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot = self.make_snapshot(
                Path(temporary_directory) / "claim-source", b"synthetic source\n"
            )
            with materialize_github_snapshot(snapshot) as workspace:
                root = workspace.path
                request = ExecutionRequest(
                    process_id="process-remote-lease-001",
                    task_id="task-remote-lease-001",
                    repository_id="fixture-owner/fixture-repository",
                    base_commit=snapshot.claim.commit_oid,
                    snapshot_path=workspace.path,
                    allowed_commands=frozenset({"python3"}),
                    declared_change_paths=("calculator.py",),
                    test_command=("python3", "-m", "unittest"),
                    remote_snapshot=snapshot,
                    remote_workspace=workspace,
                )

                class FakeWorker:
                    def propose(self, worker_input: WorkerInput) -> WorkerProposal:
                        return WorkerProposal(
                            (("calculator.py", "synthetic proposed change\n"),)
                        )

                result = run_local_execution(
                    request,
                    FakeWorker(),
                    verifier=AcceptingVerifier(),
                    sandbox_backend=self.FakeBackend(),
                )
                self.assertEqual(result.status, ExecutionStatus.VERIFIED, result.failure_code)
            self.assertFalse(root.exists())

            with materialize_github_snapshot(snapshot) as workspace:
                root = workspace.path
                request = ExecutionRequest(
                    process_id="process-remote-lease-002",
                    task_id="task-remote-lease-002",
                    repository_id="fixture-owner/fixture-repository",
                    base_commit=snapshot.claim.commit_oid,
                    snapshot_path=workspace.path,
                    allowed_commands=frozenset({"python3"}),
                    declared_change_paths=("calculator.py",),
                    test_command=("python3", "-m", "unittest"),
                    remote_workspace=workspace,
                )

                class FailingWorker:
                    def propose(self, worker_input: WorkerInput) -> WorkerProposal:
                        raise RuntimeError("synthetic worker failure")

                result = run_local_execution(
                    request,
                    FailingWorker(),
                    verifier=AcceptingVerifier(),
                    sandbox_backend=self.FakeBackend(),
                )
                self.assertEqual(result.status, ExecutionStatus.FAILED)
                self.assertEqual(result.snapshot_origin, "github_rest_api_claim")
            self.assertFalse(root.exists())

    def test_closed_or_mismatched_remote_workspace_fails_before_backend(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot = self.make_snapshot(
                Path(temporary_directory) / "claim-source", b"synthetic source\n"
            )
            workspace = materialize_github_snapshot(snapshot)
            request = ExecutionRequest(
                process_id="process-remote-lease-closed",
                task_id="task-remote-lease-closed",
                repository_id="fixture-owner/fixture-repository",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=workspace.path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-m", "unittest"),
                remote_workspace=workspace,
            )
            worker = self.CountingWorker()
            backend = self.FakeBackend()
            workspace.close()
            with self.assertRaisesRegex(
                ExecutionError,
                "^execution request: remote snapshot workspace is invalid$",
            ):
                run_local_execution(
                    request,
                    worker,
                    verifier=AcceptingVerifier(),
                    sandbox_backend=backend,
                )
            self.assertEqual(worker.calls, 0)
            self.assertEqual(backend.sessions, [])

    class CountingWorker:
        def __init__(self):
            self.calls = 0

        def propose(self, worker_input: WorkerInput) -> WorkerProposal:
            self.calls += 1
            return WorkerProposal((("calculator.py", "unused\n"),))


class AuditOnlyVerifierAttestationTests(unittest.TestCase):
    def test_caller_boolean_and_digest_without_verified_decision_cannot_stage(self):
        from app_contracts.verifier_attestation import VerifiedVerifierAttestation
        from app_contracts.verifier_process import VerifierProcessRequest, serialize_verifier_request

        class CallerClaimOnlyVerifier:
            def verify(self, prepared: VerifierInput):
                normal = AcceptingVerifier().verify(prepared)
                request = VerifierProcessRequest.from_verifier_input(prepared)
                return VerifiedVerifierAttestation(
                    verifier_result=normal,
                    key_id="fixture-key-1",
                    invocation_nonce="a" * 64,
                    request_digest=sha256_bytes(serialize_verifier_request(request)),
                    verifier_profile_digest="sha256:" + "b" * 64,
                    issued_at="2026-10-08T00:00:00Z",
                    attestation_digest="sha256:" + "c" * 64,
                    trust_enrollment_digest="sha256:" + "d" * 64,
                    independent_host_trust_established=True,
                    host_trust_decision_digest="sha256:" + "e" * 64,
                    host_trust_decision=None,
                )

        class NoTouchStage:
            save_calls = 0
            load_calls = 0

            def save(self, artifact):
                self.save_calls += 1
                raise AssertionError("caller claim must not stage")

            def load(self, digest):
                self.load_calls += 1
                raise AssertionError("caller claim must not stage")

        class Worker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                source = (ROOT / "fixtures/repository/project/calculator.py").read_text(
                    encoding="utf-8"
                )
                return WorkerProposal((("calculator.py", source + "\n# staged\n"),))

        stage = NoTouchStage()
        result = run_local_execution(
            valid_request(), Worker(), verifier=CallerClaimOnlyVerifier(),
            stage_sink=stage,
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "verifier-attestation-invalid")
        self.assertEqual((stage.save_calls, stage.load_calls), (0, 0))

    def test_authority_reviewed_host_decision_allows_verified_result(self):
        from app_contracts.verifier_attestation import VerifiedVerifierAttestation
        from app_contracts.verifier_process import VerifierProcessRequest, serialize_verifier_request
        from app_contracts.verifier_host_trust_decision import (
            build_signed_verifier_host_trust_decision,
            verify_verifier_host_trust_decision,
        )
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        class TrustedReceiptVerifier:
            def verify(self, prepared: VerifierInput):
                normal = AcceptingVerifier().verify(prepared)
                request = VerifierProcessRequest.from_verifier_input(prepared)
                request_digest = sha256_bytes(serialize_verifier_request(request))
                authority_key = Ed25519PrivateKey.generate()
                authority_public_key = authority_key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
                now = datetime.now(timezone.utc).replace(microsecond=0)
                enrollment_digest = "sha256:" + "d" * 64
                profile_digest = "sha256:" + "b" * 64
                key_id = "fixture-key-1"
                host_decision_bytes = build_signed_verifier_host_trust_decision(
                    decision_id="synthetic-executor-host-review",
                    authority_key_id="synthetic-authority-1",
                    enrollment_digest=enrollment_digest,
                    endpoint_url="https://verifier.example.test/v1/verify",
                    verifier_id=normal.verifier_id,
                    verifier_profile_digest=profile_digest,
                    verifier_key_id=key_id,
                    worker_host_id="worker-host-a",
                    verifier_host_id="verifier-host-b",
                    host_separation_evidence_digest="sha256:" + "f" * 64,
                    signing_key=authority_key,
                    issued_at=now,
                    expires_at=now + timedelta(hours=1),
                )
                host_decision = verify_verifier_host_trust_decision(
                    host_decision_bytes,
                    trusted_authority_keys={"synthetic-authority-1": authority_public_key},
                    expected_enrollment_digest=enrollment_digest,
                    expected_endpoint_url="https://verifier.example.test/v1/verify",
                    expected_verifier_id=normal.verifier_id,
                    expected_verifier_profile_digest=profile_digest,
                    expected_verifier_key_id=key_id,
                    expected_worker_host_id="worker-host-a",
                    expected_verifier_host_id="verifier-host-b",
                    expected_host_separation_evidence_digest="sha256:" + "f" * 64,
                    now=now,
                )
                return VerifiedVerifierAttestation(
                    verifier_result=normal,
                    key_id=key_id,
                    invocation_nonce="a" * 64,
                    request_digest=request_digest,
                    verifier_profile_digest=profile_digest,
                    issued_at="2026-10-08T00:00:00Z",
                    attestation_digest="sha256:" + "c" * 64,
                    trust_enrollment_digest=enrollment_digest,
                    independent_host_trust_established=True,
                    host_trust_decision_digest=host_decision.decision_digest,
                    host_trust_decision=host_decision,
                )

        class Worker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                source = (ROOT / "fixtures/repository/project/calculator.py").read_text(
                    encoding="utf-8"
                )
                return WorkerProposal((("calculator.py", source + "\n# staged\n"),))

        result = run_local_execution(
            valid_request(), Worker(), verifier=TrustedReceiptVerifier()
        )
        self.assertEqual(result.status, ExecutionStatus.VERIFIED, result.failure_code)
        self.assertTrue(result.verifier_signature_valid)
        self.assertTrue(result.verifier_independent_host_trust_established)
        self.assertRegex(result.verifier_host_trust_decision_digest, r"sha256:[0-9a-f]{64}")

    def test_signed_receipt_fails_before_durable_stage_calls(self):
        from app_contracts.verifier_attestation import VerifiedVerifierAttestation
        from app_contracts.verifier_process import VerifierProcessRequest, serialize_verifier_request

        class ReceiptVerifier:
            def verify(self, prepared: VerifierInput):
                normal = AcceptingVerifier().verify(prepared)
                request = VerifierProcessRequest.from_verifier_input(prepared)
                request_digest = sha256_bytes(serialize_verifier_request(request))
                return VerifiedVerifierAttestation(
                    verifier_result=normal,
                    key_id="fixture-key-1",
                    invocation_nonce="a" * 64,
                    request_digest=request_digest,
                    verifier_profile_digest="sha256:" + "b" * 64,
                    issued_at="2026-10-08T00:00:00Z",
                    attestation_digest="sha256:" + "c" * 64,
                    trust_enrollment_digest="sha256:" + "d" * 64,
                )

        class NoTouchStage:
            save_calls = 0
            load_calls = 0

            def save(self, artifact):
                self.save_calls += 1
                raise AssertionError("audit-only receipt must not stage")

            def load(self, digest):
                self.load_calls += 1
                raise AssertionError("audit-only receipt must not stage")

        class Worker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                source = (ROOT / "fixtures/repository/project/calculator.py").read_text(
                    encoding="utf-8"
                )
                return WorkerProposal((("calculator.py", source + "\n# staged\n"),))

        stage = NoTouchStage()
        result = run_local_execution(
            valid_request(), Worker(), verifier=ReceiptVerifier(), stage_sink=stage
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "verifier-trust-unestablished")
        self.assertEqual(result.verifier_attestation_digest, "sha256:" + "c" * 64)
        self.assertEqual(result.verifier_attestation_key_id, "fixture-key-1")
        self.assertEqual(result.verifier_attestation_profile_digest, "sha256:" + "b" * 64)
        self.assertEqual(result.verifier_trust_enrollment_digest, "sha256:" + "d" * 64)
        self.assertIs(result.verifier_signature_valid, True)
        self.assertIs(result.verifier_independent_host_trust_established, False)
        self.assertEqual((stage.save_calls, stage.load_calls), (0, 0))

    def test_malformed_enrollment_digest_invalidates_attestation_before_stage(self):
        from app_contracts.verifier_attestation import VerifiedVerifierAttestation
        from app_contracts.verifier_process import VerifierProcessRequest, serialize_verifier_request

        class MalformedReceiptVerifier:
            def verify(self, prepared: VerifierInput):
                normal = AcceptingVerifier().verify(prepared)
                request = VerifierProcessRequest.from_verifier_input(prepared)
                return VerifiedVerifierAttestation(
                    verifier_result=normal,
                    key_id="fixture-key-1",
                    invocation_nonce="a" * 64,
                    request_digest=sha256_bytes(serialize_verifier_request(request)),
                    verifier_profile_digest="sha256:" + "b" * 64,
                    issued_at="2026-10-08T00:00:00Z",
                    attestation_digest="sha256:" + "c" * 64,
                    trust_enrollment_digest="not-a-digest",
                )

        class NoTouchStage:
            save_calls = 0
            load_calls = 0

            def save(self, artifact):
                self.save_calls += 1
                raise AssertionError("invalid attestation must not stage")

            def load(self, digest):
                self.load_calls += 1
                raise AssertionError("invalid attestation must not stage")

        class Worker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                source = (ROOT / "fixtures/repository/project/calculator.py").read_text(
                    encoding="utf-8"
                )
                return WorkerProposal((
                    ("calculator.py", source + "\n# staged\n"),
                ))

        stage = NoTouchStage()
        result = run_local_execution(
            valid_request(), Worker(), verifier=MalformedReceiptVerifier(), stage_sink=stage
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "verifier-attestation-invalid")
        self.assertEqual((stage.save_calls, stage.load_calls), (0, 0))


class ExecutionRecordTests(unittest.TestCase):
    def test_executor_import_does_not_require_remote_snapshot_modules(self):
        script = """
import importlib.abc
import sys

blocked = {"app_contracts.github_snapshot", "app_contracts.remote_snapshot_workspace"}
class BlockRemoteModules(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in blocked:
            raise RuntimeError("remote module import blocked for local-only check")
        return None

sys.meta_path.insert(0, BlockRemoteModules())
from app_contracts.executor import MAX_VERIFIER_SNAPSHOT_FILE_BYTES
from app_contracts.executor import verifier_snapshot_tree_digest
assert MAX_VERIFIER_SNAPSHOT_FILE_BYTES == 262144
assert verifier_snapshot_tree_digest((("a.py", "100644", b"x"),)).startswith("sha256:")
print("local_executor_import=ok")
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env={
                "PYTHONPATH": str(ROOT / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, "isolated import failed")
        self.assertEqual(completed.stdout.strip(), "local_executor_import=ok")
        self.assertEqual(completed.stderr, "")

    def test_pinned_snapshot_reader_accepts_source_limit_and_enforces_total_limit(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot = Path(temporary_directory) / "snapshot"
            snapshot.mkdir()
            (snapshot / "large.bin").write_bytes(b"x" * 220_064)
            files = (("large.bin", "100644", b"x" * 220_064),)
            digest = executor_module.verifier_snapshot_tree_digest(files)
            self.assertEqual(_read_pinned_snapshot_files(snapshot, digest), files)

            oversized = Path(temporary_directory) / "oversized"
            oversized.mkdir()
            over_total_files = tuple(
                (f"file-{index}.bin", "100644", b"x" * 200_000)
                for index in range(3)
            )
            for path, _mode, content in over_total_files:
                (oversized / path).write_bytes(content)
            with self.assertRaisesRegex(
                ExecutionError,
                "^execution verifier input: pinned snapshot is invalid$",
            ):
                _read_pinned_snapshot_files(
                    oversized,
                    executor_module.verifier_snapshot_tree_digest(over_total_files),
                )

    def test_oversized_pinned_snapshot_fails_before_verifier_can_be_called(self):
        class CountingVerifier:
            calls = 0

            def verify(self, prepared):
                self.calls += 1
                raise AssertionError("oversized snapshot reached verifier")

        verifier = CountingVerifier()
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot = Path(temporary_directory) / "snapshot"
            snapshot.mkdir()
            for index in range(257):
                (snapshot / f"file-{index:03}.txt").write_bytes(b"x")
            commit_oid = "a" * 40
            pin = PinnedSnapshot(
                repository_id="fixture-repository",
                commit_oid=commit_oid,
                tree_digest=compute_snapshot_tree_digest(snapshot),
                snapshot_path=snapshot,
            )
            request = valid_request(
                snapshot_path=snapshot,
                base_commit=commit_oid,
                pinned_snapshot=pin,
            )
            content = "candidate"
            with self.assertRaisesRegex(
                ExecutionError, "^execution verifier input: pinned snapshot is invalid$"
            ):
                prepared = _build_verifier_input(
                    request=request,
                    proposal=WorkerProposal((("calculator.py", content),)),
                    staged={
                        "patch_digest": "sha256:" + "1" * 64,
                        "evidence_digest": "sha256:" + "2" * 64,
                        "verification_digest": "sha256:" + "3" * 64,
                    },
                    verified_contents=(("calculator.py", content),),
                    verified_contents_digest="sha256:" + "4" * 64,
                    replay_result_digest="sha256:" + "5" * 64,
                )
                verifier.verify(prepared)
        self.assertEqual(verifier.calls, 0)

    def test_complete_pinned_git_export_to_second_pass_flow_is_local_and_bound(self):
        from app_contracts.sandbox import CommandResult

        class FakeBackend:
            def __init__(self):
                self.sessions = []
                self.commands = []
                self.temp_roots = []

            def create(self, snapshot: Path, allowed_commands: set[str]):
                temporary = tempfile.TemporaryDirectory()
                root = Path(temporary.name)
                self.temp_roots.append(root)
                copied_snapshot = root / "snapshot"
                workspace = root / "workspace"
                shutil.copytree(snapshot, copied_snapshot)
                shutil.copytree(snapshot, workspace)
                for path in (workspace, *workspace.rglob("*")):
                    path.chmod(path.stat().st_mode | 0o200)
                backend = self

                class Session:
                    def __init__(self):
                        self.index = len(backend.sessions) + 1
                        self.snapshot = copied_snapshot
                        self.workspace = workspace
                        self.closed = False
                        self.initial_tree_digest = compute_snapshot_tree_digest(self.snapshot)

                    def run(self, argv, timeout_seconds=30):
                        backend.commands.append(
                            (self.index, tuple(argv), timeout_seconds)
                        )
                        return CommandResult(tuple(argv), 0, "test stdout sentinel", "test stderr sentinel")

                    def close(self):
                        self.closed = True
                        temporary.cleanup()

                session = Session()
                self.sessions.append(session)
                return session

        class FakeWorker:
            def __init__(self, content):
                self.content = content
                self.calls = 0
                self.received = None

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                self.received = task
                return WorkerProposal((("calculator.py", self.content),))

        class EchoVerifier:
            def __init__(self, verdict=VerifierVerdict.PASS):
                self.verdict = verdict
                self.calls = 0
                self.received = None

            def verify(self, prepared: VerifierInput) -> VerifierResult:
                self.calls += 1
                self.received = prepared
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="end-to-end-local-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=self.verdict,
                )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = root / "source-repository"
            shutil.copytree(ROOT / "fixtures/repository/project", repository)
            subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "add", "-A"], check=True
            )
            subprocess.run(
                [
                    "git", "-C", str(repository), "-c", "user.name=E2E Test",
                    "-c", "user.email=e2e@example.invalid", "commit", "--quiet", "-m",
                    "pinned base",
                ],
                check=True,
            )
            commit_oid = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            base_content = (repository / "calculator.py").read_text(encoding="utf-8")
            (repository / "calculator.py").write_text(
                base_content + "\n# uncommitted-source-sentinel\n", encoding="utf-8"
            )
            (repository / "untracked-source-sentinel.txt").write_text(
                "untracked-source-sentinel", encoding="utf-8"
            )
            source_status = subprocess.run(
                ["git", "-C", str(repository), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            local_repository = open_local_repository(repository)
            lease = export_local_commit_tree(local_repository, commit_oid, root)
            lease_path = lease.path
            try:
                self.assertEqual(
                    (lease.path / "calculator.py").read_text(encoding="utf-8"), base_content
                )
                self.assertFalse((lease.path / "untracked-source-sentinel.txt").exists())
                pin = PinnedSnapshot(
                    repository_id="fixture-repository",
                    commit_oid=commit_oid,
                    tree_digest=compute_snapshot_tree_digest(lease.path),
                    snapshot_path=lease.path,
                )
                command = ("python3", "-c", "print('pinned-e2e-test')")
                request = ExecutionRequest(
                    process_id="process-e2e-001",
                    task_id="task-e2e-001",
                    repository_id=pin.repository_id,
                    base_commit=pin.commit_oid,
                    snapshot_path=lease.path,
                    allowed_commands=frozenset({"python3"}),
                    declared_change_paths=("calculator.py",),
                    test_command=command,
                    test_timeout_seconds=23,
                    pinned_snapshot=pin,
                )
                proposed_content = base_content + "\n# prepared-candidate\n"

                success_backend = FakeBackend()
                success_worker = FakeWorker(proposed_content)
                success_verifier = EchoVerifier()
                success = run_local_execution(
                    request,
                    success_worker,
                    verifier=success_verifier,
                    sandbox_backend=success_backend,
                    require_pinned_snapshot=True,
                )
                self.assertEqual(success.status, ExecutionStatus.VERIFIED)
                self.assertEqual(success_worker.calls, 1)
                self.assertEqual(
                    success_worker.received.base_commit, commit_oid
                )
                self.assertEqual(
                    success_worker.received.snapshot_tree_digest, pin.tree_digest
                )
                self.assertEqual(success_verifier.calls, 1)
                self.assertEqual(success_verifier.received.base_commit, commit_oid)
                self.assertEqual(
                    success_verifier.received.snapshot_tree_digest, pin.tree_digest
                )
                self.assertEqual(
                    success_verifier.received.snapshot_files,
                    tuple(
                        (
                            path.relative_to(lease.path).as_posix(),
                            "100755" if path.stat().st_mode & 0o111 else "100644",
                            path.read_bytes(),
                        )
                        for path in sorted(lease.path.rglob("*"))
                        if path.is_file() and not path.is_symlink()
                    ),
                )
                self.assertEqual(
                    success_verifier.received.verified_contents,
                    (("calculator.py", proposed_content),),
                )
                self.assertEqual(success_backend.sessions[0].initial_tree_digest, pin.tree_digest)
                self.assertEqual(success_backend.sessions[1].initial_tree_digest, pin.tree_digest)
                self.assertEqual(
                    [command_call for command_call in success_backend.commands if command_call[0] == 2],
                    [(2, command, 23)],
                )
                self.assertTrue(all(session.closed for session in success_backend.sessions))
                self.assertTrue(all(not path.exists() for path in success_backend.temp_roots))

                snapshot_denial_backend = FakeBackend()
                snapshot_denial_worker = FakeWorker(proposed_content)
                snapshot_denial_verifier = EchoVerifier()
                wrong_pin = replace(pin, tree_digest="sha256:" + "e" * 64)
                with self.assertRaisesRegex(
                    ExecutionError, "^execution snapshot: digest mismatch$"
                ):
                    run_local_execution(
                        replace(request, pinned_snapshot=wrong_pin),
                        snapshot_denial_worker,
                        verifier=snapshot_denial_verifier,
                        sandbox_backend=snapshot_denial_backend,
                        require_pinned_snapshot=True,
                    )
                self.assertEqual(snapshot_denial_worker.calls, 0)
                self.assertEqual(snapshot_denial_verifier.calls, 0)
                self.assertEqual(len(snapshot_denial_backend.sessions), 1)
                self.assertTrue(snapshot_denial_backend.sessions[0].closed)
                self.assertTrue(all(not path.exists() for path in snapshot_denial_backend.temp_roots))

                denial_backend = FakeBackend()
                denial_worker = FakeWorker(proposed_content)
                denial_verifier = EchoVerifier(VerifierVerdict.BLOCKED)
                denied = run_local_execution(
                    request,
                    denial_worker,
                    verifier=denial_verifier,
                    sandbox_backend=denial_backend,
                    require_pinned_snapshot=True,
                )
                self.assertEqual(denied.status, ExecutionStatus.FAILED)
                self.assertEqual(denied.failure_code, "verifier-not-pass")
                self.assertEqual(denial_worker.calls, 1)
                self.assertEqual(denial_verifier.calls, 1)
                self.assertTrue(all(session.closed for session in denial_backend.sessions))
                self.assertTrue(all(not path.exists() for path in denial_backend.temp_roots))
                self.assertEqual(
                    subprocess.run(
                        ["git", "-C", str(repository), "status", "--porcelain"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout,
                    source_status,
                )
                serialized = repr((success, denied))
                for sentinel in (
                    str(repository),
                    "uncommitted-source-sentinel",
                    "untracked-source-sentinel",
                    "prepared-candidate",
                    "pinned-e2e-test",
                    "test stdout sentinel",
                    "test stderr sentinel",
                ):
                    self.assertNotIn(sentinel, serialized)
            finally:
                lease.close()
                self.assertFalse(lease_path.exists())

    def test_pinned_verifier_replays_command_in_fresh_sandbox_and_closes_it(self):
        from app_contracts.sandbox import CommandResult

        class FakeBackend:
            def __init__(self, replay_returncode=0):
                self.replay_returncode = replay_returncode
                self.sessions = []
                self.commands = []
                self.events = []
                self.temp_roots = []

            def create(self, snapshot: Path, allowed_commands: set[str]):
                temporary = tempfile.TemporaryDirectory()
                root = Path(temporary.name)
                self.temp_roots.append(root)
                copied_snapshot = root / "snapshot"
                workspace = root / "workspace"
                shutil.copytree(snapshot, copied_snapshot)
                shutil.copytree(snapshot, workspace)
                for path in (workspace, *workspace.rglob("*")):
                    path.chmod(path.stat().st_mode | 0o200)
                backend = self

                class Session:
                    def __init__(self):
                        self.index = len(backend.sessions) + 1
                        self.snapshot = copied_snapshot
                        self.workspace = workspace
                        self.closed = False
                        self.initial_tree_digest = compute_snapshot_tree_digest(self.snapshot)

                    def run(self, argv, timeout_seconds=30):
                        backend.events.append(f"sandbox.run.{self.index}")
                        backend.commands.append((tuple(argv), timeout_seconds, self))
                        code = backend.replay_returncode if len(backend.sessions) == 2 else 0
                        if len(backend.sessions) == 2:
                            self.applied_contents = (
                                self.workspace / "calculator.py"
                            ).read_text(encoding="utf-8")
                        return CommandResult(
                            tuple(argv), code, "REPLAY-STDOUT-CANARY", "REPLAY-STDERR-CANARY"
                        )

                    def close(self):
                        backend.events.append(f"sandbox.close.{self.index}")
                        self.closed = True
                        temporary.cleanup()

                self.events.append(f"sandbox.create.{len(self.sessions) + 1}")
                session = Session()
                self.sessions.append(session)
                return session

        class FakeWorker:
            def __init__(self, events):
                self.events = events

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.events.append("worker.propose")
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                self.content = original + "\n# independently replayed\n"
                return WorkerProposal((("calculator.py", self.content),))

        command = ("python3", "-c", "print('allowlisted')")
        for replay_returncode in (0, 1):
            with self.subTest(replay_returncode=replay_returncode), pinned_test_request(
                test_command=command, test_timeout_seconds=17
            ) as request:
                backend = FakeBackend(replay_returncode)
                worker = FakeWorker(backend.events)

                class OrderedVerifier(AcceptingVerifier):
                    def verify(self, prepared: VerifierInput) -> VerifierResult:
                        backend.events.append("verifier.verify")
                        return super().verify(prepared)

                verifier = OrderedVerifier()
                lease_path = request.snapshot_path
                result = run_local_execution(
                    request,
                    worker,
                    verifier=verifier,
                    sandbox_backend=backend,
                    require_pinned_snapshot=True,
                )

                self.assertEqual(len(backend.sessions), 2)
                first, replay = backend.sessions
                self.assertIsNot(first, replay)
                self.assertNotEqual(first.workspace, replay.workspace)
                self.assertEqual(first.initial_tree_digest, request.pinned_snapshot.tree_digest)
                self.assertEqual(replay.initial_tree_digest, request.pinned_snapshot.tree_digest)
                self.assertTrue(first.closed)
                self.assertTrue(replay.closed)
                self.assertEqual(len(backend.commands), 2)
                self.assertEqual(backend.commands[1][:2], (command, 17))
                expected_events = [
                    "sandbox.create.1",
                    "worker.propose",
                    "sandbox.run.1",
                    "sandbox.create.2",
                    "sandbox.run.2",
                    "sandbox.close.2",
                ]
                if replay_returncode == 0:
                    expected_events.append("verifier.verify")
                expected_events.append("sandbox.close.1")
                self.assertEqual(backend.events, expected_events)
                self.assertTrue(all(not root.exists() for root in backend.temp_roots))
                self.assertEqual(
                    replay.applied_contents, worker.content
                )
                if replay_returncode == 0:
                    self.assertEqual(result.status, ExecutionStatus.VERIFIED)
                    self.assertEqual(verifier.calls, 1)
                    self.assertEqual(result.snapshot_origin, "local_git_commit")
                    serialized_result = repr(result)
                    for sentinel in (
                        str(request.snapshot_path),
                        worker.content,
                        "allowlisted",
                        "REPLAY-STDOUT-CANARY",
                        "REPLAY-STDERR-CANARY",
                    ):
                        self.assertNotIn(sentinel, serialized_result)
                    self.assertNotIn("snapshot_path", ExecutionResult.__dataclass_fields__)
                    self.assertNotIn("verified_contents", ExecutionResult.__dataclass_fields__)
                    self.assertNotIn("test_command", ExecutionResult.__dataclass_fields__)
                    self.assertNotIn("stdout", ExecutionResult.__dataclass_fields__)
                    self.assertNotIn("stderr", ExecutionResult.__dataclass_fields__)
                    self.assertNotIn("environment", ExecutionResult.__dataclass_fields__)
                    self.assertEqual(
                        verifier.received.base_commit, request.pinned_snapshot.commit_oid
                    )
                    self.assertEqual(
                        verifier.received.snapshot_tree_digest,
                        request.pinned_snapshot.tree_digest,
                    )
                    self.assertRegex(
                        verifier.received.replay_result_digest, r"^sha256:[0-9a-f]{64}$"
                    )
                    self.assertEqual(
                        result.verifier_result.replay_result_digest,
                        verifier.received.replay_result_digest,
                    )
                else:
                    self.assertEqual(result.status, ExecutionStatus.FAILED)
                    self.assertEqual(result.failure_code, "verification-replay-failed")
                    self.assertEqual(verifier.calls, 0)
            self.assertFalse(lease_path.exists())

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
            {
                "process_id", "task_id", "repository_id", "base_commit",
                "declared_change_paths", "snapshot_tree_digest", "snapshot_origin",
                "task_instruction", "context_files", "snapshot_claim_digest",
            },
        )
        self.assertIsNone(task.snapshot_tree_digest)
        self.assertEqual(task.snapshot_origin, "unverified_local_test")
        self.assertIsNone(task.task_instruction)
        self.assertEqual(task.context_files, ())
        self.assertEqual(set(WorkerProposal.__dataclass_fields__), {"changes"})

    def test_verifier_contract_is_separate_and_explicitly_local(self):
        class FakeVerifier:
            def verify(self, prepared: VerifierInput) -> VerifierResult:
                self.received = prepared
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
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
            repository_id="fixture-repository",
            base_commit="a" * 40,
            snapshot_tree_digest=None,
            declared_change_paths=("calculator.py",),
            verified_contents=(("calculator.py", "safe content"),),
            test_command=("python3", "-m", "unittest"),
            test_timeout_seconds=30,
            patch_digest="sha256:" + "a" * 64,
            evidence_digest="sha256:" + "b" * 64,
            verification_digest="sha256:" + "c" * 64,
            verified_contents_digest="sha256:" + "d" * 64,
        )
        result = verifier.verify(prepared)
        self.assertTrue(isinstance(verifier, IndependentVerifier))
        self.assertEqual(verifier.received.evidence_origin, "local_test")
        self.assertNotIn("snapshot_path", VerifierInput.__dataclass_fields__)
        self.assertNotIn("stdout", VerifierInput.__dataclass_fields__)
        self.assertNotIn("stderr", VerifierInput.__dataclass_fields__)
        self.assertNotIn("environment", VerifierInput.__dataclass_fields__)
        self.assertNotIn("credential", VerifierInput.__dataclass_fields__)
        with self.assertRaises(FrozenInstanceError):
            prepared.base_commit = "changed"
        self.assertEqual(result.verdict, VerifierVerdict.PASS)
        self.assertEqual(result.evidence_origin, "local_test")
        self.assertEqual(
            set(VerifierInput.__dataclass_fields__),
            {
                "process_id", "repository_id", "base_commit", "snapshot_tree_digest",
                "declared_change_paths", "verified_contents", "test_command",
                "test_timeout_seconds", "patch_digest", "evidence_digest",
                "verification_digest", "verified_contents_digest", "evidence_origin",
                "replay_result_digest", "snapshot_files", "snapshot_claim_digest",
            },
        )

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
            with pinned_test_request(
                test_command=("python3", "-c", "print('ok')")
            ) as request:
                result = run_local_execution(
                    request,
                    worker,
                    verifier=verifier,
                    require_pinned_snapshot=True,
                )

        self.assertEqual(worker.calls, 1)
        prepare_call.assert_called_once()
        self.assertEqual(worker.task.declared_change_paths, ("calculator.py",))
        self.assertEqual(worker.task.base_commit, request.pinned_snapshot.commit_oid)
        self.assertEqual(worker.task.snapshot_tree_digest, request.pinned_snapshot.tree_digest)
        self.assertEqual(worker.task.snapshot_origin, "local_git_commit")
        self.assertNotIn("snapshot_path", WorkerInput.__dataclass_fields__)
        self.assertNotIn(str(request.snapshot_path), repr(worker.task))
        self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
        self.assertEqual(result.snapshot_tree_digest, request.pinned_snapshot.tree_digest)
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
        self.assertEqual(verifier.received.repository_id, request.repository_id)
        self.assertEqual(verifier.received.base_commit, request.pinned_snapshot.commit_oid)
        self.assertEqual(
            verifier.received.snapshot_tree_digest, request.pinned_snapshot.tree_digest
        )
        self.assertEqual(
            verifier.received.declared_change_paths, request.declared_change_paths
        )
        self.assertEqual(
            verifier.received.verified_contents, (("calculator.py", worker.content),)
        )
        self.assertEqual(verifier.received.test_command, request.test_command)
        self.assertEqual(
            verifier.received.test_timeout_seconds, request.test_timeout_seconds
        )
        self.assertEqual(result.verifier_result.verifier_id, "test-verifier")
        self.assertNotIn("approval", ExecutionResult.__dataclass_fields__)
        self.assertNotIn("publishable", ExecutionResult.__dataclass_fields__)

    def test_required_durable_stage_without_sink_rejects_before_worker(self):
        class CountingWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                return WorkerProposal(())

        for sink, message in (
            (None, "execution stage: durable sink is required"),
            (object(), "execution stage: durable sink is invalid"),
        ):
            with self.subTest(sink=sink):
                worker = CountingWorker()
                with self.assertRaisesRegex(ExecutionError, f"^{message}$"):
                    run_local_execution(
                        valid_request(),
                        worker,
                        verifier=AcceptingVerifier(),
                        stage_sink=sink,
                        require_durable_stage=True,
                    )
                self.assertEqual(worker.calls, 0)

    def test_snapshot_copy_digest_mismatch_stops_before_worker_and_preparation(self):
        from app_contracts.sandbox import LocalProcessSandbox

        class TrackingBackend:
            def __init__(self):
                self.closed = 0

            def create(self, snapshot: Path, allowed_commands: set[str]):
                sandbox = LocalProcessSandbox(snapshot, allowed_commands)
                copied_file = sandbox.snapshot / "calculator.py"
                copied_file.chmod(0o644)
                copied_file.write_text("substituted snapshot content\n", encoding="utf-8")
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

        class CountingWorker:
            calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                return WorkerProposal((("calculator.py", "unused"),))

        worker = CountingWorker()
        backend = TrackingBackend()
        verifier = AcceptingVerifier()
        with pinned_test_request() as request:
            with patch("app_contracts.executor.prepare_change") as prepare:
                with self.assertRaisesRegex(ExecutionError, "^execution snapshot: digest mismatch$"):
                    run_local_execution(request, worker, verifier=verifier, sandbox_backend=backend)

        self.assertEqual(worker.calls, 0)
        self.assertEqual(prepare.call_count, 0)
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(backend.closed, 1)

    def test_pinned_tree_mismatch_and_commit_binding_stop_before_collaborators(self):
        class FakeBackend:
            def __init__(self):
                self.created = 0
                self.closed = 0
                self.temp_roots = []

            def create(self, snapshot: Path, allowed_commands: set[str]):
                self.created += 1
                temporary = tempfile.TemporaryDirectory()
                root = Path(temporary.name)
                self.temp_roots.append(root)
                copied_snapshot = root / "snapshot"
                workspace = root / "workspace"
                shutil.copytree(snapshot, copied_snapshot)
                shutil.copytree(snapshot, workspace)
                for path in (workspace, *workspace.rglob("*")):
                    path.chmod(path.stat().st_mode | 0o200)
                backend = self

                class Session:
                    def __init__(self):
                        self.snapshot = copied_snapshot
                        self.workspace = workspace

                    def run(self, argv, timeout_seconds=30):
                        raise AssertionError("no command should run")

                    def close(self):
                        backend.closed += 1
                        temporary.cleanup()

                return Session()

        class CountingWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                return WorkerProposal((("calculator.py", "unused"),))

        with pinned_test_request() as request:
            backend = FakeBackend()
            worker = CountingWorker()
            verifier = AcceptingVerifier()
            wrong_tree = replace(
                request.pinned_snapshot, tree_digest="sha256:" + "f" * 64
            )
            tampered_request = replace(request, pinned_snapshot=wrong_tree)
            with patch("app_contracts.executor.prepare_change") as prepare:
                with self.assertRaisesRegex(
                    ExecutionError, "^execution snapshot: digest mismatch$"
                ):
                    run_local_execution(
                        tampered_request, worker, verifier=verifier, sandbox_backend=backend
                    )
            self.assertEqual(backend.created, 1)
            self.assertEqual(backend.closed, 1)
            self.assertEqual(worker.calls, 0)
            self.assertEqual(verifier.calls, 0)
            prepare.assert_not_called()
            self.assertTrue(all(not root.exists() for root in backend.temp_roots))

            malformed_backend = FakeBackend()
            with self.assertRaisesRegex(
                ExecutionError, "^execution request: pinned snapshot binding is invalid$"
            ):
                replace(request, base_commit="a" * 40)
            self.assertEqual(malformed_backend.created, 0)

    def test_local_coordinator_returns_no_success_when_preparation_fails(self):
        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                return WorkerProposal((("calculator.py", "invalid but different"),))

        request = valid_request(test_command=("python3", "-c", "raise SystemExit(1)"))
        result = run_local_execution(
            request, FakeWorker(), verifier=AcceptingVerifier()
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(
            result.failure_code, "target-test-allowlisted-tests-failed"
        )

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
        result = run_local_execution(
            valid_request(), FailingWorker(), verifier=AcceptingVerifier(),
            sandbox_backend=backend,
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "worker-failed")
        self.assertEqual(backend.closed, 1)
        self.assertIsInstance(backend, ExecutorSandboxBackend)

    def test_worker_timeout_is_not_retried_or_exposed(self):
        class TimedOutWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                raise TimeoutError("SECRET worker payload")

        worker = TimedOutWorker()
        result = run_local_execution(valid_request(), worker, verifier=AcceptingVerifier())
        self.assertEqual(worker.calls, 1)
        self.assertEqual(result.failure_code, "worker-failed")
        self.assertIsNone(result.prepared_change_id)
        self.assertNotIn("SECRET", repr(result))

    def test_verifier_exception_is_not_retried_or_exposed(self):
        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                return WorkerProposal((("calculator.py", original + "\n# local change\n"),))

        class TimedOutVerifier:
            def __init__(self):
                self.calls = 0

            def verify(self, prepared: VerifierInput) -> VerifierResult:
                self.calls += 1
                raise TimeoutError("SECRET verifier response")

        verifier = TimedOutVerifier()
        result = run_local_execution(
            valid_request(test_command=("python3", "-c", "print('ok')")),
            FakeWorker(),
            verifier=verifier,
        )
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "verifier-failed")
        self.assertIsNone(result.prepared_change_id)
        self.assertTrue(result.evidence_digest.startswith("sha256:"))
        self.assertNotIn("SECRET", repr(result))

    def test_execution_evidence_contains_digests_not_raw_inputs_or_outputs(self):
        proposal_canary = "PROPOSAL-CANARY-RAW-CONTENT"
        command_canary = "COMMAND-OUTPUT-CANARY"

        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                return WorkerProposal(
                    (("calculator.py", original + f"\n# {proposal_canary}\n"),)
                )

        result = run_local_execution(
            valid_request(test_command=("python3", "-c", f"print('{command_canary}')")),
            FakeWorker(),
            verifier=AcceptingVerifier(),
        )
        serialized = json.dumps(asdict(result))
        self.assertNotIn(proposal_canary, serialized)
        self.assertNotIn(command_canary, serialized)
        self.assertEqual(result.evidence_origin, "local_test")
        self.assertEqual(result.snapshot_origin, "unverified_local_test")
        self.assertIn("injected_worker", result.limitations)
        self.assertIn("remote_snapshot_unverified", result.limitations)
        self.assertIn("publication_not_attempted", result.limitations)
        self.assertNotIn("prompt", ExecutionResult.__dataclass_fields__)
        self.assertNotIn("task_description", WorkerInput.__dataclass_fields__)

    def test_staged_change_digest_binds_verified_prepared_change(self):
        content_canary = "STAGED-DIGEST-PROPOSAL-CANARY"
        request = valid_request(test_command=("python3", "-c", "print('ok')"))
        staged = {
            "process_id": request.process_id,
            "repository_id": request.repository_id,
            "base_commit": request.base_commit,
            "staged_change_id": "staged-local-001",
            "patch_digest": "sha256:" + "a" * 64,
            "evidence_digest": "sha256:" + "b" * 64,
            "verification_digest": "sha256:" + "c" * 64,
        }
        expected_digest = sha256_digest(staged)

        class LocalTestBackend:
            def create(self, snapshot: Path, allowed_commands: set[str]):
                local_snapshot = snapshot

                class Session:
                    snapshot = local_snapshot
                    workspace = local_snapshot

                    def run(self, argv, timeout_seconds=30):
                        raise AssertionError("the fake preparation must not run commands")

                    def close(self):
                        pass

                return Session()

        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                return WorkerProposal((("calculator.py", f"proposal {content_canary}"),))

        def run_with(layered_verifier):
            with patch(
                "app_contracts.executor.prepare_change",
                return_value=SimpleNamespace(
                    staged_change=dict(staged),
                    verified_contents=(("calculator.py", f"proposal {content_canary}"),),
                ),
            ):
                return run_local_execution(
                    request,
                    FakeWorker(),
                    verifier=layered_verifier,
                    sandbox_backend=LocalTestBackend(),
                )

        verified = run_with(AcceptingVerifier())
        self.assertEqual(verified.status, ExecutionStatus.VERIFIED)
        self.assertEqual(verified.staged_change_digest, expected_digest)
        self.assertRegex(verified.staged_change_digest, r"^sha256:[0-9a-f]{64}$")
        serialized = json.dumps(asdict(verified))
        self.assertIn(expected_digest, serialized)
        self.assertNotIn(content_canary, serialized)

        class FailingVerifier:
            def verify(self, prepared: VerifierInput):
                raise TimeoutError("SECRET verifier response")

        verifier_failed = run_with(FailingVerifier())
        self.assertEqual(verifier_failed.status, ExecutionStatus.FAILED)
        self.assertEqual(verifier_failed.failure_code, "verifier-failed")
        self.assertEqual(verifier_failed.staged_change_digest, expected_digest)
        self.assertNotIn(content_canary, json.dumps(asdict(verifier_failed)))

        class DenyingVerifier:
            def verify(self, prepared: VerifierInput) -> VerifierResult:
                genuine = AcceptingVerifier().verify(prepared)
                return VerifierResult(**{**genuine.__dict__, "verdict": VerifierVerdict.FAIL})

        denied = run_with(DenyingVerifier())
        self.assertEqual(denied.status, ExecutionStatus.FAILED)
        self.assertEqual(denied.failure_code, "verifier-not-pass")
        self.assertEqual(denied.staged_change_digest, expected_digest)

        class FailingWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                raise RuntimeError("injected worker failure")

        with patch("app_contracts.executor.prepare_change") as prepare:
            worker_failed = run_local_execution(
                request,
                FailingWorker(),
                verifier=AcceptingVerifier(),
                sandbox_backend=LocalTestBackend(),
            )
        prepare.assert_not_called()
        self.assertEqual(worker_failed.status, ExecutionStatus.FAILED)
        self.assertEqual(worker_failed.failure_code, "worker-failed")
        self.assertIsNone(worker_failed.staged_change_digest)

    def test_staged_change_digest_survives_pinned_replay_failure(self):
        from app_contracts.sandbox import CommandResult

        captured: dict = {}

        class FakeBackend:
            def __init__(self):
                self.sessions = []
                self.temp_roots = []

            def create(self, snapshot: Path, allowed_commands: set[str]):
                temporary = tempfile.TemporaryDirectory()
                root = Path(temporary.name)
                self.temp_roots.append(root)
                copied_snapshot = root / "snapshot"
                workspace = root / "workspace"
                shutil.copytree(snapshot, copied_snapshot)
                shutil.copytree(snapshot, workspace)
                for path in (workspace, *workspace.rglob("*")):
                    path.chmod(path.stat().st_mode | 0o200)
                backend = self

                class Session:
                    def __init__(self):
                        self.index = len(backend.sessions) + 1
                        self.snapshot = copied_snapshot
                        self.workspace = workspace

                    def run(self, argv, timeout_seconds=30):
                        if len(backend.sessions) == 2:
                            return CommandResult(tuple(argv), 1, "replay stdout", "replay stderr")
                        return CommandResult(tuple(argv), 0, "prepare stdout", "prepare stderr")

                    def close(self):
                        temporary.cleanup()

                session = Session()
                self.sessions.append(session)
                return session

        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                self.content = original + "\n# replay-failure-canary\n"
                return WorkerProposal((("calculator.py", self.content),))

        with pinned_test_request(test_command=("python3", "-c", "print('ok')")) as request:
            real_prepare = prepare_change

            def capturing_prepare(sandbox, **kwargs):
                prepared = real_prepare(sandbox, **kwargs)
                captured["staged_change"] = dict(prepared.staged_change)
                return prepared

            with patch("app_contracts.executor.prepare_change", side_effect=capturing_prepare):
                result = run_local_execution(
                    request,
                    FakeWorker(),
                    verifier=AcceptingVerifier(),
                    sandbox_backend=FakeBackend(),
                    require_pinned_snapshot=True,
                )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "verification-replay-failed")
        self.assertIsNotNone(captured.get("staged_change"))
        self.assertEqual(result.staged_change_digest, sha256_digest(captured["staged_change"]))
        self.assertNotIn("replay-failure-canary", json.dumps(asdict(result)))

    def test_local_executor_types_and_imports_expose_no_publication_capability(self):
        forbidden_fields = {
            "token", "access_token", "credential", "credentials", "gateway",
            "broker", "actuator", "publication_client", "github_client",
        }
        records = (
            ExecutionRequest, WorkerInput, WorkerProposal, VerifierInput,
            VerifierResult, ExecutionResult,
        )
        for record in records:
            self.assertTrue(forbidden_fields.isdisjoint(record.__dataclass_fields__))

        source = Path(executor_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = set()
        called_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add((node.module or "").lower())
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id.lower())
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr.lower())
        forbidden_modules = {"gateway", "broker", "actuator", "publication", "github_app"}
        self.assertTrue(
            all(not any(forbidden in module for module in imported_modules) for forbidden in forbidden_modules)
        )
        self.assertTrue(
            {"publish_pull_request", "publish_verified_files", "create_pull_request"}.isdisjoint(
                called_names
            )
        )

    def test_composed_executor_orders_local_fakes_and_stops_after_first_failure(self):
        from app_contracts.sandbox import LocalProcessSandboxBackend

        self.assertIn("Development fallback", LocalProcessSandboxBackend.__doc__)
        self.assertIn("development-only", executor_module.run_local_execution.__doc__)
        request = valid_request()
        staged = {
            "process_id": request.process_id,
            "repository_id": request.repository_id,
            "base_commit": request.base_commit,
            "staged_change_id": "staged-local-001",
            "patch_digest": "sha256:" + "a" * 64,
            "evidence_digest": "sha256:" + "b" * 64,
            "verification_digest": "sha256:" + "c" * 64,
        }

        def exercise(worker_output, preparation_error=None, prepared_contents=None):
            calls = []

            class LocalTestBackend:
                def create(self, snapshot: Path, allowed_commands: set[str]):
                    calls.append("sandbox.create")
                    local_snapshot = snapshot

                    class Session:
                        snapshot = local_snapshot
                        workspace = local_snapshot

                        def run(self, argv, timeout_seconds=30):
                            raise AssertionError("the fake preparation must not run commands")

                        def close(self):
                            calls.append("sandbox.close")

                    return Session()

            class FakeWorker:
                def propose(self, task: WorkerInput):
                    calls.append("worker.propose")
                    return worker_output

            class FakeVerifier:
                calls_count = 0

                def verify(self, prepared: VerifierInput):
                    self.calls_count += 1
                    calls.append("verifier.verify")
                    return VerifierResult(
                        process_id=prepared.process_id,
                        base_commit=prepared.base_commit,
                        snapshot_tree_digest=prepared.snapshot_tree_digest,
                        replay_result_digest=prepared.replay_result_digest,
                        verifier_id="local-fake-verifier",
                        patch_digest=prepared.patch_digest,
                        evidence_digest=prepared.evidence_digest,
                        verification_digest=prepared.verification_digest,
                        verified_contents_digest=prepared.verified_contents_digest,
                        verdict=VerifierVerdict.PASS,
                    )

            verifier = FakeVerifier()

            def prepare(*_args, **_kwargs):
                calls.append("prepare_change")
                if preparation_error is not None:
                    raise preparation_error
                return SimpleNamespace(
                    staged_change=staged,
                    verified_contents=(
                        (("calculator.py", "proposal"),)
                        if prepared_contents is None
                        else prepared_contents
                    ),
                )

            with patch("app_contracts.executor.prepare_change", side_effect=prepare) as prepare_mock:
                try:
                    result = run_local_execution(
                        request,
                        FakeWorker(),
                        verifier=verifier,
                        sandbox_backend=LocalTestBackend(),
                    )
                except Exception as exc:
                    result = exc
            return result, calls, verifier.calls_count, prepare_mock.call_count

        valid_proposal = WorkerProposal((("calculator.py", "proposal"),))
        result, calls, verifier_calls, prepare_calls = exercise(valid_proposal)
        self.assertIsInstance(result, ExecutionResult, repr(result))
        self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
        self.assertEqual(
            calls,
            ["sandbox.create", "worker.propose", "prepare_change", "verifier.verify", "sandbox.close"],
        )
        self.assertEqual(verifier_calls, 1)
        self.assertEqual(prepare_calls, 1)
        self.assertEqual(result.evidence_origin, "local_test")

        result, calls, verifier_calls, prepare_calls = exercise(object())
        self.assertIsInstance(result, ExecutionError)
        self.assertEqual(str(result), "execution proposal: shape is invalid")
        self.assertEqual(calls, ["sandbox.create", "worker.propose", "sandbox.close"])
        self.assertEqual(verifier_calls, 0)
        self.assertEqual(prepare_calls, 0)

        result, calls, verifier_calls, prepare_calls = exercise(
            valid_proposal, ContractValidationError("preparation denied")
        )
        self.assertIsInstance(result, ContractValidationError)
        self.assertEqual(str(result), "preparation denied")
        self.assertEqual(
            calls, ["sandbox.create", "worker.propose", "prepare_change", "sandbox.close"]
        )
        self.assertEqual(verifier_calls, 0)
        self.assertEqual(prepare_calls, 1)

        result, calls, verifier_calls, prepare_calls = exercise(
            valid_proposal, prepared_contents=(("other.py", "proposal"),)
        )
        self.assertIsInstance(result, ExecutionError)
        self.assertEqual(str(result), "execution verifier input: prepared scope is invalid")
        self.assertEqual(
            calls, ["sandbox.create", "worker.propose", "prepare_change", "sandbox.close"]
        )
        self.assertEqual(verifier_calls, 0)
        self.assertEqual(prepare_calls, 1)

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
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
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
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="test-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=self.verdict,
                )

        for verdict in (VerifierVerdict.FAIL, VerifierVerdict.BLOCKED):
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

        with self.assertRaisesRegex(
            ExecutionError, "^execution verifier: result shape is invalid$"
        ):
            run_local_execution(
                valid_request(test_command=("python3", "-c", "print('ok')")),
                FakeWorker(),
                verifier=ReturningVerifier("unknown"),
            )

    def test_malformed_verifier_results_are_denied_without_echoing_values(self):
        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                return WorkerProposal((("calculator.py", original + "\n# local change\n"),))

        class MalformedVerifier:
            def __init__(self, transform):
                self.transform = transform

            def verify(self, prepared: VerifierInput):
                genuine = AcceptingVerifier().verify(prepared)
                return self.transform(genuine)

        malformed = (
            None,
            {"verifier_id": "SECRET-RAW-VALUE"},
            lambda result: SimpleNamespace(**result.__dict__),
            lambda result: VerifierResult(**{**result.__dict__, "verifier_id": "SECRET RAW VALUE"}),
            lambda result: VerifierResult(**{**result.__dict__, "verdict": "pass"}),
            lambda result: VerifierResult(**{**result.__dict__, "blocker_codes": ["bad"]}),
            lambda result: VerifierResult(
                **{**result.__dict__, "blocker_codes": tuple(f"blocker-{i}" for i in range(17))}
            ),
        )
        for value in malformed:
            transform = value if callable(value) else lambda _result, fixed=value: fixed
            with self.subTest(result_type=type(value).__name__), self.assertRaisesRegex(
                ExecutionError, "^execution verifier: result shape is invalid$"
            ) as raised:
                run_local_execution(
                    valid_request(test_command=("python3", "-c", "print('ok')")),
                    FakeWorker(),
                    verifier=MalformedVerifier(transform),
                )
            self.assertNotIn("SECRET RAW VALUE", str(raised.exception))

        for field in (
            "process_id", "base_commit", "snapshot_tree_digest", "replay_result_digest",
            "patch_digest", "evidence_digest", "verification_digest",
            "verified_contents_digest",
        ):
            with self.subTest(binding=field), self.assertRaisesRegex(
                ExecutionError, "^execution verifier: result binding mismatch$"
            ):
                run_local_execution(
                    valid_request(test_command=("python3", "-c", "print('ok')")),
                    FakeWorker(),
                    verifier=MalformedVerifier(
                        lambda result: VerifierResult(
                            **{
                                **result.__dict__,
                                field: (
                                    "sha256:" + "f" * 64
                                    if field.endswith("digest")
                                    else "foreign-value"
                                ),
                            }
                        )
                    ),
                )

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

    def test_pinned_request_rejects_identity_or_path_mismatch(self):
        for overrides in (
            {"repository_id": "other-repository"},
            {"base_commit": "b" * 40},
            {"snapshot_path": ROOT / "fixtures"},
            {"pinned_snapshot": "not-a-pinned-record"},
        ):
            with self.subTest(overrides=tuple(overrides)):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: pinned snapshot binding is invalid$"
                ):
                    with pinned_test_request(**overrides):
                        self.fail("mismatched pinned request unexpectedly constructed")

    def test_pinned_execution_path_rejects_legacy_unpinned_request_before_sandbox(self):
        class MustNotStartBackend:
            calls = 0

            def create(self, snapshot: Path, allowed_commands: set[str]):
                self.calls += 1
                raise AssertionError("unpinned request reached sandbox")

        class CountingWorker:
            calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                return WorkerProposal((("calculator.py", "unused"),))

        backend = MustNotStartBackend()
        worker = CountingWorker()
        with self.assertRaisesRegex(
            ExecutionError, "^execution request: pinned snapshot is required$"
        ):
            run_local_execution(
                valid_request(),
                worker,
                verifier=AcceptingVerifier(),
                sandbox_backend=backend,
                require_pinned_snapshot=True,
            )
        self.assertEqual(backend.calls, 0)
        self.assertEqual(worker.calls, 0)

    def test_prepared_base_and_source_drift_fail_before_verifier(self):
        class FakeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                return WorkerProposal((("calculator.py", original + "\n# staged\n"),))

        for drift in ("base_commit", "source_digest"):
            with self.subTest(drift=drift), pinned_test_request(
                test_command=("python3", "-c", "print('ok')")
            ) as request:
                verifier = AcceptingVerifier()

                def drifted_prepare(sandbox, **kwargs):
                    prepared = prepare_change(sandbox, **kwargs)
                    if drift == "base_commit":
                        staged = {**prepared.staged_change, "base_commit": "b" * 40}
                        return replace(prepared, staged_change=staged)
                    evidence = {
                        **prepared.evidence_bundle,
                        "source_digests": ["sha256:" + "0" * 64],
                    }
                    evidence_digest = sha256_digest(evidence)
                    verification = {
                        **prepared.verification_report,
                        "evidence_digest": evidence_digest,
                    }
                    staged = {
                        **prepared.staged_change,
                        "evidence_digest": evidence_digest,
                        "verification_digest": sha256_digest(verification),
                    }
                    return replace(
                        prepared,
                        evidence_bundle=evidence,
                        verification_report=verification,
                        staged_change=staged,
                    )

                expected_error = (
                    "execution preparation: binding mismatch"
                    if drift == "base_commit"
                    else "execution preparation: pinned source binding mismatch"
                )
                with patch(
                    "app_contracts.executor.prepare_change", side_effect=drifted_prepare
                ):
                    with self.assertRaisesRegex(ExecutionError, f"^{expected_error}$"):
                        run_local_execution(
                            request,
                            FakeWorker(),
                            verifier=verifier,
                            require_pinned_snapshot=True,
                        )
                self.assertEqual(verifier.calls, 0)


class ExplicitWorkerInputTests(unittest.TestCase):
    def test_missing_instruction_and_empty_context_allowed_for_fake_workers(self):
        request = valid_request()
        self.assertIsNone(request.task_instruction)
        self.assertEqual(request.context_files, ())

        class RecordingWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                self.received = task
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                return WorkerProposal((("calculator.py", original + "\n# explicit-input\n"),))

        worker = RecordingWorker()
        result = run_local_execution(
            valid_request(test_command=("python3", "-c", "print('ok')")),
            worker,
            verifier=AcceptingVerifier(),
        )
        self.assertEqual(worker.calls, 1)
        self.assertIsNone(worker.received.task_instruction)
        self.assertEqual(worker.received.context_files, ())
        self.assertEqual(result.status, ExecutionStatus.VERIFIED)

    def test_explicit_instruction_and_context_pass_through_detached(self):
        instruction = "Summarize change\n\twith printable text"
        context = (("calculator.py", "selected file content"),)
        request = valid_request(task_instruction=instruction, context_files=context)
        self.assertEqual(request.task_instruction, instruction)
        self.assertEqual(request.context_files, context)
        self.assertIsNot(request.context_files, context)
        self.assertIsNot(request.context_files[0], context[0])

        class RecordingWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                self.received = task
                original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                return WorkerProposal((("calculator.py", original + "\n# detached\n"),))

        worker = RecordingWorker()
        result = run_local_execution(
            valid_request(
                task_instruction=instruction,
                context_files=context,
                test_command=("python3", "-c", "print('ok')"),
            ),
            worker,
            verifier=AcceptingVerifier(),
        )
        self.assertEqual(worker.calls, 1)
        self.assertEqual(worker.received.task_instruction, instruction)
        self.assertEqual(worker.received.context_files, context)
        self.assertIsNot(worker.received.context_files, request.context_files)
        self.assertIsNot(worker.received.context_files[0], request.context_files[0])
        self.assertEqual(result.status, ExecutionStatus.VERIFIED)

    def test_invalid_instructions_rejected_at_request_creation(self):
        class CountingWorker:
            calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                return WorkerProposal((("calculator.py", "unused"),))

        worker = CountingWorker()
        invalid_instructions = (
            "",
            42,
            b"bytes-instruction",
            object(),
            "x" * 4097,
            "bad\x00char",
            "bad\x07bell",
            "bad\rmiddle",
            "\ud800",
        )
        for value in invalid_instructions:
            with self.subTest(value=repr(value)[:40]):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: worker input is invalid$"
                ):
                    valid_request(task_instruction=value)
        self.assertEqual(worker.calls, 0)
        boundary = valid_request(task_instruction="x" * 4096)
        self.assertEqual(len(boundary.task_instruction.encode("utf-8")), 4096)
        allowed = valid_request(task_instruction="line one\nline two\tindented")
        self.assertIn("\n", allowed.task_instruction)

    def test_invalid_context_paths_rejected_before_worker(self):
        class CountingWorker:
            calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                return WorkerProposal((("calculator.py", "unused"),))

        worker = CountingWorker()
        invalid_contexts = (
            (["calculator.py", "content"],),
            (("calculator.py", object()),),
            ((None, "content"),),
            ((123, "content"),),
            ((("calculator.py", "content", "extra")),),
            (("/tmp/calculator.py", "content"),),
            (("../escape.py", "content"),),
            (("other.py", "content"),),
            (("./calculator.py", "content"),),
            (("calculator.py", "one"), ("calculator.py", "two")),
        )
        for context in invalid_contexts:
            with self.subTest(context=repr(context)[:60]):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: worker input is invalid$"
                ):
                    valid_request(context_files=context)
                with self.assertRaisesRegex(
                    ExecutionError, "^execution request: worker input is invalid$"
                ):
                    WorkerInput(
                        process_id="process-local-001",
                        task_id="task-local-001",
                        repository_id="fixture-repository",
                        base_commit="fixture-base-001",
                        declared_change_paths=("calculator.py",),
                        task_instruction="do work",
                        context_files=context,
                    )
        self.assertEqual(worker.calls, 0)

    def test_context_limits_rejected_before_worker(self):
        class CountingWorker:
            calls = 0

            def propose(self, task: WorkerInput) -> WorkerProposal:
                self.calls += 1
                return WorkerProposal((("calculator.py", "unused"),))

        worker = CountingWorker()
        with self.assertRaisesRegex(
            ExecutionError, "^execution request: worker input is invalid$"
        ):
            valid_request(context_files=(("calculator.py", "x" * 12_001),))
        paths = tuple(f"file-{index}.py" for index in range(9))
        many = tuple((path, "x") for path in paths)
        with self.assertRaisesRegex(
            ExecutionError, "^execution request: worker input is invalid$"
        ):
            valid_request(declared_change_paths=paths, context_files=many)
        total_paths = ("a.py", "b.py")
        total_context = (("a.py", "x" * 12_000), ("b.py", "x" * 12_000))
        with self.assertRaisesRegex(
            ExecutionError, "^execution request: worker input is invalid$"
        ):
            valid_request(declared_change_paths=total_paths, context_files=total_context)
        self.assertEqual(worker.calls, 0)
        ok_context = (("calculator.py", "x" * 12_000),)
        ok_request = valid_request(context_files=ok_context)
        self.assertEqual(ok_request.context_files, ok_context)
        self.assertIsNot(ok_request.context_files, ok_context)


class WorkerTerminalOutcomeTests(unittest.TestCase):
    def test_terminal_outcome_stops_before_tests_verifier_and_stage(self):
        request = valid_request()
        calls = []

        class Session:
            snapshot = request.snapshot_path
            workspace = request.snapshot_path

            def run(self, *_args, **_kwargs):
                calls.append("target-test")
                raise AssertionError("target tests must not run")

            def close(self):
                calls.append("sandbox.close")

        class Backend:
            def create(self, *_args, **_kwargs):
                calls.append("sandbox.create")
                return Session()

        class Worker:
            def propose(self, _task):
                calls.append("worker.propose")
                return WorkerTerminalOutcome(
                    "clarification_required", "conflicting_requirements"
                )

        class Verifier:
            def verify(self, _prepared):
                calls.append("verifier")
                raise AssertionError("verifier must not run")

        class StageSink:
            def save(self, _artifact):
                calls.append("stage.save")

            def load(self, _digest):
                calls.append("stage.load")

        with patch("app_contracts.executor.prepare_change") as prepare:
            result = run_local_execution(
                request,
                Worker(),
                verifier=Verifier(),
                sandbox_backend=Backend(),
                stage_sink=StageSink(),
                require_durable_stage=True,
            )
        prepare.assert_not_called()
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.worker_terminal_outcome, "clarification_required")
        self.assertEqual(
            result.worker_terminal_reason_code, "conflicting_requirements"
        )
        self.assertEqual(calls, ["sandbox.create", "worker.propose", "sandbox.close"])


class WorkerProposalDecisionObservationTests(unittest.TestCase):
    def _execute(
        self, store, raw_proposal=None, verifier=None, stage_sink=None, backend=None
    ):
        request = valid_request()
        candidate = (
            (ROOT / "fixtures/repository/project/calculator.py").read_text(
                encoding="utf-8"
            )
            + "\n# PRIVATE_CANDIDATE_CANARY\n"
        )

        class Worker:
            def propose(self, _task):
                if raw_proposal is not None:
                    return raw_proposal
                return WorkerProposal((("calculator.py", candidate),))

        return run_local_execution(
            request,
            Worker(),
            verifier=verifier or AcceptingVerifier(),
            sandbox_backend=backend or RemoteSnapshotExecutionTests.FakeBackend(),
            observation_store=store,
            stage_sink=stage_sink,
            require_durable_stage=stage_sink is not None,
        )

    def test_proposal_acceptance_is_journaled_before_preparation_and_redacted(self):
        store = ObservationStore()
        result = self._execute(store)
        events = store.events()
        labels = [event.get("decision_or_tool") for event in events]
        proposed = labels.index("WorkerProposal.validate")
        self.assertEqual(result.status, ExecutionStatus.VERIFIED)
        self.assertEqual(events[proposed]["event_type"], "decision_proposed")
        self.assertEqual(events[proposed + 1]["event_type"], "decision_applied")
        self.assertEqual(events[proposed + 1]["status"], "ok")
        self.assertIn(
            events[proposed]["checkpoint_id"],
            {checkpoint["checkpoint_id"] for checkpoint in store.checkpoints()},
        )
        self.assertNotIn("PRIVATE_CANDIDATE_CANARY", repr(events))
        self.assertEqual(
            len(
                [
                    checkpoint
                    for checkpoint in store.checkpoints()
                    if checkpoint.get("kind") == "decision"
                    and checkpoint.get("agent_id") == "service-publication-observer"
                ]
            ),
            3,
        )

    def test_invalid_proposal_is_recorded_denied_and_keeps_validation_error(self):
        store = ObservationStore()
        with self.assertRaisesRegex(
            ExecutionError, "^execution proposal: shape is invalid$"
        ):
            self._execute(store, raw_proposal=object())
        events = store.events()
        decision_events = [
            event
            for event in events
            if event.get("decision_or_tool") == "WorkerProposal.validate"
        ]
        self.assertEqual(
            [event["event_type"] for event in decision_events],
            ["decision_proposed", "decision_applied"],
        )
        self.assertEqual(decision_events[-1]["status"], "denied")
        self.assertEqual(decision_events[-1]["error_code"], "publication-gate-denied")
        self.assertNotIn("PRIVATE_CANDIDATE_CANARY", repr(events))

    def test_pinned_sandbox_binding_is_journaled_before_worker_dispatch(self):
        store = ObservationStore()
        candidate = (
            (ROOT / "fixtures/repository/project/calculator.py").read_text(
                encoding="utf-8"
            )
            + "\n# PRIVATE_CANDIDATE_CANARY\n"
        )

        class Worker:
            calls = 0

            def propose(self, _task):
                self.calls += 1
                return WorkerProposal((("calculator.py", candidate),))

        worker = Worker()
        with pinned_test_request() as request:
            result = run_local_execution(
                request,
                worker,
                verifier=AcceptingVerifier(),
                sandbox_backend=RemoteSnapshotExecutionTests.FakeBackend(),
                observation_store=store,
            )

        self.assertEqual(result.status, ExecutionStatus.VERIFIED)
        self.assertEqual(worker.calls, 1)
        events = store.events()
        binding = [
            (index, event)
            for index, event in enumerate(events)
            if event.get("decision_or_tool")
            == "SandboxSnapshot.validate-binding"
        ]
        worker_intent = next(
            index
            for index, event in enumerate(events)
            if event.get("decision_or_tool") == "ProposalWorker.propose"
            and event.get("event_type") == "tool_requested"
        )
        self.assertEqual(
            [event["event_type"] for _, event in binding],
            ["decision_proposed", "decision_applied"],
        )
        self.assertEqual(binding[1][1]["status"], "ok")
        self.assertLess(binding[1][0], worker_intent)
        self.assertIn(
            binding[0][1]["checkpoint_id"],
            {checkpoint["checkpoint_id"] for checkpoint in store.checkpoints()},
        )
        self.assertNotIn("PRIVATE_CANDIDATE_CANARY", repr(events))

    def test_pinned_sandbox_binding_gate_refusal_or_unknown_stops_worker(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint(self, checkpoint):
                if checkpoint.get("state_ref", "").endswith(
                    "publication-sandboxsnapshot-validate-binding"
                ):
                    raise ObservationStoreError("synthetic gate refusal")
                return super().record_checkpoint(checkpoint)

        class LosingTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-publication-observer"
                    and event.get("decision_or_tool")
                    == "SandboxSnapshot.validate-binding"
                    and event.get("event_type") == "decision_applied"
                ):
                    raise RuntimeError("synthetic terminal loss")
                return super().append(event)

        class NeverWorker:
            calls = 0

            def propose(self, _task):
                self.calls += 1
                raise AssertionError("worker must not run")

        for store, expected_code in (
            (RefusingStore(), "snapshot-binding-observation-gate-failed"),
            (LosingTerminalStore(), "snapshot-binding-outcome-unknown"),
        ):
            with self.subTest(expected_code=expected_code):
                worker = NeverWorker()
                with pinned_test_request() as request:
                    result = run_local_execution(
                        request,
                        worker,
                        verifier=AcceptingVerifier(),
                        sandbox_backend=RemoteSnapshotExecutionTests.FakeBackend(),
                        observation_store=store,
                    )
                self.assertEqual(result.status, ExecutionStatus.FAILED)
                self.assertEqual(result.failure_code, expected_code)
                self.assertEqual(worker.calls, 0)

    def test_pinned_sandbox_binding_mismatch_is_journaled_denied(self):
        class TamperingBackend(RemoteSnapshotExecutionTests.FakeBackend):
            def create(self, snapshot, allowed_commands):
                session = super().create(snapshot, allowed_commands)
                copied_file = session.snapshot / "calculator.py"
                copied_file.chmod(copied_file.stat().st_mode | 0o200)
                copied_file.write_text(
                    "synthetic mismatch\n", encoding="utf-8"
                )
                return session

        class NeverWorker:
            calls = 0

            def propose(self, _task):
                self.calls += 1
                raise AssertionError("worker must not run")

        store = ObservationStore()
        worker = NeverWorker()
        with pinned_test_request() as request:
            try:
                result = run_local_execution(
                    request,
                    worker,
                    verifier=AcceptingVerifier(),
                    sandbox_backend=TamperingBackend(),
                    observation_store=store,
                )
            except ExecutionError as error:
                self.assertEqual(str(error), "execution snapshot: digest mismatch")
            else:
                self.fail(
                    f"snapshot tampering was not rejected: {result!r}; "
                    f"events={store.events()!r}"
                )
        self.assertEqual(worker.calls, 0)
        events = [
            event
            for event in store.events()
            if event.get("decision_or_tool")
            == "SandboxSnapshot.validate-binding"
        ]
        self.assertEqual(
            [event["event_type"] for event in events],
            ["decision_proposed", "decision_applied"],
        )
        self.assertEqual(events[-1]["status"], "denied")
        self.assertNotIn("synthetic mismatch", repr(events))

    def test_refused_or_unknown_proposal_decision_never_prepares_change(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint(self, checkpoint):
                if checkpoint.get("state_ref", "").endswith(
                    "publication-workerproposal-validate"
                ):
                    raise ObservationStoreError("synthetic gate refusal")
                return super().record_checkpoint(checkpoint)

        class LosingTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-publication-observer"
                    and event.get("decision_or_tool") == "WorkerProposal.validate"
                    and event.get("event_type") == "decision_applied"
                ):
                    raise RuntimeError("synthetic terminal loss")
                return super().append(event)

        for store, expected_code in (
            (RefusingStore(), "proposal-validation-observation-gate-failed"),
            (LosingTerminalStore(), "proposal-validation-outcome-unknown"),
        ):
            with self.subTest(expected_code=expected_code):
                with patch("app_contracts.executor.prepare_change") as prepare:
                    result = self._execute(store)
                self.assertEqual(result.status, ExecutionStatus.FAILED)
                self.assertEqual(
                    result.failure_code,
                    expected_code,
                    repr(
                        [
                            (event.get("event_type"), event.get("decision_or_tool"))
                            for event in store.events()
                        ]
                    ),
                )
                prepare.assert_not_called()

    def test_prepared_change_binding_is_journaled_before_verifier(self):
        store = ObservationStore()
        test_case = self

        class CheckingVerifier:
            def verify(self, prepared):
                events = store.events()
                binding = [
                    event
                    for event in events
                    if event.get("decision_or_tool")
                    == "PreparedChange.validate-binding"
                ]
                test_case.assertEqual(
                    [event["event_type"] for event in binding],
                    ["decision_proposed", "decision_applied"],
                )
                test_case.assertEqual(binding[-1]["status"], "ok")
                test_case.assertEqual(
                    events[-1]["decision_or_tool"], "IndependentVerifier.verify"
                )
                return AcceptingVerifier().verify(prepared)

        result = self._execute(store, verifier=CheckingVerifier())
        events = store.events()
        proposed = next(
            index
            for index, event in enumerate(events)
            if event.get("decision_or_tool") == "PreparedChange.validate-binding"
            and event["event_type"] == "decision_proposed"
        )
        self.assertEqual(result.status, ExecutionStatus.VERIFIED)
        self.assertEqual(events[proposed + 1]["status"], "ok")
        self.assertNotIn("PRIVATE_CANDIDATE_CANARY", repr(events))
        self.assertEqual(
            len(
                [
                    checkpoint
                    for checkpoint in store.checkpoints()
                    if checkpoint.get("kind") == "decision"
                    and checkpoint.get("agent_id") == "service-publication-observer"
                ]
            ),
            3,
        )

    def test_proposal_workspace_application_is_journaled_before_target_tests(self):
        store = ObservationStore()
        backend = RemoteSnapshotExecutionTests.FakeBackend()
        result = self._execute(store, backend=backend)
        events = store.events()
        applied = [
            (index, event)
            for index, event in enumerate(events)
            if event.get("decision_or_tool") == "PreparedChange.apply-proposal"
        ]
        target_test_intent = next(
            index
            for index, event in enumerate(events)
            if event.get("decision_or_tool") == "SandboxSession.run.target-tests"
            and event.get("event_type") == "tool_requested"
        )

        self.assertEqual(result.status, ExecutionStatus.VERIFIED)
        self.assertEqual(
            [event["event_type"] for _, event in applied],
            ["decision_proposed", "decision_applied"],
        )
        self.assertEqual(applied[1][1]["status"], "ok")
        self.assertLess(applied[1][0], target_test_intent)
        self.assertIn(
            "PRIVATE_CANDIDATE_CANARY", backend.closed_workspace_contents[0]
        )
        self.assertNotIn("PRIVATE_CANDIDATE_CANARY", repr(events))

    def test_refused_workspace_application_gate_writes_no_candidate(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint(self, checkpoint):
                if checkpoint.get("state_ref", "").endswith(
                    "publication-preparedchange-apply-proposal"
                ):
                    raise ObservationStoreError("synthetic gate refusal")
                return super().record_checkpoint(checkpoint)

        backend = RemoteSnapshotExecutionTests.FakeBackend()
        verifier = AcceptingVerifier()
        stage_calls = []

        class Stage:
            def save(self, _artifact):
                stage_calls.append("save")

            def load(self, _digest):
                stage_calls.append("load")

        stage = Stage()
        result = self._execute(
            RefusingStore(), verifier=verifier, stage_sink=stage, backend=backend
        )

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(
            result.failure_code, "proposal-application-observation-gate-failed"
        )
        self.assertEqual(backend.commands, [])
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(
            backend.closed_workspace_contents[0],
            backend.closed_snapshot_contents[0],
        )
        self.assertEqual(stage_calls, [])

    def test_lost_workspace_application_terminal_stops_before_tests_and_verifier(self):
        class LosingTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-publication-observer"
                    and event.get("decision_or_tool")
                    == "PreparedChange.apply-proposal"
                    and event.get("event_type") == "decision_applied"
                ):
                    raise RuntimeError("synthetic terminal loss")
                return super().append(event)

        backend = RemoteSnapshotExecutionTests.FakeBackend()
        verifier = AcceptingVerifier()
        stage_calls = []

        class Stage:
            def save(self, _artifact):
                stage_calls.append("save")

            def load(self, _digest):
                stage_calls.append("load")

        result = self._execute(
            LosingTerminalStore(),
            verifier=verifier,
            stage_sink=Stage(),
            backend=backend,
        )

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "proposal-application-outcome-unknown")
        self.assertEqual(backend.commands, [])
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(stage_calls, [])
        self.assertIn(
            "PRIVATE_CANDIDATE_CANARY",
            backend.closed_workspace_contents[0],
        )

    def test_prepared_binding_gate_refusal_or_unknown_stops_before_verifier_and_stage(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint(self, checkpoint):
                if checkpoint.get("state_ref", "").endswith(
                    "publication-preparedchange-validate-binding"
                ):
                    raise ObservationStoreError("synthetic gate refusal")
                return super().record_checkpoint(checkpoint)

        class LosingTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-publication-observer"
                    and event.get("decision_or_tool")
                    == "PreparedChange.validate-binding"
                    and event.get("event_type") == "decision_applied"
                ):
                    raise RuntimeError("synthetic terminal loss")
                return super().append(event)

        class NeverVerifier:
            calls = 0

            def verify(self, _prepared):
                self.calls += 1
                raise AssertionError("verifier must not run")

        class NeverStage:
            calls = []

            def save(self, _artifact):
                self.calls.append("save")

            def load(self, _digest):
                self.calls.append("load")

        for store, expected_code in (
            (RefusingStore(), "prepared-binding-observation-gate-failed"),
            (LosingTerminalStore(), "prepared-binding-outcome-unknown"),
        ):
            with self.subTest(expected_code=expected_code):
                verifier = NeverVerifier()
                stage = NeverStage()
                result = self._execute(store, verifier=verifier, stage_sink=stage)
                self.assertEqual(result.status, ExecutionStatus.FAILED)
                self.assertEqual(result.failure_code, expected_code)
                self.assertEqual(verifier.calls, 0)
                self.assertEqual(stage.calls, [])

    def test_invalid_prepared_binding_is_recorded_denied_and_preserves_error(self):
        store = ObservationStore()
        invalid_prepared = SimpleNamespace(
            staged_change={
                "process_id": "process-foreign-001",
                "repository_id": "fixture-repository",
                "base_commit": "fixture-base-001",
            },
            verified_contents=(("calculator.py", "PRIVATE_VERIFIED_CANARY"),),
        )
        with patch(
            "app_contracts.executor.prepare_change", return_value=invalid_prepared
        ):
            with self.assertRaisesRegex(
                ExecutionError, "^execution preparation: binding mismatch$"
            ):
                self._execute(store)
        decision_events = [
            event
            for event in store.events()
            if event.get("decision_or_tool") == "PreparedChange.validate-binding"
        ]
        self.assertEqual(
            [event["event_type"] for event in decision_events],
            ["decision_proposed", "decision_applied"],
        )
        self.assertEqual(decision_events[-1]["status"], "denied")
        self.assertNotIn("PRIVATE_VERIFIED_CANARY", repr(store.events()))


if __name__ == "__main__":
    unittest.main()
