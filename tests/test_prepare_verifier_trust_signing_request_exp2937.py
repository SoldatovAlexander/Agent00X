from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import ed25519

from scripts import prepare_verifier_trust_signing_request_exp2271 as base
from scripts import prepare_verifier_trust_signing_request_exp2937 as profile
from scripts import prepare_verifier_trust_signing_request_exp2956 as decision_profile
from scripts import record_verifier_trust_signature_exp2196 as recorder
from scripts.serve_ephemeral_signed_verifier_https import _serialize_public_bootstrap
from tests.test_import_testdev_verifier_bootstrap import _public_ca


class PrepareVerifierTrustSigningRequestExp2937Tests(unittest.TestCase):
    def test_profile_binds_only_the_successor_bootstrap_and_ids(self):
        self.assertEqual(profile.BOOTSTRAP_PATH.name, "verifier-bootstrap-exp2973.json")
        self.assertEqual(profile.ENROLLMENT_ID, "agent00x-enrollment-exp2974")
        self.assertEqual(profile.DECISION_ID, "agent00x-host-decision-exp2975")

    def test_request_is_public_bounded_and_neither_signed_nor_persisted(self):
        certificate = _public_ca()
        raw = _serialize_public_bootstrap(
            port=49231,
            ca_certificate_pem=certificate,
            ca_sha256=hashlib.sha256(certificate).hexdigest(),
            signing_key=ed25519.Ed25519PrivateKey.generate(),
            listen_host="192.168.88.101",
            allowed_peer_address="192.168.88.5",
        ) + b"\n"
        with tempfile.TemporaryDirectory() as directory:
            bootstrap_path = Path(directory) / "bootstrap.json"
            descriptor = os.open(bootstrap_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, raw)
            finally:
                os.close(descriptor)
            now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
            with patch.object(profile, "BOOTSTRAP_PATH", bootstrap_path), patch.object(
                base, "BOOTSTRAP_PATH", bootstrap_path
            ):
                request_raw = profile.build_enrollment_request(now=now)
            request = json.loads(request_raw)
            self.assertEqual(request["kind"], "enrollment")
            self.assertEqual(request["trust"], "unestablished")
            self.assertRegex(request["message_sha256"], r"^sha256:[0-9a-f]{64}$")
            payload = base64.b64decode(request["message_base64"])
            prefix = b"agent00x-verifier-trust-enrollment-ed25519-v1\0"
            self.assertTrue(payload.startswith(prefix))
            signed_payload = json.loads(payload[len(prefix):])
            self.assertEqual(signed_payload["enrollment_id"], profile.ENROLLMENT_ID)
            self.assertEqual(
                signed_payload["verifier_profile_digest"],
                "sha256:2b5f093aefc915c8248bd04326f6cfc8f3958313384944869fb81adeffdad1f6",
            )
            expires = datetime.fromisoformat(signed_payload["expires_at"].replace("Z", "+00:00"))
            self.assertLessEqual(expires, now + timedelta(minutes=5))
            self.assertFalse((Path(directory) / "signature.json").exists())

    def test_successor_host_decision_is_bound_to_recorded_enrollment_digest(self):
        certificate = _public_ca()
        signing_key = ed25519.Ed25519PrivateKey.generate()
        verifier_public_key = signing_key.public_key().public_bytes_raw().hex()
        raw_bootstrap = _serialize_public_bootstrap(
            port=49231,
            ca_certificate_pem=certificate,
            ca_sha256=hashlib.sha256(certificate).hexdigest(),
            signing_key=signing_key,
            listen_host="192.168.88.101",
            allowed_peer_address="192.168.88.5",
        ) + b"\n"
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bootstrap_path = root / "bootstrap.json"
            bootstrap_path.write_bytes(raw_bootstrap)
            os.chmod(bootstrap_path, 0o600)
            artifact = {
                "schema": "verifier-trust-enrollment/v1",
                "enrollment_id": profile.ENROLLMENT_ID,
                "authority_key_id": recorder.AUTHORITY_KEY_ID,
                "endpoint_url": recorder.ENDPOINT,
                "verifier_id": recorder.VERIFIER_ID,
                "verifier_profile_digest": recorder.PROFILE_DIGEST,
                "verifier_key_id": recorder.VERIFIER_KEY_ID,
                "verifier_public_key": verifier_public_key,
                "worker_host_id": recorder.WORKER_HOST_ID,
                "verifier_host_id": recorder.VERIFIER_HOST_ID,
                "host_separation_evidence_digest": recorder.SEPARATION_DIGEST,
                "issued_at": "2026-10-17T11:59:00Z",
                "expires_at": "2026-10-17T12:04:00Z",
            }
            artifact_raw = (
                json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("ascii")
            artifact_digest = "sha256:" + hashlib.sha256(artifact_raw).hexdigest()
            report = {
                "kind": "enrollment",
                "artifact_id": profile.ENROLLMENT_ID,
                "artifact_digest": artifact_digest,
                "authority_signature_valid": True,
                "authority_key_set_digest": recorder.AUTHORITY_KEY_SET_DIGEST,
                "independent_host_trust_established": False,
            }
            report_path = root / "enrollment-report.json"
            report_path.write_text(json.dumps(report), encoding="ascii")
            artifact_path = root / "enrollment-artifact.json"
            artifact_path.write_bytes(artifact_raw)
            os.chmod(report_path, 0o600)
            os.chmod(artifact_path, 0o600)

            with patch.object(decision_profile, "BOOTSTRAP_PATH", bootstrap_path), patch.object(
                recorder, "ENROLLMENT_REPORT_EXP2955", report_path
            ), patch.object(recorder, "ENROLLMENT_ARTIFACT_EXP2955", artifact_path):
                request_raw = decision_profile.build_host_decision_request(now=now)

            request = json.loads(request_raw)
            message = base64.b64decode(request["message_base64"])
            domain = b"agent00x-verifier-host-trust-decision-ed25519-v1\0"
            self.assertTrue(message.startswith(domain))
            payload = json.loads(message[len(domain):])
            self.assertEqual(payload["decision_id"], profile.DECISION_ID)
            self.assertEqual(payload["enrollment_digest"], artifact_digest)
            self.assertLessEqual(
                datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00")),
                datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
                - timedelta(seconds=5),
            )
            self.assertFalse((root / "signature.json").exists())


if __name__ == "__main__":
    unittest.main()
