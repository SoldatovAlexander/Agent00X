from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.authority import DeterministicPolicy, PolicyConfig
from app_contracts.broker import InMemoryCredentialBroker
from app_contracts.controlled_publication import (
    run_controlled_local_publication,
)
from app_contracts.executor import (
    ExecutionRequest,
    ExecutionStatus,
    VerifierResult,
    VerifierVerdict,
    WorkerProposal,
    run_local_execution,
)
from app_contracts.deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
    DeepSeekProposalWorker,
)
import app_contracts.executor as executor_module
from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
)
from app_contracts.gateway import GatewayDecision, GatewayPath
from app_contracts.mock_github import MockGitHubEndpoint
from approval_test_support import TEST_APPROVER_PUBLIC_KEYS, sign_test_approval
from app_contracts.openai_worker import OpenAIProposalWorker, ResponsesModelResult
from app_contracts.pinned_snapshot import SNAPSHOT_DIGEST_CANONICALIZATION
from app_contracts.publication_seed import (
    build_publication_seed,
    derive_publication_intent,
)
from app_contracts.publication import PublicationJournal
from app_contracts.durable_stage import SQLiteStagedArtifactStore
from app_contracts.remote_snapshot_workspace import materialize_github_snapshot
from app_contracts.sandbox import DockerSandboxBackend, LocalProcessSandboxBackend
from app_contracts.stage_approval import run_local_mock_publication
from app_contracts.stage_preview import render_stage_preview
from app_contracts.verifier_process import SubprocessVerifier, VerifierProcessConfig
from app_contracts.verifier_container import (
    DockerContainerVerifier,
    VerifierContainerConfig,
)
from app_contracts.validator import ContractValidationError
from app_contracts.worker_cli import run_remote_snapshot_execution


class FixedResponsesChannel:
    def __init__(self, proposed_content: str) -> None:
        self.proposed_content = proposed_content
        self.calls = 0

    def create_response(self, payload: dict, *, timeout_seconds: float) -> ResponsesModelResult:
        self.calls += 1
        changes = [{"path": "calculator.py", "content": self.proposed_content}]
        return ResponsesModelResult(
            status="completed",
            output_text=json.dumps({"changes": changes}, separators=(",", ":")),
        )


class FixedChatCompletionsChannel:
    def __init__(self, proposed_content: str) -> None:
        self.proposed_content = proposed_content
        self.calls = 0
        self.payloads: list[dict] = []

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        self.calls += 1
        self.payloads.append(payload)
        output = json.dumps(
            {"changes": [{"path": "calculator.py", "content": self.proposed_content}]},
            separators=(",", ":"),
        )
        return ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=output,
                        reasoning_content="must not enter proposal or evidence",
                    ),
                ),
            )
        )


def make_full_snapshot() -> tuple[GitHubSnapshotContents, str]:
    fixture = ROOT / "fixtures" / "repository" / "project" / "calculator.py"
    content = fixture.read_bytes()
    content_text = content.decode("utf-8")
    blob = GitHubBlobClaim(
        path="calculator.py",
        mode="100644",
        sha=hashlib.sha1(
            b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        ).hexdigest(),
        size=len(content),
        content=content,
        content_digest=sha256_bytes(content),
    )
    content_digest = sha256_digest(
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
    )
    snapshot = GitHubSnapshotContents(
        claim=GitHubSnapshotClaim(
            owner="FixtureOwner",
            repository="calculator-fixture",
            commit_oid="a" * 40,
            tree_oid="b" * 40,
            content_digest=content_digest,
        ),
        files=(blob,),
    )
    return snapshot, content_text


