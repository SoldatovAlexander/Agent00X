from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import prepare_verifier_trust_signing_message as prepare_cli
import verify_detached_verifier_trust_signature as verify_cli
from app_contracts.verifier_host_trust_decision import (
    verify_verifier_host_trust_decision,
)
from app_contracts.verifier_trust_enrollment import (
    assemble_signed_verifier_trust_enrollment,
    verify_verifier_trust_enrollment,
)


AUTHORITY_ID = "authority-test-01"
ENDPOINT = "https://testdev.local/v1/verify"
VERIFIER_ID = "docker-image:sha256:" + "1" * 64 + "/code:sha256:" + "2" * 64
PROFILE_DIGEST = "sha256:" + "3" * 64
VERIFIER_KEY_ID = "verifier-key-01"
WORKER_HOST_ID = "worker-host-01"
VERIFIER_HOST_ID = "verifier-host-02"
SEPARATION_DIGEST = "sha256:" + "4" * 64


def raw_public_key(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


class VerifyDetachedVerifierTrustSignatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.authority = Ed25519PrivateKey.generate()
        self.verifier = Ed25519PrivateKey.generate()
        self.key_set_path = self.root / "authority-keys.json"
        key_set = {
            "keys": {AUTHORITY_ID: raw_public_key(self.authority).hex()},
            "schema": "control-plane-authority-key-set/v1",
        }
        self.key_set_bytes = json.dumps(
            key_set, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        self.key_set_path.write_bytes(self.key_set_bytes)
        self.key_set_digest = "sha256:" + hashlib.sha256(
            self.key_set_bytes
        ).hexdigest()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        enrollment_response = self._request("enrollment")
        enrollment_message = base64.b64decode(
            enrollment_response["message_base64"], validate=True
        )
        self.enrollment_artifact = assemble_signed_verifier_trust_enrollment(
            enrollment_message,
            bytes.fromhex(enrollment_response["signature_hex"]),
        )
        self.enrollment_path = self.root / "verified-enrollment.json"
        self.enrollment_path.write_bytes(self.enrollment_artifact)
        enrollment = verify_verifier_trust_enrollment(
            self.enrollment_artifact,
            trusted_authority_keys={AUTHORITY_ID: raw_public_key(self.authority)},
            expected_endpoint_url=ENDPOINT,
            expected_verifier_id=VERIFIER_ID,
            expected_verifier_profile_digest=PROFILE_DIGEST,
            now=self.now,
        )
        self.enrollment_digest = enrollment.enrollment_digest

    def _request(
        self, kind: str, *, enrollment_id: str = "enrollment-test-01"
    ) -> dict[str, str]:
        issued = self.now - timedelta(seconds=5)
        expires = self.now + timedelta(hours=1)
        common = {
            "authority_key_id": AUTHORITY_ID,
            "endpoint_url": ENDPOINT,
            "verifier_id": VERIFIER_ID,
            "verifier_profile_digest": PROFILE_DIGEST,
            "verifier_key_id": VERIFIER_KEY_ID,
            "worker_host_id": WORKER_HOST_ID,
            "verifier_host_id": VERIFIER_HOST_ID,
            "host_separation_evidence_digest": SEPARATION_DIGEST,
            "issued_at": issued.isoformat().replace("+00:00", "Z"),
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
        }
        if kind == "enrollment":
            request = {
                "enrollment_id": enrollment_id,
                **common,
                "verifier_public_key": raw_public_key(self.verifier).hex(),
            }
        else:
            request = {
                "decision_id": "decision-test-01",
                "enrollment_digest": self.enrollment_digest,
                **common,
            }
        prepared = json.loads(
            prepare_cli.prepare_request(
                kind,
                json.dumps(request, sort_keys=True, separators=(",", ":")).encode(
                    "ascii"
                ),
            )
        )
        message = base64.b64decode(prepared["message_base64"], validate=True)
        return {
            "schema": "agent00x-detached-trust-signature-response/v1",
            "kind": kind,
            "message_base64": prepared["message_base64"],
            "message_sha256": prepared["message_sha256"],
            "signature_hex": self.authority.sign(message).hex(),
        }

    def _argv(self, kind: str, **overrides: str) -> list[str]:
        values = {
            "--kind": kind,
            "--authority-key-set": str(self.key_set_path),
            "--authority-key-set-digest": self.key_set_digest,
            "--expected-authority-key-id": AUTHORITY_ID,
            "--expected-endpoint-url": ENDPOINT,
            "--expected-verifier-id": VERIFIER_ID,
            "--expected-verifier-profile-digest": PROFILE_DIGEST,
            "--expected-verifier-key-id": VERIFIER_KEY_ID,
            "--expected-worker-host-id": WORKER_HOST_ID,
            "--expected-verifier-host-id": VERIFIER_HOST_ID,
            "--expected-host-separation-evidence-digest": SEPARATION_DIGEST,
        }
        if kind == "host-decision":
            values["--expected-enrollment-digest"] = self.enrollment_digest
            values["--enrollment-artifact"] = str(self.enrollment_path)
        values.update(overrides)
        return [item for pair in values.items() for item in pair]

    def _run(self, kind: str, response: dict[str, str], **overrides: str):
        stdout = io.StringIO()
        stderr = io.StringIO()
        status = verify_cli.main(
            self._argv(kind, **overrides),
            stdin=io.BytesIO(
                json.dumps(response, sort_keys=True, separators=(",", ":")).encode(
                    "ascii"
                )
            ),
            stdout=stdout,
            stderr=stderr,
        )
        return status, stdout.getvalue(), stderr.getvalue()

    def test_enrollment_is_assembled_and_verified_but_trust_stays_unestablished(self):
        status, stdout, stderr = self._run("enrollment", self._request("enrollment"))
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        artifact = base64.b64decode(result["artifact_base64"], validate=True)
        verified = verify_verifier_trust_enrollment(
            artifact,
            trusted_authority_keys={AUTHORITY_ID: raw_public_key(self.authority)},
            expected_endpoint_url=ENDPOINT,
            expected_verifier_id=VERIFIER_ID,
            expected_verifier_profile_digest=PROFILE_DIGEST,
            now=self.now,
        )
        self.assertEqual(result["artifact_digest"], verified.enrollment_digest)
        self.assertEqual(result["authority_key_set_digest"], self.key_set_digest)
        self.assertEqual(
            result["verified_bindings"],
            {
                "authority_key_id": AUTHORITY_ID,
                "endpoint_url": ENDPOINT,
                "verifier_id": VERIFIER_ID,
                "verifier_profile_digest": PROFILE_DIGEST,
                "verifier_key_id": VERIFIER_KEY_ID,
                "worker_host_id": WORKER_HOST_ID,
                "verifier_host_id": VERIFIER_HOST_ID,
                "host_separation_evidence_digest": SEPARATION_DIGEST,
            },
        )
        self.assertEqual(result["issued_at"], verified.issued_at)
        self.assertEqual(result["expires_at"], verified.expires_at)
        self.assertTrue(result["authority_signature_valid"])
        self.assertFalse(result["independent_host_trust_established"])
        self.assertEqual(
            result["trust"],
            "authority_claim_verified; deployment_and_host_separation_unestablished",
        )

    def test_host_decision_is_assembled_and_verified_without_claiming_host_trust(self):
        status, stdout, stderr = self._run(
            "host-decision", self._request("host-decision")
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        artifact = base64.b64decode(result["artifact_base64"], validate=True)
        verified = verify_verifier_host_trust_decision(
            artifact,
            trusted_authority_keys={AUTHORITY_ID: raw_public_key(self.authority)},
            expected_enrollment_digest=self.enrollment_digest,
            expected_endpoint_url=ENDPOINT,
            expected_verifier_id=VERIFIER_ID,
            expected_verifier_profile_digest=PROFILE_DIGEST,
            expected_verifier_key_id=VERIFIER_KEY_ID,
            expected_worker_host_id=WORKER_HOST_ID,
            expected_verifier_host_id=VERIFIER_HOST_ID,
            expected_host_separation_evidence_digest=SEPARATION_DIGEST,
            now=self.now,
        )
        self.assertEqual(result["artifact_digest"], verified.decision_digest)
        self.assertEqual(
            result["bound_enrollment_digest"], self.enrollment_digest
        )
        self.assertEqual(
            result["verified_bindings"]["host_separation_evidence_digest"],
            SEPARATION_DIGEST,
        )
        self.assertEqual(result["issued_at"], verified.issued_at)
        self.assertEqual(result["expires_at"], verified.expires_at)
        self.assertFalse(result["independent_host_trust_established"])

    def test_host_decision_rejects_missing_tampered_or_substituted_enrollment(self):
        response = self._request("host-decision")
        cases = (
            {"--enrollment-artifact": str(self.root / "missing-enrollment.json")},
            {"--expected-enrollment-digest": "sha256:" + "6" * 64},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                status, stdout, stderr = self._run(
                    "host-decision", response, **overrides
                )
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")
                self.assertEqual(stderr, "DETACHED_TRUST_SIGNATURE_REJECTED\n")

        tampered_path = self.root / "tampered-enrollment.json"
        tampered_path.write_bytes(self.enrollment_artifact + b" ")
        status, stdout, stderr = self._run(
            "host-decision",
            response,
            **{"--enrollment-artifact": str(tampered_path)},
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "DETACHED_TRUST_SIGNATURE_REJECTED\n")

        alternate_response = self._request(
            "enrollment", enrollment_id="substituted-enrollment"
        )
        alternate_message = base64.b64decode(
            alternate_response["message_base64"], validate=True
        )
        alternate_artifact = assemble_signed_verifier_trust_enrollment(
            alternate_message,
            bytes.fromhex(alternate_response["signature_hex"]),
        )
        alternate_path = self.root / "substituted-enrollment.json"
        alternate_path.write_bytes(alternate_artifact)
        status, stdout, stderr = self._run(
            "host-decision",
            response,
            **{"--enrollment-artifact": str(alternate_path)},
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "DETACHED_TRUST_SIGNATURE_REJECTED\n")

    def test_rejects_authority_pin_and_expected_binding_mismatch_without_output(self):
        response = self._request("enrollment")
        for overrides in (
            {"--authority-key-set-digest": "sha256:" + "0" * 64},
            {"--expected-verifier-host-id": "unexpected-host"},
            {"--expected-authority-key-id": "unexpected-authority"},
            {"--expected-enrollment-digest": "sha256:" + "5" * 64},
        ):
            with self.subTest(overrides=overrides):
                status, stdout, stderr = self._run(
                    "enrollment", response, **overrides
                )
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")
                self.assertEqual(stderr, "DETACHED_TRUST_SIGNATURE_REJECTED\n")

    def test_rejects_tampered_signature_and_malformed_or_duplicate_fields(self):
        response = self._request("host-decision")
        response["signature_hex"] = "0" * 128
        status, stdout, stderr = self._run("host-decision", response)
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "DETACHED_TRUST_SIGNATURE_REJECTED\n")

        duplicate = (
            b'{"schema":"agent00x-detached-trust-signature-response/v1",'
            b'"schema":"agent00x-detached-trust-signature-response/v1"}'
        )
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        status = verify_cli.main(
            self._argv("enrollment"),
            stdin=io.BytesIO(duplicate),
            stdout=stdout_buffer,
            stderr=stderr_buffer,
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertEqual(
            stderr_buffer.getvalue(), "DETACHED_TRUST_SIGNATURE_REJECTED\n"
        )

    def test_documented_cli_entrypoint_round_trips_synthetic_evidence(self):
        response = self._request("enrollment")
        raw = json.dumps(
            response, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        environment = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"}
        script = str(ROOT / "scripts" / "verify_detached_verifier_trust_signature.py")
        command = [sys.executable, script, *self._argv("enrollment")]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            input=raw,
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, b"")
        self.assertEqual(completed.stdout.count(b"\n"), 1)
        result = json.loads(completed.stdout)
        self.assertEqual(result["verified_bindings"]["endpoint_url"], ENDPOINT)
        self.assertEqual(result["authority_key_set_digest"], self.key_set_digest)
        self.assertTrue(result["authority_signature_valid"])
        self.assertFalse(result["independent_host_trust_established"])

        rejected = subprocess.run(
            [
                sys.executable,
                script,
                *self._argv(
                    "enrollment",
                    **{"--authority-key-set-digest": "sha256:" + "0" * 64},
                ),
            ],
            cwd=ROOT,
            env=environment,
            input=raw,
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected.stdout, b"")
        self.assertEqual(
            rejected.stderr, b"DETACHED_TRUST_SIGNATURE_REJECTED\n"
        )

    def test_rejects_unknown_fields_and_oversized_input(self):
        response = self._request("enrollment")
        response["unexpected"] = "ignored fields must not be accepted"
        status, stdout, stderr = self._run("enrollment", response)
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "DETACHED_TRUST_SIGNATURE_REJECTED\n")

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        status = verify_cli.main(
            self._argv("enrollment"),
            stdin=io.BytesIO(b" " * (verify_cli.MAX_INPUT_BYTES + 1)),
            stdout=stdout_buffer,
            stderr=stderr_buffer,
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertEqual(
            stderr_buffer.getvalue(), "DETACHED_TRUST_SIGNATURE_REJECTED\n"
        )


if __name__ == "__main__":
    unittest.main()
