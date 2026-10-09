from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app_contracts.approver_trust_enrollment import (
    ENROLLMENT_SCHEMA,
    MAX_ENROLLMENT_BYTES,
    ApproverTrustEnrollmentError,
    build_signed_approver_trust_enrollment,
    verify_approver_trust_enrollment,
)
from app_contracts.validator import ContractValidationError, validate


AUTHORITY_KEY_ID = "synthetic-authority-exp684"
APPROVER_ID = "user-alice"
PROFILE_DIGEST = "sha256:" + "1" * 64
REPOSITORY_ID = "github-installation/456/repository/1001"
NOW = datetime(2026, 10, 8, 17, 0, 0, tzinfo=timezone.utc)


def raw_public_key(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


class ApproverTrustEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.authority = Ed25519PrivateKey.generate()
        self.approver = Ed25519PrivateKey.generate()
        self.raw = build_signed_approver_trust_enrollment(
            enrollment_id="enroll-exp684-001",
            authority_key_id=AUTHORITY_KEY_ID,
            approver_id=APPROVER_ID,
            approver_public_key=raw_public_key(self.approver),
            trust_profile_digest=PROFILE_DIGEST,
            provider_repository_id=REPOSITORY_ID,
            signing_key=self.authority,
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(days=7),
        )

    def verify(self, raw=None, **overrides):
        return verify_approver_trust_enrollment(
            self.raw if raw is None else raw,
            trusted_authority_keys={AUTHORITY_KEY_ID: raw_public_key(self.authority)},
            expected_approver_id=overrides.get("approver_id", APPROVER_ID),
            expected_trust_profile_digest=overrides.get("profile_digest", PROFILE_DIGEST),
            expected_provider_repository_id=overrides.get("repository_id", REPOSITORY_ID),
            now=overrides.get("now", NOW),
        )

    def test_valid_enrollment_binds_scope_without_claiming_human_identity(self):
        result = self.verify()
        self.assertEqual(result.approver_id, APPROVER_ID)
        self.assertEqual(result.approver_public_key, raw_public_key(self.approver))
        self.assertEqual(result.trust_profile_digest, PROFILE_DIGEST)
        self.assertEqual(result.provider_repository_id, REPOSITORY_ID)
        self.assertEqual(result.operation, "publish_pull_request")
        self.assertTrue(result.authority_signature_valid)
        self.assertFalse(result.human_identity_authenticated)
        self.assertNotIn(raw_public_key(self.approver).hex(), repr(result))
        self.assertTrue(result.enrollment_digest.startswith("sha256:"))

    def test_signed_record_matches_schema_and_rejects_unknown_fields(self):
        schema = json.loads(
            (ROOT / "schemas/approver-trust-enrollment.schema.json").read_text(
                encoding="utf-8"
            )
        )
        record = json.loads(self.raw.decode("utf-8"))
        self.assertEqual(record["schema"], ENROLLMENT_SCHEMA)
        validate(record, schema)
        with self.assertRaises(ContractValidationError):
            validate({**record, "extra": True}, schema)
        for changes in (
            {"operation": "delete_repository"},
            {"approver_public_key": "0" * 63},
            {"trust_profile_digest": "not-a-digest"},
            {"provider_repository_id": "../other"},
        ):
            with self.subTest(schema_changes=changes), self.assertRaises(
                ContractValidationError
            ):
                validate({**record, **changes}, schema)

    def test_rejects_wrong_authority_and_expected_scope(self):
        with self.assertRaises(ApproverTrustEnrollmentError):
            verify_approver_trust_enrollment(
                self.raw,
                trusted_authority_keys={
                    AUTHORITY_KEY_ID: raw_public_key(Ed25519PrivateKey.generate())
                },
                expected_approver_id=APPROVER_ID,
                expected_trust_profile_digest=PROFILE_DIGEST,
                expected_provider_repository_id=REPOSITORY_ID,
                now=NOW,
            )
        for changes in (
            {"approver_id": "user-bob"},
            {"profile_digest": "sha256:" + "2" * 64},
            {"repository_id": "github-installation/999/repository/1"},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ApproverTrustEnrollmentError
            ):
                self.verify(**changes)

    def test_rejects_tampering_unknown_fields_duplicates_and_noncanonical_json(self):
        record = json.loads(self.raw.decode("utf-8"))
        record["approver_id"] = "user-bob"
        tampered = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(ApproverTrustEnrollmentError):
            self.verify(tampered)

        record = json.loads(self.raw.decode("utf-8"))
        record["extra"] = "value"
        unknown = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(ApproverTrustEnrollmentError):
            self.verify(unknown)
        with self.assertRaises(ApproverTrustEnrollmentError):
            self.verify(b'{"schema":"one","schema":"two"}')
        with self.assertRaises(ApproverTrustEnrollmentError):
            self.verify(self.raw + b" ")
        with self.assertRaises(ApproverTrustEnrollmentError):
            self.verify(b"x" * (MAX_ENROLLMENT_BYTES + 1))

    def test_rejects_expired_future_and_overlong_enrollment(self):
        expired = build_signed_approver_trust_enrollment(
            enrollment_id="enroll-exp684-expired",
            authority_key_id=AUTHORITY_KEY_ID,
            approver_id=APPROVER_ID,
            approver_public_key=raw_public_key(self.approver),
            trust_profile_digest=PROFILE_DIGEST,
            provider_repository_id=REPOSITORY_ID,
            signing_key=self.authority,
            issued_at=NOW - timedelta(days=2),
            expires_at=NOW - timedelta(days=1),
        )
        with self.assertRaises(ApproverTrustEnrollmentError):
            self.verify(expired)

        future = build_signed_approver_trust_enrollment(
            enrollment_id="enroll-exp684-future",
            authority_key_id=AUTHORITY_KEY_ID,
            approver_id=APPROVER_ID,
            approver_public_key=raw_public_key(self.approver),
            trust_profile_digest=PROFILE_DIGEST,
            provider_repository_id=REPOSITORY_ID,
            signing_key=self.authority,
            issued_at=NOW + timedelta(minutes=1),
            expires_at=NOW + timedelta(days=1),
        )
        with self.assertRaises(ApproverTrustEnrollmentError):
            self.verify(future)
        with self.assertRaises(ApproverTrustEnrollmentError):
            build_signed_approver_trust_enrollment(
                enrollment_id="enroll-exp684-long",
                authority_key_id=AUTHORITY_KEY_ID,
                approver_id=APPROVER_ID,
                approver_public_key=raw_public_key(self.approver),
                trust_profile_digest=PROFILE_DIGEST,
                provider_repository_id=REPOSITORY_ID,
                signing_key=self.authority,
                issued_at=NOW,
                expires_at=NOW + timedelta(days=31),
            )

    def test_fixed_operation_and_malformed_fields_fail_before_acceptance(self):
        record = json.loads(self.raw.decode("utf-8"))
        record["operation"] = "delete_repository"
        with self.assertRaises(ApproverTrustEnrollmentError):
            self.verify(
                json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            )
        for invalid in (
            {"approver_public_key": "0" * 63},
            {"trust_profile_digest": "bad"},
            {"provider_repository_id": "../other"},
            {"approver_id": ""},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                ApproverTrustEnrollmentError
            ):
                fields = {
                    "enrollment_id": "enroll-exp684-invalid",
                    "authority_key_id": AUTHORITY_KEY_ID,
                    "approver_id": APPROVER_ID,
                    "approver_public_key": raw_public_key(self.approver),
                    "trust_profile_digest": PROFILE_DIGEST,
                    "provider_repository_id": REPOSITORY_ID,
                    "signing_key": self.authority,
                    "issued_at": NOW,
                    "expires_at": NOW + timedelta(days=1),
                }
                fields.update(invalid)
                build_signed_approver_trust_enrollment(**fields)


if __name__ == "__main__":
    unittest.main()
