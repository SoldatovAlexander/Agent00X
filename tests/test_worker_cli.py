from __future__ import annotations

import ast
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import (
    ExecutionError,
    ExecutionResult,
    ExecutionStatus,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    WorkerInput,
    WorkerProposal,
)
from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitHubTreeClaim,
    GitHubTreeEntry,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
    GitHubSnapshotError,
)
from app_contracts.github_http_transport import GitHubRateLimitEvidence
from app_contracts.observation_store import ObservationStore
from app_contracts.observer_runtime import JournaledProposalWorker
from app_contracts.observer_report import build_history_report
from app_contracts.pinned_snapshot import SNAPSHOT_DIGEST_CANONICALIZATION
from app_contracts.brainbooster_target_profile import (
    TARGET_RUNTIME_IMAGE_ID,
)
from app_contracts.verifier_image_pin import (
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.openai_worker import OpenAIProposalWorker
from app_contracts.deepseek_worker import DeepSeekProposalWorker
from app_contracts.deepseek_http_channel import DeepSeekHTTPChannel
import app_contracts.worker_cli as cli
import app_contracts.remote_snapshot_pipeline as snapshot_pipeline
from app_contracts.stage_approval import StageApprovalError, run_local_mock_publication
from app_contracts.signed_verifier_client import (
    SignedVerifierClient,
    SignedVerifierHTTPSTransport,
)
from app_contracts.verifier_trust_enrollment import (
    build_signed_verifier_trust_enrollment,
)
from app_contracts.verifier_host_trust_decision import (
    build_signed_verifier_host_trust_decision,
)


SENTINELS = (
    "Tiny repository fixture",
    "cli-demo-synthetic",
    "synthetic demo context",
    "Add a synthetic demo comment",
    "SECRET",
    "credential",
    "test stdout",
    "test stderr",
)


class FixedDemoTests(unittest.TestCase):
    def test_success_outputs_only_metadata(self):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main([], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(set(payload.keys()), {"status", "demo", "evidence_origin"})
        self.assertEqual(payload["status"], "verified")
        self.assertEqual(payload["demo"], "worker-cli-synthetic")
        self.assertEqual(payload["evidence_origin"], "local_test")
        combined = out.getvalue() + err.getvalue()
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, combined)

    def test_extra_argv_rejected_without_execution(self):
        for argv in (["--help"], ["extra"], ["a", "b"]):
            with self.subTest(argv=argv):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(cli, "run_local_execution") as run_mock:
                    run_mock.side_effect = AssertionError("must not execute")
                    code = cli.main(list(argv), stdout=out, stderr=err)
                self.assertEqual(code, 2)
                self.assertEqual(out.getvalue(), "")
                payload = json.loads(err.getvalue().strip())
                self.assertEqual(set(payload.keys()), {"status", "failure_code"})
                self.assertNotIn("Tiny repository", err.getvalue())

    def test_worker_failure_is_sanitized(self):
        class FailingWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                raise RuntimeError("SENTINEL-WORKER-BOOM")

        out, err = io.StringIO(), io.StringIO()
        code = cli.main([], worker=FailingWorker(), stdout=out, stderr=err)
        self.assertNotEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(set(payload.keys()), {"status", "failure_code"})
        self.assertEqual(payload["status"], "failed")
        combined = out.getvalue() + err.getvalue()
        self.assertNotIn("SENTINEL-WORKER-BOOM", combined)
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, combined)

    def test_verifier_failure_is_sanitized(self):
        class DenyingVerifier:
            def verify(self, prepared: VerifierInput) -> VerifierResult:
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="cli-demo-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.BLOCKED,
                )

        out, err = io.StringIO(), io.StringIO()
        code = cli.main([], verifier=DenyingVerifier(), stdout=out, stderr=err)
        self.assertNotEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(set(payload.keys()), {"status", "failure_code"})
        combined = out.getvalue() + err.getvalue()
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, combined)

    def test_blocked_proposal_is_sanitized(self):
        class OutOfScopeWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                return WorkerProposal((("other.py", "SECRET-BLOCKED-PROPOSAL"),))

        out, err = io.StringIO(), io.StringIO()
        code = cli.main([], worker=OutOfScopeWorker(), stdout=out, stderr=err)
        self.assertNotEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(set(payload.keys()), {"status", "failure_code"})
        combined = out.getvalue() + err.getvalue()
        self.assertNotIn("SECRET-BLOCKED-PROPOSAL", combined)
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, combined)

    def test_bounded_request_scope_and_injected_collaborators(self):
        captured: dict = {}

        class PassWorker:
            def propose(self, task: WorkerInput) -> WorkerProposal:
                return WorkerProposal((("calculator.py", "unused"),))

        class PassVerifier:
            def verify(self, prepared: VerifierInput) -> VerifierResult:
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="cli-demo-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        worker, verifier = PassWorker(), PassVerifier()

        def fake_run(request, active_worker, *, verifier: object = None, **kwargs):
            captured["request"] = request
            captured["worker"] = active_worker
            captured["verifier"] = verifier
            return ExecutionResult(status=ExecutionStatus.VERIFIED)

        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "run_local_execution", side_effect=fake_run):
            code = cli.main([], worker=worker, verifier=verifier, stdout=out, stderr=err)
        self.assertEqual(code, 0)
        request = captured["request"]
        self.assertTrue(str(request.snapshot_path).endswith("fixtures/repository/project"))
        self.assertEqual(request.declared_change_paths, ("calculator.py",))
        self.assertEqual(request.allowed_commands, frozenset({"python3"}))
        self.assertEqual(
            request.test_command,
            ("python3", "-m", "unittest", "discover", "-s", ".", "-p", "test_calculator.py", "-q"),
        )
        self.assertEqual(request.task_instruction, cli.DEMO_INSTRUCTION)
        self.assertEqual(request.context_files, cli.DEMO_CONTEXT)
        self.assertIs(captured["worker"], worker)
        self.assertIs(captured["verifier"], verifier)

    def test_default_collaborators_are_demo_only(self):
        captured: dict = {}

        def fake_run(request, active_worker, *, verifier: object = None, **kwargs):
            captured["worker"] = active_worker
            captured["verifier"] = verifier
            return ExecutionResult(status=ExecutionStatus.VERIFIED)

        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "run_local_execution", side_effect=fake_run):
            code = cli.main([], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertIsInstance(captured["worker"], OpenAIProposalWorker)
        self.assertEqual(captured["verifier"].verify.__self__.__class__.__name__, "_DemoVerifier")

    def test_remote_fixture_preview_runs_local_pipeline_and_emits_only_metadata(self):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(["--remote-fixture-preview"], stdout=out, stderr=err)
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(
            set(payload),
            {
                "status",
                "demo",
                "evidence_origin",
                "repository_id",
                "base_commit",
                "base_branch",
                "branch_preview",
                "staged_change_digest",
                "snapshot_claim_digest",
                "verified_contents_digest",
                "publication",
            },
        )
        self.assertEqual(payload["status"], "preview_ready")
        self.assertEqual(payload["demo"], "remote-fixture-publication-preview")
        self.assertEqual(payload["evidence_origin"], "local_synthetic_test")
        self.assertEqual(payload["repository_id"], "FixtureOwner/calculator-fixture")
        self.assertEqual(payload["branch_preview"], "agent/remote-fixture-preview")
        self.assertEqual(payload["publication"], "not_attempted")
        for key in ("staged_change_digest", "snapshot_claim_digest", "verified_contents_digest"):
            self.assertRegex(payload[key], r"^sha256:[0-9a-f]{64}$")
        combined = out.getvalue() + err.getvalue()
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, combined)
        self.assertNotIn("remote-fixture-preview\n", combined)

    def test_deepseek_remote_fixture_preview_is_fixed_fake_and_sanitized(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "read_github_snapshot_contents") as network_reader:
            code = cli.main(["--deepseek-remote-fixture-preview"], stdout=out, stderr=err)
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")
        network_reader.assert_not_called()
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(
            set(payload),
            {
                "status",
                "demo",
                "evidence_origin",
                "repository_id",
                "base_commit",
                "base_branch",
                "branch_preview",
                "staged_change_digest",
                "snapshot_claim_digest",
                "verified_contents_digest",
                "publication",
            },
        )
        self.assertEqual(payload["status"], "preview_ready")
        self.assertEqual(payload["demo"], cli.DEEPSEEK_REMOTE_DEMO_NAME)
        self.assertEqual(payload["evidence_origin"], "local_synthetic_test")
        self.assertEqual(payload["branch_preview"], "agent/deepseek-remote-fixture-preview")
        self.assertEqual(payload["publication"], "not_attempted")
        for key in ("staged_change_digest", "snapshot_claim_digest", "verified_contents_digest"):
            self.assertRegex(payload[key], r"^sha256:[0-9a-f]{64}$")
        combined = out.getvalue() + err.getvalue()
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, combined)
        self.assertNotIn("deepseek-remote-fixture-preview\n", combined)
        self.assertNotIn("synthetic reasoning is ignored", combined)

    def test_deepseek_remote_fixture_preview_failure_is_sanitized(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "run_remote_snapshot_execution", side_effect=RuntimeError("proposal secret sentinel")):
            code = cli.main(["--deepseek-remote-fixture-preview"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out.getvalue().strip()),
            {"status": "failed", "failure_code": "deepseek-fixture-preview-failed"},
        )
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn("proposal secret sentinel", out.getvalue())

    def test_deepseek_channel_timeout_is_sanitized_at_fixture_cli_boundary(self):
        class TimeoutChannel:
            def __init__(self):
                self.calls = 0

            def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
                self.calls += 1
                raise TimeoutError("provider timeout secret sentinel")

        channel = TimeoutChannel()
        worker = DeepSeekProposalWorker(channel=channel)
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(
            ["--deepseek-remote-fixture-preview"],
            worker=worker,
            stdout=out,
            stderr=err,
        )
        self.assertEqual(code, 1)
        self.assertEqual(channel.calls, 1)
        self.assertEqual(
            json.loads(out.getvalue().strip()),
            {"status": "failed", "failure_code": "deepseek-fixture-preview-failed"},
        )
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn("provider timeout secret sentinel", out.getvalue())

        # The test-only Python injection does not create an argv-selectable
        # provider hook; ordinary CLI argument parsing rejects such switches.
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(
            ["--deepseek-remote-fixture-preview", "--worker=live"],
            stdout=out,
            stderr=err,
        )
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(
            json.loads(err.getvalue().strip()),
            {"status": "error", "failure_code": "cli-usage-invalid"},
        )

    def test_remote_snapshot_metadata_mode_prints_bound_metadata_only(self):
        tree = GitHubTreeClaim(
            owner=cli.REMOTE_REPOSITORY_OWNER,
            repository=cli.REMOTE_REPOSITORY_NAME,
            tree_oid=cli.REMOTE_REPOSITORY_TREE,
            entries=(
                GitHubTreeEntry(
                    path="backend/routes.py",
                    mode="100644",
                    entry_type="blob",
                    sha="f" * 40,
                    size=12_345,
                ),
            ),
        )
        transport = object()
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport", return_value=transport),
            patch.object(cli, "REMOTE_REPOSITORY_FILE_COUNT", 1),
            patch.object(cli, "read_github_snapshot_metadata", return_value=tree) as read,
        ):
            code = cli.main(["--remote-snapshot-metadata"], stdout=out, stderr=err)
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")
        request = read.call_args.args[0]
        self.assertEqual(request.owner, cli.REMOTE_REPOSITORY_OWNER)
        self.assertEqual(request.repository, cli.REMOTE_REPOSITORY_NAME)
        self.assertEqual(request.commit_oid, cli.REMOTE_REPOSITORY_COMMIT)
        self.assertIsNone(request.include_paths)
        self.assertIs(read.call_args.args[1], transport)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(
            set(payload),
            {
                "schema", "status", "evidence_origin", "authenticated", "repository_id",
                "commit", "tree", "blob_count", "total_blob_bytes", "max_blob_bytes",
                "executable_blob_count", "blobs_over_verifier_file_limit",
                "total_over_verifier_limit", "blob_contents_fetched",
                "snapshot_content_verified",
            },
        )
        self.assertEqual(payload["status"], "snapshot_metadata_ready")
        self.assertEqual(payload["evidence_origin"], "github_rest_api_claim")
        self.assertIs(payload["authenticated"], False)
        self.assertEqual(payload["blob_count"], 1)
        self.assertEqual(payload["total_blob_bytes"], 12_345)
        self.assertEqual(payload["max_blob_bytes"], 12_345)
        self.assertEqual(payload["blobs_over_verifier_file_limit"], 0)
        self.assertIs(payload["total_over_verifier_limit"], False)
        self.assertIs(payload["blob_contents_fetched"], False)
        self.assertIs(payload["snapshot_content_verified"], False)
        self.assertNotIn("backend/routes.py", out.getvalue())
        self.assertNotIn("content_digest", payload)

    def test_remote_snapshot_metadata_errors_are_sanitized(self):
        for bad_snapshot in (
            ValueError("raw source credential sentinel"),
            GitHubTreeClaim(
                owner=cli.REMOTE_REPOSITORY_OWNER,
                repository=cli.REMOTE_REPOSITORY_NAME,
                tree_oid="f" * 40,
                entries=(),
            ),
        ):
            with self.subTest(kind=type(bad_snapshot).__name__):
                out, err = io.StringIO(), io.StringIO()
                with (
                    patch.object(cli, "GitHubAnonymousSnapshotTransport"),
                    patch.object(
                        cli,
                        "read_github_snapshot_metadata",
                        side_effect=bad_snapshot if isinstance(bad_snapshot, Exception) else None,
                        return_value=None if isinstance(bad_snapshot, Exception) else bad_snapshot,
                    ),
                ):
                    code = cli.main(["--remote-snapshot-metadata"], stdout=out, stderr=err)
                self.assertEqual(code, 1)
                payload = json.loads(out.getvalue().strip())
                self.assertEqual(payload, {"status": "failed", "failure_code": "remote-snapshot-fetch-failed"})
                self.assertNotIn("raw source", out.getvalue() + err.getvalue())
                self.assertNotIn("SYNTHETIC-SOURCE-CANARY", out.getvalue() + err.getvalue())

    def test_remote_snapshot_http_failure_surfaces_only_status_code(self):
        response_canary = "private remote response body sentinel"
        failure = GitHubSnapshotError(
            f"github snapshot: snapshot response failed (HTTP 429) {response_canary}",
            http_status=429,
        )
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
            patch.object(cli, "read_github_snapshot_metadata", side_effect=failure),
        ):
            code = cli.main(["--remote-snapshot-metadata"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out.getvalue()),
            {"status": "failed", "failure_code": "remote-snapshot-http-429"},
        )
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn(response_canary, out.getvalue() + err.getvalue())


