from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID

import prepare_pinned_verifier_enrollment_request as cli
from app_contracts.signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE
from app_contracts.verifier_image_pin import (
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.verifier_trust_enrollment import (
    assemble_signed_verifier_trust_enrollment,
    verify_verifier_trust_enrollment,
)
from serve_ephemeral_signed_verifier_https import _serialize_public_bootstrap


NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def _make_bootstrap() -> tuple[bytes, ed25519.Ed25519PrivateKey, bytes]:
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic CA")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(1001)
        .not_valid_before(NOW - timedelta(days=1))
        .not_valid_after(NOW + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = certificate.public_bytes(serialization.Encoding.PEM)
    verifier_key = ed25519.Ed25519PrivateKey.from_private_bytes(b"v" * 32)
    raw = _serialize_public_bootstrap(
        port=49152,
        ca_certificate_pem=ca_pem,
        ca_sha256=hashlib.sha256(ca_pem).hexdigest(),
        signing_key=verifier_key,
    ) + b"\n"
    verifier_public = verifier_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return raw, verifier_key, verifier_public


class PreparePinnedVerifierEnrollmentRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bootstrap, self.verifier_key, self.verifier_public = _make_bootstrap()
        self.bootstrap_digest = "sha256:" + hashlib.sha256(self.bootstrap).hexdigest()
        self.bindings = {
            "enrollment_id": "enrollment-test-01",
            "authority_key_id": "test-authority-01",
            "worker_host_id": "worker-host-01",
            "verifier_host_id": "verifier-host-02",
            "host_separation_evidence_digest": "sha256:" + "4" * 64,
            "issued_at": "2026-10-17T12:00:00Z",
            "expires_at": "2026-10-24T12:00:00Z",
        }

    def _input(self, bootstrap: bytes | None = None, bindings: dict | None = None) -> bytes:
        return (
            self.bootstrap if bootstrap is None else bootstrap
        ) + json.dumps(
            self.bindings if bindings is None else bindings,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii") + b"\n"

    def test_pinned_bootstrap_derives_exact_signed_enrollment_bindings(self) -> None:
        output = cli.prepare_pinned_enrollment_request(
            self._input(), expected_bootstrap_sha256=self.bootstrap_digest
        )
        request = json.loads(output)
        self.assertEqual(request["kind"], "enrollment")
        self.assertEqual(request["trust"], "unestablished")
        message = base64.b64decode(request["message_base64"], validate=True)
        authority = ed25519.Ed25519PrivateKey.from_private_bytes(b"a" * 32)
        record = assemble_signed_verifier_trust_enrollment(
            message, authority.sign(message)
        )
        verified = verify_verifier_trust_enrollment(
            record,
            trusted_authority_keys={
                "test-authority-01": authority.public_key().public_bytes(
                    serialization.Encoding.Raw,
                    serialization.PublicFormat.Raw,
                )
            },
            expected_endpoint_url="https://testdev.local/v1/verify",
            expected_verifier_id=(
                f"docker-image:{VERIFIER_RUNTIME_IMAGE_ID}"
                f"/code:{VERIFIER_RUNTIME_CODE_DIGEST}"
            ),
            expected_verifier_profile_digest=BRAINBOOSTER_VERIFIER_PROFILE.profile_digest,
            now=NOW,
        )
        self.assertEqual(verified.enrollment_id, "enrollment-test-01")
        self.assertEqual(verified.verifier_public_key, self.verifier_public)
        self.assertEqual(verified.worker_host_id, "worker-host-01")
        self.assertEqual(verified.verifier_host_id, "verifier-host-02")
        self.assertFalse(verified.independent_host_trust_established)

    def test_wrong_bootstrap_pin_fails_closed_without_partial_stdout(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        result = cli.main(
            ["--expected-bootstrap-sha256", "sha256:" + "0" * 64],
            stdin=io.BytesIO(self._input()),
            stdout=stdout,
            stderr=stderr,
        )
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "PINNED_ENROLLMENT_REQUEST_REJECTED\n")

    def test_operator_cli_subprocess_emits_one_untrusted_request_record(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "prepare_pinned_verifier_enrollment_request.py"),
                "--expected-bootstrap-sha256",
                self.bootstrap_digest,
            ],
            input=self._input(),
            capture_output=True,
            timeout=10,
            check=False,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, b"")
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        output = json.loads(completed.stdout)
        self.assertEqual(output["kind"], "enrollment")
        self.assertEqual(output["trust"], "unestablished")
        self.assertNotIn(b"BEGIN CERTIFICATE", completed.stdout)

    def test_invalid_bootstrap_and_duplicate_or_extra_bindings_are_rejected(self) -> None:
        invalid = self.bootstrap.replace(b'"status":"ready"', b'"status":"unknown"')
        invalid_digest = "sha256:" + hashlib.sha256(invalid).hexdigest()
        with self.assertRaisesRegex(ValueError, "request rejected"):
            cli.prepare_pinned_enrollment_request(
                self._input(bootstrap=invalid),
                expected_bootstrap_sha256=invalid_digest,
            )

        valid_bindings = json.dumps(
            self.bindings, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        duplicate = valid_bindings[:-1] + b',"authority_key_id":"second"}'
        for value in (
            self.bindings | {"signature": "0" * 128},
            self.bindings | {"authority_private_key": "forbidden"},
            self.bindings | {"extra": True},
        ):
            with self.subTest(extra=set(value) - set(self.bindings)):
                with self.assertRaisesRegex(ValueError, "request rejected"):
                    cli.prepare_pinned_enrollment_request(
                        self._input(bindings=value),
                        expected_bootstrap_sha256=self.bootstrap_digest,
                    )
        with self.assertRaisesRegex(ValueError, "request rejected"):
            cli.prepare_pinned_enrollment_request(
                self.bootstrap + duplicate + b"\n",
                expected_bootstrap_sha256=self.bootstrap_digest,
            )
        with self.assertRaisesRegex(ValueError, "request rejected"):
            cli.prepare_pinned_enrollment_request(
                self.bootstrap + b"{malformed}\n",
                expected_bootstrap_sha256=self.bootstrap_digest,
            )

    def test_cli_rejects_unterminated_or_trailing_records_and_oversize_input(self) -> None:
        base = self._input()
        invalid_inputs = (
            base[:-1],
            base + b"{}\n",
            base + b"x" * cli.MAX_INPUT_BYTES,
        )
        for raw in invalid_inputs:
            with self.subTest(size=len(raw)):
                stdout, stderr = io.StringIO(), io.StringIO()
                result = cli.main(
                    ["--expected-bootstrap-sha256", self.bootstrap_digest],
                    stdin=io.BytesIO(raw),
                    stdout=stdout,
                    stderr=stderr,
                )
                self.assertEqual(result, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(
                    stderr.getvalue(), "PINNED_ENROLLMENT_REQUEST_REJECTED\n"
                )


if __name__ == "__main__":
    unittest.main()
