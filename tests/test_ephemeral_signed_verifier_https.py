from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import test_signed_verifier_http_service as service_fixtures
from app_contracts.signed_verifier_client import (
    SignedVerifierClient,
    SignedVerifierHTTPSTransport,
)
from app_contracts.signed_verifier_http_service import (
    SignedVerifierHTTPService,
    create_ephemeral_verifier_tls_context,
    create_loopback_https_server,
)
from app_contracts.signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE
import serve_ephemeral_signed_verifier_https as launcher
from serve_ephemeral_signed_verifier_https import main


class FakeServer:
    def __init__(self, port: int, tls_context: object):
        self.server_address = ("127.0.0.1", port)
        self.tls_enabled = True
        self.tls_context = tls_context
        self.timeout = None
        self.last_response_status = None
        self.handle_count = 0
        self.close_count = 0

    def handle_request(self):
        self.handle_count += 1
        self.last_response_status = 200

    def server_close(self):
        self.close_count += 1


class EphemeralVerifierBootstrapTests(unittest.TestCase):
    def test_bootstrap_emits_only_public_trust_data_and_handles_once(self):
        signing_key = Ed25519PrivateKey.from_private_bytes(b"s" * 32)
        ca_certificate = b"-----BEGIN CERTIFICATE-----\nsynthetic public CA\n-----END CERTIFICATE-----\n"
        ca_digest = hashlib.sha256(ca_certificate).hexdigest()
        verifier = service_fixtures.AcceptingVerifier(BRAINBOOSTER_VERIFIER_PROFILE)
        server_holder = []
        output, errors = io.StringIO(), io.StringIO()

        def make_server(service, port, context, *, request_timeout_seconds):
            self.assertIsInstance(service, SignedVerifierHTTPService)
            self.assertIs(service._signing_key, signing_key)
            self.assertEqual(request_timeout_seconds, 30.0)
            server = FakeServer(port, context)
            server_holder.append(server)
            return server

        code = main(
            ["--port", "8443"],
            verifier_factory=lambda: verifier,
            tls_identity_factory=lambda: (object(), ca_certificate, ca_digest),
            signer_factory=lambda: signing_key,
            server_factory=make_server,
            stdout=output,
            stderr=errors,
        )

        self.assertEqual(code, 0)
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        record = json.loads(output.getvalue())
        self.assertEqual(record["schema"], "agent00x-ephemeral-verifier-bootstrap/v1")
        self.assertEqual(record["status"], "ready")
        self.assertEqual(record["endpoint_url"], "https://testdev.local/v1/verify")
        self.assertEqual(record["listen_host"], "127.0.0.1")
        self.assertEqual(record["connect_port"], 8443)
        self.assertEqual(record["tls_ca_certificate_pem"], ca_certificate.decode())
        self.assertEqual(record["tls_ca_sha256"], "sha256:" + ca_digest)
        self.assertEqual(record["verifier_key_id"], BRAINBOOSTER_VERIFIER_PROFILE.signer_key_id)
        self.assertEqual(len(record["verifier_public_key"]), 64)
        self.assertNotIn("PRIVATE KEY", output.getvalue())
        self.assertNotIn((b"s" * 32).hex(), output.getvalue())
        self.assertEqual(len(server_holder), 1)
        self.assertEqual(server_holder[0].timeout, 900)
        self.assertEqual(server_holder[0].handle_count, 1)
        self.assertEqual(server_holder[0].close_count, 1)

    def test_invalid_port_stops_before_any_key_or_verifier_creation(self):
        for port in ("-1", "443", "65536"):
            with self.subTest(port=port):
                calls = []
                output, errors = io.StringIO(), io.StringIO()
                code = main(
                    ["--port", port],
                    verifier_factory=lambda: calls.append("verifier"),
                    tls_identity_factory=lambda: calls.append("tls"),
                    signer_factory=lambda: calls.append("signer"),
                    stdout=output,
                    stderr=errors,
                )
                self.assertEqual(code, 2)
                self.assertEqual(calls, [])
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(
                    errors.getvalue(),
                    "signed verifier HTTPS service: startup or request failed\n",
                )

    def test_zero_port_reports_actual_loopback_binding_in_bootstrap(self):
        signing_key = Ed25519PrivateKey.from_private_bytes(b"p" * 32)
        ca_certificate = b"synthetic public CA"
        ca_digest = hashlib.sha256(ca_certificate).hexdigest()
        verifier = service_fixtures.AcceptingVerifier(BRAINBOOSTER_VERIFIER_PROFILE)
        server_holder = []
        output, errors = io.StringIO(), io.StringIO()

        def make_server(service, port, context, *, request_timeout_seconds):
            self.assertIsInstance(service, SignedVerifierHTTPService)
            self.assertEqual(port, 0)
            self.assertEqual(request_timeout_seconds, 30.0)
            server = FakeServer(49_152, context)
            server_holder.append(server)
            return server

        code = main(
            ["--port", "0"],
            verifier_factory=lambda: verifier,
            tls_identity_factory=lambda: (object(), ca_certificate, ca_digest),
            signer_factory=lambda: signing_key,
            server_factory=make_server,
            stdout=output,
            stderr=errors,
        )

        self.assertEqual(code, 0)
        self.assertEqual(errors.getvalue(), "")
        record = json.loads(output.getvalue())
        self.assertEqual(record["listen_host"], "127.0.0.1")
        self.assertEqual(record["connect_port"], 49_152)
        self.assertEqual(server_holder[0].handle_count, 1)
        self.assertEqual(server_holder[0].close_count, 1)

    def test_wrong_server_binding_never_emits_bootstrap(self):
        signing_key = Ed25519PrivateKey.from_private_bytes(b"k" * 32)
        ca_certificate = b"synthetic public CA"
        ca_digest = hashlib.sha256(ca_certificate).hexdigest()
        server = FakeServer(8444, object())
        output, errors = io.StringIO(), io.StringIO()
        code = main(
            ["--port", "8443"],
            verifier_factory=lambda: service_fixtures.AcceptingVerifier(
                BRAINBOOSTER_VERIFIER_PROFILE
            ),
            tls_identity_factory=lambda: (object(), ca_certificate, ca_digest),
            signer_factory=lambda: signing_key,
            server_factory=lambda *_args, **_kwargs: server,
            stdout=output,
            stderr=errors,
        )
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(
            errors.getvalue(),
            "signed verifier HTTPS service: startup or request failed\n",
        )
        self.assertEqual(server.close_count, 1)


