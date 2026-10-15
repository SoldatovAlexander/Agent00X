from __future__ import annotations

import ast
import base64
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.approval_request import (
    APPROVAL_REQUEST_TTL_SECONDS,
    ApprovalRequestError,
    build_approval_request,
    main,
    repository_target_binding_from_metadata,
    _requires_verified_verifier_provenance,
)
from app_contracts.approval_signature import APPROVAL_SIGNED_FIELDS, approval_signature_payload
from app_contracts.authority import DeterministicPolicy, PolicyConfig
from app_contracts.broker import InMemoryCredentialBroker
from app_contracts.controlled_publication import run_controlled_local_publication
from app_contracts.digests import sha256_digest
from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts.gateway import GatewayDecision, GatewayPath
from app_contracts.mock_github import MockGitHubEndpoint
from app_contracts.publication import PublicationJournal
from app_contracts.publication_seed import (
    PublicationSeed,
    bind_publication_seed_to_target,
    derive_publication_intent,
)
from app_contracts.validator import ContractValidationError
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts import worker_cli
from test_durable_stage import (
    as_unverified_local_approval_fixture,
    add_synthetic_verifier_trust_digests,
    get_verified_artifact,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
METADATA = {
    "AGENT_GITHUB_TEST_REPOSITORY": "FixtureOwner/stage-fixture",
    "AGENT_GITHUB_INSTALLATION_ID": "456",
    "AGENT_GITHUB_REPOSITORY_ID": "1001",
}


class ApprovalRequestTests(unittest.TestCase):
    def setUp(self):
        request, prepared, result, _ = get_verified_artifact()
        self.artifact = as_unverified_local_approval_fixture(
            build_staged_artifact(request, prepared, result)
        )
        self.binding = RepositoryTargetBinding(
            "FixtureOwner/stage-fixture",
            "github-installation/456/repository/1001",
        )

    def build(self):
        return build_approval_request(
            self.artifact,
            self.binding,
            branch="agent/process-durable-stage-001",
            base_branch="master",
            approval_id="approval-stage-review-001",
            approver_id="user-alice",
            policy_version="production-policy-v1",
            now=NOW,
        )

    def test_all_remote_snapshot_origins_require_verified_verifier_provenance(self):
        self.assertTrue(_requires_verified_verifier_provenance("github_rest_api_claim"))
        self.assertTrue(_requires_verified_verifier_provenance("github_codeload_archive"))
        self.assertFalse(_requires_verified_verifier_provenance("local_git_commit"))
        self.assertFalse(_requires_verified_verifier_provenance("unverified_local_test"))

    def test_request_is_unsigned_reviewable_deterministic_and_digest_bound(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "unsigned")
        self.assertEqual(first["approval"], "not_created")
        self.assertIs(first["provider_write"], False)
        self.assertNotIn("signature", first["unsigned_approval"])
        self.assertEqual(
            first["target"],
            {
                "source_repository_id": "FixtureOwner/stage-fixture",
                "provider_repository_id": "github-installation/456/repository/1001",
            },
        )
        self.assertEqual(
            first["intent"]["source_repository_id"], "FixtureOwner/stage-fixture"
        )
        self.assertEqual(
            first["intent"]["repository_id"], "github-installation/456/repository/1001"
        )
        self.assertEqual(
            set(first["unsigned_approval"]), set(APPROVAL_SIGNED_FIELDS)
        )
        signing_bytes = base64.b64decode(first["signing_payload_base64"], validate=True)
        self.assertEqual(signing_bytes, approval_signature_payload(first["unsigned_approval"]))
        self.assertEqual(
            first["signing_payload_digest"], "sha256:" + hashlib.sha256(signing_bytes).hexdigest()
        )
        self.assertEqual(
            first["unsigned_approval"]["approved_intent_digest"],
            sha256_digest(first["intent"]),
        )
        self.assertEqual(first["review"]["change"]["patch"], self.artifact.payload_copy()["patch"])
        self.assertEqual(first["intent"]["verifier_trust"]["status"], "not_recorded")
        self.assertEqual(
            first["review"]["verifier_trust"]["status"], "not_recorded"
        )
        self.assertNotIn("credential", json.dumps(first).lower())

    def test_trust_digests_are_visible_and_inside_signed_intent_digest(self):
        artifact = add_synthetic_verifier_trust_digests(self.artifact)
        request = build_approval_request(
            artifact,
            self.binding,
            branch="agent/process-durable-stage-001",
            base_branch="master",
            approval_id="approval-stage-review-001",
            approver_id="user-alice",
            policy_version="production-policy-v1",
            now=NOW,
        )
        trust = request["intent"]["verifier_trust"]
        self.assertEqual(trust["status"], "recorded_digest_only_not_revalidated")
        self.assertEqual(request["review"]["verifier_trust"], trust)
        self.assertEqual(request["review"]["requested_action"]["verifier_trust"], trust)
        self.assertEqual(
            request["unsigned_approval"]["approved_intent_digest"],
            sha256_digest(request["intent"]),
        )
        changed = dict(request["intent"])
        changed["verifier_trust"] = dict(trust, host_trust_decision_digest="sha256:" + "e" * 64)
        self.assertNotEqual(
            request["unsigned_approval"]["approved_intent_digest"],
            sha256_digest(changed),
        )

    def test_mutating_signed_fields_or_source_intent_changes_signing_payload(self):
        original = self.build()
        baseline = approval_signature_payload(original["unsigned_approval"])
        for field in APPROVAL_SIGNED_FIELDS:
            mutated = dict(original["unsigned_approval"])
            mutated[field] = str(mutated[field]) + "-changed"
            with self.subTest(field=field):
                self.assertNotEqual(approval_signature_payload(mutated), baseline)

        for field, value in original["intent"].items():
            mutated_intent = dict(original["intent"])
            mutated_intent[field] = f"{value}-changed"
            changed_approval = dict(original["unsigned_approval"])
            changed_approval["approved_intent_digest"] = sha256_digest(mutated_intent)
            with self.subTest(intent_field=field):
                self.assertNotEqual(
                    approval_signature_payload(changed_approval), baseline
                )

    def test_target_metadata_reads_only_public_identity_fields(self):
        binding = repository_target_binding_from_metadata(METADATA)
        self.assertEqual(binding, self.binding)
        for metadata in (
            {},
            dict(METADATA, AGENT_GITHUB_REPOSITORY_ID="01"),
            dict(METADATA, AGENT_GITHUB_INSTALLATION_ID="0"),
        ):
            with self.subTest(metadata=metadata), self.assertRaisesRegex(
                ApprovalRequestError, "^approval request: target metadata is invalid$"
            ):
                repository_target_binding_from_metadata(metadata)

    def test_target_mismatch_and_invalid_inputs_are_rejected(self):
        wrong_binding = RepositoryTargetBinding(
            "other/repository", "github-installation/456/repository/1001"
        )
        with self.assertRaisesRegex(ApprovalRequestError, "verified stage or target is invalid"):
            build_approval_request(
                self.artifact,
                wrong_binding,
                branch="agent/process-durable-stage-001",
                base_branch="master",
                approval_id="approval-stage-review-001",
                approver_id="user-alice",
                policy_version="production-policy-v1",
                now=NOW,
            )
        for overrides in (
            {"branch": "main"},
            {"base_branch": "../unsafe"},
            {"approval_id": "bad-id"},
            {"approver_id": ""},
            {"policy_version": ""},
            {"now": datetime(2026, 10, 7, 12, 0, 0)},
        ):
            fields = {
                "branch": "agent/process-durable-stage-001",
                "base_branch": "master",
                "approval_id": "approval-stage-review-001",
                "approver_id": "user-alice",
                "policy_version": "production-policy-v1",
                "now": NOW,
            }
            fields.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ApprovalRequestError):
                build_approval_request(self.artifact, self.binding, **fields)

    def test_cli_is_read_only_unsigned_and_has_no_secret_or_provider_adapter_imports(self):
        with tempfile.TemporaryDirectory(prefix="approval-request-cli-") as temporary:
            database = Path(temporary) / "stage.sqlite3"
            with SQLiteStagedArtifactStore(database) as store:
                store.save(self.artifact)
            before = database.read_bytes()
            args = [
                str(database), self.artifact.staged_change_digest,
                "agent/process-durable-stage-001", "master",
                "approval-stage-review-001", "user-alice", "production-policy-v1",
            ]
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(args, environ=METADATA, now=NOW)
            output = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(output["status"], "unsigned")
            self.assertIs(output["provider_write"], False)
            self.assertEqual(database.read_bytes(), before)

            tree = ast.parse(
                (ROOT / "src/app_contracts/approval_request.py").read_text(encoding="utf-8")
            )
            forbidden = {
                "github_app", "github_http_transport", "deepseek_http_channel",
                "openai_worker", "credential_source", "broker", "gateway",
            }
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.rsplit(".", 1)[-1] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add((node.module or "").rsplit(".", 1)[-1])
            self.assertFalse(forbidden.intersection(imported))

    def test_cli_reports_wal_and_shm_stage_as_not_quiescent(self):
        with tempfile.TemporaryDirectory(prefix="approval-request-sidecar-") as temporary:
            database = Path(temporary) / "stage.sqlite3"
            with SQLiteStagedArtifactStore(database) as store:
                store.save(self.artifact)
            before = database.read_bytes()
            for suffix in ("-wal", "-shm"):
                sidecar = database.with_name(database.name + suffix)
                self.assertFalse(sidecar.exists())
                sidecar.touch()
                args = [
                    str(database), self.artifact.staged_change_digest,
                    "agent/process-durable-stage-001", "master",
                    "approval-stage-review-001", "user-alice", "production-policy-v1",
                ]
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(args, environ=METADATA, now=NOW)
                self.assertEqual(code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(
                    stderr.getvalue().strip(),
                    "approval request: stage database is not quiescent",
                )
                self.assertEqual(database.read_bytes(), before)
                sidecar.unlink()

    def test_verified_runtime_evidence_hands_exact_stage_to_read_only_approval_cli(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        with tempfile.TemporaryDirectory(prefix="runtime-approval-handoff-") as temporary:
            database = Path(temporary) / "verified-stage.sqlite3"
            with SQLiteStagedArtifactStore(database) as store:
                store.save(artifact)
            original_bytes = database.read_bytes()

            evidence = worker_cli._remote_execution_evidence(
                result, stage_database_path=database
            )
            self.assertEqual(
                list(database.parent.glob(database.name + "-wal")), []
            )
            self.assertEqual(
                list(database.parent.glob(database.name + "-shm")), []
            )
            self.assertEqual(evidence["status"], "verified")
            self.assertEqual(evidence["stage_database_path"], str(database))
            self.assertEqual(
                evidence["staged_change_digest"], artifact.staged_change_digest
            )
            args = [
                evidence["stage_database_path"],
                evidence["staged_change_digest"],
                "agent/process-durable-stage-001",
                "master",
                "approval-stage-handoff-001",
                "user-alice",
                "production-policy-v1",
            ]
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(args, environ=METADATA, now=NOW)
            self.assertEqual(code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("verifier provenance trust is unavailable", stderr.getvalue())
            self.assertEqual(database.read_bytes(), original_bytes)

            failed_args = list(args)
            failed_args[1] = "sha256:" + "0" * 64
            failed_out, failed_err = io.StringIO(), io.StringIO()
            with redirect_stdout(failed_out), redirect_stderr(failed_err):
                failed_code = main(failed_args, environ=METADATA, now=NOW)
            self.assertEqual(failed_code, 2)
            self.assertEqual(failed_out.getvalue(), "")
            self.assertTrue(failed_err.getvalue())
            self.assertEqual(database.read_bytes(), original_bytes)

            unavailable_args = list(args)
            unavailable_args[0] = str(Path(temporary) / "missing-stage.sqlite3")
            unavailable_out, unavailable_err = io.StringIO(), io.StringIO()
            with redirect_stdout(unavailable_out), redirect_stderr(unavailable_err):
                unavailable_code = main(
                    unavailable_args, environ=METADATA, now=NOW
                )
            self.assertEqual(unavailable_code, 2)
            self.assertEqual(unavailable_out.getvalue(), "")
            self.assertTrue(unavailable_err.getvalue())
            self.assertEqual(database.read_bytes(), original_bytes)

    def test_expiry_is_bounded_and_checked(self):
        request = self.build()
        expires_at = datetime.fromisoformat(
            request["unsigned_approval"]["expires_at"].replace("Z", "+00:00")
        )
        self.assertEqual(
            expires_at - NOW,
            timedelta(seconds=APPROVAL_REQUEST_TTL_SECONDS),
        )

    def test_external_signer_round_trip_is_accepted_only_for_exact_policy_intent(self):
        request = self.build()
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        signed_approval = dict(request["unsigned_approval"])
        signed_approval["signature"] = private_key.sign(
            base64.b64decode(request["signing_payload_base64"], validate=True)
        ).hex()
        payload = self.artifact.payload_copy()
        staged_change = payload["staged_change"]
        engine_intent = request["intent"]
        actuator_request = {
            "operation": "publish_pull_request",
            "repository_id": engine_intent["repository_id"],
            "actuator_id": "test-github-actuator",
            "staged_change_digest": self.artifact.staged_change_digest,
            "branch_namespace": engine_intent["branch_namespace"],
            "idempotency_key": engine_intent["idempotency_key"],
        }
        policy = DeterministicPolicy(
            PolicyConfig(
                version="production-policy-v1",
                allowed_repositories=frozenset({engine_intent["repository_id"]}),
                allowed_actuators=frozenset({"test-github-actuator"}),
                allowed_approver_ids=frozenset({"user-alice"}),
                trusted_approver_public_keys={"user-alice": public_key},
            )
        )
        decision = policy.decide(
            decision_id="decision-approval-request-round-trip",
            actuator_request=actuator_request,
            approval=signed_approval,
            staged_change=staged_change,
            intent=engine_intent,
            now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(decision["effect"], "allow")
        self.assertIn("digest-bound", decision["reason_codes"])

        tampered_intent = dict(engine_intent, branch="agent/attacker-change")
        rejected = policy.decide(
            decision_id="decision-tampered-approval-request-round-trip",
            actuator_request=actuator_request,
            approval=signed_approval,
            staged_change=staged_change,
            intent=tampered_intent,
            now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(rejected["effect"], "deny")
        self.assertIn("approval-approved-intent-digest-mismatch", rejected["reason_codes"])

    def test_signed_export_runs_only_through_controlled_local_mock_publication(self):
        request = self.build()
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        approval = dict(request["unsigned_approval"])
        approval["signature"] = private_key.sign(
            base64.b64decode(request["signing_payload_base64"], validate=True)
        ).hex()
        payload = self.artifact.payload_copy()
        stage = payload["staged_change"]
        seed = bind_publication_seed_to_target(
            PublicationSeed(**payload["seed"]), self.binding
        )
        intent = derive_publication_intent(
            seed, "agent/process-durable-stage-001", "master"
        )
        policy = DeterministicPolicy(
            PolicyConfig(
                version="production-policy-v1",
                allowed_repositories=frozenset({intent.repository_id}),
                allowed_actuators=frozenset({"test-github-actuator"}),
                allowed_approver_ids=frozenset({"user-alice"}),
                trusted_approver_public_keys={"user-alice": public_key},
            )
        )
        now = NOW + timedelta(seconds=1)
        actuator_request = {
            "operation": "publish_pull_request",
            "repository_id": intent.repository_id,
            "actuator_id": "test-github-actuator",
            "base_branch": intent.base_branch,
            "staged_change_digest": intent.staged_change_digest,
            "branch_namespace": intent.branch.split("/", 1)[0],
            "idempotency_key": intent.idempotency_key,
        }
        grant = {
            "credential_grant_id": "synthetic-grant-approval-request-001",
            "actuator_id": "test-github-actuator",
            "repository_id": intent.repository_id,
            "operation": "publish_pull_request",
            "request_digest": sha256_digest(actuator_request),
            "single_use": True,
            "credential_class": "github-app-installation",
            "expires_at": request["intent"]["expires_at"],
        }
        envelope = {
            "intent": {"operation": "publish_pull_request"},
            "destination": {
                "repository_id": intent.repository_id,
                "base_branch": intent.base_branch,
            },
            "source": {"principal_id": intent.process_id},
            "payload": {"content_digest": intent.staged_change_digest},
            "correlation_id": intent.idempotency_key,
        }

        class SlowAllowGateway:
            def __init__(self):
                self.calls = 0

            def __call__(self, _envelope, *, now):
                self.calls += 1
                return GatewayDecision(
                    GatewayPath.SLOW, True, ("synthetic-test-approval",)
                )

        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        gateway = SlowAllowGateway()
        with tempfile.TemporaryDirectory(prefix="approval-request-chain-") as temporary:
            with PublicationJournal(Path(temporary) / "journal.sqlite3") as journal:
                receipt = run_controlled_local_publication(
                    seed,
                    intent,
                    approval,
                    policy,
                    request["intent"],
                    lambda _seed: stage,
                    "decision-approval-request-chain",
                    gateway,
                    envelope,
                    broker,
                    grant,
                    journal,
                    endpoint,
                    actuator_id="test-github-actuator",
                    now=now,
                )
                self.assertEqual(receipt.repository_id, intent.repository_id)
                self.assertEqual(receipt.branch, intent.branch)
                self.assertEqual(receipt.base_branch, intent.base_branch)
                self.assertEqual(receipt.staged_change_digest, intent.staged_change_digest)
                self.assertEqual(receipt.idempotency_key, intent.idempotency_key)
                self.assertIs(
                    endpoint.find_by_idempotency_key(
                        intent.idempotency_key,
                        repository_id=intent.repository_id,
                        base_branch=intent.base_branch,
                    ),
                    receipt,
                )
                self.assertEqual(journal.get(intent.process_id).status, "completed")
                self.assertEqual(gateway.calls, 1)
                self.assertEqual(len(endpoint._by_idempotency_key), 1)

        denied_endpoint = MockGitHubEndpoint()
        denied_broker = InMemoryCredentialBroker(lambda: denied_endpoint)
        denied_gateway = SlowAllowGateway()
        invalid_approval = dict(approval, signature="0" * 128)
        with tempfile.TemporaryDirectory(prefix="approval-request-denied-") as temporary:
            with PublicationJournal(Path(temporary) / "journal.sqlite3") as journal:
                with self.assertRaisesRegex(
                    ContractValidationError, "^decision: not allow$"
                ):
                    run_controlled_local_publication(
                        seed,
                        intent,
                        invalid_approval,
                        policy,
                        request["intent"],
                        lambda _seed: stage,
                        "decision-approval-request-denied",
                        denied_gateway,
                        envelope,
                        denied_broker,
                        grant,
                        journal,
                        denied_endpoint,
                        actuator_id="test-github-actuator",
                        now=now,
                    )
        self.assertEqual(denied_gateway.calls, 0)
        self.assertEqual(denied_broker.opened_grants, [])
        self.assertEqual(denied_endpoint._by_idempotency_key, {})


if __name__ == "__main__":
    unittest.main()
