from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app_contracts.verifier_host_trust_decision import (
    VerifierHostTrustDecisionError,
    assemble_signed_verifier_host_trust_decision,
    build_signed_verifier_host_trust_decision,
    build_verifier_host_trust_decision_signing_message,
    is_verified_verifier_host_trust_decision,
    verify_verifier_host_trust_decision,
)


NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
AUTHORITY_KEY_ID = "synthetic-authority-1"
ENROLLMENT_DIGEST = "sha256:" + "1" * 64
ENDPOINT = "https://testdev.local/v1/verify"
VERIFIER_ID = "synthetic-verifier"
PROFILE_DIGEST = "sha256:" + "2" * 64
VERIFIER_KEY_ID = "synthetic-verifier-key"
WORKER_HOST_ID = "worker-host-a"
VERIFIER_HOST_ID = "verifier-host-b"
EVIDENCE_DIGEST = "sha256:" + "3" * 64


class VerifierHostTrustDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authority_key = Ed25519PrivateKey.generate()
        self.public_key = self.authority_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        self.decision = build_signed_verifier_host_trust_decision(
            decision_id="synthetic-decision-1",
            authority_key_id=AUTHORITY_KEY_ID,
            enrollment_digest=ENROLLMENT_DIGEST,
            endpoint_url=ENDPOINT,
            verifier_id=VERIFIER_ID,
            verifier_profile_digest=PROFILE_DIGEST,
            verifier_key_id=VERIFIER_KEY_ID,
            worker_host_id=WORKER_HOST_ID,
            verifier_host_id=VERIFIER_HOST_ID,
            host_separation_evidence_digest=EVIDENCE_DIGEST,
            signing_key=self.authority_key,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )

    def verify(self, decision: bytes | None = None, **overrides):
        arguments = {
            "trusted_authority_keys": {AUTHORITY_KEY_ID: self.public_key},
            "expected_enrollment_digest": ENROLLMENT_DIGEST,
            "expected_endpoint_url": ENDPOINT,
            "expected_verifier_id": VERIFIER_ID,
            "expected_verifier_profile_digest": PROFILE_DIGEST,
            "expected_verifier_key_id": VERIFIER_KEY_ID,
            "expected_worker_host_id": WORKER_HOST_ID,
            "expected_verifier_host_id": VERIFIER_HOST_ID,
            "expected_host_separation_evidence_digest": EVIDENCE_DIGEST,
            "now": NOW,
        }
        arguments.update(overrides)
        return verify_verifier_host_trust_decision(
            self.decision if decision is None else decision,
            **arguments,
        )

    def test_valid_authority_decision_is_digest_addressed(self) -> None:
        verified = self.verify()
        self.assertTrue(is_verified_verifier_host_trust_decision(verified))
        self.assertEqual(verified.enrollment_digest, ENROLLMENT_DIGEST)
        self.assertTrue(verified.decision_digest.startswith("sha256:"))

    def test_detached_authority_signature_round_trips_through_existing_validator(self) -> None:
        message = build_verifier_host_trust_decision_signing_message(
            decision_id="synthetic-decision-1",
            authority_key_id=AUTHORITY_KEY_ID,
            enrollment_digest=ENROLLMENT_DIGEST,
            endpoint_url=ENDPOINT,
            verifier_id=VERIFIER_ID,
            verifier_profile_digest=PROFILE_DIGEST,
            verifier_key_id=VERIFIER_KEY_ID,
            worker_host_id=WORKER_HOST_ID,
            verifier_host_id=VERIFIER_HOST_ID,
            host_separation_evidence_digest=EVIDENCE_DIGEST,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
        assembled = assemble_signed_verifier_host_trust_decision(
            message, self.authority_key.sign(message)
        )
        self.assertEqual(assembled, self.decision)
        self.assertEqual(self.verify(assembled).decision_digest,
                         self.verify().decision_digest)

    def test_detached_assembler_rejects_wrong_domain_payload_shape_and_signature(self) -> None:
        message = build_verifier_host_trust_decision_signing_message(
            decision_id="synthetic-decision-1",
            authority_key_id=AUTHORITY_KEY_ID,
            enrollment_digest=ENROLLMENT_DIGEST,
            endpoint_url=ENDPOINT,
            verifier_id=VERIFIER_ID,
            verifier_profile_digest=PROFILE_DIGEST,
            verifier_key_id=VERIFIER_KEY_ID,
            worker_host_id=WORKER_HOST_ID,
            verifier_host_id=VERIFIER_HOST_ID,
            host_separation_evidence_digest=EVIDENCE_DIGEST,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
        signature = self.authority_key.sign(message)
        invalid_messages = (
            b"wrong-domain\0" + message,
            message + b" ",
            message[:-1] + b',"schema":"duplicate"}',
        )
        for invalid in invalid_messages:
            with self.subTest(message=invalid[:24]):
                with self.assertRaises(VerifierHostTrustDecisionError):
                    assemble_signed_verifier_host_trust_decision(invalid, signature)
        for invalid_signature in ("not-bytes", b"short", b"x" * 65):
            with self.subTest(signature_type=type(invalid_signature).__name__):
                with self.assertRaises(VerifierHostTrustDecisionError):
                    assemble_signed_verifier_host_trust_decision(message, invalid_signature)

    def test_detached_but_invalid_signature_is_rejected_by_existing_validator(self) -> None:
        message = build_verifier_host_trust_decision_signing_message(
            decision_id="synthetic-decision-1",
            authority_key_id=AUTHORITY_KEY_ID,
            enrollment_digest=ENROLLMENT_DIGEST,
            endpoint_url=ENDPOINT,
            verifier_id=VERIFIER_ID,
            verifier_profile_digest=PROFILE_DIGEST,
            verifier_key_id=VERIFIER_KEY_ID,
            worker_host_id=WORKER_HOST_ID,
            verifier_host_id=VERIFIER_HOST_ID,
            host_separation_evidence_digest=EVIDENCE_DIGEST,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
        assembled = assemble_signed_verifier_host_trust_decision(
            message, b"x" * 64
        )
        with self.assertRaises(VerifierHostTrustDecisionError):
            self.verify(assembled)

    def test_copied_claim_without_verifier_provenance_is_not_trusted(self) -> None:
        verified = self.verify()
        forged = replace(verified, _verification_token=object())
        self.assertFalse(is_verified_verifier_host_trust_decision(forged))

    def test_signature_tampering_is_rejected(self) -> None:
        record = json.loads(self.decision)
        record["host_separation_evidence_digest"] = "sha256:" + "4" * 64
        tampered = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaisesRegex(
            VerifierHostTrustDecisionError, "verification failed"
        ):
            self.verify(tampered)

    def test_noncanonical_and_duplicate_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            VerifierHostTrustDecisionError, "verification failed"
        ):
            self.verify(self.decision + b" ")
        duplicated = self.decision[:-1] + b',"outcome":"approve_independent_host"}'
        with self.assertRaisesRegex(
            VerifierHostTrustDecisionError, "verification failed"
        ):
            self.verify(duplicated)

    def test_expired_decision_is_rejected(self) -> None:
        expired = build_signed_verifier_host_trust_decision(
            decision_id="synthetic-decision-expired",
            authority_key_id=AUTHORITY_KEY_ID,
            enrollment_digest=ENROLLMENT_DIGEST,
            endpoint_url=ENDPOINT,
            verifier_id=VERIFIER_ID,
            verifier_profile_digest=PROFILE_DIGEST,
            verifier_key_id=VERIFIER_KEY_ID,
            worker_host_id=WORKER_HOST_ID,
            verifier_host_id=VERIFIER_HOST_ID,
            host_separation_evidence_digest=EVIDENCE_DIGEST,
            signing_key=self.authority_key,
            issued_at=NOW - timedelta(hours=2),
            expires_at=NOW - timedelta(hours=1),
        )
        with self.assertRaisesRegex(
            VerifierHostTrustDecisionError, "verification failed"
        ):
            self.verify(expired)

    def test_every_expected_binding_is_exact(self) -> None:
        mismatches = (
            {"expected_enrollment_digest": "sha256:" + "9" * 64},
            {"expected_endpoint_url": "https://other.example.test/v1/verify"},
            {"expected_verifier_id": "other-verifier"},
            {"expected_verifier_profile_digest": "sha256:" + "8" * 64},
            {"expected_verifier_key_id": "other-key"},
            {"expected_worker_host_id": "other-worker"},
            {"expected_verifier_host_id": "other-host"},
            {"expected_host_separation_evidence_digest": "sha256:" + "7" * 64},
            {"trusted_authority_keys": {"other-authority": self.public_key}},
        )
        for mismatch in mismatches:
            with self.subTest(mismatch=mismatch):
                with self.assertRaisesRegex(
                    VerifierHostTrustDecisionError, "verification failed"
                ):
                    self.verify(**mismatch)

    def test_builder_rejects_same_worker_and_verifier_host(self) -> None:
        with self.assertRaisesRegex(
            VerifierHostTrustDecisionError, "record rejected"
        ):
            build_signed_verifier_host_trust_decision(
                decision_id="synthetic-decision-same-host",
                authority_key_id=AUTHORITY_KEY_ID,
                enrollment_digest=ENROLLMENT_DIGEST,
                endpoint_url=ENDPOINT,
                verifier_id=VERIFIER_ID,
                verifier_profile_digest=PROFILE_DIGEST,
                verifier_key_id=VERIFIER_KEY_ID,
                worker_host_id=WORKER_HOST_ID,
                verifier_host_id=WORKER_HOST_ID,
                host_separation_evidence_digest=EVIDENCE_DIGEST,
                signing_key=self.authority_key,
                issued_at=NOW,
                expires_at=NOW + timedelta(hours=1),
            )


if __name__ == "__main__":
    unittest.main()