@unittest.skipUnless(
    sys.platform.startswith("linux")
    and callable(getattr(os, "memfd_create", None))
    and os.path.isdir("/proc/self/fd"),
    "ephemeral TLS key loading requires Linux sealed memfd support",
)
class LinuxEphemeralVerifierTLSIntegrationTests(unittest.TestCase):
    def test_launcher_serves_one_pinned_loopback_exchange_with_ephemeral_identity(self):
        selected_profile = service_fixtures.profile()
        verifier = service_fixtures.AcceptingVerifier(selected_profile)
        server_state = {}
        client_state = {}
        client_threads = []

        def make_server(service, port, tls_context, *, request_timeout_seconds):
            server = create_loopback_https_server(
                service,
                port,
                tls_context,
                request_timeout_seconds=request_timeout_seconds,
            )
            server_state["server"] = server
            server_state["handle_calls"] = 0
            server_state["close_calls"] = 0
            original_handle = server.handle_request
            original_close = server.server_close

            def handle_once():
                server_state["handle_calls"] += 1
                return original_handle()

            def close_once():
                server_state["close_calls"] += 1
                return original_close()

            server.handle_request = handle_once
            server.server_close = close_once
            return server

        with tempfile.TemporaryDirectory(
            prefix="ephemeral-launcher-public-ca-"
        ) as temporary:
            ca_path = Path(temporary) / "public-ca.pem"

            def request_from_bootstrap(bootstrap: dict) -> None:
                try:
                    ca_pem = bootstrap["tls_ca_certificate_pem"].encode("ascii")
                    ca_path.write_bytes(ca_pem)
                    ca_digest = hashlib.sha256(ca_pem).hexdigest()
                    self.assertEqual(bootstrap["tls_ca_sha256"], "sha256:" + ca_digest)
                    public_key = bytes.fromhex(bootstrap["verifier_public_key"])
                    self.assertEqual(
                        bootstrap["verifier_public_key_sha256"],
                        "sha256:" + hashlib.sha256(public_key).hexdigest(),
                    )
                    transport = SignedVerifierHTTPSTransport(
                        bootstrap["endpoint_url"],
                        timeout_seconds=2,
                        custom_ca_bundle_path=str(ca_path),
                        custom_ca_bundle_sha256=ca_digest,
                        connect_address=bootstrap["listen_host"],
                        connect_port=bootstrap["connect_port"],
                    )
                    client = SignedVerifierClient(
                        selected_profile,
                        transport,
                        {selected_profile.signer_key_id: public_key},
                    )
                    client_state["attestation"] = client.verify(
                        service_fixtures.prepared_input()
                    )
                except Exception as exc:
                    client_state["error"] = exc

            class BootstrapOutput(io.StringIO):
                def write(self, value: str) -> int:
                    written = super().write(value)
                    if value.endswith("\n"):
                        bootstrap = json.loads(value)
                        thread = threading.Thread(
                            target=request_from_bootstrap,
                            args=(bootstrap,),
                            daemon=True,
                        )
                        client_threads.append(thread)
                        thread.start()
                    return written

            output, errors = BootstrapOutput(), io.StringIO()
            with (
                patch.object(launcher, "_MAX_IDLE_WAIT_SECONDS", 3),
                patch.object(launcher, "BRAINBOOSTER_VERIFIER_PROFILE", selected_profile),
            ):
                code = main(
                    ["--port", "0"],
                    verifier_factory=lambda: verifier,
                    server_factory=make_server,
                    stdout=output,
                    stderr=errors,
                )
            for thread in client_threads:
                thread.join(3)

            self.assertEqual(code, 0, errors.getvalue())
            self.assertEqual(errors.getvalue(), "")
            self.assertEqual(len(client_threads), 1)
            self.assertFalse(client_threads[0].is_alive())
            self.assertNotIn("error", client_state, repr(client_state.get("error")))
            attestation = client_state["attestation"]
            self.assertTrue(attestation.signature_valid)
            self.assertFalse(attestation.independent_host_trust_established)
            self.assertEqual(len(verifier.calls), 1)
            self.assertEqual(server_state["server"].last_response_status, 200)
            self.assertEqual(server_state["handle_calls"], 1)
            self.assertEqual(server_state["close_calls"], 1)
            self.assertEqual(len(output.getvalue().splitlines()), 1)
            self.assertNotIn("PRIVATE KEY", output.getvalue())
            self.assertEqual([path.name for path in Path(temporary).iterdir()], ["public-ca.pem"])

    def test_memfd_identity_completes_one_pinned_loopback_signed_exchange(self):
        tls_context, ca_pem, ca_digest = create_ephemeral_verifier_tls_context()
        self.assertEqual(hashlib.sha256(ca_pem).hexdigest(), ca_digest)

        selected_profile = service_fixtures.profile()
        verifier = service_fixtures.AcceptingVerifier(selected_profile)
        signer = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        service = SignedVerifierHTTPService(selected_profile, verifier, signer)
        server = create_loopback_https_server(service, 0, tls_context, request_timeout_seconds=5)
        server.timeout = 5
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        with tempfile.TemporaryDirectory(prefix="ephemeral-verifier-public-ca-") as root:
            ca_path = Path(root) / "public-ca.pem"
            ca_path.write_bytes(ca_pem)
            transport = SignedVerifierHTTPSTransport(
                "https://testdev.local/v1/verify",
                timeout_seconds=4,
                custom_ca_bundle_path=str(ca_path),
                custom_ca_bundle_sha256=ca_digest,
                connect_address="127.0.0.1",
                connect_port=server.server_port,
            )
            public_key = signer.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
            client = SignedVerifierClient(
                selected_profile,
                transport,
                {selected_profile.signer_key_id: public_key},
            )
            try:
                attestation = client.verify(service_fixtures.prepared_input())
                self.assertTrue(attestation.signature_valid)
                self.assertFalse(attestation.independent_host_trust_established)
                self.assertEqual(server.last_response_status, 200)
                self.assertEqual(len(verifier.calls), 1)
                self.assertEqual(transport.endpoint_url, "https://testdev.local/v1/verify")
                self.assertEqual(transport.connect_address, "127.0.0.1")
                self.assertEqual(transport.connect_port, server.server_port)
            finally:
                server.server_close()
                thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertEqual([path.name for path in Path(root).iterdir()], ["public-ca.pem"])


if __name__ == "__main__":
    unittest.main()
