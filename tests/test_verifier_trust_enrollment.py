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

from app_contracts.validator import ContractValidationError, validate
from app_contracts.verifier_trust_enrollment import (
    ENROLLMENT_SCHEMA,
    MAX_ENROLLMENT_BYTES,
    VerifierTrustEnrollmentError,
    build_signed_verifier_trust_enrollment,
    verify_verifier_trust_enrollment,
)


AUTHORITY_KEY_ID = "control-plane-enrollment-v1"
VERIFIER_KEY_ID = "remote-verifier-signing-v1"
ENDPOINT = "https://verifier.example.com/v1/verify"
VERIFIER_ID = "docker-image:sha256:" + "1" * 64 + "/code:sha256:" + "2" * 64
PROFILE_DIGEST = "sha256:" + "3" * 64
HOST_EVIDENCE_DIGEST = "sha256:" + "4" * 64
NOW = datetime(2026, 10, 8, 13, 0, 0, tzinfo=timezone.utc)


def raw_public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def build_record(
    authority_key: Ed25519PrivateKey,
    verifier_key: Ed25519PrivateKey,
    *,
    issued_at: datetime = NOW - timedelta(minutes=1),
    expires_at: datetime = NOW + timedelta(days=7),
    endpoint: str = ENDPOINT,
    verifier_id: str = VERIFIER_ID,
    profile_digest: str = PROFILE_DIGEST,
) -> bytes:
    return build_signed_verifier_trust_enrollment(
        enrollment_id="enroll-exp680-001",
        authority_key_id=AUTHORITY_KEY_ID,
        endpoint_url=endpoint,
        verifier_id=verifier_id,
        verifier_profile_digest=profile_digest,
        verifier_key_id=VERIFIER_KEY_ID,
        verifier_public_key=raw_public_key(verifier_key),
        worker_host_id="worker-host-01",
        verifier_host_id="verifier-host-02",
        host_separation_evidence_digest=HOST_EVIDENCE_DIGEST,
        signing_key=authority_key,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def verify_record(raw: bytes, authority_key: Ed25519PrivateKey, **kwargs):
    return verify_verifier_trust_enrollment(
        raw,
        trusted_authority_keys={AUTHORITY_KEY_ID: raw_public_key(authority_key)},
        expected_endpoint_url=kwargs.get("endpoint", ENDPOINT),
        expected_verifier_id=kwargs.get("verifier_id", VERIFIER_ID),
        expected_verifier_profile_digest=kwargs.get(
            "profile_digest", PROFILE_DIGEST
        ),
        now=kwargs.get("now", NOW),
    )


class VerifierTrustEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.authority_key = Ed25519PrivateKey.generate()
        self.verifier_key = Ed25519PrivateKey.generate()
        self.raw = build_record(self.authority_key, self.verifier_key)

    def test_valid_enrollment_binds_endpoint_profile_hosts_and_key_without_claiming_deployment(self):
        verified = verify_record(self.raw, self.authority_key)

        self.assertEqual(verified.endpoint_url, ENDPOINT)
        self.assertEqual(verified.verifier_id, VERIFIER_ID)
        self.assertEqual(verified.verifier_profile_digest, PROFILE_DIGEST)
        self.assertEqual(verified.verifier_key_id, VERIFIER_KEY_ID)
        self.assertEqual(verified.verifier_public_key, raw_public_key(self.verifier_key))
        self.assertEqual(verified.worker_host_id, "worker-host-01")
        self.assertEqual(verified.verifier_host_id, "verifier-host-02")
        self.assertEqual(verified.host_separation_evidence_digest, HOST_EVIDENCE_DIGEST)
        self.assertTrue(verified.authority_signature_valid)
        self.assertFalse(verified.independent_host_trust_established)
        self.assertNotIn(raw_public_key(self.verifier_key).hex(), repr(verified))

    def test_signed_record_matches_json_schema(self):
        schema_path = ROOT / "schemas" / "verifier-trust-enrollment.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        instance = json.loads(self.raw.decode("utf-8"))
        self.assertEqual(instance["schema"], ENROLLMENT_SCHEMA)
        validate(instance, schema)

        with self.assertRaises(ContractValidationError):
            validate({**instance, "extra": "value"}, schema)
        for endpoint in (
            "http://verifier.example.com/v1/verify",
            "https://127.0.0.1/v1/verify",
            "https://verifier.example.com:444/v1/verify",
            "https://verifier.example.com/v1/verify?debug=1",
            ENDPOINT + "\n",
        ):
            with self.subTest(schema_endpoint=endpoint):
                with self.assertRaises(ContractValidationError):
                    validate({**instance, "endpoint_url": endpoint}, schema)

    def test_rejects_wrong_authority_key_and_wrong_expected_bindings(self):
        other_authority = Ed25519PrivateKey.generate()
        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(self.raw, other_authority)

        for overrides in (
            {"endpoint": "https://other.example.com/v1/verify"},
            {"verifier_id": "another-verifier"},
            {"profile_digest": "sha256:" + "5" * 64},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(VerifierTrustEnrollmentError):
                    verify_record(self.raw, self.authority_key, **overrides)

    def test_rejects_tampered_fields_and_signature(self):
        parsed = json.loads(self.raw.decode("utf-8"))
        parsed["verifier_host_id"] = "worker-host-01"
        tampered = json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(tampered, self.authority_key)

        parsed = json.loads(self.raw.decode("utf-8"))
        parsed["signature"] = "0" * 128
        tampered_signature = json.dumps(
            parsed, sort_keys=True, separators=(",", ":")
        ).encode()
        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(tampered_signature, self.authority_key)

    def test_rejects_duplicate_unknown_noncanonical_and_oversized_records(self):
        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(b'{"schema":"a","schema":"b"}', self.authority_key)

        parsed = json.loads(self.raw.decode("utf-8"))
        parsed["unexpected"] = True
        unknown = json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(unknown, self.authority_key)

        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(self.raw + b" ", self.authority_key)
        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(b"x" * (MAX_ENROLLMENT_BYTES + 1), self.authority_key)

    def test_rejects_expired_future_and_overlong_enrollment_windows(self):
        expired = build_record(
            self.authority_key,
            self.verifier_key,
            issued_at=NOW - timedelta(days=2),
            expires_at=NOW - timedelta(days=1),
        )
        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(expired, self.authority_key)

        future = build_record(
            self.authority_key,
            self.verifier_key,
            issued_at=NOW + timedelta(minutes=1),
            expires_at=NOW + timedelta(days=1),
        )
        with self.assertRaises(VerifierTrustEnrollmentError):
            verify_record(future, self.authority_key)

        with self.assertRaises(VerifierTrustEnrollmentError):
            build_record(
                self.authority_key,
                self.verifier_key,
                issued_at=NOW,
                expires_at=NOW + timedelta(days=31),
            )

    def test_rejects_same_host_ids_and_unsafe_endpoints_before_signing(self):
        for endpoint in (
            "http://verifier.example.com/v1/verify",
            "https://127.0.0.1/v1/verify",
            "https://user@verifier.example.com/v1/verify",
            "https://verifier.example.com:444/v1/verify",
            "https://verifier.example.com/v1/verify?debug=1",
            "https://verifier.example.com/v1/verify?",
            "https://999.999.999.999/v1/verify",
            "https://verifier.example.com/other",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(VerifierTrustEnrollmentError):
                    build_record(self.authority_key, self.verifier_key, endpoint=endpoint)

        with self.assertRaises(VerifierTrustEnrollmentError):
            build_signed_verifier_trust_enrollment(
                enrollment_id="enroll-exp680-001",
                authority_key_id=AUTHORITY_KEY_ID,
                endpoint_url=ENDPOINT,
                verifier_id=VERIFIER_ID,
                verifier_profile_digest=PROFILE_DIGEST,
                verifier_key_id=VERIFIER_KEY_ID,
                verifier_public_key=raw_public_key(self.verifier_key),
                worker_host_id="same-host",
                verifier_host_id="same-host",
                host_separation_evidence_digest=HOST_EVIDENCE_DIGEST,
                signing_key=self.authority_key,
                issued_at=NOW,
                expires_at=NOW + timedelta(days=1),
            )


if __name__ == "__main__":
    unittest.main()
