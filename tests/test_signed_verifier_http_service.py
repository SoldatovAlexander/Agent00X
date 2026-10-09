from __future__ import annotations

from datetime import datetime, timezone
import http.client
import io
import json
from pathlib import Path
import select
import shutil
import sys
import ssl
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app_contracts.credential_source import CredentialSource
from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.executor import (
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    verifier_snapshot_tree_digest,
)
from app_contracts.signed_verifier_http_service import (
    SignedVerifierHTTPService,
    create_loopback_http_server,
)
from app_contracts.signed_verifier_client import (
    SignedVerifierClient,
    SignedVerifierHTTPSTransport,
)
from app_contracts.signed_verifier_protocol import serialize_signed_verifier_invocation
from app_contracts.signed_verifier_service import VerifierProfile
from app_contracts.signer_key_source import Ed25519SeedCredentialSource
from app_contracts.verifier_attestation import verify_signed_verifier_response
from app_contracts.verifier_process import (
    VerifierProcessRequest,
    serialize_verifier_request,
)
from serve_signed_verifier_http import main as server_main


KEY_ID = "synthetic-http-service-key-v1"
SNAPSHOT_FILES = (("src.py", "100644", b"verified base"),)
TREE_DIGEST = verifier_snapshot_tree_digest(SNAPSHOT_FILES)
USER_AGENT = "Agent00X-SignedVerifier/1"


def profile() -> VerifierProfile:
    return VerifierProfile(
        repository_id="fixture/repository",
        base_commit="a" * 40,
        snapshot_tree_digest=TREE_DIGEST,
        snapshot_file_count=1,
        allowed_change_paths=("src.py",),
        test_command=("python3", "-m", "unittest"),
        test_timeout_seconds=30,
        verifier_image_id="sha256:" + "1" * 64,
        verifier_code_digest="sha256:" + "2" * 64,
        signer_key_id=KEY_ID,
    )


def prepared_input() -> VerifierInput:
    return VerifierInput(
        process_id="process-signed-verifier-http-001",
        repository_id="fixture/repository",
        base_commit="a" * 40,
        snapshot_tree_digest=TREE_DIGEST,
        declared_change_paths=("src.py",),
        verified_contents=(("src.py", "candidate contents"),),
        test_command=("python3", "-m", "unittest"),
        test_timeout_seconds=30,
        patch_digest=sha256_bytes(b"patch"),
        evidence_digest=sha256_bytes(b"evidence"),
        verification_digest=sha256_bytes(b"verification"),
        verified_contents_digest=sha256_digest((("src.py", "candidate contents"),)),
        evidence_origin="local_test",
        replay_result_digest=sha256_bytes(b"replay"),
        snapshot_files=SNAPSHOT_FILES,
        snapshot_claim_digest=sha256_bytes(b"synthetic snapshot claim"),
    )


def invocation_bytes(selected_profile_digest: str | None = None) -> bytes:
    request = serialize_verifier_request(
        VerifierProcessRequest.from_verifier_input(prepared_input())
    )
    return serialize_signed_verifier_invocation(
        request,
        invocation_nonce="a" * 64,
        verifier_profile_digest=(
            selected_profile_digest or profile().profile_digest
        ),
    )


def request_headers(body: bytes) -> tuple[tuple[str, str], ...]:
    return (
        ("Host", "verifier.example.com"),
        ("Accept", "application/json"),
        ("Content-Length", str(len(body))),
        ("Content-Type", "application/json"),
        ("User-Agent", USER_AGENT),
    )


class AcceptingVerifier:
    def __init__(self, selected_profile):
        self.profile = selected_profile
        self.calls = []

    def verify(self, prepared):
        self.calls.append(prepared)
        return VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id=self.profile.expected_verifier_id,
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
            evidence_origin="local_test",
        )


class CountingSeedSource(CredentialSource):
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return bytes(range(32)).hex()