class PinnedRemoteExecutionCLITests(unittest.TestCase):
    class DummyStageSink:
        def save(self, _artifact):
            return None

        def load(self, _digest):
            return None

    @staticmethod
    def make_full_snapshot() -> GitHubSnapshotContents:
        paths = ["backend/routes.py"] + [
            f"backend/unused-{index:02d}.py" for index in range(22)
        ]
        files = []
        for path in sorted(paths):
            content = (
                b"SOURCE-CANARY\n"
                if path == "backend/routes.py"
                else f"# synthetic {path}\n".encode("utf-8")
            )
            files.append(
                GitHubBlobClaim(
                    path=path,
                    mode="100644",
                    sha=hashlib.sha1(
                        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
                    ).hexdigest(),
                    size=len(content),
                    content=content,
                    content_digest=sha256_bytes(content),
                )
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
                    for blob in files
                ],
            }
        )
        return GitHubSnapshotContents(
            claim=GitHubSnapshotClaim(
                owner=cli.REMOTE_REPOSITORY_OWNER,
                repository=cli.REMOTE_REPOSITORY_NAME,
                commit_oid=cli.REMOTE_REPOSITORY_COMMIT,
                tree_oid=cli.REMOTE_REPOSITORY_TREE,
                content_digest=content_digest,
            ),
            files=tuple(files),
            verified_commit_object=cli.GitCommitObject(
                cli.REMOTE_REPOSITORY_COMMIT, cli.REMOTE_REPOSITORY_TREE
            ),
        )

    def profile(self) -> cli.RemoteSnapshotExecutionProfile:
        return cli.RemoteSnapshotExecutionProfile(
            process_id="process-cli-remote-001",
            task_id="task-cli-remote-001",
            task_instruction="SYNTHETIC-PROMPT-CANARY: validate the route",
            declared_change_paths=("backend/routes.py",),
            allowed_commands=frozenset({"python3"}),
            test_command=("python3", "-m", "unittest"),
            worker=SimpleNamespace(propose=lambda _task: None),
            verifier=SimpleNamespace(verify=lambda _prepared: None),
            sandbox_backend=SimpleNamespace(create=lambda *_args: None),
            stage_sink=self.DummyStageSink(),
        )

    @staticmethod
    def permit(
        process_id="process-cli-remote-001",
        task_id="task-cli-remote-001",
        *,
        status=200,
        remaining=60,
        observed_monotonic=None,
        provider_call_approved=True,
        snapshot_evidence_origin="github_rest_api_claim",
    ):
        evidence = GitHubRateLimitEvidence(
            status=status,
            remaining=remaining,
            reset_unix=1791378648,
            observed_monotonic=(
                time.monotonic()
                if observed_monotonic is None
                else observed_monotonic
            ),
        )
        return cli.issue_remote_execution_permit(
            card_id="EXP-517",
            process_id=process_id,
            task_id=task_id,
            readiness=evidence,
            provider_call_approved=provider_call_approved,
            snapshot_evidence_origin=snapshot_evidence_origin,
        )

    @staticmethod
    def signed_verifier_client(
        *, host_trust_decision=True, validated_days_ago=0
    ):
        profile = cli.BRAINBOOSTER_VERIFIER_PROFILE
        endpoint = cli.PINNED_SIGNED_VERIFIER_ENDPOINT_URL
        authority_key_id = "synthetic-authority-exp796"
        worker_host_id = "synthetic-worker-host-exp796"
        verifier_host_id = "synthetic-testdev-host-exp796"
        authority_key = Ed25519PrivateKey.generate()
        verifier_key = Ed25519PrivateKey.generate()
        authority_public_key = authority_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        verifier_public_key = verifier_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        now = (
            datetime.now(timezone.utc).replace(microsecond=0)
            - timedelta(days=validated_days_ago)
        )
        enrollment = build_signed_verifier_trust_enrollment(
            enrollment_id="synthetic-enrollment-exp796",
            authority_key_id=authority_key_id,
            endpoint_url=endpoint,
            verifier_id=profile.expected_verifier_id,
            verifier_profile_digest=profile.profile_digest,
            verifier_key_id=profile.signer_key_id,
            verifier_public_key=verifier_public_key,
            worker_host_id=worker_host_id,
            verifier_host_id=verifier_host_id,
            host_separation_evidence_digest="sha256:" + "4" * 64,
            signing_key=authority_key,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        decision = None
        if host_trust_decision:
            decision = build_signed_verifier_host_trust_decision(
                decision_id="synthetic-host-decision-exp796",
                authority_key_id=authority_key_id,
                enrollment_digest=sha256_bytes(enrollment),
                endpoint_url=endpoint,
                verifier_id=profile.expected_verifier_id,
                verifier_profile_digest=profile.profile_digest,
                verifier_key_id=profile.signer_key_id,
                worker_host_id=worker_host_id,
                verifier_host_id=verifier_host_id,
                host_separation_evidence_digest="sha256:" + "4" * 64,
                signing_key=authority_key,
                issued_at=now,
                expires_at=now + timedelta(minutes=30),
            )
        transport = SignedVerifierHTTPSTransport(
            endpoint,
            connection_factory=lambda *_args, **_kwargs: None,
        )
        client = SignedVerifierClient.from_trust_enrollment(
            profile,
            transport,
            enrollment,
            trusted_authority_keys={authority_key_id: authority_public_key},
            expected_endpoint_url=endpoint,
            expected_worker_host_id=worker_host_id,
            expected_verifier_host_id=verifier_host_id,
            host_trust_decision_bytes=decision,
            now=now,
        )
        return client, worker_host_id, verifier_host_id

    def test_deepseek_profile_factory_injects_bounded_worker_without_credential_lookup(self):
        calls: list[str] = []
        profile = cli.build_deepseek_remote_execution_profile(
            process_id="process-cli-remote-002",
            task_id="task-cli-remote-002",
            task_instruction="SYNTHETIC-PROMPT-CANARY: validate the route",
            declared_change_paths=("backend/routes.py",),
            allowed_commands=frozenset({"python3"}),
            test_command=("python3", "-m", "unittest"),
            credential_source=lambda: calls.append("lookup") or "synthetic-key",
            verifier=SimpleNamespace(verify=lambda _prepared: None),
            sandbox_backend=SimpleNamespace(create=lambda *_args: None),
            stage_sink=self.DummyStageSink(),
        )

        self.assertIs(type(profile), cli.RemoteSnapshotExecutionProfile)
        self.assertIs(type(profile.worker), DeepSeekProposalWorker)
        self.assertIs(type(profile.worker.channel), DeepSeekHTTPChannel)
        self.assertEqual(profile.process_id, "process-cli-remote-002")
        self.assertEqual(profile.declared_change_paths, ("backend/routes.py",))
        self.assertEqual(calls, [])

    def test_deepseek_profile_factory_rejects_invalid_scope_without_lookup(self):
        calls: list[str] = []
        with self.assertRaisesRegex(ValueError, "^remote CLI runtime is unavailable$"):
            cli.build_deepseek_remote_execution_profile(
                process_id="process-cli-remote-003",
                task_id="task-cli-remote-003",
                task_instruction="synthetic instruction",
                declared_change_paths=("../outside.py",),
                allowed_commands=frozenset({"python3"}),
                test_command=("python3", "-m", "unittest"),
                credential_source=lambda: calls.append("lookup") or "synthetic-key",
                verifier=SimpleNamespace(verify=lambda _prepared: None),
                sandbox_backend=SimpleNamespace(create=lambda *_args: None),
                stage_sink=self.DummyStageSink(),
            )
        self.assertEqual(calls, [])

    def test_injected_worker_profile_does_not_require_a_credential_source(self):
        worker = SimpleNamespace(propose=lambda _request: None)
        profile = cli.build_deepseek_remote_execution_profile(
            process_id="process-cli-local-model-001",
            task_id="task-cli-local-model-001",
            task_instruction="synthetic instruction",
            declared_change_paths=("backend/routes.py",),
            allowed_commands=frozenset({"python3"}),
            test_command=("python3", "-m", "unittest"),
            credential_source=None,
            proposal_worker=worker,
            verifier=SimpleNamespace(verify=lambda _prepared: None),
            sandbox_backend=SimpleNamespace(create=lambda *_args: None),
            stage_sink=self.DummyStageSink(),
        )
        self.assertIs(profile.worker, worker)

    def test_codeload_profile_does_not_require_a_raw_git_commit_source(self):
        profile = replace(
            self.profile(),
            git_executable="/nonexistent/agent00x-git",
            snapshot_evidence_origin="github_codeload_archive",
        )
        self.assertIs(cli._validate_remote_execution_profile(profile), profile)

    def test_explicit_runtime_wires_pinned_docker_and_sqlite_without_lookup(self):
        calls: list[str] = []
        captured: dict = {}
        observer_store = ObservationStore()
        proposal_worker = SimpleNamespace(propose=lambda _request: None)
        execution_worker = JournaledProposalWorker(
            proposal_worker,
            observer_store,
            process_id="process-cli-runtime-001",
            task_id="task-cli-runtime-001",
        )
        verifier_config = cli.VerifierContainerConfig(
            docker_executable="/usr/bin/docker",
            runtime_image_id="sha256:" + "a" * 64,
            verifier_code_digest="sha256:" + "b" * 64,
        )

        def fake_main(argv, **kwargs):
            captured["argv"] = argv
            captured["profile"] = kwargs["remote_execution_profile"]
            captured["execution_worker"] = kwargs["execution_worker"]
            return 0

        with tempfile.TemporaryDirectory(prefix="agent00x-runtime-factory-") as root:
            database = Path(root) / "stage.sqlite3"
            with patch.object(cli, "main", side_effect=fake_main) as main:
                code = cli.run_remote_snapshot_with_runtime(
                    process_id="process-cli-runtime-001",
                    task_id="task-cli-runtime-001",
                    task_instruction="SYNTHETIC-PROMPT-CANARY: validate the route",
                    declared_change_paths=("backend/routes.py",),
                    allowed_commands=frozenset({"python3"}),
                    test_command=("python3", "-m", "unittest"),
                    execution_image="sha256:" + "c" * 64,
                    credential_source=lambda: calls.append("lookup") or "synthetic-key",
                    proposal_worker=proposal_worker,
                    verifier_config=verifier_config,
                    stage_database_path=database,
                    execution_permit=self.permit(
                        "process-cli-runtime-001", "task-cli-runtime-001"
                    ),
                    observation_store=observer_store,
                    execution_worker=execution_worker,
                )

            self.assertEqual(code, 0)
            self.assertTrue(database.is_file())
            main.assert_called_once()
            self.assertEqual(captured["argv"], ["--remote-snapshot-execute"])
            profile = captured["profile"]
            self.assertEqual(profile.stage_database_path, database)
            self.assertIs(profile.observation_store, observer_store)
            self.assertIs(profile.worker, proposal_worker)
            self.assertIs(captured["execution_worker"], execution_worker)
            self.assertIs(type(profile.verifier), cli.DockerContainerVerifier)
            self.assertIs(type(profile.sandbox_backend), cli.DockerSandboxBackend)
            self.assertEqual(profile.sandbox_backend.image, "sha256:" + "c" * 64)
            self.assertIs(type(profile.stage_sink), cli.SQLiteStagedArtifactStore)
            self.assertEqual(calls, [])

    def test_explicit_runtime_accepts_fixed_classic_store_verifier(self):
        captured: dict = {}
        verifier = cli.ClassicStoreBrainboosterVerifier("/usr/bin/docker")

        def fake_main(argv, **kwargs):
            captured["profile"] = kwargs["remote_execution_profile"]
            return 0

        with tempfile.TemporaryDirectory(prefix="pinned-classic-store-runtime-") as root:
            database = Path(root) / "stage.sqlite3"
            with patch.object(cli, "main", side_effect=fake_main):
                code = cli.run_remote_snapshot_with_runtime(
                    process_id="process-cli-classic-store-001",
                    task_id="task-cli-classic-store-001",
                    task_instruction="synthetic classic-store verifier wiring",
                    declared_change_paths=("backend/routes.py",),
                    allowed_commands=frozenset({"python3"}),
                    test_command=("python3", "-m", "unittest"),
                    execution_image="sha256:" + "c" * 64,
                    credential_source=None,
                    proposal_worker=SimpleNamespace(propose=lambda _request: None),
                    classic_store_verifier=verifier,
                    stage_database_path=database,
                    execution_permit=self.permit(
                        "process-cli-classic-store-001",
                        "task-cli-classic-store-001",
                    ),
                )

        self.assertEqual(code, 0)
        self.assertIs(captured["profile"].verifier, verifier)

    def test_explicit_runtime_rejects_mixed_verifier_backends_before_side_effects(self):
        verifier = cli.ClassicStoreBrainboosterVerifier("/usr/bin/docker")
        config = cli.VerifierContainerConfig(
            docker_executable="/usr/bin/docker",
            runtime_image_id="sha256:" + "a" * 64,
            verifier_code_digest="sha256:" + "b" * 64,
        )
        with tempfile.TemporaryDirectory(prefix="mixed-verifier-runtime-") as root:
            database = Path(root) / "must-not-exist.sqlite3"
            with patch.object(cli, "main") as main:
                with self.assertRaisesRegex(
                    ValueError, "^remote CLI runtime is unavailable$"
                ):
                    cli.run_remote_snapshot_with_runtime(
                        process_id="process-cli-mixed-verifier-001",
                        task_id="task-cli-mixed-verifier-001",
                        task_instruction="synthetic mixed verifier wiring",
                        declared_change_paths=("backend/routes.py",),
                        allowed_commands=frozenset({"python3"}),
                        test_command=("python3", "-m", "unittest"),
                        execution_image="sha256:" + "c" * 64,
                        credential_source=None,
                        verifier_config=config,
                        classic_store_verifier=verifier,
                        stage_database_path=database,
                        execution_permit=self.permit(
                            "process-cli-mixed-verifier-001",
                            "task-cli-mixed-verifier-001",
                        ),
                    )
            self.assertFalse(database.exists())
            main.assert_not_called()

        client, worker_host_id, verifier_host_id = self.signed_verifier_client()
        with tempfile.TemporaryDirectory(prefix="mixed-signed-classic-runtime-") as root:
            database = Path(root) / "must-not-exist.sqlite3"
            with patch.object(cli, "main") as main:
                with self.assertRaisesRegex(
                    ValueError, "^remote CLI runtime is unavailable$"
                ):
                    cli.run_remote_snapshot_with_runtime(
                        process_id="process-cli-mixed-signed-classic-001",
                        task_id="task-cli-mixed-signed-classic-001",
                        task_instruction="synthetic mixed signed/classic verifier wiring",
                        declared_change_paths=("backend/routes.py",),
                        allowed_commands=frozenset({"python3"}),
                        test_command=("python3", "-m", "unittest"),
                        execution_image="sha256:" + "c" * 64,
                        credential_source=None,
                        proposal_worker=SimpleNamespace(propose=lambda _request: None),
                        verifier_client=client,
                        classic_store_verifier=verifier,
                        expected_worker_host_id=worker_host_id,
                        expected_verifier_host_id=verifier_host_id,
                        stage_database_path=database,
                        execution_permit=self.permit(
                            "process-cli-mixed-signed-classic-001",
                            "task-cli-mixed-signed-classic-001",
                        ),
                    )
            self.assertFalse(database.exists())
            main.assert_not_called()

    def test_explicit_runtime_accepts_only_trusted_pinned_signed_verifier(self):
        client, worker_host_id, verifier_host_id = self.signed_verifier_client()
        self.assertTrue(client.independent_host_trust_established)
        self.assertEqual(
            client.endpoint_url, cli.PINNED_SIGNED_VERIFIER_ENDPOINT_URL
        )

        captured: dict = {}

        def fake_main(argv, **kwargs):
            captured["profile"] = kwargs["remote_execution_profile"]
            return 0

        with tempfile.TemporaryDirectory(prefix="agent00x-signed-verifier-runtime-") as root:
            database = Path(root) / "stage.sqlite3"
            with patch.object(cli, "main", side_effect=fake_main):
                code = cli.run_remote_snapshot_with_runtime(
                    process_id="process-cli-signed-verifier-001",
                    task_id="task-cli-signed-verifier-001",
                    task_instruction="synthetic signed-verifier runtime test",
                    declared_change_paths=("backend/routes.py",),
                    allowed_commands=frozenset({"python3"}),
                    test_command=("python3", "-m", "unittest"),
                    execution_image="sha256:" + "c" * 64,
                    credential_source=lambda: self.fail(
                        "runtime construction must not resolve the Worker credential"
                    ),
                    stage_database_path=database,
                    execution_permit=self.permit(
                        "process-cli-signed-verifier-001",
                        "task-cli-signed-verifier-001",
                    ),
                    verifier_client=client,
                    expected_worker_host_id=worker_host_id,
                    expected_verifier_host_id=verifier_host_id,
                )
            self.assertEqual(code, 0)
            self.assertTrue(database.is_file())
            self.assertIs(captured["profile"].verifier, client)

    def test_explicit_runtime_rejects_audit_only_signed_verifier_before_side_effects(self):
        client, worker_host_id, verifier_host_id = self.signed_verifier_client(
            host_trust_decision=False
        )
        self.assertFalse(client.independent_host_trust_established)
        calls: list[str] = []

        with tempfile.TemporaryDirectory(prefix="agent00x-audit-only-verifier-") as root:
            database = Path(root) / "must-not-exist.sqlite3"
            with patch.object(cli, "main") as main:
                with self.assertRaisesRegex(
                    ValueError, "^remote CLI runtime is unavailable$"
                ):
                    cli.run_remote_snapshot_with_runtime(
                        process_id="process-cli-audit-verifier-001",
                        task_id="task-cli-audit-verifier-001",
                        task_instruction="synthetic audit-only verifier test",
                        declared_change_paths=("backend/routes.py",),
                        allowed_commands=frozenset({"python3"}),
                        test_command=("python3", "-m", "unittest"),
                        execution_image="sha256:" + "c" * 64,
                        credential_source=lambda: calls.append("lookup")
                        or "synthetic-key",
                        stage_database_path=database,
                        execution_permit=self.permit(
                            "process-cli-audit-verifier-001",
                            "task-cli-audit-verifier-001",
                        ),
                        verifier_client=client,
                        expected_worker_host_id=worker_host_id,
                        expected_verifier_host_id=verifier_host_id,
                    )
            self.assertFalse(database.exists())
            main.assert_not_called()
            self.assertEqual(calls, [])

    def test_explicit_runtime_rejects_expired_signed_trust_before_side_effects(self):
        client, worker_host_id, verifier_host_id = self.signed_verifier_client(
            validated_days_ago=2
        )
        self.assertTrue(client.independent_host_trust_established)
        self.assertFalse(client.has_current_independent_host_trust())
        calls: list[str] = []

        with tempfile.TemporaryDirectory(prefix="agent00x-expired-verifier-trust-") as root:
            database = Path(root) / "must-not-exist.sqlite3"
            with patch.object(cli, "main") as main:
                with self.assertRaisesRegex(
                    ValueError, "^remote CLI runtime is unavailable$"
                ):
                    cli.run_remote_snapshot_with_runtime(
                        process_id="process-cli-expired-verifier-001",
                        task_id="task-cli-expired-verifier-001",
                        task_instruction="synthetic expired verifier trust test",
                        declared_change_paths=("backend/routes.py",),
                        allowed_commands=frozenset({"python3"}),
                        test_command=("python3", "-m", "unittest"),
                        execution_image="sha256:" + "c" * 64,
                        credential_source=lambda: calls.append("lookup")
                        or "synthetic-key",
                        stage_database_path=database,
                        execution_permit=self.permit(
                            "process-cli-expired-verifier-001",
                            "task-cli-expired-verifier-001",
                        ),
                        verifier_client=client,
                        expected_worker_host_id=worker_host_id,
                        expected_verifier_host_id=verifier_host_id,
                    )
            self.assertFalse(database.exists())
            main.assert_not_called()
            self.assertEqual(calls, [])

    def test_explicit_runtime_rejects_invalid_scope_before_database_or_reader(self):
        calls: list[str] = []
        verifier_config = cli.VerifierContainerConfig(
            docker_executable="/usr/bin/docker",
            runtime_image_id="sha256:" + "a" * 64,
            verifier_code_digest="sha256:" + "b" * 64,
        )

        with tempfile.TemporaryDirectory(prefix="agent00x-runtime-invalid-") as root:
            database = Path(root) / "must-not-exist.sqlite3"
            with patch.object(cli, "main") as main:
                with self.assertRaisesRegex(
                    ValueError, "^remote CLI runtime is unavailable$"
                ):
                    cli.run_remote_snapshot_with_runtime(
                        process_id="process-cli-runtime-002",
                        task_id="task-cli-runtime-002",
                        task_instruction="synthetic instruction",
                        declared_change_paths=("../outside.py",),
                        allowed_commands=frozenset({"python3"}),
                        test_command=("python3", "-m", "unittest"),
                        execution_image="sha256:" + "c" * 64,
                        credential_source=lambda: calls.append("lookup") or "synthetic-key",
                        verifier_config=verifier_config,
                        stage_database_path=database,
                        execution_permit=self.permit(
                            "process-cli-runtime-002", "task-cli-runtime-002"
                        ),
                    )
            self.assertFalse(database.exists())
            main.assert_not_called()
            self.assertEqual(calls, [])

    def test_explicit_runtime_accepts_digest_reference_without_mutable_tag_fallback(self):
        for image in (
            "sha256:" + "d" * 64,
            "python:3.11.16-slim@sha256:" + "f" * 64,
            "registry.example.test/agent00x/brainbooster:runtime-v1@sha256:"
            + "e" * 64,
        ):
            with self.subTest(image=image):
                calls: list[str] = []
                captured: dict = {}
                verifier_config = cli.VerifierContainerConfig(
                    docker_executable="/usr/bin/docker",
                    runtime_image_id="sha256:" + "a" * 64,
                    verifier_code_digest="sha256:" + "b" * 64,
                )

                def fake_main(argv, **kwargs):
                    captured["profile"] = kwargs["remote_execution_profile"]
                    return 0

                with tempfile.TemporaryDirectory(prefix="agent00x-runtime-image-") as root:
                    with patch.object(cli, "main", side_effect=fake_main):
                        cli.run_remote_snapshot_with_runtime(
                            process_id="process-cli-runtime-image-001",
                            task_id="task-cli-runtime-image-001",
                            task_instruction="synthetic instruction",
                            declared_change_paths=("backend/routes.py",),
                            allowed_commands=frozenset({"python3"}),
                            test_command=("python3", "-m", "unittest"),
                            execution_image=image,
                            credential_source=lambda: calls.append("lookup") or "synthetic-key",
                            verifier_config=verifier_config,
                            stage_database_path=Path(root) / "stage.sqlite3",
                            execution_permit=self.permit(
                                "process-cli-runtime-image-001",
                                "task-cli-runtime-image-001",
                            ),
                        )

                self.assertEqual(captured["profile"].sandbox_backend.image, image)
                self.assertEqual(calls, [])

    def test_explicit_runtime_rejects_unpinned_execution_image_before_side_effects(self):
        verifier_config = cli.VerifierContainerConfig(
            docker_executable="/usr/bin/docker",
            runtime_image_id="sha256:" + "a" * 64,
            verifier_code_digest="sha256:" + "b" * 64,
        )
        for image in (
            None,
            "",
            "python:3.11.16-slim",
            "python:latest",
            "--network=host",
            "sha256:" + "F" * 64,
            "sha256:" + "f" * 63,
            "registry.example.test/agent00x/runtime:tag",
            "registry..example/agent00x/runtime@sha256:" + "f" * 64,
            "registry.example.test//runtime@sha256:" + "f" * 64,
            "registry.example.test:abc/runtime@sha256:" + "f" * 64,
            "/agent00x/runtime@sha256:" + "f" * 64,
            "registry.example.test/agent00x/runtime@sha256:" + "g" * 64,
            object(),
        ):
            with self.subTest(image=repr(image)), tempfile.TemporaryDirectory(
                prefix="agent00x-runtime-image-invalid-"
            ) as root:
                calls: list[str] = []
                database = Path(root) / "must-not-exist.sqlite3"
                permit = self.permit(
                    "process-cli-runtime-image-invalid-001",
                    "task-cli-runtime-image-invalid-001",
                )
                with (
                    patch.object(cli, "main") as main,
                    patch.object(cli, "DockerSandboxBackend") as sandbox,
                ):
                    with self.assertRaisesRegex(
                        ValueError, "^remote CLI runtime is unavailable$"
                    ):
                        cli.run_remote_snapshot_with_runtime(
                            process_id="process-cli-runtime-image-invalid-001",
                            task_id="task-cli-runtime-image-invalid-001",
                            task_instruction="synthetic instruction",
                            declared_change_paths=("backend/routes.py",),
                            allowed_commands=frozenset({"python3"}),
                            test_command=("python3", "-m", "unittest"),
                            execution_image=image,
                            credential_source=lambda: calls.append("lookup") or "synthetic-key",
                            verifier_config=verifier_config,
                            stage_database_path=database,
                            execution_permit=permit,
                        )
                self.assertFalse(database.exists())
                main.assert_not_called()
                sandbox.assert_not_called()
                self.assertEqual(calls, [])
                permit.validate(
                    process_id="process-cli-runtime-image-invalid-001",
                    task_id="task-cli-runtime-image-invalid-001",
                )

    @staticmethod
    def verified_result() -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.VERIFIED,
            snapshot_claim_digest="sha256:" + "1" * 64,
            verified_contents_digest="sha256:" + "2" * 64,
            verification_digest="sha256:" + "3" * 64,
            staged_change_digest="sha256:" + "4" * 64,
            verifier_result=SimpleNamespace(verifier_id="synthetic-verifier"),
        )

    def test_worker_terminal_outcomes_have_fixed_cli_projection(self):
        cases = (
            ("clarification_required", "conflicting_requirements", "needs_input"),
            ("blocked", "target_test_outcome_unknown", "blocked"),
            ("denied", "publication_not_authorized", "denied"),
        )
        for outcome, reason_code, expected_status in cases:
            with self.subTest(outcome=outcome):
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    worker_terminal_outcome=outcome,
                    worker_terminal_reason_code=reason_code,
                )
                payload = cli._remote_execution_evidence(result)
                self.assertEqual(payload["status"], expected_status)
                self.assertEqual(payload["reason_code"], reason_code)
                self.assertIs(payload["external_write"], False)
                self.assertEqual(payload["approval"], "not_created")
                self.assertEqual(payload["publication"], "not_attempted")

        malformed = ExecutionResult(
            status=ExecutionStatus.FAILED,
            worker_terminal_outcome="denied",
            worker_terminal_reason_code="conflicting_requirements",
        )
        payload = cli._remote_execution_evidence(malformed)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(
            payload["failure_code"], "remote-snapshot-execution-failed"
        )

    def test_local_cli_returns_terminal_worker_status(self):
        class Worker:
            def propose(self, _task):
                from app_contracts.executor import WorkerTerminalOutcome

                return WorkerTerminalOutcome(
                    "blocked", "target_test_outcome_unknown"
                )

        class Verifier:
            def verify(self, _prepared):
                raise AssertionError("verifier must not run")

        out, err = io.StringIO(), io.StringIO()
        code = cli.main(
            [], stdout=out, stderr=err, worker=Worker(), verifier=Verifier()
        )
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(
            json.loads(out.getvalue()),
            {"status": "blocked", "reason_code": "target_test_outcome_unknown"},
        )

    def test_missing_or_invalid_runtime_fails_before_snapshot_read(self):
        for profile in (None, object()):
            with self.subTest(profile=type(profile).__name__):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(cli, "read_github_snapshot_contents") as read:
                    code = cli.main(
                        ["--remote-snapshot-execute"],
                        stdout=out,
                        stderr=err,
                        remote_execution_profile=profile,
                    )
                self.assertEqual(code, 2)
                self.assertEqual(err.getvalue(), "")
                self.assertEqual(read.call_count, 0)
                self.assertEqual(
                    json.loads(out.getvalue()),
                    {
                        "status": "error",
                        "failure_code": (
                            "remote-execution-runtime-unavailable"
                            if profile is None
                            else "remote-execution-profile-invalid"
                        ),
                    },
                )

    def test_missing_authorization_fails_before_snapshot_read(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "read_github_snapshot_contents") as read:
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=self.profile(),
            )
        self.assertEqual(code, 2)
        self.assertEqual(read.call_count, 0)
        self.assertEqual(
            json.loads(out.getvalue()),
            {
                "status": "error",
                "failure_code": "remote-execution-authorization-unavailable",
            },
        )

    def test_permit_rejects_insufficient_or_unapproved_readiness(self):
        for status, remaining, approved in (
            (403, 60, True),
            (200, 35, True),
            (200, 60, False),
        ):
            with self.subTest(status=status, remaining=remaining, approved=approved):
                with self.assertRaises(cli.RemoteExecutionPermitError):
                    self.permit(
                        status=status,
                        remaining=remaining,
                        provider_call_approved=approved,
                    )

    def test_permit_accepts_exact_readiness_threshold(self):
        permit = self.permit(remaining=36)

        self.assertIs(type(permit), cli.RemoteExecutionPermit)

    def test_permit_is_bound_fresh_and_single_use_under_concurrency(self):
        permit = self.permit()
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def consume():
            barrier.wait()
            try:
                permit.consume(
                    process_id="process-cli-remote-001",
                    task_id="task-cli-remote-001",
                )
                outcomes.append("accepted")
            except cli.RemoteExecutionPermitError:
                outcomes.append("rejected")

        threads = [threading.Thread(target=consume) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(outcomes, ["accepted", "rejected"])
        with self.assertRaises(cli.RemoteExecutionPermitError):
            permit.consume(
                process_id="process-cli-remote-001",
                task_id="task-cli-remote-001",
            )

    def test_stale_or_mismatched_permit_is_burned_before_snapshot_read(self):
        stale = self.permit()
        mismatched = self.permit(process_id="another-process")
        for permit, clock_value in (
            (stale, stale.readiness.observed_monotonic + 121),
            (mismatched, time.monotonic()),
        ):
            out, err = io.StringIO(), io.StringIO()
            with (
                patch.object(cli.time, "monotonic", return_value=clock_value),
                patch.object(cli, "read_github_snapshot_contents") as read,
            ):
                code = cli.main(
                    ["--remote-snapshot-execute"],
                    stdout=out,
                    stderr=err,
                    remote_execution_profile=self.profile(),
                    execution_permit=permit,
                )
            self.assertEqual(code, 2)
            self.assertEqual(read.call_count, 0)
            self.assertEqual(
                json.loads(out.getvalue())["failure_code"],
                "remote-execution-authorization-unavailable",
            )
            with self.assertRaises(cli.RemoteExecutionPermitError):
                permit.consume(
                    process_id="process-cli-remote-001",
                    task_id="task-cli-remote-001",
                )

    def test_permit_source_mismatch_fails_before_either_snapshot_reader(self):
        permit = self.permit(snapshot_evidence_origin="github_rest_api_claim")
        profile = replace(
            self.profile(), snapshot_evidence_origin="github_codeload_archive"
        )
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "read_github_snapshot_contents") as rest_reader,
            patch.object(cli, "read_github_archive_snapshot_contents") as archive_reader,
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=profile,
                execution_permit=permit,
            )
        self.assertEqual(code, 2)
        self.assertEqual(rest_reader.call_count, 0)
        self.assertEqual(archive_reader.call_count, 0)
        self.assertEqual(
            json.loads(out.getvalue())["failure_code"],
            "remote-execution-authorization-unavailable",
        )

    def test_fixed_snapshot_profile_executes_and_emits_only_digest_evidence(self):
        snapshot = self.make_full_snapshot()
        result = self.verified_result()
        profile = self.profile()
        transport = object()
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport", return_value=transport),
            patch.object(cli, "read_github_snapshot_contents", return_value=snapshot) as read,
            patch.object(cli, "REMOTE_REPOSITORY_CONTENT_DIGEST", snapshot.claim.content_digest),
            patch.object(cli, "run_remote_snapshot_execution", return_value=result) as execute,
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=profile,
                execution_permit=self.permit(),
            )

        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        request = read.call_args.args[0]
        self.assertEqual(request.owner, cli.REMOTE_REPOSITORY_OWNER)
        self.assertEqual(request.repository, cli.REMOTE_REPOSITORY_NAME)
        self.assertEqual(request.commit_oid, cli.REMOTE_REPOSITORY_COMMIT)
        self.assertIsNone(request.include_paths)
        self.assertIs(read.call_args.args[1], transport)
        source = read.call_args.kwargs["commit_object_source"]
        self.assertIs(type(source), cli.GitHubRawCommitObjectSource)
        args = execute.call_args.kwargs
        self.assertIs(args["worker"], profile.worker)
        self.assertIs(args["verifier"], profile.verifier)
        self.assertIs(args["sandbox_backend"], profile.sandbox_backend)
        self.assertIs(args["stage_sink"], profile.stage_sink)
        self.assertEqual(args["context_files"], (("backend/routes.py", "SOURCE-CANARY\n"),))
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "verified")
        self.assertEqual(payload["staged_change_digest"], result.staged_change_digest)
        self.assertEqual(payload["external_write"], False)
        self.assertEqual(payload["approval"], "not_created")
        self.assertEqual(payload["publication"], "not_attempted")
        self.assertEqual(
            payload["raw_commit_object"],
            {
                "status": "verified-by-object-hash",
                "commit_oid": cli.REMOTE_REPOSITORY_COMMIT,
                "root_tree_oid": cli.REMOTE_REPOSITORY_TREE,
            },
        )
        self.assertIn(
            "verifier-trust-depends-on-the-injected-authority-and-host-decision",
            payload["limitations"],
        )
        self.assertIn("verifier_identity_digest", payload)
        self.assertNotIn("SOURCE-CANARY", out.getvalue())
        self.assertNotIn("SYNTHETIC-PROMPT-CANARY", out.getvalue())

    def test_observed_snapshot_intake_precedes_same_worker_executor_handoff(self):
        snapshot = self.make_full_snapshot()
        result = self.verified_result()
        observer_store = ObservationStore()
        profile = replace(self.profile(), observation_store=observer_store)
        execution_worker = JournaledProposalWorker(
            profile.worker,
            observer_store,
            process_id=profile.process_id,
            task_id=profile.task_id,
        )
        execution_worker.run_controlled_step(
            "GitHubReadiness.fetch",
            lambda: "synthetic readiness metadata",
            process_id=profile.process_id,
        )
        issued_permit = execution_worker.run_controlled_step(
            "RemoteExecutionPermit.issue",
            self.permit,
            process_id=profile.process_id,
        )
        raw_source = lambda _claim: b"synthetic raw commit object"
        captured = {}
        out, err = io.StringIO(), io.StringIO()

        def fake_snapshot_reader(request, transport, *, commit_object_source):
            authorization_event = observer_store.events()[-1]
            self.assertEqual(authorization_event["event_type"], "decision_applied")
            self.assertEqual(authorization_event["decision_or_tool"], "RemoteExecutionPermit.consume")
            self.assertEqual(authorization_event["status"], "ok")
            response = transport(
                "GET",
                "https://api.github.com/repos/Owner/Repo/commits/"
                + request.commit_oid,
                {
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                },
                1_000_000,
                allow_redirects=False,
            )
            self.assertEqual(response, {"status": 200, "body": b"{}"})
            self.assertEqual(
                commit_object_source(SimpleNamespace()), raw_source(None)
            )
            return snapshot

        def fake_executor(
            _snapshot,
            *,
            worker,
            observation_store,
            **_kwargs,
        ):
            self.assertEqual(
                observation_store.events()[-1]["event_type"], "decision_applied"
            )
            self.assertEqual(observation_store.events()[-1]["status"], "ok")
            captured["worker"] = worker
            captured["store"] = observation_store
            self.assertIs(worker, execution_worker)
            return result

        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport", return_value=lambda *_args, **_kwargs: {"status": 200, "body": b"{}"}),
            patch.object(cli, "GitHubRawCommitObjectSource", return_value=raw_source),
            patch.object(cli, "read_github_snapshot_contents", side_effect=fake_snapshot_reader),
            patch.object(cli, "REMOTE_REPOSITORY_CONTENT_DIGEST", snapshot.claim.content_digest),
            patch.object(cli, "run_remote_snapshot_execution", side_effect=fake_executor),
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=profile,
                execution_permit=issued_permit,
                execution_worker=execution_worker,
            )

        events = observer_store.events()
        evidence = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(
            evidence["observer"],
            {
                "run_id": events[-1]["run_id"],
                "as_of_cursor": len(events) - 1,
                "completeness": "partial",
            },
        )
        report = build_history_report(
            list(enumerate(events)),
            list(enumerate(observer_store.checkpoints())),
            run_id=evidence["observer"]["run_id"],
            as_of_cursor=evidence["observer"]["as_of_cursor"],
        )
        self.assertEqual(
            report["snapshot"]["event_count"],
            evidence["observer"]["as_of_cursor"] + 1,
        )
        self.assertEqual(report["snapshot"]["completeness"], "partial")
        self.assertEqual(
            [event["decision_or_tool"] for event in events if event["event_type"] == "tool_requested"],
            [
                "GitHubReadiness.fetch",
                "GitHubSnapshot.GET.commit",
                "GitHubRawCommitObjectSource.read",
            ],
        )
        self.assertEqual(
            [event["sequence"] for event in events], list(range(len(events)))
        )
        self.assertEqual(
            [
                event.get("decision_or_tool")
                for event in events
                if event.get("event_type")
                in {"decision_proposed", "tool_requested"}
                and event.get("decision_or_tool")
                in {
                    "GitHubReadiness.fetch",
                    "RemoteExecutionPermit.issue",
                    "RemoteExecutionPermit.consume",
                    "PinnedSnapshot.validate-fixed-pin",
                }
            ],
            [
                "GitHubReadiness.fetch",
                "RemoteExecutionPermit.issue",
                "RemoteExecutionPermit.consume",
                "PinnedSnapshot.validate-fixed-pin",
            ],
        )
        self.assertEqual(len({event["run_id"] for event in events}), 1)
        self.assertEqual(type(captured["worker"]).__name__, "JournaledProposalWorker")
        self.assertTrue(
            captured["worker"].matches(
                observer_store,
                process_id=profile.process_id,
                task_id=profile.task_id,
            )
        )
        self.assertIs(captured["store"], observer_store)
        self.assertEqual(evidence["status"], "verified")

    def test_observed_rejected_permit_stops_before_snapshot_intake(self):
        observer_store = ObservationStore()
        profile = replace(self.profile(), observation_store=observer_store)
        out, err = io.StringIO(), io.StringIO()
        rejected_permit = self.permit(process_id="process-other-cli-remote-001")
        with (
            patch.object(cli, "read_github_snapshot_contents") as read_snapshot,
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=profile,
                execution_permit=rejected_permit,
            )

        self.assertEqual(code, 2)
        self.assertEqual(
            json.loads(out.getvalue()),
            {
                "status": "error",
                "failure_code": "remote-execution-authorization-unavailable",
                "observer": {
                    "run_id": observer_store.events()[0]["run_id"],
                    "as_of_cursor": len(observer_store.events()) - 1,
                    "completeness": "partial",
                },
            },
        )
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(observer_store.events()[-2]["event_type"], "decision_applied")
        self.assertEqual(observer_store.events()[-2]["status"], "denied")
        self.assertEqual(observer_store.events()[-1]["event_type"], "agent_finished")
        self.assertEqual(observer_store.events()[-1]["status"], "failed")
        read_snapshot.assert_not_called()

    def test_observed_permit_journal_failures_stop_before_snapshot_intake(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint(self, checkpoint):
                if checkpoint.get("agent_id") == "service-execution-authorizer":
                    raise RuntimeError("synthetic gate refusal")
                return super().record_checkpoint(checkpoint)

        class LoseTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-execution-authorizer"
                    and event.get("event_type") == "decision_applied"
                ):
                    raise RuntimeError("synthetic terminal loss")
                return super().append(event)

        for store_type, consumed in ((RefusingStore, False), (LoseTerminalStore, True)):
            with self.subTest(store=store_type.__name__):
                observer_store = store_type()
                profile = replace(self.profile(), observation_store=observer_store)
                permit = self.permit()
                out, err = io.StringIO(), io.StringIO()
                with (
                    patch.object(cli, "read_github_snapshot_contents") as read_snapshot,
                    patch.object(cli, "GitHubAnonymousSnapshotTransport"),
                ):
                    code = cli.main(
                        ["--remote-snapshot-execute"],
                        stdout=out,
                        stderr=err,
                        remote_execution_profile=profile,
                        execution_permit=permit,
                    )
                self.assertEqual(code, 2)
                self.assertEqual(
                    json.loads(out.getvalue())["failure_code"],
                    "remote-execution-authorization-unavailable",
                )
                self.assertEqual(err.getvalue(), "")
                read_snapshot.assert_not_called()
                self.assertEqual(permit._consumed, consumed)

    def test_observed_pin_mismatch_is_journaled_before_executor_refusal(self):
        snapshot = self.make_full_snapshot()
        observer_store = ObservationStore()
        profile = replace(self.profile(), observation_store=observer_store)
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
            patch.object(cli, "read_github_snapshot_contents", return_value=snapshot),
            patch.object(cli, "run_remote_snapshot_execution") as execute,
        ):
            with self.assertRaisesRegex(ValueError, "^remote snapshot pin mismatch$"):
                cli._run_pinned_remote_execution(profile)
        events = observer_store.events()
        self.assertEqual(events[-2]["event_type"], "decision_proposed")
        self.assertEqual(events[-1]["event_type"], "decision_applied")
        self.assertEqual(events[-1]["status"], "denied")
        self.assertEqual(events[-1]["error_code"], "pinned-snapshot-rejected")
        execute.assert_not_called()

    def test_unknown_observed_pin_decision_never_reaches_executor(self):
        class LoseDecisionTerminalStore:
            def __init__(self):
                self.inner = ObservationStore()

            def append(self, event):
                if event.get("event_type") == "decision_applied":
                    raise RuntimeError("synthetic journal loss")
                return self.inner.append(event)

            def events(self):
                return self.inner.events()

            def record_checkpoint(self, checkpoint):
                return self.inner.record_checkpoint(checkpoint)

        snapshot = self.make_full_snapshot()
        observer_store = LoseDecisionTerminalStore()
        profile = replace(self.profile(), observation_store=observer_store)
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
            patch.object(cli, "read_github_snapshot_contents", return_value=snapshot),
            patch.object(
                cli, "REMOTE_REPOSITORY_CONTENT_DIGEST", snapshot.claim.content_digest
            ),
            patch.object(cli, "run_remote_snapshot_execution") as execute,
        ):
            with self.assertRaisesRegex(
                ValueError, "^remote CLI observer is unavailable$"
            ):
                cli._run_pinned_remote_execution(profile)
        execute.assert_not_called()

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1",
        "synthetic pinned CLI Docker composition is opt-in",
    )
    def test_synthetic_pinned_cli_runs_docker_verifier_and_durable_stage(self):
        snapshot = self.make_full_snapshot()
        route_source = next(
            blob.content.decode("utf-8")
            for blob in snapshot.files
            if blob.path == "backend/routes.py"
        )
        proposed = route_source + "# cli-synthetic-candidate\n"
        credential_calls: list[str] = []

        class FixedWorker:
            def __init__(self, credential_source):
                self.calls = 0
                self.credential_source = credential_source

            def propose(self, _task):
                self.calls += 1
                return WorkerProposal((("backend/routes.py", proposed),))

        docker = shutil.which("docker")
        self.assertTrue(docker and Path(docker).is_absolute())
        worker = FixedWorker(
            lambda: credential_calls.append("lookup") or "synthetic-key"
        )
        target_image_id = TARGET_RUNTIME_IMAGE_ID
        verifier_image_id = VERIFIER_RUNTIME_IMAGE_ID
        verifier_code_digest = VERIFIER_RUNTIME_CODE_DIGEST
        verifier_identity = (
            f"docker-image:{verifier_image_id}/code:{verifier_code_digest}"
        )
        profile = cli.RemoteSnapshotExecutionProfile(
            process_id="process-exp530-cli-001",
            task_id="task-exp530-cli-001",
            task_instruction="Append a fixed synthetic marker to the route file",
            declared_change_paths=("backend/routes.py",),
            allowed_commands=frozenset({"python3"}),
            test_command=(
                "python3",
                "-c",
                "from pathlib import Path; assert Path('backend/routes.py').read_text().endswith('# cli-synthetic-candidate\\n')",
            ),
            worker=worker,
            verifier=cli.DockerContainerVerifier(
                cli.VerifierContainerConfig(
                    docker_executable=docker,
                    runtime_image_id=verifier_image_id,
                    verifier_code_digest=verifier_code_digest,
                    timeout_seconds=60,
                    max_stdout_bytes=65_536,
                    max_stderr_bytes=16_384,
                )
            ),
            sandbox_backend=cli.DockerSandboxBackend(target_image_id),
            stage_sink=None,
        )
        out, err = io.StringIO(), io.StringIO()
        readiness = GitHubRateLimitEvidence(
            status=200,
            remaining=60,
            reset_unix=1791384392,
            observed_monotonic=time.monotonic(),
        )
        permit = cli.issue_remote_execution_permit(
            card_id="EXP-530",
            process_id=profile.process_id,
            task_id=profile.task_id,
            readiness=readiness,
            provider_call_approved=True,
        )

        with tempfile.TemporaryDirectory(prefix="agent00x-exp530-cli-stage-") as root:
            database = Path(root) / "stage.sqlite3"
            with cli.SQLiteStagedArtifactStore(database) as store:
                profile = replace(profile, stage_sink=store)
                with (
                    patch.object(
                        cli,
                        "GitHubAnonymousSnapshotTransport",
                        return_value=object(),
                    ) as transport_factory,
                    patch.object(
                        cli,
                        "read_github_snapshot_contents",
                        return_value=snapshot,
                    ) as snapshot_reader,
                    patch.object(
                        cli,
                        "REMOTE_REPOSITORY_CONTENT_DIGEST",
                        snapshot.claim.content_digest,
                    ),
                ):
                    code = cli.main(
                        ["--remote-snapshot-execute"],
                        stdout=out,
                        stderr=err,
                        remote_execution_profile=profile,
                        execution_permit=permit,
                    )

                self.assertEqual(code, 0)
                self.assertEqual(worker.calls, 1)
                self.assertEqual(credential_calls, [])
                transport_factory.assert_called_once()
                snapshot_reader.assert_called_once()
                payload = json.loads(out.getvalue())
                self.assertEqual(payload["status"], "verified")
                self.assertEqual(payload["external_write"], False)
                self.assertEqual(payload["approval"], "not_created")
                self.assertEqual(payload["publication"], "not_attempted")
                self.assertEqual(
                    payload["verifier_identity_digest"],
                    "sha256:" + hashlib.sha256(verifier_identity.encode()).hexdigest(),
                )
                artifact = store.load(payload["staged_change_digest"])
                self.assertEqual(
                    artifact.staged_change_digest,
                    payload["staged_change_digest"],
                )
                self.assertEqual(
                    artifact.payload_copy()["seed"]["verified_contents_digest"],
                    payload["verified_contents_digest"],
                )
                self.assertEqual(err.getvalue(), "")
                self.assertNotIn("SOURCE-CANARY", out.getvalue())
                self.assertNotIn("synthetic marker", out.getvalue())

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1",
        "synthetic DeepSeek CLI Docker composition is opt-in",
    )
    def test_synthetic_cli_composes_deepseek_worker_and_fake_https_channel(self):
        snapshot = self.make_full_snapshot()
        route_source = next(
            blob.content.decode("utf-8")
            for blob in snapshot.files
            if blob.path == "backend/routes.py"
        )
        proposed = route_source + "# deepseek-cli-synthetic-candidate\n"
        proposal_json = json.dumps(
            {"changes": [{"path": "backend/routes.py", "content": proposed}]},
            separators=(",", ":"),
        )
        response_body = json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": proposal_json},
                    }
                ]
            },
            separators=(",", ":"),
        ).encode("utf-8")
        key_marker = "EXP-531-SYNTHETIC-KEY-NOT-A-SECRET"
        credential_calls: list[str] = []
        captured: dict = {}

        class FakeResponse:
            status = 200

            def read(self, amount):
                captured["read_limit"] = amount
                return response_body[:amount]

        class FakeConnection:
            def __init__(self, host, *, timeout, context):
                captured["host"] = host
                captured["timeout"] = timeout
                captured["tls_context"] = context
                captured["closed"] = False

            def request(self, method, path, *, body, headers):
                captured["method"] = method
                captured["path"] = path
                captured["body"] = body
                captured["headers"] = headers

            def getresponse(self):
                return FakeResponse()

            def close(self):
                captured["closed"] = True

        def synthetic_credential_source():
            credential_calls.append("lookup")
            return key_marker

        channel = cli.DeepSeekHTTPChannel(
            synthetic_credential_source,
            connection_factory=FakeConnection,
        )
        worker = cli.DeepSeekProposalWorker(channel)
        docker = shutil.which("docker")
        self.assertTrue(docker and Path(docker).is_absolute())
        target_image_id = TARGET_RUNTIME_IMAGE_ID
        verifier_image_id = VERIFIER_RUNTIME_IMAGE_ID
        verifier_code_digest = VERIFIER_RUNTIME_CODE_DIGEST
        verifier_identity = (
            f"docker-image:{verifier_image_id}/code:{verifier_code_digest}"
        )
        profile = cli.RemoteSnapshotExecutionProfile(
            process_id="process-exp531-cli-001",
            task_id="task-exp531-cli-001",
            task_instruction="Append a fixed synthetic marker to the route file",
            declared_change_paths=("backend/routes.py",),
            allowed_commands=frozenset({"python3"}),
            test_command=(
                "python3",
                "-c",
                "from pathlib import Path; assert Path('backend/routes.py').read_text().endswith('# deepseek-cli-synthetic-candidate\\n')",
            ),
            worker=worker,
            verifier=cli.DockerContainerVerifier(
                cli.VerifierContainerConfig(
                    docker_executable=docker,
                    runtime_image_id=verifier_image_id,
                    verifier_code_digest=verifier_code_digest,
                    timeout_seconds=60,
                    max_stdout_bytes=65_536,
                    max_stderr_bytes=16_384,
                )
            ),
            sandbox_backend=cli.DockerSandboxBackend(target_image_id),
            stage_sink=None,
        )
        out, err = io.StringIO(), io.StringIO()
        readiness = GitHubRateLimitEvidence(
            status=200,
            remaining=60,
            reset_unix=1791384392,
            observed_monotonic=time.monotonic(),
        )
        permit = cli.issue_remote_execution_permit(
            card_id="EXP-531",
            process_id=profile.process_id,
            task_id=profile.task_id,
            readiness=readiness,
            provider_call_approved=True,
        )

        with tempfile.TemporaryDirectory(prefix="agent00x-exp531-cli-stage-") as root:
            database = Path(root) / "stage.sqlite3"
            with cli.SQLiteStagedArtifactStore(database) as store:
                profile = replace(profile, stage_sink=store)
                with (
                    patch.object(
                        cli,
                        "GitHubAnonymousSnapshotTransport",
                        return_value=object(),
                    ) as transport_factory,
                    patch.object(
                        cli,
                        "read_github_snapshot_contents",
                        return_value=snapshot,
                    ) as snapshot_reader,
                    patch.object(
                        cli,
                        "REMOTE_REPOSITORY_CONTENT_DIGEST",
                        snapshot.claim.content_digest,
                    ),
                ):
                    code = cli.main(
                        ["--remote-snapshot-execute"],
                        stdout=out,
                        stderr=err,
                        remote_execution_profile=profile,
                        execution_permit=permit,
                    )

                self.assertEqual(code, 0)
                self.assertEqual(credential_calls, ["lookup"])
                self.assertEqual(captured["host"], "api.deepseek.com")
                self.assertEqual(captured["method"], "POST")
                self.assertEqual(captured["path"], "/chat/completions")
                self.assertLessEqual(len(captured["body"]), 128_000)
                self.assertEqual(captured["read_limit"], 65_537)
                self.assertTrue(captured["closed"])
                self.assertNotIn(key_marker, captured["body"].decode("utf-8"))
                self.assertEqual(
                    captured["headers"]["Authorization"], f"Bearer {key_marker}"
                )
                payload = json.loads(out.getvalue())
                self.assertEqual(payload["status"], "verified")
                self.assertEqual(payload["external_write"], False)
                self.assertEqual(payload["approval"], "not_created")
                self.assertEqual(payload["publication"], "not_attempted")
                self.assertEqual(
                    payload["verifier_identity_digest"],
                    "sha256:" + hashlib.sha256(verifier_identity.encode()).hexdigest(),
                )
                artifact = store.load(payload["staged_change_digest"])
                self.assertEqual(
                    artifact.staged_change_digest,
                    payload["staged_change_digest"],
                )
                branch = "agent/exp532-synthetic-preview"
                approval_time = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
                with self.assertRaisesRegex(
                    StageApprovalError,
                    "^stage approval: digest confirmation mismatch$",
                ):
                    run_local_mock_publication(
                        artifact,
                        "sha256:" + "0" * 64,
                        branch,
                        now=approval_time,
                    )
                receipt = run_local_mock_publication(
                    artifact,
                    payload["staged_change_digest"],
                    branch,
                    now=approval_time,
                )
                self.assertEqual(
                    receipt.staged_change_digest,
                    payload["staged_change_digest"],
                )
                self.assertEqual(
                    receipt.repository_id,
                    f"{cli.REMOTE_REPOSITORY_OWNER}/{cli.REMOTE_REPOSITORY_NAME}",
                )
                self.assertEqual(receipt.branch, branch)
                self.assertEqual(receipt.pull_request_id, 1)
                serialized_output = out.getvalue() + err.getvalue()
                self.assertNotIn(key_marker, serialized_output)
                self.assertNotIn(key_marker, repr(receipt))
                self.assertNotIn("SOURCE-CANARY", serialized_output)
                self.assertNotIn("Append a fixed synthetic marker", serialized_output)
                self.assertEqual(err.getvalue(), "")
                transport_factory.assert_called_once()
                snapshot_reader.assert_called_once()

    def test_pipeline_exception_is_sanitized(self):
        snapshot = self.make_full_snapshot()
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
            patch.object(cli, "read_github_snapshot_contents", return_value=snapshot),
            patch.object(cli, "REMOTE_REPOSITORY_CONTENT_DIGEST", snapshot.claim.content_digest),
            patch.object(
                cli,
                "run_remote_snapshot_execution",
                side_effect=RuntimeError("provider body SECRET-CANARY"),
            ),
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=self.profile(),
                execution_permit=self.permit(),
            )
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out.getvalue()),
            {"status": "failed", "failure_code": "remote-execution-pipeline-failed"},
        )
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn("SECRET-CANARY", out.getvalue() + err.getvalue())

    def test_snapshot_digest_mismatch_stops_before_execution(self):
        snapshot = self.make_full_snapshot()
        observer_store = ObservationStore()
        profile = replace(self.profile(), observation_store=observer_store)
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
            patch.object(cli, "read_github_snapshot_contents", return_value=snapshot),
            patch.object(cli, "run_remote_snapshot_execution") as execute,
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=profile,
                execution_permit=self.permit(),
            )
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out.getvalue()),
            {
                "status": "failed",
                "failure_code": "remote-snapshot-preparation-failed",
                "observer": {
                    "run_id": observer_store.events()[0]["run_id"],
                    "as_of_cursor": len(observer_store.events()) - 1,
                    "completeness": "partial",
                },
            },
        )
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(observer_store.events()[-2]["event_type"], "decision_applied")
        self.assertEqual(observer_store.events()[-2]["status"], "denied")
        self.assertEqual(observer_store.events()[-1]["event_type"], "agent_finished")
        self.assertEqual(observer_store.events()[-1]["status"], "failed")
        execute.assert_not_called()

    def test_missing_raw_commit_object_proof_stops_before_worker_or_target(self):
        snapshot = replace(
            self.make_full_snapshot(), verified_commit_object=None
        )
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
            patch.object(cli, "read_github_snapshot_contents", return_value=snapshot),
            patch.object(cli, "run_remote_snapshot_execution") as execute,
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=self.profile(),
                execution_permit=self.permit(),
            )

        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out.getvalue()),
            {"status": "failed", "failure_code": "remote-snapshot-preparation-failed"},
        )
        self.assertEqual(err.getvalue(), "")
        execute.assert_not_called()

    def test_unexpected_snapshot_error_has_only_preparation_marker(self):
        canary = "SYNTHETIC-EXCEPTION-CANARY"
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
            patch.object(
                cli, "read_github_snapshot_contents", side_effect=RuntimeError(canary)
            ),
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=self.profile(),
                execution_permit=self.permit(),
            )
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out.getvalue()),
            {
                "status": "failed",
                "failure_code": "remote-snapshot-preparation-failed",
            },
        )
        self.assertNotIn(canary, out.getvalue() + err.getvalue())

    def test_unexpected_execution_error_has_only_pipeline_marker(self):
        canary = "SYNTHETIC-EXCEPTION-CANARY"
        snapshot = self.make_full_snapshot()
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubAnonymousSnapshotTransport"),
            patch.object(cli, "read_github_snapshot_contents", return_value=snapshot),
            patch.object(
                cli,
                "REMOTE_REPOSITORY_CONTENT_DIGEST",
                snapshot.claim.content_digest,
            ),
            patch.object(
                cli, "run_remote_snapshot_execution", side_effect=RuntimeError(canary)
            ),
        ):
            code = cli.main(
                ["--remote-snapshot-execute"],
                stdout=out,
                stderr=err,
                remote_execution_profile=self.profile(),
                execution_permit=self.permit(),
            )
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out.getvalue()),
            {
                "status": "failed",
                "failure_code": "remote-execution-pipeline-failed",
            },
        )
        self.assertNotIn(canary, out.getvalue() + err.getvalue())

    def test_unrecognized_execution_failure_code_is_not_echoed(self):
        payload = cli._remote_execution_evidence(
            ExecutionResult(
                status=ExecutionStatus.FAILED,
                failure_code="secret-token-canary",
            ),
            stage_database_path=Path("/tmp/nonexistent-stage.sqlite3"),
        )
        self.assertEqual(payload["failure_code"], "remote-snapshot-execution-failed")
        self.assertNotIn("secret-token-canary", json.dumps(payload))
        self.assertNotIn("stage_database_path", payload)

    def test_fixed_target_test_failure_fallback_is_projected(self):
        payload = cli._remote_execution_evidence(
            ExecutionResult(
                status=ExecutionStatus.FAILED,
                failure_code="target-test-allowlisted-tests-failed",
            )
        )
        self.assertEqual(payload["failure_code"], "target-test-allowlisted-tests-failed")
        self.assertNotIn("stdout", payload)
        self.assertNotIn("stderr", payload)

    def test_signed_verifier_failure_evidence_is_bounded_and_audit_only(self):
        payload = cli._remote_execution_evidence(
            replace(
                ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    failure_code="verifier-trust-unestablished",
                ),
                verifier_attestation_digest="sha256:" + "a" * 64,
                verifier_attestation_key_id="fixture-key-1",
                verifier_attestation_profile_digest="sha256:" + "b" * 64,
                verifier_trust_enrollment_digest="sha256:" + "d" * 64,
                verifier_signature_valid=True,
                verifier_independent_host_trust_established=False,
            )
        )
        self.assertEqual(payload["failure_code"], "verifier-trust-unestablished")
        self.assertEqual(
            payload["verifier_attestation"],
            {
                "attestation_digest": "sha256:" + "a" * 64,
                "key_id": "fixture-key-1",
                "verifier_profile_digest": "sha256:" + "b" * 64,
                "trust_enrollment_digest": "sha256:" + "d" * 64,
                "signature_valid": True,
                "independent_host_trust_established": False,
            },
        )
        self.assertNotIn('"signature":', json.dumps(payload))
        self.assertNotIn("verifier_result", payload)

    def test_hand_built_verified_result_cannot_promote_audit_only_receipt(self):
        result = replace(
            self.verified_result(),
            verifier_attestation_digest="sha256:" + "a" * 64,
            verifier_attestation_key_id="fixture-key-1",
            verifier_attestation_profile_digest="sha256:" + "b" * 64,
            verifier_trust_enrollment_digest="sha256:" + "d" * 64,
            verifier_signature_valid=True,
            verifier_independent_host_trust_established=False,
        )
        payload = cli._remote_execution_evidence(
            result, stage_database_path=Path("/tmp/must-not-be-inspected.sqlite3")
        )
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["failure_code"], "verifier-trust-unestablished")
        self.assertEqual(
            payload["verifier_attestation"],
            {
                "attestation_digest": "sha256:" + "a" * 64,
                "key_id": "fixture-key-1",
                "verifier_profile_digest": "sha256:" + "b" * 64,
                "trust_enrollment_digest": "sha256:" + "d" * 64,
                "signature_valid": True,
                "independent_host_trust_established": False,
            },
        )
        self.assertNotIn("stage_database_path", payload)
        self.assertNotIn("verified_contents_digest", payload)
        self.assertNotIn("staged_change_digest", payload)

    def test_caller_supplied_host_trust_boolean_cannot_be_projected_as_verified(self):
        result = replace(
            self.verified_result(),
            verifier_attestation_digest="sha256:" + "a" * 64,
            verifier_attestation_key_id="fixture-key-1",
            verifier_attestation_profile_digest="sha256:" + "b" * 64,
            verifier_trust_enrollment_digest="sha256:" + "d" * 64,
            verifier_host_trust_decision_digest="sha256:" + "e" * 64,
            verifier_signature_valid=True,
            verifier_independent_host_trust_established=True,
        )

        payload = cli._remote_execution_evidence(result)

        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["failure_code"], "verifier-attestation-invalid")
        self.assertNotIn("verifier_attestation", payload)
        serialized = json.dumps(payload)
        self.assertNotIn('"signature":', serialized)
        self.assertNotIn("public_key", serialized)

    def test_malformed_verified_attestation_is_sanitized_before_success_projection(self):
        result = replace(
            self.verified_result(),
            verifier_attestation_digest="SECRET-CANARY",
            verifier_trust_enrollment_digest="SECRET-ENROLLMENT-CANARY",
            verifier_independent_host_trust_established=True,
        )
        payload = cli._remote_execution_evidence(result)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["failure_code"], "verifier-attestation-invalid")
        self.assertNotIn("SECRET-CANARY", json.dumps(payload))
        self.assertNotIn("SECRET-ENROLLMENT-CANARY", json.dumps(payload))
        self.assertNotIn("verifier_attestation", payload)

    def test_verified_evidence_reports_only_an_explicit_existing_stage_path(self):
        with tempfile.TemporaryDirectory(prefix="remote-stage-locator-") as root:
            database = Path(root) / "stage.sqlite3"
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    "CREATE TABLE staged_artifacts (digest TEXT PRIMARY KEY)"
                )
            payload = cli._remote_execution_evidence(
                self.verified_result(), stage_database_path=database
            )
            self.assertEqual(payload["status"], "verified")
            self.assertEqual(payload["stage_database_path"], str(database))

            no_locator = cli._remote_execution_evidence(self.verified_result())
            self.assertNotIn("stage_database_path", no_locator)

            symlink = Path(root) / "stage-link.sqlite3"
            symlink.symlink_to(database)
            with self.assertRaisesRegex(
                ValueError, "^remote CLI runtime is unavailable$"
            ):
                cli._validate_stage_database_locator(symlink)

    def test_remote_profile_rejects_invalid_stage_locator_before_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="remote-profile-stage-locator-") as root:
            directory = Path(root) / "stage-dir"
            directory.mkdir()
            symlink = Path(root) / "stage-link.sqlite3"
            target = Path(root) / "stage.sqlite3"
            target.write_bytes(b"synthetic")
            symlink.symlink_to(target)
            for invalid in (Path("relative.sqlite3"), directory, symlink):
                profile = replace(
                    self.profile(), stage_database_path=invalid
                )
                with self.subTest(path=str(invalid)):
                    with patch.object(
                        cli, "read_github_snapshot_contents"
                    ) as read_snapshot:
                        with self.assertRaisesRegex(
                            ValueError, "^remote CLI runtime is unavailable$"
                        ):
                            cli._run_pinned_remote_execution(profile)
                    read_snapshot.assert_not_called()

    def test_remote_profile_rejects_invalid_observer_before_snapshot(self):
        profile = replace(self.profile(), observation_store=object())
        with patch.object(cli, "read_github_snapshot_contents") as read_snapshot:
            with self.assertRaisesRegex(
                ValueError, "^remote CLI runtime is unavailable$"
            ):
                cli._run_pinned_remote_execution(profile)
        read_snapshot.assert_not_called()


