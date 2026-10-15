from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.approval_request import build_approval_request
from app_contracts.approval_signature import verify_approval_signature
from app_contracts.approval_signer import (
    ApprovalSigningError,
    sign_approval_request,
)
from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts.signer_key_source import Ed25519SeedCredentialSource
from scripts.sign_approval_request import main
from test_durable_stage import as_unverified_local_approval_fixture, get_verified_artifact
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
METADATA = {
    "AGENT_GITHUB_TEST_REPOSITORY": "FixtureOwner/stage-fixture",
    "AGENT_GITHUB_INSTALLATION_ID": "456",
    "AGENT_GITHUB_REPOSITORY_ID": "1001",
}


class ApprovalSignerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="approval-signer-")
        root = Path(self.temporary.name)
        self.database = root / "stage.sqlite3"
        self.request_path = root / "request.json"
        request, prepared, result, _ = get_verified_artifact()
        self.artifact = as_unverified_local_approval_fixture(
            build_staged_artifact(request, prepared, result)
        )
        with SQLiteStagedArtifactStore(self.database) as store:
            store.save(self.artifact)
        self.binding = RepositoryTargetBinding(
            "FixtureOwner/stage-fixture",
            "github-installation/456/repository/1001",
        )
        self.request = build_approval_request(
            self.artifact,
            self.binding,
            branch="agent/process-approval-signer-001",
            base_branch="master",
            approval_id="approval-signer-test-001",
            approver_id="user-alice",
            policy_version="synthetic-policy-v1",
            now=NOW,
        )
        self._write_request(self.request)
        self.database_before = self.database.read_bytes()
        self.seed = "42" * 32

    def tearDown(self):
        self.temporary.cleanup()

    def _write_request(self, request):
        self.request_path.write_text(
            json.dumps(request, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    def _source(self, calls):
        return Ed25519SeedCredentialSource(
            lambda: calls.append("read") or self.seed
        )

    def _public_key(self):
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.seed)).public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def _sign(self, *, confirmation=None, calls=None, clock=lambda: NOW):
        source_calls = [] if calls is None else calls

        def confirm(_review, phrase):
            return phrase if confirmation is None else confirmation

        return sign_approval_request(
            self.database,
            self.artifact.staged_change_digest,
            self.request_path,
            self.binding,
            self._source(source_calls),
            confirm,
            clock=clock,
        )

    def test_exact_stage_request_is_reviewed_then_signed_once(self):
        calls = []
        reviews = []

        def confirm(review, phrase):
            reviews.append((review, phrase))
            return phrase

        signed = sign_approval_request(
            self.database,
            self.artifact.staged_change_digest,
            self.request_path,
            self.binding,
            self._source(calls),
            confirm,
            clock=lambda: NOW,
        )
        approval = signed["approval"]
        expected_phrase = (
            "SIGN APPROVAL approval-signer-test-001 "
            + self.artifact.staged_change_digest
        )
        self.assertEqual(signed["schema"], "signed-approval/v1")
        self.assertEqual(calls, ["read"])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0][1], expected_phrase)
        self.assertEqual(
            reviews[0][0]["requested_action"]["staged_change_digest"],
            self.artifact.staged_change_digest,
        )
        self.assertTrue(
            verify_approval_signature(
                approval,
                self._public_key(),
            )
        )
        self.assertEqual(self.database.read_bytes(), self.database_before)
        self.assertNotIn(self.seed, json.dumps(signed))

    def test_wrong_confirmation_never_reads_signer_source(self):
        calls = []
        with self.assertRaisesRegex(
            ApprovalSigningError, "^approval signer: confirmation did not match$"
        ):
            self._sign(confirmation="SIGN APPROVAL wrong", calls=calls)
        self.assertEqual(calls, [])
        self.assertEqual(self.database.read_bytes(), self.database_before)

    def test_mismatched_request_is_rejected_before_confirmation_or_key_lookup(self):
        changed = json.loads(json.dumps(self.request))
        changed["intent"]["branch"] = "agent/attacker-branch"
        self._write_request(changed)
        calls = []
        confirmations = []

        with self.assertRaisesRegex(
            ApprovalSigningError, "^approval signer: request does not match exact stage$"
        ):
            sign_approval_request(
                self.database,
                self.artifact.staged_change_digest,
                self.request_path,
                self.binding,
                self._source(calls),
                lambda *_: confirmations.append(True) or "unused",
                clock=lambda: NOW,
            )
        self.assertEqual(calls, [])
        self.assertEqual(confirmations, [])

    def test_expired_request_is_rejected_before_confirmation_or_key_lookup(self):
        expired_at = NOW - timedelta(seconds=400)
        expired_request = build_approval_request(
            self.artifact,
            self.binding,
            branch="agent/process-approval-signer-001",
            base_branch="master",
            approval_id="approval-signer-test-001",
            approver_id="user-alice",
            policy_version="synthetic-policy-v1",
            now=expired_at,
        )
        self._write_request(expired_request)
        calls = []
        confirmations = []

        with self.assertRaisesRegex(
            ApprovalSigningError, "^approval signer: request is expired or invalid$"
        ):
            sign_approval_request(
                self.database,
                self.artifact.staged_change_digest,
                self.request_path,
                self.binding,
                self._source(calls),
                lambda *_: confirmations.append(True) or "unused",
                clock=lambda: NOW,
            )
        self.assertEqual(calls, [])
        self.assertEqual(confirmations, [])

    def test_request_expiring_during_review_is_not_signed(self):
        calls = []
        clock_values = iter((NOW, NOW + timedelta(minutes=6)))
        with self.assertRaisesRegex(
            ApprovalSigningError, "^approval signer: request is expired or invalid$"
        ):
            self._sign(calls=calls, clock=lambda: next(clock_values))
        self.assertEqual(calls, [])

    def test_cli_uses_fixed_injected_environment_name_and_emits_signed_envelope(self):
        metadata = dict(METADATA, AGENT_APPROVER_SIGNING_SEED=self.seed)
        phrase = (
            "SIGN APPROVAL approval-signer-test-001 "
            + self.artifact.staged_change_digest
        )
        output, errors = io.StringIO(), io.StringIO()
        code = main(
            [
                str(self.database),
                self.artifact.staged_change_digest,
                str(self.request_path),
            ],
            environ=metadata,
            input_fn=lambda: phrase,
            stdout=output,
            stderr=errors,
            now=NOW,
        )
        envelope = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertIn("requested_action", errors.getvalue())
        self.assertIn(phrase, errors.getvalue())
        self.assertTrue(
            verify_approval_signature(
                envelope["approval"], self._public_key()
            )
        )
        self.assertNotIn(self.seed, output.getvalue() + errors.getvalue())
        self.assertEqual(self.database.read_bytes(), self.database_before)

    def test_cli_wrong_phrase_does_not_read_injected_seed(self):
        class TrackingEnvironment(dict):
            secret_reads = 0

            def __getitem__(self, key):
                if key == "AGENT_APPROVER_SIGNING_SEED":
                    self.secret_reads += 1
                return super().__getitem__(key)

        metadata = TrackingEnvironment(
            dict(METADATA, AGENT_APPROVER_SIGNING_SEED=self.seed)
        )
        output, errors = io.StringIO(), io.StringIO()
        code = main(
            [
                str(self.database),
                self.artifact.staged_change_digest,
                str(self.request_path),
            ],
            environ=metadata,
            input_fn=lambda: "wrong phrase",
            stdout=output,
            stderr=errors,
            now=NOW,
        )
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(metadata.secret_reads, 0)
        self.assertNotIn(self.seed, errors.getvalue())


if __name__ == "__main__":
    unittest.main()