class RemoteSnapshotPipelineTests(unittest.TestCase):
    def test_remote_claim_revalidation_accepts_docker_copy_with_executable_file(self):
        raw_files = (
            ("README.md", "100644", b"synthetic pinned readme\n"),
            ("scripts/probe.sh", "100755", b"#!/bin/sh\nexit 0\n"),
        )
        blobs = tuple(
            GitHubBlobClaim(
                path=path,
                mode=mode,
                sha=hashlib.sha1(
                    b"blob " + str(len(content)).encode("ascii") + b"\0" + content
                ).hexdigest(),
                size=len(content),
                content=content,
                content_digest=sha256_bytes(content),
            )
            for path, mode, content in raw_files
        )
        claim_digest = sha256_digest(
            {
                "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
                "files": [
                    {
                        "path": path,
                        "content_digest": sha256_bytes(content),
                        "mode": mode,
                    }
                    for path, mode, content in raw_files
                ],
            }
        )
        snapshot = GitHubSnapshotContents(
            claim=GitHubSnapshotClaim(
                owner="FixtureOwner",
                repository="mode-fixture",
                commit_oid="c" * 40,
                tree_oid="d" * 40,
                content_digest=claim_digest,
            ),
            files=blobs,
        )
        readme = raw_files[0][2].decode("utf-8")
        proposed_readme = readme + "\nsynthetic update\n"

        class FixedBoundWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, _task):
                self.calls += 1
                return WorkerProposal(changes=(("README.md", proposed_readme),))

        worker = FixedBoundWorker()

        class BoundAcceptingVerifier:
            def __init__(self):
                self.calls = 0

            def verify(self, prepared):
                self.calls += 1
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="synthetic-mode-claim-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        verifier = BoundAcceptingVerifier()

        class RecordingDockerSandboxBackend(DockerSandboxBackend):
            def __init__(self):
                super().__init__("synthetic-local-image")
                self.sessions = []
                self.initial_workspace_digests = []
                self.initial_snapshot_files = []

            def create(self, snapshot_path, allowed_commands):
                session = super().create(snapshot_path, allowed_commands)
                self.sessions.append(session)
                self.initial_workspace_digests.append(
                    executor_module.compute_snapshot_tree_digest(session.workspace)
                )
                self.initial_snapshot_files.append(
                    tuple(
                        (
                            path.relative_to(session.snapshot).as_posix(),
                            "100755" if path.stat().st_mode & 0o111 else "100644",
                            path.read_bytes(),
                        )
                        for path in sorted(session.snapshot.rglob("*"))
                        if path.is_file() and not path.is_symlink()
                    )
                )
                return session

        backend = RecordingDockerSandboxBackend()
        backend._assert_image_available = lambda: None
        docker_commands = []

        def fake_docker_run(command, **_kwargs):
            docker_commands.append(tuple(command))
            stdout = "synthetic-container-id\n" if command[1:2] == ["run"] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        python = sys.executable
        with patch("app_contracts.sandbox.subprocess.run", side_effect=fake_docker_run):
            with materialize_github_snapshot(snapshot) as lease:
                result = run_local_execution(
                    ExecutionRequest(
                        process_id="process-synthetic-mode-claim",
                        task_id="task-synthetic-mode-claim",
                        repository_id="FixtureOwner/mode-fixture",
                        base_commit=snapshot.claim.commit_oid,
                        snapshot_path=lease.path,
                        allowed_commands=frozenset({Path(python).name}),
                        declared_change_paths=("README.md",),
                        test_command=(python, "-c", "assert True"),
                        task_instruction="Make a harmless synthetic README update",
                        context_files=(("README.md", readme),),
                        remote_snapshot=snapshot,
                        remote_workspace=lease,
                    ),
                    worker,
                    verifier=verifier,
                    sandbox_backend=backend,
                )

        self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
        self.assertEqual(worker.calls, 1)
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(len(backend.sessions), 2)
        self.assertEqual(backend.initial_workspace_digests, [claim_digest, claim_digest])
        self.assertEqual(
            len([command for command in docker_commands if len(command) > 1 and command[1] == "run"]),
            2,
        )
        for index, session in enumerate(backend.sessions):
            copied_files = backend.initial_snapshot_files[index]
            self.assertEqual(copied_files, raw_files)
            self.assertEqual(executor_module.verifier_snapshot_tree_digest(copied_files), claim_digest)
            self.assertTrue(session._closed)
            self.assertFalse(session._root.exists())

    def test_remote_composition_requires_persists_previews_and_mock_approves_exact_digest(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# synthetic remote composition fixture\n"
        channel = FixedChatCompletionsChannel(proposed_content)
        worker = DeepSeekProposalWorker(channel=channel)
        nonce = "4" * 64
        verifier = SubprocessVerifier(
            VerifierProcessConfig(
                executable=sys.executable,
                argv=(
                    sys.executable,
                    "-m",
                    "app_contracts.verifier_container_entrypoint",
                    "--invocation-nonce=" + nonce,
                ),
                timeout_seconds=30,
                max_stdout_bytes=65_536,
                max_stderr_bytes=4_096,
            ),
            environ={"PYTHONPATH": str(ROOT / "src")},
        )
        python = sys.executable
        test_command = (
            python,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )
        with tempfile.TemporaryDirectory(prefix="remote-composition-stage-") as directory:
            stage_database = Path(directory) / "stages.sqlite3"
            with SQLiteStagedArtifactStore(stage_database) as stage_store:
                result = run_remote_snapshot_execution(
                    snapshot,
                    process_id="process-remote-composition-001",
                    task_id="task-remote-composition-001",
                    task_instruction="Add a harmless fixture-only comment to calculator.py",
                    declared_change_paths=("calculator.py",),
                    allowed_commands=frozenset({Path(python).name}),
                    test_command=test_command,
                    worker=worker,
                    verifier=verifier,
                    sandbox_backend=LocalProcessSandboxBackend(),
                    context_files=(("calculator.py", base_content),),
                    stage_sink=stage_store,
                )
                self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
                self.assertIsNotNone(result.staged_change_digest)
                artifact = stage_store.load(result.staged_change_digest)

            self.assertEqual(channel.calls, 1)
            self.assertEqual(artifact.staged_change_digest, result.staged_change_digest)
            preview = json.loads(render_stage_preview(artifact))
            self.assertEqual(
                preview["stage"]["staged_change_digest"], result.staged_change_digest
            )
            self.assertEqual(preview["approval"], "not_created")
            self.assertEqual(preview["publication"], "not_attempted")

            receipt = run_local_mock_publication(
                artifact,
                result.staged_change_digest,
                "agent/remote-composition-mock",
                "master",
                now=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(receipt.staged_change_digest, result.staged_change_digest)
            self.assertEqual(receipt.repository_id, "FixtureOwner/calculator-fixture")

    def test_deepseek_fake_worker_remote_replay_verifier_seed_and_intent(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# synthetic deepseek pipeline fixture\n"
        channel = FixedChatCompletionsChannel(proposed_content)
        worker = DeepSeekProposalWorker(channel=channel)
        nonce = "3" * 64
        verifier = SubprocessVerifier(
            VerifierProcessConfig(
                executable=sys.executable,
                argv=(
                    sys.executable,
                    "-m",
                    "app_contracts.verifier_container_entrypoint",
                    "--invocation-nonce=" + nonce,
                ),
                timeout_seconds=30,
                max_stdout_bytes=65_536,
                max_stderr_bytes=4_096,
            ),
            environ={"PYTHONPATH": str(ROOT / "src")},
        )
        python = sys.executable
        test_command = (
            python,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )

        with materialize_github_snapshot(snapshot) as workspace:
            workspace_path = workspace.path
            request = ExecutionRequest(
                process_id="process-remote-deepseek-001",
                task_id="task-remote-deepseek-001",
                repository_id="FixtureOwner/calculator-fixture",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=workspace.path,
                allowed_commands=frozenset({Path(python).name}),
                declared_change_paths=("calculator.py",),
                test_command=test_command,
                task_instruction="Add a harmless fixture-only comment to calculator.py",
                context_files=(("calculator.py", base_content),),
                remote_snapshot=snapshot,
                remote_workspace=workspace,
            )
            result = run_local_execution(
                request,
                worker,
                verifier=verifier,
                sandbox_backend=LocalProcessSandboxBackend(),
            )
            self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
            self.assertEqual(channel.calls, 1)
            self.assertEqual(channel.payloads[0]["model"], "deepseek-flash")
            self.assertEqual(channel.payloads[0]["response_format"], {"type": "json_object"})
            self.assertEqual(result.verifier_result.verifier_id, nonce)
            self.assertIsNotNone(result.verifier_result.replay_result_digest)
            seed = build_publication_seed(request, result)
            intent = derive_publication_intent(seed, "agent/deepseek-fixture", "master")
            self.assertEqual(seed.staged_change_digest, intent.staged_change_digest)
            self.assertEqual(seed.snapshot_claim_digest, result.snapshot_claim_digest)
            for value in (repr(result), repr(seed), repr(intent)):
                self.assertNotIn("synthetic deepseek pipeline fixture", value)
                self.assertNotIn("must not enter proposal or evidence", value)
                self.assertNotIn(base_content, value)

        self.assertTrue(workspace.closed)
        self.assertFalse(workspace_path.exists())

    def test_remote_snapshot_worker_replay_verifier_seed_and_intent(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# synthetic mvp pipeline fixture\n"
        channel = FixedResponsesChannel(proposed_content)
        worker = OpenAIProposalWorker(channel=channel)

        nonce = "1" * 64
        verifier_config = VerifierProcessConfig(
            executable=sys.executable,
            argv=(
                sys.executable,
                "-m",
                "app_contracts.verifier_container_entrypoint",
                "--invocation-nonce=" + nonce,
            ),
            timeout_seconds=30,
            max_stdout_bytes=65_536,
            max_stderr_bytes=4_096,
        )
        verifier = SubprocessVerifier(
            verifier_config,
            environ={"PYTHONPATH": str(ROOT / "src")},
        )
        python = sys.executable
        request_command = (
            python,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )
        allowed_commands = frozenset({Path(python).name})

        with materialize_github_snapshot(snapshot) as workspace:
            workspace_path = workspace.path
            request = ExecutionRequest(
                process_id="process-remote-mvp-001",
                task_id="task-remote-mvp-001",
                repository_id="FixtureOwner/calculator-fixture",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=workspace.path,
                allowed_commands=allowed_commands,
                declared_change_paths=("calculator.py",),
                test_command=request_command,
                task_instruction="Add a harmless fixture-only comment to calculator.py",
                context_files=(("calculator.py", base_content),),
                remote_snapshot=snapshot,
                remote_workspace=workspace,
            )
            result = run_local_execution(
                request,
                worker,
                verifier=verifier,
                sandbox_backend=LocalProcessSandboxBackend(),
            )
            self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
            self.assertEqual(channel.calls, 1)
            self.assertEqual(result.verifier_result.verifier_id, nonce)
            self.assertIsNotNone(result.verifier_result.replay_result_digest)
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
                    "evidence_origin": snapshot.claim.evidence_origin,
                }
            )
            self.assertEqual(result.snapshot_claim_digest, expected_claim_digest)

            seed = build_publication_seed(request, result)
            intent = derive_publication_intent(seed, "agent/remote-mvp-smoke", "master")
            self.assertEqual(seed.staged_change_digest, intent.staged_change_digest)
            self.assertEqual(seed.snapshot_claim_digest, result.snapshot_claim_digest)
            self.assertEqual(intent.base_commit, snapshot.claim.commit_oid)
            self.assertEqual(intent.repository_id, "FixtureOwner/calculator-fixture")
            for value in (repr(result), repr(seed), repr(intent)):
                self.assertNotIn("synthetic mvp pipeline fixture", value)
                self.assertNotIn(base_content, value)

        self.assertTrue(workspace.closed)
        self.assertFalse(workspace_path.exists())

    def test_remote_seed_approval_and_mock_publication_share_exact_digest(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# synthetic mvp publication fixture\n"
        channel = FixedResponsesChannel(proposed_content)
        worker = OpenAIProposalWorker(channel=channel)
        nonce = "2" * 64
        verifier = SubprocessVerifier(
            VerifierProcessConfig(
                executable=sys.executable,
                argv=(
                    sys.executable,
                    "-m",
                    "app_contracts.verifier_container_entrypoint",
                    "--invocation-nonce=" + nonce,
                ),
                timeout_seconds=30,
                max_stdout_bytes=65_536,
                max_stderr_bytes=4_096,
            ),
            environ={"PYTHONPATH": str(ROOT / "src")},
        )
        python = sys.executable
        test_command = (
            python,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )
        captured: dict = {}
        with materialize_github_snapshot(snapshot) as workspace:
            request = ExecutionRequest(
                process_id="process-remote-publication-001",
                task_id="task-remote-publication-001",
                repository_id="FixtureOwner/calculator-fixture",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=workspace.path,
                allowed_commands=frozenset({Path(python).name}),
                declared_change_paths=("calculator.py",),
                test_command=test_command,
                task_instruction="Add a harmless fixture-only comment to calculator.py",
                context_files=(("calculator.py", base_content),),
                remote_snapshot=snapshot,
                remote_workspace=workspace,
            )
            real_prepare = executor_module.prepare_change

            def capture_stage(sandbox, **kwargs):
                prepared = real_prepare(sandbox, **kwargs)
                captured["stage"] = dict(prepared.staged_change)
                captured["prepared"] = prepared
                return prepared

            with tempfile.TemporaryDirectory(prefix="remote-pipeline-stage-") as stage_directory:
                stage_database = Path(stage_directory) / "stages.sqlite3"
                with SQLiteStagedArtifactStore(stage_database) as stage_store:
                    with patch("app_contracts.executor.prepare_change", side_effect=capture_stage):
                        result = run_local_execution(
                            request,
                            worker,
                            verifier=verifier,
                            sandbox_backend=LocalProcessSandboxBackend(),
                            stage_sink=stage_store,
                            require_durable_stage=True,
                        )
                    persisted_artifact = stage_store.load(result.staged_change_digest)
            self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
            self.assertEqual(channel.calls, 1)
            seed = build_publication_seed(request, result)
            intent = derive_publication_intent(seed, "agent/remote-mock-publication", "master")
            staged_change = persisted_artifact.payload_copy()["staged_change"]
            self.assertEqual(staged_change, captured["stage"])
            self.assertEqual(sha256_digest(staged_change), intent.staged_change_digest)

            now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
            mock_receipt = run_local_mock_publication(
                persisted_artifact,
                persisted_artifact.staged_change_digest,
                "agent/remote-mock-publication",
                "master",
                now=now,
            )
            self.assertEqual(mock_receipt.staged_change_digest, intent.staged_change_digest)
            self.assertEqual(mock_receipt.repository_id, intent.repository_id)

            expires_at = (now + timedelta(hours=1)).isoformat()
            policy_version = "remote-fixture-policy-v1"
            approval_id = "approval-remote-fixture-001"
            engine_intent = {
                "process_id": intent.process_id,
                "repository_id": intent.repository_id,
                "base_commit": intent.base_commit,
                "operation": "publish_pull_request",
                "approval_id": approval_id,
                "expires_at": expires_at,
                "branch_namespace": intent.branch.split("/", 1)[0],
                "idempotency_key": intent.idempotency_key,
                "staged_change_digest": intent.staged_change_digest,
            }
            approval = sign_test_approval({
                "schema_version": 1,
                "process_id": intent.process_id,
                "repository_id": intent.repository_id,
                "operation": "publish_pull_request",
                "approval_id": approval_id,
                "approver_id": "user-alice",
                "policy_version": policy_version,
                "expires_at": expires_at,
                "staged_change_digest": intent.staged_change_digest,
                "approved_intent_digest": sha256_digest(engine_intent),
                "approved_at": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            })
            policy = DeterministicPolicy(
                PolicyConfig(
                    version=policy_version,
                    allowed_repositories=frozenset({intent.repository_id}),
                    allowed_actuators=frozenset({"test-actuator"}),
                    allowed_approver_ids=frozenset(TEST_APPROVER_PUBLIC_KEYS),
                    trusted_approver_public_keys=TEST_APPROVER_PUBLIC_KEYS,
                    decision_ttl_seconds=300,
                )
            )
            actuator_request = {
                "operation": "publish_pull_request",
                "repository_id": intent.repository_id,
                "actuator_id": "test-actuator",
                "base_branch": intent.base_branch,
                "staged_change_digest": intent.staged_change_digest,
                "branch_namespace": intent.branch.split("/", 1)[0],
                "idempotency_key": intent.idempotency_key,
            }
            grant = {
                "credential_grant_id": "test-only-grant-001",
                "actuator_id": "test-actuator",
                "repository_id": intent.repository_id,
                "operation": "publish_pull_request",
                "request_digest": sha256_digest(actuator_request),
                "single_use": True,
                "credential_class": "github-app-installation",
                "expires_at": expires_at,
            }

            diagnostic_decision = policy.decide(
                decision_id="decision-remote-fixture-diagnostic",
                actuator_request=actuator_request,
                approval=approval,
                staged_change=staged_change,
                intent=engine_intent,
                now=now,
            )
            self.assertEqual(diagnostic_decision["effect"], "allow", diagnostic_decision["reason_codes"])

            def envelope():
                return {
                    "intent": {"operation": "publish_pull_request"},
                    "destination": {
                        "port": "approval",
                        "repository_id": intent.repository_id,
                        "base_branch": intent.base_branch,
                    },
                    "source": {
                        "protocol": "internal",
                        "principal_id": intent.process_id,
                    },
                    "security": {"tainted": False, "sensitivity": "internal"},
                    "payload": {"content_digest": intent.staged_change_digest},
                    "correlation_id": intent.idempotency_key,
                }

            class AllowGateway:
                def __init__(self):
                    self.calls = 0

                def __call__(self, _envelope, *, now):
                    self.calls += 1
                    return GatewayDecision(
                        GatewayPath.SLOW, True, ("write-or-unknown-operation",)
                    )

            endpoint = MockGitHubEndpoint()
            broker = InMemoryCredentialBroker(lambda: endpoint)
            gateway = AllowGateway()

            def load_stage(candidate_seed):
                self.assertEqual(candidate_seed.staged_change_digest, intent.staged_change_digest)
                return staged_change

            with tempfile.TemporaryDirectory() as directory:
                journal_path = Path(directory) / "journal.sqlite"
                with PublicationJournal(journal_path) as journal:
                    receipt = run_controlled_local_publication(
                        seed,
                        intent,
                        approval,
                        policy,
                        engine_intent,
                        load_stage,
                        "decision-remote-fixture-001",
                        gateway,
                        envelope(),
                        broker,
                        grant,
                        journal,
                        endpoint,
                        actuator_id="test-actuator",
                        now=now,
                    )
                    self.assertEqual(receipt.repository_id, intent.repository_id)
                    self.assertEqual(receipt.staged_change_digest, intent.staged_change_digest)
                    self.assertEqual(journal.get(intent.process_id).status, "completed")
                    self.assertEqual(gateway.calls, 1)
                    self.assertEqual(len(broker.opened_grants), 1)

                bad_endpoint = MockGitHubEndpoint()
                bad_broker = InMemoryCredentialBroker(lambda: bad_endpoint)
                bad_gateway = AllowGateway()
                with PublicationJournal(Path(directory) / "denied.sqlite") as denied_journal:
                    bad_approval = dict(
                        approval,
                        staged_change_digest="sha256:" + "f" * 64,
                    )
                    with self.assertRaises(ContractValidationError) as raised:
                        run_controlled_local_publication(
                            seed,
                            intent,
                            bad_approval,
                            policy,
                            engine_intent,
                            load_stage,
                            "decision-remote-fixture-denied",
                            bad_gateway,
                            envelope(),
                            bad_broker,
                            grant,
                            denied_journal,
                            bad_endpoint,
                            actuator_id="test-actuator",
                            now=now,
                        )
                    self.assertNotIn("sha256:", str(raised.exception))
                    self.assertEqual(bad_gateway.calls, 0)
                    self.assertEqual(bad_broker.opened_grants, [])
                    self.assertIsNone(
                        bad_endpoint.find_by_idempotency_key(intent.idempotency_key)
                    )
                    with self.assertRaises(KeyError):
                        denied_journal.get(intent.process_id)


@unittest.skipUnless(
    os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1"
    and re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        os.environ.get("AGENT00X_VERIFIER_IMAGE_ID", ""),
    )
    and re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        os.environ.get("AGENT00X_VERIFIER_CODE_DIGEST", ""),
    )
    and os.path.isabs(os.environ.get("AGENT00X_DOCKER_EXECUTABLE", "")),
    "real Docker verifier composition is opt-in",
)
class RemoteSnapshotVerifierStageDockerTests(unittest.TestCase):
    def test_container_verifier_completes_synthetic_stage(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# docker-verifier-stage-fixture\n"
        channel = FixedChatCompletionsChannel(proposed_content)
        worker = DeepSeekProposalWorker(channel=channel)
        verifier_image_id = os.environ["AGENT00X_VERIFIER_IMAGE_ID"]
        verifier_code_digest = os.environ["AGENT00X_VERIFIER_CODE_DIGEST"]
        verifier = DockerContainerVerifier(
            VerifierContainerConfig(
                os.environ["AGENT00X_DOCKER_EXECUTABLE"],
                verifier_image_id,
                verifier_code_digest,
                timeout_seconds=60,
                max_stdout_bytes=65_536,
                max_stderr_bytes=16_384,
            )
        )
        test_command = (
            "python3",
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )

        with tempfile.TemporaryDirectory(prefix="synthetic-docker-stage-") as directory:
            stage_database = Path(directory) / "stage.sqlite3"
            with SQLiteStagedArtifactStore(stage_database) as stage_store:
                result = run_remote_snapshot_execution(
                    snapshot,
                    process_id="process-synthetic-docker-stage-001",
                    task_id="task-synthetic-docker-stage-001",
                    task_instruction="Add one harmless synthetic fixture comment",
                    declared_change_paths=("calculator.py",),
                    allowed_commands=frozenset({"python3"}),
                    test_command=test_command,
                    test_timeout_seconds=20,
                    worker=worker,
                    verifier=verifier,
                    sandbox_backend=LocalProcessSandboxBackend(),
                    context_files=(("calculator.py", base_content),),
                    stage_sink=stage_store,
                )
                self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
                self.assertIsNotNone(result.staged_change_digest)
                artifact = stage_store.load(result.staged_change_digest)
                self.assertEqual(
                    artifact.staged_change_digest, result.staged_change_digest
                )

            self.assertEqual(channel.calls, 1)
            self.assertEqual(
                result.verifier_result.verifier_id,
                f"docker-image:{verifier_image_id}/code:{verifier_code_digest}",
            )
            preview = json.loads(render_stage_preview(artifact))
            self.assertEqual(
                preview["stage"]["staged_change_digest"],
                result.staged_change_digest,
            )
            self.assertEqual(preview["approval"], "not_created")
            self.assertEqual(preview["publication"], "not_attempted")
            receipt = run_local_mock_publication(
                artifact,
                result.staged_change_digest,
                "agent/synthetic-docker-stage-mock",
                "master",
                now=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(
                receipt.staged_change_digest, result.staged_change_digest
            )
            self.assertEqual(receipt.repository_id, "FixtureOwner/calculator-fixture")


if __name__ == "__main__":
    unittest.main()
