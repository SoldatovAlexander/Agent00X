from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import prepare_verifier_trust_signing_message as cli
from app_contracts.verifier_host_trust_decision import (
    assemble_signed_verifier_host_trust_decision,
    verify_verifier_host_trust_decision,
)
from app_contracts.verifier_trust_enrollment import (
    assemble_signed_verifier_trust_enrollment,
    verify_verifier_trust_enrollment,
)


NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
AUTHORITY_ID = "test-authority-01"
ENDPOINT = "https://testdev.local/v1/verify"
VERIFIER_ID = "docker-image:sha256:" + "1" * 64 + "/code:sha256:" + "2" * 64
PROFILE_DIGEST = "sha256:" + "3" * 64
VERIFIER_KEY_ID = "verifier-key-01"
WORKER_HOST_ID = "worker-host-01"
VERIFIER_HOST_ID = "verifier-host-02"
SEPARATION_DIGEST = "sha256:" + "4" * 64


def public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def decode_response(raw: bytes) -> dict:
    return json.loads(raw)


class PrepareVerifierTrustSigningMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = Ed25519PrivateKey.generate()
        self.verifier = Ed25519PrivateKey.generate()

    def test_enrollment_message_can_be_signed_externally_and_validated(self) -> None:
        input_value = {
            "enrollment_id": "enrollment-01",
            "authority_key_id": AUTHORITY_ID,
            "endpoint_url": ENDPOINT,
            "verifier_id": VERIFIER_ID,
            "verifier_profile_digest": PROFILE_DIGEST,
            "verifier_key_id": VERIFIER_KEY_ID,
            "verifier_public_key": public_key(self.verifier).hex(),
            "worker_host_id": WORKER_HOST_ID,
            "verifier_host_id": VERIFIER_HOST_ID,
            "host_separation_evidence_digest": SEPARATION_DIGEST,
            "issued_at": "2026-10-17T12:00:00Z",
            "expires_at": "2026-10-24T12:00:00Z",
        }
        response = decode_response(
            cli.prepare_request(
                "enrollment",
                json.dumps(input_value).encode("utf-8"),
            )
        )
        message = base64.b64decode(response["message_base64"], validate=True)
        self.assertEqual(
            response["message_sha256"],
            "sha256:" + hashlib.sha256(message).hexdigest(),
        )
        self.assertEqual(response["trust"], "unestablished")
        record = assemble_signed_verifier_trust_enrollment(
            message, self.authority.sign(message)
        )
        verified = verify_verifier_trust_enrollment(
            record,
            trusted_authority_keys={AUTHORITY_ID: public_key(self.authority)},
            expected_endpoint_url=ENDPOINT,
            expected_verifier_id=VERIFIER_ID,
            expected_verifier_profile_digest=PROFILE_DIGEST,
            now=NOW,
        )
        self.assertEqual(verified.enrollment_id, "enrollment-01")
        self.assertFalse(verified.independent_host_trust_established)

    def test_host_decision_message_can_be_signed_externally_and_validated(self) -> None:
        input_value = {
            "decision_id": "decision-01",
            "authority_key_id": AUTHORITY_ID,
            "enrollment_digest": "sha256:" + "5" * 64,
            "endpoint_url": ENDPOINT,
            "verifier_id": VERIFIER_ID,
            "verifier_profile_digest": PROFILE_DIGEST,
            "verifier_key_id": VERIFIER_KEY_ID,
            "worker_host_id": WORKER_HOST_ID,
            "verifier_host_id": VERIFIER_HOST_ID,
            "host_separation_evidence_digest": SEPARATION_DIGEST,
            "issued_at": "2026-10-17T12:00:00Z",
            "expires_at": "2026-10-17T13:00:00Z",
        }
        response = decode_response(
            cli.prepare_request(
                "host-decision",
                json.dumps(input_value).encode("utf-8"),
            )
        )
        message = base64.b64decode(response["message_base64"], validate=True)
        record = assemble_signed_verifier_host_trust_decision(
            message, self.authority.sign(message)
        )
        verified = verify_verifier_host_trust_decision(
            record,
            trusted_authority_keys={AUTHORITY_ID: public_key(self.authority)},
            expected_enrollment_digest=input_value["enrollment_digest"],
            expected_endpoint_url=ENDPOINT,
            expected_verifier_id=VERIFIER_ID,
            expected_verifier_profile_digest=PROFILE_DIGEST,
            expected_verifier_key_id=VERIFIER_KEY_ID,
            expected_worker_host_id=WORKER_HOST_ID,
            expected_verifier_host_id=VERIFIER_HOST_ID,
            expected_host_separation_evidence_digest=SEPARATION_DIGEST,
            now=NOW,
        )
        self.assertEqual(verified.decision_id, "decision-01")

    def test_rejects_duplicate_unknown_and_secret_or_signature_fields(self) -> None:
        valid = {
            "enrollment_id": "enrollment-01",
            "authority_key_id": AUTHORITY_ID,
            "endpoint_url": ENDPOINT,
            "verifier_id": VERIFIER_ID,
            "verifier_profile_digest": PROFILE_DIGEST,
            "verifier_key_id": VERIFIER_KEY_ID,
            "verifier_public_key": public_key(self.verifier).hex(),
            "worker_host_id": WORKER_HOST_ID,
            "verifier_host_id": VERIFIER_HOST_ID,
            "host_separation_evidence_digest": SEPARATION_DIGEST,
            "issued_at": "2026-10-17T12:00:00Z",
            "expires_at": "2026-10-24T12:00:00Z",
        }
        for extra in ({"signature": "0" * 128}, {"authority_private_key": "no"}, {"extra": True}):
            with self.subTest(extra=next(iter(extra))):
                with self.assertRaisesRegex(ValueError, "request rejected"):
                    cli.prepare_request(
                        "enrollment",
                        json.dumps({**valid, **extra}).encode("utf-8"),
                    )
        duplicated = json.dumps(valid, separators=(",", ":"))[:-1] + ',"enrollment_id":"second"}'
        with self.assertRaisesRegex(ValueError, "request rejected"):
            cli.prepare_request("enrollment", duplicated.encode("utf-8"))

    def test_cli_emits_only_fixed_error_marker_and_no_partial_stdout(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        result = cli.main(
            ["--kind", "enrollment"],
            stdin=io.BytesIO(b'{"signature":"private-looking-input"}'),
            stdout=stdout,
            stderr=stderr,
        )
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "TRUST_SIGNING_REQUEST_REJECTED\n")


if __name__ == "__main__":
    unittest.main()