class SignedVerifierHTTPServiceTests(unittest.TestCase):
    def make_service(self, *, signing_key=None):
        selected_profile = profile()
        verifier = AcceptingVerifier(selected_profile)
        key = signing_key or Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        service = SignedVerifierHTTPService(
            selected_profile,
            verifier,
            key,
            now_factory=lambda: datetime.now(timezone.utc),
        )
        return service, verifier, key

    def test_valid_request_is_signed_once_and_remains_profile_bound(self):
        service, verifier, signing_key = self.make_service()
        body = invocation_bytes()

        response = service.handle_request(
            "POST", "/v1/verify", request_headers(body), body
        )

        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        attestation = verify_signed_verifier_response(
            response.body,
            prepared_input(),
            expected_invocation_nonce="a" * 64,
            expected_verifier_profile_digest=profile().profile_digest,
            trusted_public_keys={KEY_ID: public_key},
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(dict(response.headers)["Content-Type"], "application/json")
        self.assertTrue(attestation.signature_valid)
        self.assertEqual(attestation.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertEqual(len(verifier.calls), 1)
        second = service.handle_request(
            "POST", "/v1/verify", request_headers(body), body
        )
        self.assertEqual(second.status, 429)
        self.assertEqual(len(verifier.calls), 1)

    def test_preflight_rejections_do_not_call_verifier_or_lazy_signer(self):
        invalid_cases = (
            ("GET", "/v1/verify", request_headers(b"x"), b"x", 405),
            ("POST", "/wrong", request_headers(b"x"), b"x", 404),
            (
                "POST",
                "/v1/verify",
                (("Host", "verifier.example.com"),),
                b"",
                415,
            ),
            (
                "POST",
                "/v1/verify",
                request_headers(b"x") + (("Content-Length", "1"),),
                b"x",
                400,
            ),
            (
                "POST",
                "/v1/verify",
                request_headers(b"x") + (("Transfer-Encoding", "chunked"),),
                b"x",
                400,
            ),
            (
                "POST",
                "/v1/verify",
                (
                    ("Host", "verifier.example.com"),
                    ("Accept", "application/json"),
                    ("Content-Length", str(len(b"x") + 1)),
                    ("Content-Type", "application/json"),
                    ("User-Agent", USER_AGENT),
                ),
                b"x",
                400,
            ),
        )
        for method, path, headers, body, expected_status in invalid_cases:
            with self.subTest(method=method, path=path, expected=expected_status):
                source = CountingSeedSource()
                service, verifier, _key = self.make_service(
                    signing_key=Ed25519SeedCredentialSource(source)
                )
                response = service.handle_request(method, path, headers, body)
                self.assertEqual(response.status, expected_status)
                self.assertEqual(source.calls, 0)
                self.assertEqual(verifier.calls, [])

    def test_rejects_oversized_length_before_read_or_execution(self):
        source = CountingSeedSource()
        service, verifier, _key = self.make_service(
            signing_key=Ed25519SeedCredentialSource(source)
        )
        headers = (
            ("Host", "verifier.example.com"),
            ("Accept", "application/json"),
            ("Content-Length", str(256_000_000)),
            ("Content-Type", "application/json"),
            ("User-Agent", USER_AGENT),
        )

        response = service.handle_request("POST", "/v1/verify", headers, b"")

        self.assertEqual(response.status, 413)
        self.assertEqual(source.calls, 0)
        self.assertEqual(verifier.calls, [])

    def test_rejects_malformed_or_wrong_profile_before_verifier_or_signer(self):
        for body in (b"{}", invocation_bytes("sha256:" + "f" * 64)):
            with self.subTest(body_size=len(body)):
                source = CountingSeedSource()
                service, verifier, _key = self.make_service(
                    signing_key=Ed25519SeedCredentialSource(source)
                )
                response = service.handle_request(
                    "POST", "/v1/verify", request_headers(body), body
                )
                self.assertEqual(response.status, 400)
                self.assertEqual(source.calls, 0)
                self.assertEqual(verifier.calls, [])

    def test_service_failure_is_fixed_and_does_not_expose_exception_text(self):
        source = CountingSeedSource()
        selected_profile = profile()
        verifier = AcceptingVerifier(selected_profile)

        def failing_handler(*_args, **_kwargs):
            raise RuntimeError("synthetic sensitive diagnostic")

        service = SignedVerifierHTTPService(
            selected_profile,
            verifier,
            Ed25519SeedCredentialSource(source),
            invocation_handler=failing_handler,
        )
        body = invocation_bytes()

        response = service.handle_request(
            "POST", "/v1/verify", request_headers(body), body
        )

        self.assertEqual(response.status, 500)
        self.assertEqual(response.body, b'{"error":"verifier_unavailable"}')
        self.assertNotIn(b"synthetic sensitive diagnostic", response.body)
        self.assertEqual(source.calls, 0)

    def test_real_loopback_http_handler_completes_signed_exchange(self):
        service, verifier, signing_key = self.make_service()
        server = create_loopback_http_server(service, 0, request_timeout_seconds=2)
        self.assertEqual(server.server_address[0], "127.0.0.1")
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=2
        )
        body = invocation_bytes()
        try:
            connection.request(
                "POST",
                "/v1/verify",
                body=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )
            response = connection.getresponse()
            response_body = response.read(65_536)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "application/json")
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            public_key = signing_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            attestation = verify_signed_verifier_response(
                response_body,
                prepared_input(),
                expected_invocation_nonce="a" * 64,
                expected_verifier_profile_digest=profile().profile_digest,
                trusted_public_keys={KEY_ID: public_key},
                now=datetime.now(timezone.utc),
            )
            self.assertTrue(attestation.signature_valid)
            self.assertEqual(len(verifier.calls), 1)
            self.assertEqual(server.last_response_status, 200)
        finally:
            connection.close()
            server.server_close()
            thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_signed_verifier_exchange_crosses_a_local_child_process_boundary(self):
        selected_profile = profile()
        profile_payload = {
            "repository_id": selected_profile.repository_id,
            "base_commit": selected_profile.base_commit,
            "snapshot_tree_digest": selected_profile.snapshot_tree_digest,
            "snapshot_file_count": selected_profile.snapshot_file_count,
            "allowed_change_paths": list(selected_profile.allowed_change_paths),
            "test_command": list(selected_profile.test_command),
            "test_timeout_seconds": selected_profile.test_timeout_seconds,
            "verifier_image_id": selected_profile.verifier_image_id,
            "verifier_code_digest": selected_profile.verifier_code_digest,
            "signer_key_id": selected_profile.signer_key_id,
        }
        child_code = """
import json
import sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app_contracts.executor import VerifierResult, VerifierVerdict
from app_contracts.signed_verifier_http_service import (
    SignedVerifierHTTPService, create_loopback_http_server,
)
from app_contracts.signed_verifier_service import VerifierProfile

data = json.loads(sys.argv[1])
selected_profile = VerifierProfile(
    repository_id=data["repository_id"],
    base_commit=data["base_commit"],
    snapshot_tree_digest=data["snapshot_tree_digest"],
    snapshot_file_count=data["snapshot_file_count"],
    allowed_change_paths=tuple(data["allowed_change_paths"]),
    test_command=tuple(data["test_command"]),
    test_timeout_seconds=data["test_timeout_seconds"],
    verifier_image_id=data["verifier_image_id"],
    verifier_code_digest=data["verifier_code_digest"],
    signer_key_id=data["signer_key_id"],
)

class AcceptingVerifier:
    def verify(self, prepared):
        return VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id=selected_profile.expected_verifier_id,
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
            evidence_origin="local_test",
        )

signing_key = Ed25519PrivateKey.generate()
service = SignedVerifierHTTPService(selected_profile, AcceptingVerifier(), signing_key)
server = create_loopback_http_server(service, 0, request_timeout_seconds=5)
public_key = signing_key.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw
)
print(json.dumps({"port": server.server_port, "public_key": public_key.hex()}), flush=True)
try:
    server.handle_request()
    print(json.dumps({"status": server.last_response_status}), flush=True)
finally:
    server.server_close()
"""

        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-c",
                child_code,
                json.dumps(profile_payload, sort_keys=True),
            ],
            cwd=ROOT,
            env={
                "PYTHONPATH": str(ROOT / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            readable, _writable, _exceptional = select.select(
                [process.stdout], [], [], 5
            )
            self.assertTrue(readable, "child verifier did not publish bounded startup metadata")
            startup = json.loads(process.stdout.readline())
            port = startup["port"]
            self.assertGreaterEqual(port, 1024)
            self.assertLessEqual(port, 65_535)
            public_key = bytes.fromhex(startup["public_key"])
            self.assertEqual(len(public_key), 32)

            class ChildProcessLoopbackTransport:
                def request(self, body):
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", port, timeout=3
                    )
                    try:
                        connection.request(
                            "POST",
                            "/v1/verify",
                            body=body,
                            headers={
                                "Accept": "application/json",
                                "Content-Type": "application/json",
                                "User-Agent": USER_AGENT,
                            },
                        )
                        response = connection.getresponse()
                        response_body = response.read(65_536)
                        if response.status != 200:
                            raise AssertionError("child verifier rejected request")
                        return response_body
                    finally:
                        connection.close()

            client = SignedVerifierClient(
                selected_profile,
                ChildProcessLoopbackTransport(),
                {KEY_ID: public_key},
            )
            attestation = client.verify(prepared_input())
            self.assertTrue(attestation.signature_valid)
            self.assertFalse(attestation.independent_host_trust_established)
            self.assertIn("independent_host_trust_not_established", client.limitations)

            remaining_stdout, remaining_stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, remaining_stderr)
            terminal_lines = remaining_stdout.splitlines()
            self.assertEqual(len(terminal_lines), 1)
            self.assertEqual(json.loads(terminal_lines[0]), {"status": 200})
            self.assertEqual(remaining_stderr, "")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

    def test_https_client_composes_with_loopback_service_and_keeps_audit_only(self):
        openssl = shutil.which("openssl")
        if openssl is None:
            self.skipTest("openssl is unavailable for ephemeral TLS fixture")

        with tempfile.TemporaryDirectory(prefix="signed-verifier-service-tls-") as directory:
            certificate = Path(directory) / "server-cert.pem"
            private_key_path = Path(directory) / "server-key.pem"
            subprocess.run(
                [
                    openssl,
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    str(private_key_path),
                    "-out",
                    str(certificate),
                    "-days",
                    "1",
                    "-nodes",
                    "-subj",
                    "/CN=verifier.example.com",
                    "-addext",
                    "subjectAltName=DNS:verifier.example.com",
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
            service, verifier, signing_key = self.make_service()
            server = create_loopback_http_server(
                service, 0, request_timeout_seconds=2
            )
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(certificate, private_key_path)
            server.socket = server_context.wrap_socket(
                server.socket, server_side=True
            )
            thread = threading.Thread(target=server.handle_request, daemon=True)
            thread.start()

            def connection_factory(host, *, port, timeout, context):
                self.assertEqual(host, "verifier.example.com")
                self.assertEqual(port, 443)
                context.load_verify_locations(cafile=certificate)
                connection = http.client.HTTPSConnection(
                    host,
                    port=server.server_port,
                    timeout=timeout,
                    context=context,
                )

                def connect_to_loopback(
                    _address, connect_timeout, source_address=None
                ):
                    self.assertIsNone(source_address)
                    return socket.create_connection(
                        ("127.0.0.1", server.server_port),
                        timeout=connect_timeout,
                    )

                connection._create_connection = connect_to_loopback
                return connection

            transport = SignedVerifierHTTPSTransport(
                "https://verifier.example.com/v1/verify",
                timeout_seconds=2,
                connection_factory=connection_factory,
            )
            public_key = signing_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            client = SignedVerifierClient(
                profile(), transport, {KEY_ID: public_key}
            )
            try:
                original_getaddrinfo = socket.getaddrinfo

                def loopback_only_getaddrinfo(host, *args, **kwargs):
                    if host != "127.0.0.1":
                        raise AssertionError("non-loopback DNS lookup attempted")
                    return original_getaddrinfo(host, *args, **kwargs)

                with patch(
                    "socket.getaddrinfo", side_effect=loopback_only_getaddrinfo
                ):
                    attestation = client.verify(prepared_input())
                self.assertTrue(attestation.signature_valid)
                self.assertFalse(attestation.independent_host_trust_established)
                self.assertIn("audit_only", client.limitations)
                self.assertEqual(len(verifier.calls), 1)
                self.assertEqual(server.last_response_status, 200)
            finally:
                server.server_close()
                thread.join(1)
            self.assertFalse(thread.is_alive())

    def test_cli_rejects_privileged_or_invalid_port_before_service_creation(self):
        service_calls = []
        output = io.StringIO()
        result = server_main(
            ["--port", "80"],
            service_factory=lambda: service_calls.append(True),
            stderr=output,
        )
        self.assertEqual(result, 2)
        self.assertEqual(service_calls, [])
        self.assertEqual(
            output.getvalue(),
            "signed verifier HTTP service: startup or request failed\n",
        )


if __name__ == "__main__":
    unittest.main()
