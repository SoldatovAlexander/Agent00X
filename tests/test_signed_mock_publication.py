from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from approval_test_support import TEST_APPROVER_ID, TEST_APPROVER_PUBLIC_KEY, sign_test_approval
from app_contracts.approval_request import build_approval_request
from app_contracts.approver_trust_enrollment import build_signed_approver_trust_enrollment
from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts.digests import sha256_digest
from app_contracts.observation_store import SQLiteObservationStore
from app_contracts.observer_runtime import JournaledProposalWorker
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts.signed_mock_publication import main
import app_contracts.signed_mock_publication as mock_publication
from test_durable_stage import (
    as_unverified_local_approval_fixture,
    add_synthetic_verifier_trust_digests,
    get_verified_artifact,
)


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
BINDING = RepositoryTargetBinding(
    "FixtureOwner/stage-fixture",
    "github-installation/456/repository/1001",
)


def raw_public_key(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


class SignedMockPublicationTests(unittest.TestCase):
    def setUp(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = as_unverified_local_approval_fixture(
            add_synthetic_verifier_trust_digests(
                build_staged_artifact(request, prepared, result)
            )
        )
        self.artifact = artifact
        self.temporary = tempfile.TemporaryDirectory(prefix="signed-mock-publication-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "stage.sqlite3"
        with SQLiteStagedArtifactStore(self.database) as store:
            store.save(artifact)
        self.digest = artifact.staged_change_digest
        self.assertEqual(
            artifact.payload_copy()["seed"]["verifier_host_trust_decision_digest"],
            "sha256:" + "d" * 64,
        )
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
            self.profile,
        )
        self.authority_key = Ed25519PrivateKey.generate()
        self.authority_key_id = "synthetic-mock-authority-exp687"
        self.authority_public_key = raw_public_key(self.authority_key)
        self.authority_keys = {self.authority_key_id: self.authority_public_key}
        self.authority_key_set = self.root / "authority-key-set.json"
        self._write(
            self.authority_key_set,
            {
                "schema": "control-plane-authority-key-set/v1",
                "keys": {self.authority_key_id: self.authority_public_key.hex()},
            },
        )
        self.enrollment_path = self.root / "approver-enrollment.json"
        self.enrollment = build_signed_approver_trust_enrollment(
            enrollment_id="synthetic-mock-approver-enrollment-exp687",
            authority_key_id=self.authority_key_id,
            approver_id=TEST_APPROVER_ID,
            approver_public_key=TEST_APPROVER_PUBLIC_KEY,
            trust_profile_digest=sha256_digest(self.profile),
            provider_repository_id=BINDING.provider_repository_id,
            signing_key=self.authority_key,
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(days=1),
        )
        self.enrollment_path.write_bytes(self.enrollment)

    @property
    def profile(self):
        return {
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

    def _enrolled_argv(self) -> list[str]:
        return [
            *self._argv(),
            "--approver-enrollment",
            str(self.enrollment_path),
            "--authority-key-set",
            str(self.authority_key_set),
            "--authority-key-set-digest",
            "sha256:" + hashlib.sha256(self.authority_key_set.read_bytes()).hexdigest(),
        ]

    def _input_bytes(self) -> dict[str, bytes]:
        return {
            "database": self.database.read_bytes(),
            **{name: path.read_bytes() for name, path in self.paths.items()},
            "approver-enrollment": self.enrollment_path.read_bytes(),
            "authority-key-set": self.authority_key_set.read_bytes(),
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
        request_data = json.loads(self.paths["request"].read_text(encoding="utf-8"))
        self.assertEqual(
            result["idempotency_key"], request_data["intent"]["idempotency_key"]
        )
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

    def test_cli_accepts_caller_pinned_enrolled_approval_but_remains_mock_only(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        before = self._input_bytes()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(self._enrolled_argv(), now=NOW + timedelta(seconds=1))
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["status"], "mock_published")
        self.assertEqual(result["destination"], "in_memory_mock_only")
        self.assertIs(result["external_write"], False)
        self.assertIs(result["identity_authenticated"], False)
        self.assertEqual(
            result["trust_profile_origin"], "authority_enrolled_approver_key"
        )
        enrollment = result["approver_enrollment"]
        self.assertEqual(enrollment["enrollment_id"], "synthetic-mock-approver-enrollment-exp687")
        self.assertEqual(enrollment["authority_key_id"], self.authority_key_id)
        self.assertEqual(
            enrollment["authority_key_digest"],
            "sha256:" + hashlib.sha256(self.authority_public_key).hexdigest(),
        )
        self.assertEqual(
            enrollment["enrollment_digest"],
            "sha256:" + hashlib.sha256(self.enrollment).hexdigest(),
        )
        self.assertEqual(
            result["authority_key_set_digest"],
            "sha256:" + hashlib.sha256(self.authority_key_set.read_bytes()).hexdigest(),
        )
        self.assertNotIn(self.authority_public_key.hex(), stdout.getvalue())
        self.assertNotIn(self.enrollment.decode(), stdout.getvalue())
        self.assertNotIn(self.authority_key_set.read_text(), stdout.getvalue())
        self.assertNotIn('"signature":', stdout.getvalue())
        self.assertEqual(self._input_bytes(), before)

    def test_cli_rejects_partial_enrollment_arguments_without_fallback(self):
        options = (
            ("--approver-enrollment", str(self.enrollment_path)),
            ("--authority-key-set", str(self.authority_key_set)),
            (
                "--authority-key-set-digest",
                "sha256:" + hashlib.sha256(self.authority_key_set.read_bytes()).hexdigest(),
            ),
        )
        for missing in range(len(options)):
            extra = [item for index, pair in enumerate(options) if index != missing for item in pair]
            with self.subTest(extra=extra):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([*self._argv(), *extra], now=NOW + timedelta(seconds=1))
                self.assertEqual(code, 2)
                self.assertIn("enrollment trust is unavailable", stderr.getvalue())
                self.assertEqual(stdout.getvalue(), "")

    def test_cli_rejects_wrong_authority_pin_before_mock_publication(self):
        wrong_key_path = self.root / "wrong-authority-keys.json"
        wrong_key = raw_public_key(Ed25519PrivateKey.generate())
        self._write(
            wrong_key_path,
            {
                "schema": "control-plane-authority-key-set/v1",
                "keys": {self.authority_key_id: wrong_key.hex()},
            },
        )
        argv = [
            *self._argv(),
            "--approver-enrollment",
            str(self.enrollment_path),
            "--authority-key-set",
            str(wrong_key_path),
            "--authority-key-set-digest",
            "sha256:" + hashlib.sha256(wrong_key_path.read_bytes()).hexdigest(),
        ]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv, now=NOW + timedelta(seconds=1))
        self.assertEqual(code, 2)
        self.assertIn("enrollment verification failed", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_cli_rejects_key_set_that_does_not_match_out_of_band_digest(self):
        argv = [
            *self._argv(),
            "--approver-enrollment",
            str(self.enrollment_path),
            "--authority-key-set",
            str(self.authority_key_set),
            "--authority-key-set-digest",
            "sha256:" + "0" * 64,
        ]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv, now=NOW + timedelta(seconds=1))
        self.assertEqual(code, 2)
        self.assertIn("authority key set pin mismatch", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_authority_key_set_parser_rejects_malformed_and_duplicate_input(self):
        for data in (
            b'{"schema":"control-plane-authority-key-set/v1","keys":{"bad id":"'
            + b"0" * 64
            + b'"}}',
            b'{"schema":"control-plane-authority-key-set/v1","keys":{},"extra":true}',
            b'{"schema":"control-plane-authority-key-set/v1","keys":{"key":"'
            + b"A" * 64
            + b'"}}',
            b'{"schema":"control-plane-authority-key-set/v1","keys":{},"keys":{}}',
        ):
            with self.subTest(data=data[:48]):
                path = self.root / "malformed-authority-keys.json"
                path.write_bytes(data)
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(
                        [
                            *self._argv(),
                            "--approver-enrollment",
                            str(self.enrollment_path),
                            "--authority-key-set",
                            str(path),
                            "--authority-key-set-digest",
                            "sha256:" + hashlib.sha256(data).hexdigest(),
                        ],
                        now=NOW + timedelta(seconds=1),
                    )
                self.assertEqual(code, 2)
                self.assertIn("authority key set unavailable", stderr.getvalue())
                self.assertNotIn(data.decode("utf-8", errors="replace"), stderr.getvalue())
                self.assertEqual(stdout.getvalue(), "")

    def test_authority_key_set_parser_rejects_symlink_and_oversized_input(self):
        symlink = self.root / "authority-key-set-link.json"
        symlink.symlink_to(self.authority_key_set)
        oversized = self.root / "oversized-authority-key-set.json"
        oversized.write_bytes(b" " * (mock_publication.MAX_AUTHORITY_KEY_SET_BYTES + 1))
        for path in (symlink, oversized):
            with self.subTest(path=path.name):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(
                        [
                            *self._argv(),
                            "--approver-enrollment",
                            str(self.enrollment_path),
                            "--authority-key-set",
                            str(path),
                            "--authority-key-set-digest",
                            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                        ],
                        now=NOW + timedelta(seconds=1),
                    )
                self.assertEqual(code, 2)
                self.assertIn("authority key set unavailable", stderr.getvalue())
                self.assertEqual(stdout.getvalue(), "")

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

    def test_observer_cli_requires_paired_flags_and_distinct_database(self):
        for options in (
            ["--observer-db", str(self.root / "observer.sqlite3")],
            ["--observer-run-id", "run-observer-demo-0001"],
            [
                "--observer-db",
                str(self.database),
                "--observer-run-id",
                "run-observer-demo-0001",
            ],
        ):
            with self.subTest(options=options):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(self._argv() + options, now=NOW + timedelta(seconds=1))
                self.assertEqual(code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn("observer", stderr.getvalue())

    def _new_observed_run(self, observer_database: Path) -> tuple[str, str]:
        payload = self.artifact.payload_copy()
        process_id = payload["seed"]["process_id"]
        task_id = "task-signed-mock-observer-fixture"
        with SQLiteObservationStore(observer_database) as store:
            worker = JournaledProposalWorker(
                SimpleNamespace(propose=lambda _request: {"synthetic": True}),
                store,
                process_id=process_id,
                task_id=task_id,
            )
            worker.propose(SimpleNamespace(process_id=process_id, task_id=task_id))
            run_id = worker.observer_reference()["run_id"]
        return process_id, run_id

    def test_observered_bad_signature_is_journaled_before_publication_gates(self):
        signed = json.loads(self.paths["signed"].read_text(encoding="utf-8"))
        signed["approval"]["signature"] = "00" * 64
        self._write(self.paths["signed"], signed)
        observer_database = self.root / "observer.sqlite3"
        _process_id, run_id = self._new_observed_run(observer_database)
        before = self._input_bytes()
        with patch.object(mock_publication, "run_controlled_local_publication") as controlled:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(
                    self._argv()
                    + [
                        "--observer-db",
                        str(observer_database),
                        "--observer-run-id",
                        run_id,
                    ],
                    now=NOW + timedelta(seconds=1),
                )
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("observer run rejected", stderr.getvalue())
        controlled.assert_not_called()
        self.assertEqual(self._input_bytes(), before)
        with SQLiteObservationStore(observer_database) as store:
            events = store.events()
        self.assertEqual({event["run_id"] for event in events}, {run_id})
        signed_verification = next(
            event
            for event in events
            if event.get("decision_or_tool") == "SignedApproval.verify"
            and event["event_type"] == "decision_proposed"
        )
        self.assertEqual(signed_verification["status"], "pending")
        self.assertNotIn("signature", repr(events))
        self.assertNotIn(TEST_APPROVER_PUBLIC_KEY.hex(), repr(events))


if __name__ == "__main__":
    unittest.main()
