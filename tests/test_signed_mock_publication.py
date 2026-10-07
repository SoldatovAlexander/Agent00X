from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from approval_test_support import TEST_APPROVER_ID, TEST_APPROVER_PUBLIC_KEY, sign_test_approval
from app_contracts.approval_request import build_approval_request
from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts.signed_mock_publication import main
import app_contracts.signed_mock_publication as mock_publication
from test_durable_stage import get_verified_artifact


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
BINDING = RepositoryTargetBinding(
    "FixtureOwner/stage-fixture",
    "github-installation/456/repository/1001",
)


class SignedMockPublicationTests(unittest.TestCase):
    def setUp(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        self.temporary = tempfile.TemporaryDirectory(prefix="signed-mock-publication-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "stage.sqlite3"
        with SQLiteStagedArtifactStore(self.database) as store:
            store.save(artifact)
        self.digest = artifact.staged_change_digest
        unsigned_request = build_approval_request(
            artifact,
            BINDING,
            branch="agent/process-signed-mock-001",
            base_branch="master",
            approval_id="approval-signed-mock-001",
            approver_id=TEST_APPROVER_ID,
            policy_version="production-policy-v1",
            now=NOW,
        )
        signed = sign_test_approval(unsigned_request["unsigned_approval"])
        self.paths = {
            "request": self.root / "request.json",
            "signed": self.root / "signed.json",
            "profile": self.root / "trust.json",
        }
        self._write(self.paths["request"], unsigned_request)
        self._write(self.paths["signed"], {"schema": "signed-approval/v1", "approval": signed})
        self._write(
            self.paths["profile"],
            {
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
            },
        )

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    def _argv(self) -> list[str]:
        return [
            str(self.database),
            self.digest,
            str(self.paths["request"]),
            str(self.paths["signed"]),
            str(self.paths["profile"]),
        ]

    def _input_bytes(self) -> dict[str, bytes]:
        return {
            "database": self.database.read_bytes(),
            **{name: path.read_bytes() for name, path in self.paths.items()},
        }

    def test_cli_runs_exact_signed_stage_only_to_bounded_local_mock(self):
        before = self._input_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(self._argv(), now=NOW + timedelta(seconds=1))
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["schema"], "signed-stage-mock-publication/v1")
        self.assertEqual(result["status"], "mock_published")
        self.assertEqual(result["staged_change_digest"], self.digest)
        self.assertEqual(result["destination"], "in_memory_mock_only")
        self.assertIs(result["external_write"], False)
        self.assertIs(result["identity_authenticated"], False)
        self.assertEqual(
            result["trust_profile_origin"], "operator_supplied_unverified"
        )
        self.assertNotIn("signature", stdout.getvalue())
        self.assertNotIn("signing_payload", stdout.getvalue())
        self.assertNotIn("patch", result)
        self.assertEqual(self._input_bytes(), before)

    def test_invalid_signature_stops_before_controlled_gates(self):
        signed = json.loads(self.paths["signed"].read_text(encoding="utf-8"))
        signed["approval"]["signature"] = "00" * 64
        self._write(self.paths["signed"], signed)
        with patch.object(mock_publication, "run_controlled_local_publication") as controlled:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(self._argv(), now=NOW + timedelta(seconds=1))
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("signed mock publication: approval denied", stderr.getvalue())
        controlled.assert_not_called()

    def test_policy_denial_stops_before_controlled_gates(self):
        profile = json.loads(self.paths["profile"].read_text(encoding="utf-8"))
        profile["allowed_approver_ids"] = ["different-operator"]
        profile["trusted_approver_public_keys"]["different-operator"] = (
            TEST_APPROVER_PUBLIC_KEY.hex()
        )
        self._write(self.paths["profile"], profile)
        with patch.object(mock_publication, "run_controlled_local_publication") as controlled:
            with self.assertRaisesRegex(
                mock_publication.SignedMockPublicationError,
                "^signed mock publication: approval denied$",
            ):
                mock_publication.publish_signed_stage_mock(
                    *self._argv(), now=NOW + timedelta(seconds=1)
                )
        controlled.assert_not_called()


if __name__ == "__main__":
    unittest.main()
