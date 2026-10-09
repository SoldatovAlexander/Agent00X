from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import ast
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

from approval_test_support import TEST_APPROVER_ID, TEST_APPROVER_PUBLIC_KEY, sign_test_approval
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app_contracts.approval_request import build_approval_request, main as approval_request_main
from app_contracts.approver_trust_enrollment import (
    build_signed_approver_trust_enrollment,
)
from app_contracts.authority import DeterministicPolicy, PolicyConfig
from app_contracts.broker import InMemoryCredentialBroker
from app_contracts import worker_cli
from app_contracts.controlled_publication import (
    ControlledPublicationError,
    run_controlled_local_publication,
    run_enrolled_signed_approval_local_mock_publication,
)
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
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts.signed_approval import (
    SignedApprovalError,
    main,
    verify_signed_approval,
)
from test_durable_stage import (
    as_unverified_local_approval_fixture,
    add_synthetic_verifier_trust_digests,
    get_verified_artifact,
)


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
BINDING = RepositoryTargetBinding(
    "FixtureOwner/stage-fixture",
    "github-installation/456/repository/1001",
)


def raw_public_key(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


class SignedApprovalVerificationTests(unittest.TestCase):
    def setUp(self):
        request, prepared, result, _ = get_verified_artifact()
        self.execution_result = result
        self.artifact = as_unverified_local_approval_fixture(
            add_synthetic_verifier_trust_digests(
                build_staged_artifact(request, prepared, result)
            )
        )
        self.temporary = tempfile.TemporaryDirectory(prefix="signed-approval-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "stage.sqlite3"
        with SQLiteStagedArtifactStore(self.database) as store:
            store.save(self.artifact)
        self.approval_request = build_approval_request(
            self.artifact,
            BINDING,
            branch="agent/process-signed-approval-001",
            base_branch="master",
            approval_id="approval-signed-review-001",
            approver_id=TEST_APPROVER_ID,
            policy_version="production-policy-v1",
            now=NOW,
        )
        self.approval = sign_test_approval(
            self.approval_request["unsigned_approval"]
        )
        self.profile = {
            "schema": "approval-trust-profile/v1",
            "policy_version": "production-policy-v1",
            "target": {
                "source_repository_id": BINDING.source_repository_id,
                "provider_repository_id": BINDING.provider_repository_id,
            },
            "allowed_repositories": [BINDING.provider_repository_id],
            "allowed_actuators": ["github-app-actuator"],
            "allowed_approver_ids": [TEST_APPROVER_ID],
            "trusted_approver_public_keys": {
                TEST_APPROVER_ID: TEST_APPROVER_PUBLIC_KEY.hex()
            },
        }
        self.request_path = self.root / "request.json"
        self.signed_path = self.root / "signed.json"
        self.profile_path = self.root / "trust.json"
        self.authority_key = Ed25519PrivateKey.generate()
        self.authority_key_id = "synthetic-approval-authority-exp685"
        authority_public_key = raw_public_key(self.authority_key)
        self.trusted_authority_keys = {
            self.authority_key_id: authority_public_key
        }
        self.enrollment_path = self.root / "approver-enrollment.json"
        self.enrollment_bytes = build_signed_approver_trust_enrollment(
            enrollment_id="synthetic-approver-enrollment-exp685",
            authority_key_id=self.authority_key_id,
            approver_id=TEST_APPROVER_ID,
            approver_public_key=TEST_APPROVER_PUBLIC_KEY,
            trust_profile_digest=sha256_digest(self.profile),
            provider_repository_id=BINDING.provider_repository_id,
            signing_key=self.authority_key,
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(days=7),
        )
        self.enrollment_path.write_bytes(self.enrollment_bytes)
        self._write(self.request_path, self.approval_request)
        self._write(
            self.signed_path,
            {"schema": "signed-approval/v1", "approval": self.approval},
        )
        self._write(self.profile_path, self.profile)

    def _write(self, path, value):
        path.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    def _verify(self, *, now=NOW + timedelta(seconds=1)):
        return verify_signed_approval(
            self.database,
            self.artifact.staged_change_digest,
            self.request_path,
            self.signed_path,
            self.profile_path,
            now=now,
        )

    def test_exact_signed_request_is_policy_allowed_read_only(self):
        stage_before = self.database.read_bytes()
        result = self._verify()
        self.assertEqual(result["status"], "policy_allowed")
        self.assertEqual(result["decision"], "allow")
        self.assertIn("digest-bound", result["reason_codes"])
        self.assertEqual(result["staged_change_digest"], self.artifact.staged_change_digest)
        self.assertEqual(result["intent_digest"], sha256_digest(self.approval_request["intent"]))
        self.assertEqual(result["trust_profile_origin"], "operator_supplied_unverified")
        self.assertIs(result["identity_authenticated"], False)
        self.assertIs(result["provider_write"], False)
        self.assertEqual(self.database.read_bytes(), stage_before)

    def test_enrolled_approver_key_is_bound_and_reported_by_read_only_cli(self):
        stage_before = self.database.read_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                [
                    self.database.as_posix(),
                    self.artifact.staged_change_digest,
                    str(self.request_path),
                    str(self.signed_path),
                    str(self.profile_path),
                    "--approver-enrollment",
                    str(self.enrollment_path),
                ],
                trusted_authority_keys=self.trusted_authority_keys,
                now=NOW + timedelta(seconds=1),
            )
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(
            result["trust_profile_origin"], "authority_enrolled_approver_key"
        )
        self.assertEqual(
            result["approver_enrollment"]["enrollment_digest"],
            "sha256:" + hashlib.sha256(self.enrollment_bytes).hexdigest(),
        )
        self.assertEqual(
            result["approver_enrollment"]["authority_key_id"],
            self.authority_key_id,
        )
        self.assertEqual(
            result["approver_enrollment"]["authority_key_digest"],
            "sha256:" + hashlib.sha256(
                self.trusted_authority_keys[self.authority_key_id]
            ).hexdigest(),
        )
        self.assertEqual(
            result["approver_enrollment"]["approver_id"], TEST_APPROVER_ID
        )
        self.assertIs(result["approver_enrollment"]["authority_signature_valid"], True)
        self.assertIs(result["approver_enrollment"]["human_identity_authenticated"], False)

    def test_enrolled_approval_composes_through_local_mock_only(self):
        payload = self.artifact.payload_copy()
        source_seed = PublicationSeed(**payload["seed"])
        seed = bind_publication_seed_to_target(source_seed, BINDING)
        intent = derive_publication_intent(
            seed,
            self.approval_request["intent"]["branch"],
            self.approval_request["intent"]["base_branch"],
        )
        policy = DeterministicPolicy(self._verify_enrolled().policy_config)
        engine_intent = self.approval_request["intent"]
        staged_change = payload["staged_change"]
        actuator_id = "github-app-actuator"
        actuator_request = {
            "operation": "publish_pull_request",
            "repository_id": intent.repository_id,
            "actuator_id": actuator_id,
            "base_branch": intent.base_branch,
            "staged_change_digest": intent.staged_change_digest,
            "branch_namespace": intent.branch.split("/", 1)[0],
            "idempotency_key": intent.idempotency_key,
        }
        grant = {
            "credential_grant_id": "synthetic-mock-grant",
            "actuator_id": actuator_id,
            "repository_id": intent.repository_id,
            "operation": "publish_pull_request",
            "request_digest": sha256_digest(actuator_request),
            "single_use": True,
            "credential_class": "github-app-installation",
            "expires_at": (NOW + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }
        envelope = {
            "intent": {"operation": "publish_pull_request"},
            "destination": {
                "port": "approval",
                "repository_id": intent.repository_id,
                "base_branch": intent.base_branch,
            },
            "source": {"protocol": "internal", "principal_id": intent.process_id},
            "security": {"tainted": False, "sensitivity": "internal"},
            "payload": {"content_digest": intent.staged_change_digest},
            "correlation_id": intent.idempotency_key,
        }
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        gateway_calls = []

        def gateway(_envelope, *, now):
            gateway_calls.append(now)
            return GatewayDecision(GatewayPath.SLOW, True, ("synthetic-test",))

        loader_calls = []

        def load_stage(candidate_seed):
            loader_calls.append(candidate_seed.staged_change_digest)
            return staged_change

        with PublicationJournal(self.root / "mock-publication.sqlite3") as journal:
            receipt = run_enrolled_signed_approval_local_mock_publication(
                self.database,
                self.artifact.staged_change_digest,
                self.request_path,
                self.signed_path,
                self.profile_path,
                self.enrollment_path,
                self.trusted_authority_keys,
                seed,
                intent,
                policy,
                engine_intent,
                load_stage,
                "decision-enrolled-approval-test",
                gateway,
                envelope,
                broker,
                grant,
                journal,
                endpoint,
                actuator_id=actuator_id,
                now=NOW + timedelta(seconds=1),
            )
            self.assertEqual(journal.get(intent.process_id).status, "completed")
        self.assertEqual(receipt.staged_change_digest, self.artifact.staged_change_digest)
        self.assertEqual(receipt.idempotency_key, intent.idempotency_key)
        self.assertEqual(endpoint.find_by_idempotency_key(intent.idempotency_key), receipt)
        self.assertEqual(loader_calls, [self.artifact.staged_change_digest])
        self.assertEqual(len(gateway_calls), 1)
        self.assertEqual(len(broker.opened_grants), 1)

        tampered_endpoint = MockGitHubEndpoint()
        tampered_broker = InMemoryCredentialBroker(lambda: tampered_endpoint)
        tampered_gateway_calls = []
        with PublicationJournal(self.root / "tampered-stage-publication.sqlite3") as journal:
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: staged change digest mismatch$",
            ):
                run_enrolled_signed_approval_local_mock_publication(
                    self.database,
                    self.artifact.staged_change_digest,
                    self.request_path,
                    self.signed_path,
                    self.profile_path,
                    self.enrollment_path,
                    self.trusted_authority_keys,
                    seed,
                    intent,
                    policy,
                    engine_intent,
                    lambda _seed: {**staged_change, "tampered": True},
                    "decision-enrolled-tampered-stage",
                    lambda *_args, **_kwargs: tampered_gateway_calls.append(True),
                    envelope,
                    tampered_broker,
                    grant,
                    journal,
                    tampered_endpoint,
                    actuator_id=actuator_id,
                    now=NOW + timedelta(seconds=1),
                )
            with self.assertRaises(KeyError):
                journal.get(intent.process_id)
        self.assertEqual(tampered_gateway_calls, [])
        self.assertEqual(tampered_broker.opened_grants, [])
        self.assertEqual(tampered_endpoint._by_idempotency_key, {})

        wrong_seed = PublicationSeed(
            **{
                **source_seed.__dict__,
                "staged_change_digest": "sha256:" + "0" * 64,
            }
        )
        wrong_seed = bind_publication_seed_to_target(wrong_seed, BINDING)
        rejected_gateway_calls = []
        rejected_endpoint = MockGitHubEndpoint()
        rejected_broker = InMemoryCredentialBroker(lambda: rejected_endpoint)
        rejected_loader_calls = []
        with PublicationJournal(self.root / "rejected-publication.sqlite3") as journal:
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: enrolled approval verification failed$",
            ):
                run_enrolled_signed_approval_local_mock_publication(
                    self.database,
                    self.artifact.staged_change_digest,
                    self.request_path,
                    self.signed_path,
                    self.profile_path,
                    self.enrollment_path,
                    self.trusted_authority_keys,
                    wrong_seed,
                    intent,
                    policy,
                    engine_intent,
                    lambda _seed: rejected_loader_calls.append(True),
                    "decision-enrolled-approval-mismatch",
                    lambda *_args, **_kwargs: rejected_gateway_calls.append(True),
                    envelope,
                    rejected_broker,
                    grant,
                    journal,
                    rejected_endpoint,
                    actuator_id=actuator_id,
                    now=NOW + timedelta(seconds=1),
                )
            with self.assertRaises(KeyError):
                journal.get(intent.process_id)
        self.assertEqual(rejected_loader_calls, [])
        self.assertEqual(rejected_gateway_calls, [])
        self.assertEqual(rejected_broker.opened_grants, [])
        self.assertEqual(rejected_endpoint._by_idempotency_key, {})

        with PublicationJournal(self.root / "provider-rejected.sqlite3") as journal:
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: enrolled approval path is mock-only$",
            ):
                run_enrolled_signed_approval_local_mock_publication(
                    self.database,
                    self.artifact.staged_change_digest,
                    self.request_path,
                    self.signed_path,
                    self.profile_path,
                    self.enrollment_path,
                    self.trusted_authority_keys,
                    seed,
                    intent,
                    policy,
                    engine_intent,
                    lambda _seed: self.fail("provider path must stop before stage loader"),
                    "decision-enrolled-provider-rejected",
                    gateway,
                    envelope,
                    object(),
                    grant,
                    journal,
                    object(),
                    actuator_id=actuator_id,
                    now=NOW + timedelta(seconds=1),
                )
            with self.assertRaises(KeyError):
                journal.get(intent.process_id)

    def _verify_enrolled(self):
        from app_contracts.signed_approval import load_verified_signed_approval

        return load_verified_signed_approval(
            self.database,
            self.artifact.staged_change_digest,
            self.request_path,
            self.signed_path,
            self.profile_path,
            approver_enrollment_path=self.enrollment_path,
            trusted_authority_keys=self.trusted_authority_keys,
            now=NOW + timedelta(seconds=1),
        )
        self.assertIs(result["identity_authenticated"], False)
        self.assertIs(result["provider_write"], False)
        self.assertNotIn('"signature":', stdout.getvalue())
        self.assertNotIn(TEST_APPROVER_PUBLIC_KEY.hex(), stdout.getvalue())
        self.assertEqual(self.database.read_bytes(), stage_before)

    def test_enrollment_requires_both_its_file_and_caller_pinned_authority(self):
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: enrollment trust is unavailable$"
        ):
            verify_signed_approval(
                self.database,
                self.artifact.staged_change_digest,
                self.request_path,
                self.signed_path,
                self.profile_path,
                approver_enrollment_path=self.enrollment_path,
                now=NOW + timedelta(seconds=1),
            )
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: enrollment trust is unavailable$"
        ):
            verify_signed_approval(
                self.database,
                self.artifact.staged_change_digest,
                self.request_path,
                self.signed_path,
                self.profile_path,
                trusted_authority_keys=self.trusted_authority_keys,
                now=NOW + timedelta(seconds=1),
            )

    def test_enrollment_rejects_wrong_authority_profile_repository_key_and_expiry(self):
        stage_before = self.database.read_bytes()
        cases = (
            ({self.authority_key_id: raw_public_key(Ed25519PrivateKey.generate())}, self.enrollment_bytes),
            (self.trusted_authority_keys, self._build_enrollment(profile_digest="sha256:" + "8" * 64)),
            (self.trusted_authority_keys, self._build_enrollment(repository_id="github-installation/999/repository/1")),
            (self.trusted_authority_keys, self._build_enrollment(approver_public_key=raw_public_key(Ed25519PrivateKey.generate()))),
            (self.trusted_authority_keys, self._build_enrollment(issued_at=NOW - timedelta(days=2), expires_at=NOW - timedelta(days=1))),
            (self.trusted_authority_keys, b"malformed-enrollment-bytes"),
        )
        for pins, enrollment in cases:
            with self.subTest(enrollment=enrollment[:30]), self.assertRaises(
                SignedApprovalError
            ):
                self.enrollment_path.write_bytes(enrollment)
                verify_signed_approval(
                    self.database,
                    self.artifact.staged_change_digest,
                    self.request_path,
                    self.signed_path,
                    self.profile_path,
                    approver_enrollment_path=self.enrollment_path,
                    trusted_authority_keys=pins,
                    now=NOW + timedelta(seconds=1),
                )
        self.assertEqual(self.database.read_bytes(), stage_before)

    def _build_enrollment(
        self,
        *,
        approver_public_key=TEST_APPROVER_PUBLIC_KEY,
        profile_digest=None,
        repository_id=BINDING.provider_repository_id,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=7),
    ):
        return build_signed_approver_trust_enrollment(
            enrollment_id="synthetic-approver-enrollment-exp685-test",
            authority_key_id=self.authority_key_id,
            approver_id=TEST_APPROVER_ID,
            approver_public_key=approver_public_key,
            trust_profile_digest=(
                sha256_digest(self.profile) if profile_digest is None else profile_digest
            ),
            provider_repository_id=repository_id,
            signing_key=self.authority_key,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def test_runtime_evidence_to_signed_approval_cli_uses_the_same_stage_digest(self):
        stage_before = self.database.read_bytes()
        evidence = worker_cli._remote_execution_evidence(
            self.execution_result, stage_database_path=self.database
        )
        metadata = {
            "AGENT_GITHUB_TEST_REPOSITORY": BINDING.source_repository_id,
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
        }
        request_stdout, request_stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(request_stdout), redirect_stderr(request_stderr):
            request_code = approval_request_main(
                [
                    evidence["stage_database_path"],
                    evidence["staged_change_digest"],
                    "agent/process-signed-approval-001",
                    "master",
                    "approval-signed-review-001",
                    TEST_APPROVER_ID,
                    "production-policy-v1",
                ],
                environ=metadata,
                now=NOW,
            )
        self.assertEqual(request_code, 0, request_stderr.getvalue())
        self.assertEqual(request_stderr.getvalue(), "")
        request = json.loads(request_stdout.getvalue())
        self.assertEqual(request["stage"]["staged_change_digest"], evidence["staged_change_digest"])
        self.assertEqual(request["status"], "unsigned")
        self._write(self.request_path, request)
        approval = sign_test_approval(request["unsigned_approval"])
        self._write(
            self.signed_path,
            {"schema": "signed-approval/v1", "approval": approval},
        )

        verify_stdout, verify_stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(verify_stdout), redirect_stderr(verify_stderr):
            verify_code = main(
                [
                    evidence["stage_database_path"],
                    evidence["staged_change_digest"],
                    str(self.request_path),
                    str(self.signed_path),
                    str(self.profile_path),
                ],
                now=NOW + timedelta(seconds=1),
            )
        self.assertEqual(verify_code, 0, verify_stderr.getvalue())
        self.assertEqual(verify_stderr.getvalue(), "")
        verdict = json.loads(verify_stdout.getvalue())
        self.assertEqual(verdict["decision"], "allow")
        self.assertEqual(verdict["staged_change_digest"], evidence["staged_change_digest"])
        self.assertIs(verdict["identity_authenticated"], False)
        self.assertIs(verdict["provider_write"], False)

        payload = self.artifact.payload_copy()
        seed = bind_publication_seed_to_target(
            PublicationSeed(**payload["seed"]), BINDING
        )
        intent = derive_publication_intent(
            seed, request["intent"]["branch"], request["intent"]["base_branch"]
        )
        staged_change = payload["staged_change"]
        actuator_id = "github-app-actuator"
        actuator_request = {
            "operation": "publish_pull_request",
            "repository_id": intent.repository_id,
            "actuator_id": actuator_id,
            "base_branch": intent.base_branch,
            "staged_change_digest": intent.staged_change_digest,
            "branch_namespace": intent.branch.split("/", 1)[0],
            "idempotency_key": intent.idempotency_key,
        }
        grant = {
            "credential_grant_id": "test-only-grant-signed-approval-001",
            "actuator_id": actuator_id,
            "repository_id": intent.repository_id,
            "operation": "publish_pull_request",
            "request_digest": sha256_digest(actuator_request),
            "single_use": True,
            "credential_class": "github-app-installation",
            "expires_at": approval["expires_at"],
        }
        policy = DeterministicPolicy(
            PolicyConfig(
                version=self.profile["policy_version"],
                allowed_repositories=frozenset(
                    self.profile["allowed_repositories"]
                ),
                allowed_actuators=frozenset(self.profile["allowed_actuators"]),
                allowed_approver_ids=frozenset(
                    self.profile["allowed_approver_ids"]
                ),
                trusted_approver_public_keys={
                    TEST_APPROVER_ID: TEST_APPROVER_PUBLIC_KEY
                },
            )
        )
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)

        def load_stage(candidate_seed):
            if candidate_seed.staged_change_digest != evidence["staged_change_digest"]:
                raise AssertionError("stage digest changed")
            return staged_change

        def allow_slow_path(_envelope, *, now):
            return GatewayDecision(
                GatewayPath.SLOW, True, ("synthetic-mock-only",)
            )

        envelope = {
            "intent": {"operation": "publish_pull_request"},
            "destination": {
                "port": "approval",
                "repository_id": intent.repository_id,
                "base_branch": intent.base_branch,
            },
            "source": {"protocol": "internal", "principal_id": intent.process_id},
            "security": {"tainted": False, "sensitivity": "internal"},
            "payload": {"content_digest": evidence["staged_change_digest"]},
            "correlation_id": intent.idempotency_key,
        }
        with PublicationJournal(self.root / "publication.sqlite3") as journal:
            receipt = run_controlled_local_publication(
                seed,
                intent,
                approval,
                policy,
                request["intent"],
                load_stage,
                "decision-test-signed-approval-001",
                allow_slow_path,
                envelope,
                broker,
                grant,
                journal,
                endpoint,
                actuator_id=actuator_id,
                now=NOW + timedelta(seconds=1),
            )
            publication_record = journal.get(intent.process_id)
        self.assertEqual(receipt.staged_change_digest, evidence["staged_change_digest"])
        self.assertEqual(receipt.repository_id, intent.repository_id)
        self.assertEqual(receipt.branch, intent.branch)
        self.assertEqual(receipt.base_branch, intent.base_branch)
        self.assertEqual(receipt.pull_request_id, 1)
        self.assertEqual(publication_record.status, "completed")
        self.assertEqual(publication_record.pull_request_id, receipt.pull_request_id)
        self.assertIs(
            endpoint.find_by_idempotency_key(intent.idempotency_key), receipt
        )
        self.assertEqual(len(broker.opened_grants), 1)
        self.assertEqual(self.database.read_bytes(), stage_before)

    def test_cli_outputs_bounded_non_identity_verdict_without_modifying_stage(self):
        stage_before = self.database.read_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                [
                    str(self.database),
                    self.artifact.staged_change_digest,
                    str(self.request_path),
                    str(self.signed_path),
                    str(self.profile_path),
                ],
                now=NOW + timedelta(seconds=1),
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        result = json.loads(stdout.getvalue())
        self.assertIs(result["provider_write"], False)
        self.assertIs(result["identity_authenticated"], False)
        self.assertNotIn("signature", stdout.getvalue())
        self.assertNotIn(TEST_APPROVER_PUBLIC_KEY.hex(), stdout.getvalue())
        self.assertEqual(self.database.read_bytes(), stage_before)

    def test_tampered_unsigned_request_is_rejected_before_policy(self):
        altered = dict(self.approval_request)
        altered["intent"] = dict(altered["intent"], branch="agent/attacker")
        self._write(self.request_path, altered)
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: request does not match stage$"
        ):
            self._verify()

    def test_changed_verifier_trust_binding_is_rejected_before_policy(self):
        altered = dict(self.approval_request)
        trust = dict(altered["intent"]["verifier_trust"])
        trust["host_trust_decision_digest"] = "sha256:" + "e" * 64
        altered["intent"] = dict(altered["intent"], verifier_trust=trust)
        self._write(self.request_path, altered)
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: request does not match stage$"
        ):
            self._verify()

    def test_wrong_stage_digest_is_rejected_without_stage_mutation(self):
        before = self.database.read_bytes()
        with self.assertRaises(SignedApprovalError):
            verify_signed_approval(
                self.database,
                "sha256:" + "0" * 64,
                self.request_path,
                self.signed_path,
                self.profile_path,
                now=NOW + timedelta(seconds=1),
            )
        self.assertEqual(self.database.read_bytes(), before)

    def test_signed_fields_must_equal_the_request_exactly(self):
        altered_approval = dict(self.approval, repository_id="github-installation/456/repository/999")
        self._write(
            self.signed_path,
            {"schema": "signed-approval/v1", "approval": altered_approval},
        )
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: signed fields mismatch$"
        ):
            self._verify()

    def test_target_binding_and_policy_version_must_match_the_signed_request(self):
        altered_profile = dict(self.profile)
        altered_profile["target"] = {
            **self.profile["target"],
            "provider_repository_id": "github-installation/456/repository/999",
        }
        altered_profile["allowed_repositories"] = [
            "github-installation/456/repository/999"
        ]
        self._write(self.profile_path, altered_profile)
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: request does not match stage$"
        ):
            self._verify()

        altered_profile = dict(self.profile, policy_version="different-policy-v1")
        self._write(self.profile_path, altered_profile)
        result = self._verify()
        self.assertEqual(result["decision"], "deny")
        self.assertIn("approval-policy-version-mismatch", result["reason_codes"])

    def test_invalid_signature_or_key_is_denied(self):
        altered_approval = dict(self.approval, signature="0" * 128)
        self._write(
            self.signed_path,
            {"schema": "signed-approval/v1", "approval": altered_approval},
        )
        result = self._verify()
        self.assertEqual(result["decision"], "deny")
        self.assertIn("approval-signature-invalid", result["reason_codes"])

        self._write(
            self.signed_path,
            {"schema": "signed-approval/v1", "approval": self.approval},
        )
        altered_profile = dict(self.profile)
        altered_profile["trusted_approver_public_keys"] = {
            TEST_APPROVER_ID: ("22" * 32)
        }
        self._write(self.profile_path, altered_profile)
        result = self._verify()
        self.assertEqual(result["decision"], "deny")

    def test_expired_signature_is_denied(self):
        result = self._verify(now=NOW + timedelta(seconds=301))
        self.assertEqual(result["decision"], "deny")
        self.assertIn("approval-expired", result["reason_codes"])

    def test_unlisted_approver_and_malformed_trust_profile_fail_closed(self):
        altered_profile = dict(self.profile)
        altered_profile["allowed_approver_ids"] = ["user-other"]
        altered_profile["trusted_approver_public_keys"] = {
            **self.profile["trusted_approver_public_keys"],
            "user-other": ("22" * 32),
        }
        self._write(self.profile_path, altered_profile)
        result = self._verify()
        self.assertEqual(result["decision"], "deny")
        self.assertIn("approver-not-allowlisted", result["reason_codes"])

        altered_profile["allowed_approver_ids"] = TEST_APPROVER_ID
        self._write(self.profile_path, altered_profile)
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: trust profile is invalid$"
        ):
            self._verify()

    def test_invalid_duplicate_or_symlink_inputs_fail_closed(self):
        duplicate_json = self.root / "duplicate.json"
        duplicate_json.write_text(
            '{"schema":"approval-request/v1","schema":"approval-request/v1"}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: input JSON is invalid$"
        ):
            verify_signed_approval(
                self.database,
                self.artifact.staged_change_digest,
                duplicate_json,
                self.signed_path,
                self.profile_path,
                now=NOW,
            )
        symlink_path = self.root / "request-link.json"
        symlink_path.symlink_to(self.request_path)
        with self.assertRaisesRegex(
            SignedApprovalError, "^signed approval: input file is unavailable$"
        ):
            verify_signed_approval(
                self.database,
                self.artifact.staged_change_digest,
                symlink_path,
                self.signed_path,
                self.profile_path,
                now=NOW,
            )

    def test_module_has_no_provider_or_secret_source_imports(self):
        source = Path(__import__(
            "app_contracts.signed_approval", fromlist=["__file__"]
        ).__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        for forbidden in (
            "credential_source", "github_app", "github_http_transport",
            "broker", "gateway", "publication",
        ):
            self.assertNotIn(forbidden, imports)


if __name__ == "__main__":
    unittest.main()
