from __future__ import annotations

import shutil
import base64
import hashlib
import io
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sign_current_verifier_trust_message_exp1666.swift"
sys.path.insert(0, str(ROOT / "scripts"))

import verify_detached_verifier_trust_signature as verify_cli


@unittest.skipUnless(shutil.which("swift"), "Swift is required for the synthetic signer self-test")
class CurrentVerifierTrustMessageSignerTests(unittest.TestCase):
    def test_synthetic_self_test_does_not_enter_signing_or_keychain_path(self):
        result = subprocess.run(
            ["swift", str(SCRIPT), "--self-test"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "EXP1666_SELF_TEST_OK\n")
        self.assertEqual(result.stderr, "")

    def test_real_signing_mode_accepts_only_the_user_pinned_digest_before_parsing(self):
        result = subprocess.run(
            [
                "swift", str(SCRIPT),
                "--key-set", "/does/not/read/authority-key-set.json",
                "--key-set-digest", "sha256:" + "6e93f28e31c9bb18e529b33f184983c4c49ccdfb132273cc66337989cf8eea60",
            ],
            cwd=ROOT,
            input="",
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "EXP1666_REQUEST_REJECTED\n")

    def test_real_signing_mode_rejects_a_different_digest_before_reading_request(self):
        result = subprocess.run(
            [
                "swift", str(SCRIPT),
                "--key-set", "/does/not/read/authority-key-set.json",
                "--key-set-digest", "sha256:" + "0" * 64,
            ],
            cwd=ROOT,
            input="",
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "EXP1666_REQUEST_REJECTED\n")

    def test_synthetic_swift_response_is_accepted_by_python_verifier(self):
        generated = subprocess.run(
            ["swift", str(SCRIPT), "--self-test-vector"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)
        vector = json.loads(generated.stdout)
        self.assertEqual(
            vector["schema"], "agent00x-exp1666-synthetic-verification-vector/v1"
        )
        key_set_bytes = base64.b64decode(vector["authority_key_set_base64"], validate=True)
        self.assertEqual(
            "sha256:" + hashlib.sha256(key_set_bytes).hexdigest(),
            vector["authority_key_set_digest"],
        )
        enrollment_response = base64.b64decode(
            vector["enrollment_response_base64"], validate=True
        )
        expected_enrollment_artifact = base64.b64decode(
            vector["enrollment_artifact_base64"], validate=True
        )
        host_decision_response = base64.b64decode(
            vector["host_decision_response_base64"], validate=True
        )

        with tempfile.TemporaryDirectory(prefix="exp1666-vector-") as temporary:
            key_set_path = Path(temporary) / "authority-key-set.json"
            key_set_path.write_bytes(key_set_bytes)
            common_args = [
                "--authority-key-set", str(key_set_path),
                "--authority-key-set-digest", vector["authority_key_set_digest"],
                "--expected-authority-key-id", "cp-macos-keychain-exp1665-20261020-v1",
                "--expected-endpoint-url", "https://testdev.local/v1/verify",
                "--expected-verifier-id", "synthetic-verifier-exp1666",
                "--expected-verifier-profile-digest",
                "sha256:34d973ee7632a397b3941b32408dd7903774ed38c9958ad41bd4e6194ddfd280",
                "--expected-verifier-key-id", "brainbooster-verifier-v1",
                "--expected-worker-host-id", "synthetic-worker-exp1666",
                "--expected-verifier-host-id", "synthetic-verifier-host-exp1666",
                "--expected-host-separation-evidence-digest", "sha256:" + "a" * 64,
            ]
            enrollment_stdout = io.StringIO()
            enrollment_stderr = io.StringIO()
            enrollment_status = verify_cli.main(
                ["--kind", "enrollment", *common_args],
                stdin=io.BytesIO(enrollment_response),
                stdout=enrollment_stdout,
                stderr=enrollment_stderr,
            )
            self.assertEqual(enrollment_status, 0, enrollment_stderr.getvalue())
            self.assertEqual(enrollment_stderr.getvalue(), "")
            enrollment_verified = json.loads(enrollment_stdout.getvalue())
            self.assertTrue(enrollment_verified["authority_signature_valid"])
            self.assertFalse(enrollment_verified["independent_host_trust_established"])
            self.assertEqual(
                base64.b64decode(enrollment_verified["artifact_base64"], validate=True),
                expected_enrollment_artifact,
            )
            self.assertEqual(enrollment_verified["artifact_digest"], vector["enrollment_digest"])

            enrollment_path = Path(temporary) / "synthetic-enrollment.json"
            enrollment_path.write_bytes(expected_enrollment_artifact)
            decision_stdout = io.StringIO()
            decision_stderr = io.StringIO()
            decision_status = verify_cli.main(
                [
                    "--kind", "host-decision",
                    *common_args,
                    "--expected-enrollment-digest", vector["enrollment_digest"],
                    "--enrollment-artifact", str(enrollment_path),
                ],
                stdin=io.BytesIO(host_decision_response),
                stdout=decision_stdout,
                stderr=decision_stderr,
            )

        self.assertEqual(decision_status, 0, decision_stderr.getvalue())
        self.assertEqual(decision_stderr.getvalue(), "")
        decision_verified = json.loads(decision_stdout.getvalue())
        self.assertTrue(decision_verified["authority_signature_valid"])
        self.assertFalse(decision_verified["independent_host_trust_established"])
        self.assertEqual(
            decision_verified["trust"],
            "authority_claim_verified; deployment_and_host_separation_unestablished",
        )


if __name__ == "__main__":
    unittest.main()