class RemoteSnapshotCompositionTests(unittest.TestCase):
    class DummyStageSink:
        def save(self, _artifact):
            return None

        def load(self, _digest):
            return None

    @staticmethod
    def make_snapshot() -> GitHubSnapshotContents:
        path = "backend/routes.py"
        content = b"def routes():\n    return []\n"
        blob = GitHubBlobClaim(
            path=path,
            mode="100644",
            sha=hashlib.sha1(
                b"blob " + str(len(content)).encode("ascii") + b"\0" + content
            ).hexdigest(),
            size=len(content),
            content=content,
            content_digest=sha256_bytes(content),
        )
        claim = GitHubSnapshotClaim(
            owner="SoldatovAlexander",
            repository="brainbooster_full_v11",
            commit_oid="a" * 40,
            tree_oid="b" * 40,
            content_digest=sha256_digest(
                {
                    "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
                    "files": [
                        {
                            "path": path,
                            "content_digest": blob.content_digest,
                            "mode": blob.mode,
                        }
                    ],
                }
            ),
            selected_paths=(path,),
        )
        return GitHubSnapshotContents(claim=claim, files=(blob,))

    def invoke(self, **overrides):
        args = {
            "snapshot": self.make_snapshot(),
            "process_id": "process-remote-cli-001",
            "task_id": "task-remote-cli-001",
            "task_instruction": "Update the route implementation",
            "declared_change_paths": ("backend/routes.py",),
            "allowed_commands": frozenset({"python3"}),
            "test_command": ("python3", "-m", "unittest"),
            "worker": object(),
            "verifier": object(),
            "sandbox_backend": object(),
            "stage_sink": self.DummyStageSink(),
        }
        args.update(overrides)
        return cli.run_remote_snapshot_execution(**args)

    def test_composition_binds_identity_and_always_closes_lease(self):
        captured = {}

        def fake_run(
            request,
            worker,
            *,
            verifier,
            sandbox_backend,
            stage_sink,
            require_durable_stage,
        ):
            captured["request"] = request
            captured["workspace"] = request.remote_workspace
            captured["path"] = request.snapshot_path
            captured["worker"] = worker
            captured["verifier"] = verifier
            captured["backend"] = sandbox_backend
            captured["stage_sink"] = stage_sink
            captured["require_durable_stage"] = require_durable_stage
            return ExecutionResult(
                status=ExecutionStatus.VERIFIED,
                snapshot_origin="github_rest_api_claim",
                snapshot_tree_digest=request.remote_snapshot.claim.content_digest,
            )

        worker, verifier, backend = object(), object(), object()
        stage_sink = self.DummyStageSink()
        with patch.object(snapshot_pipeline, "run_local_execution", side_effect=fake_run):
            result = self.invoke(
                worker=worker,
                verifier=verifier,
                sandbox_backend=backend,
                stage_sink=stage_sink,
            )

        request = captured["request"]
        self.assertEqual(result.status, ExecutionStatus.VERIFIED)
        self.assertEqual(request.repository_id, "SoldatovAlexander/brainbooster_full_v11")
        self.assertEqual(request.base_commit, "a" * 40)
        self.assertEqual(request.remote_snapshot.claim.selected_paths, ("backend/routes.py",))
        self.assertIs(request.remote_workspace, captured["workspace"])
        self.assertIs(captured["worker"], worker)
        self.assertIs(captured["verifier"], verifier)
        self.assertIs(captured["backend"], backend)
        self.assertIs(captured["stage_sink"], stage_sink)
        self.assertIs(captured["require_durable_stage"], True)
        self.assertTrue(captured["workspace"].closed)
        self.assertFalse(captured["path"].exists())
        self.assertNotIn("def routes", repr(result))
        self.assertNotIn("def routes", repr(request))

    def test_composition_threads_explicit_observer_store_to_executor(self):
        captured = {}
        observer_store = SimpleNamespace(
            append=lambda _event: 0,
            events=lambda: (),
            record_checkpoint=lambda _checkpoint: 0,
        )

        def fake_run(
            request,
            worker,
            *,
            verifier,
            sandbox_backend,
            stage_sink,
            require_durable_stage,
            observation_store,
        ):
            captured["observation_store"] = observation_store
            captured["workspace"] = request.remote_workspace
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                snapshot_origin="github_rest_api_claim",
                failure_code="worker-failed",
            )

        with patch.object(snapshot_pipeline, "run_local_execution", side_effect=fake_run):
            self.invoke(observation_store=observer_store)

        self.assertIs(captured["observation_store"], observer_store)
        self.assertTrue(captured["workspace"].closed)

    def test_executor_failures_and_exceptions_still_close_lease(self):
        outcomes = (
            ExecutionResult(status=ExecutionStatus.FAILED, failure_code="worker-failed"),
            ExecutionResult(status=ExecutionStatus.FAILED, failure_code="verifier-blocked"),
            RuntimeError("synthetic executor failure"),
        )
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__):
                captured = {}

                def fake_run(request, *_args, **_kwargs):
                    captured["workspace"] = request.remote_workspace
                    captured["path"] = request.snapshot_path
                    if isinstance(outcome, Exception):
                        raise outcome
                    return outcome

                with patch.object(snapshot_pipeline, "run_local_execution", side_effect=fake_run):
                    if isinstance(outcome, Exception):
                        with self.assertRaisesRegex(RuntimeError, "synthetic executor failure"):
                            self.invoke()
                    else:
                        result = self.invoke()
                        self.assertEqual(result.failure_code, outcome.failure_code)
                self.assertTrue(captured["workspace"].closed)
                self.assertFalse(captured["path"].exists())

    def test_invalid_change_path_fails_before_executor(self):
        with patch.object(snapshot_pipeline, "run_local_execution") as run_mock:
            with self.assertRaisesRegex(ValueError, "^remote CLI request is invalid$"):
                self.invoke(declared_change_paths=("not-selected.py",))
        run_mock.assert_not_called()

    def test_invalid_test_command_closes_materialized_snapshot_lease(self):
        original_materialize = snapshot_pipeline.materialize_github_snapshot
        captured = {}

        @contextmanager
        def observed_materialize(snapshot):
            with original_materialize(snapshot) as workspace:
                captured["workspace"] = workspace
                captured["path"] = workspace.path
                yield workspace

        with patch.object(
            snapshot_pipeline, "materialize_github_snapshot", side_effect=observed_materialize
        ), patch.object(snapshot_pipeline, "run_local_execution") as run_mock:
            with self.assertRaisesRegex(
                ExecutionError, "^execution request: test command is invalid$"
            ):
                self.invoke(test_command=("python3", "-c", "pass\n"))

        run_mock.assert_not_called()
        self.assertTrue(captured["workspace"].closed)
        self.assertFalse(captured["path"].exists())

    def test_missing_or_invalid_durable_stage_fails_before_workspace_or_worker(self):
        with patch.object(snapshot_pipeline, "materialize_github_snapshot") as materialize, patch.object(
            snapshot_pipeline, "run_local_execution"
        ) as run_mock:
            with self.assertRaisesRegex(ValueError, "^remote CLI durable stage is required$"):
                self.invoke(stage_sink=None)
            with self.assertRaisesRegex(ValueError, "^remote CLI durable stage is invalid$"):
                self.invoke(stage_sink=object())
        materialize.assert_not_called()
        run_mock.assert_not_called()


class NoExternalAccessTests(unittest.TestCase):
    def test_cli_has_no_env_file_network_access(self):
        source = Path(cli.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        called_names: set[str] = set()
        called_attrs: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.lower() for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").lower())
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called_names.add(func.id.lower())
                elif isinstance(func, ast.Attribute):
                    called_attrs.add(func.attr.lower())
        for forbidden in ("os", "socket", "urllib", "http", "ssl", "subprocess", "requests", "httpx", "openai", "logging"):
            self.assertNotIn(forbidden, imported)
        for forbidden in ("environ", "getenv", "urlopen", "get", "post", "request", "getlogger", "print"):
            self.assertNotIn(forbidden, called_names)
        for forbidden in ("environ", "getenv", "read_text", "write_text", "read_bytes", "write_bytes"):
            self.assertNotIn(forbidden, called_attrs)
        self.assertNotIn("open(", source)
        self.assertNotIn(".env", source)
        lowered = source.lower()
        for sentinel in ("api_key", "apikey", "access_token", "secret_key", "bearer ", "authorization:"):
            self.assertNotIn(sentinel, lowered)


if __name__ == "__main__":
    unittest.main()
