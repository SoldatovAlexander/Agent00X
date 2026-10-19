from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID

from app_contracts.signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE
from app_contracts.verifier_bootstrap_preflight import (
    VerifierBootstrapPreflightError,
    parse_pinned_public_verifier_bootstrap,
)
from inspect_pinned_verifier_bootstrap import main
import serve_ephemeral_signed_verifier_https as launcher


def _public_ca() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic verifier CA")])
    moment = datetime(2026, 10, 17, tzinfo=timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(123456)
        .not_valid_before(moment - timedelta(days=1))
        .not_valid_after(moment + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=None, decipher_only=None,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM)


class VerifierBootstrapPreflightTests(unittest.TestCase):
    def setUp(self):
        self.ca = _public_ca()
        signer = ed25519.Ed25519PrivateKey.from_private_bytes(b"3" * 32)
        self.public_key = signer.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.record = {
            "schema": "agent00x-ephemeral-verifier-bootstrap/v1",
            "status": "ready",
            "endpoint_url": "https://testdev.local/v1/verify",
            "listen_host": "127.0.0.1",
            "connect_port": 49152,
            "tls_ca_certificate_pem": self.ca.decode("ascii"),
            "tls_ca_sha256": "sha256:" + hashlib.sha256(self.ca).hexdigest(),
            "verifier_profile_digest": BRAINBOOSTER_VERIFIER_PROFILE.profile_digest,
            "verifier_key_id": BRAINBOOSTER_VERIFIER_PROFILE.signer_key_id,
            "verifier_public_key": self.public_key.hex(),
            "verifier_public_key_sha256": "sha256:" + hashlib.sha256(self.public_key).hexdigest(),
        }

    def _encoded(self, record=None, *, newline=True):
        raw = json.dumps(
            self.record if record is None else record,
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
        return raw + (b"\n" if newline else b"")

    def _parse(self, raw):
        return parse_pinned_public_verifier_bootstrap(
            raw, expected_sha256="sha256:" + hashlib.sha256(raw).hexdigest()
        )

    def test_exact_public_line_is_bound_without_trust_promotion(self):
        raw = self._encoded()
        result = self._parse(raw)
        self.assertEqual(result.connect_port, 49152)
        self.assertEqual(result.tls_ca_sha256, self.record["tls_ca_sha256"])
        self.assertEqual(
            result.verifier_public_key_sha256,
            self.record["verifier_public_key_sha256"],
        )
        self.assertFalse(hasattr(result, "ca_certificate_pem"))
        self.assertFalse(hasattr(result, "verifier_public_key"))
        self.assertFalse(result.trust_established)
        self.assertNotIn(self.ca.decode("ascii"), repr(result))
        self.assertNotIn(self.public_key.hex(), repr(result))

    def test_real_launcher_serializer_is_accepted_without_starting_service(self):
        signer = ed25519.Ed25519PrivateKey.from_private_bytes(b"4" * 32)
        raw = launcher._serialize_public_bootstrap(
            port=49153,
            ca_certificate_pem=self.ca,
            ca_sha256=hashlib.sha256(self.ca).hexdigest(),
            signing_key=signer,
        ) + b"\n"
        bound = self._parse(raw)
        self.assertEqual(bound.connect_port, 49153)
        self.assertFalse(bound.trust_established)

    def test_digest_mismatch_and_noncanonical_json_are_rejected(self):
        raw = self._encoded()
        with self.assertRaises(VerifierBootstrapPreflightError):
            parse_pinned_public_verifier_bootstrap(
                raw, expected_sha256="sha256:" + "0" * 64
            )
        for candidate in (b" " + raw, raw + b"\n", raw.replace(b'"status":"ready"', b'"status": "ready"')):
            with self.subTest(candidate=candidate[:20]):
                with self.assertRaises(VerifierBootstrapPreflightError):
                    self._parse(candidate)

    def test_duplicate_extra_and_wrong_fixed_fields_are_rejected(self):
        raw = self._encoded().replace(
            b'"status":"ready"', b'"status":"ready","status":"ready"'
        )
        with self.assertRaises(VerifierBootstrapPreflightError):
            self._parse(raw)
        for field, value in (
            ("extra", True),
            ("endpoint_url", "https://other.local/v1/verify"),
            ("listen_host", "0.0.0.0"),
            ("connect_port", True),
            ("verifier_profile_digest", "sha256:" + "0" * 64),
            ("verifier_key_id", "other-key"),
            ("status", "ready-but-unknown"),
        ):
            with self.subTest(field=field):
                changed = dict(self.record)
                changed[field] = value
                with self.assertRaises(VerifierBootstrapPreflightError):
                    self._parse(self._encoded(changed))

    def test_ca_and_signer_hash_or_encoding_mismatch_are_rejected(self):
        for field, value in (
            ("tls_ca_sha256", "sha256:" + "0" * 64),
            ("tls_ca_certificate_pem", "not a certificate"),
            ("verifier_public_key_sha256", "sha256:" + "0" * 64),
            ("verifier_public_key", "00"),
        ):
            with self.subTest(field=field):
                changed = dict(self.record)
                changed[field] = value
                with self.assertRaises(VerifierBootstrapPreflightError):
                    self._parse(self._encoded(changed))

    def test_cli_reports_only_bounded_public_digests_and_rejects_symlink(self):
        raw = self._encoded()
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory(prefix="verifier-bootstrap-preflight-") as root:
            source = Path(root) / "bootstrap.json"
            source.write_bytes(raw)
            output, errors = io.StringIO(), io.StringIO()
            code = main([str(source), "--expected-sha256", digest], stdout=output, stderr=errors)
            self.assertEqual(code, 0, errors.getvalue())
            self.assertIn("BOOTSTRAP_PIN_CONFIRMED|port=49152", output.getvalue())
            self.assertIn("|trust=unestablished\n", output.getvalue())
            self.assertNotIn(self.ca.decode("ascii"), output.getvalue())
            self.assertNotIn(self.public_key.hex(), output.getvalue())
            link = Path(root) / "link.json"
            link.symlink_to(source)
            output, errors = io.StringIO(), io.StringIO()
            code = main([str(link), "--expected-sha256", digest], stdout=output, stderr=errors)
            self.assertEqual(code, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(errors.getvalue(), "verifier bootstrap preflight: public input rejected\n")

    def test_cli_rejects_directory_and_oversize_input_without_echo(self):
        with tempfile.TemporaryDirectory(prefix="verifier-bootstrap-preflight-") as root:
            oversized = Path(root) / "oversized.json"
            oversized.write_bytes(b"private-material-must-not-echo" + b"x" * 8193)
            for source in (Path(root), oversized):
                with self.subTest(source=source.name):
                    output, errors = io.StringIO(), io.StringIO()
                    code = main(
                        [str(source), "--expected-sha256", "sha256:" + "0" * 64],
                        stdout=output, stderr=errors,
                    )
                    self.assertEqual(code, 2)
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(
                        errors.getvalue(),
                        "verifier bootstrap preflight: public input rejected\n",
                    )


if __name__ == "__main__":
    unittest.main()
