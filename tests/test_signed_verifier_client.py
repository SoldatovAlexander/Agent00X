from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import http.client
import http.server
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.executor import (
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    verifier_snapshot_tree_digest,
)
from app_contracts.signed_verifier_client import (
    SignedVerifierClient,
    SignedVerifierClientError,
    SignedVerifierHTTPSTransport,
    SignedVerifierHTTPSTransportError,
    SignedVerifierSubprocessTransport,
    SignedVerifierSubprocessTransportError,
)
from app_contracts.signed_verifier_service import (
    SignedVerifierServiceError,
    VerifierProfile,
    handle_signed_verifier_invocation,
)
from app_contracts.signed_verifier_protocol import (
    MAX_SIGNED_VERIFIER_INVOCATION_BYTES,
    parse_signed_verifier_invocation,
    serialize_signed_verifier_invocation,
)
from app_contracts.verifier_attestation import MAX_ATTESTATION_BYTES
from app_contracts.verifier_attestation import verifier_attestation_signing_bytes
from app_contracts.verifier_trust_enrollment import (
    build_signed_verifier_trust_enrollment,
)
from app_contracts.verifier_host_trust_decision import (
    build_signed_verifier_host_trust_decision,
)
from app_contracts.verifier_process import (
    VerifierProcessRequest,
    serialize_verifier_request,
)


KEY_ID = "synthetic-client-key-v1"
AUTHORITY_KEY_ID = "synthetic-control-plane-key-v1"
VERIFIER_ENDPOINT = "https://verifier.example.com/v1/verify"
WORKER_HOST_ID = "worker-host-exp681"
VERIFIER_HOST_ID = "verifier-host-exp681"
SNAPSHOT_FILES = (("src.py", "100644", b"verified base"),)
TREE_DIGEST = verifier_snapshot_tree_digest(SNAPSHOT_FILES)


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
        process_id="process-signed-verifier-client-001",
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


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _with_bad_signature(raw: bytes) -> bytes:
    envelope = json.loads(raw)
    envelope["signature"] = "0" * 128
    return canonical_json(envelope)


class AcceptingVerifier:
    def __init__(self, selected_profile: VerifierProfile) -> None:
        self.profile = selected_profile

    def verify(self, prepared: VerifierInput) -> VerifierResult:
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


class InProcessSignedTransport:
    def __init__(
        self,
        selected_profile: VerifierProfile,
        signing_key: Ed25519PrivateKey,
        *,
        mutate_response=None,
        nonce_override: str | None = None,
        endpoint_url: str = VERIFIER_ENDPOINT,
    ) -> None:
        self.profile = selected_profile
        self.signing_key = signing_key
        self.mutate_response = mutate_response
        self.nonce_override = nonce_override
        self.endpoint_url = endpoint_url
        self.calls: list[bytes] = []

    def request(self, invocation_bytes: bytes) -> bytes:
        self.calls.append(invocation_bytes)
        invocation = parse_signed_verifier_invocation(invocation_bytes)
        if self.nonce_override is not None:
            invocation_bytes = serialize_signed_verifier_invocation(
                invocation.request_bytes,
                invocation_nonce=self.nonce_override,
                verifier_profile_digest=invocation.verifier_profile_digest,
            )
        envelope = handle_signed_verifier_invocation(
            invocation_bytes,
            profile=self.profile,
            verifier=AcceptingVerifier(self.profile),
            signing_key=self.signing_key,
            issued_at=datetime.now(timezone.utc),
        )
        return self.mutate_response(envelope) if self.mutate_response else envelope


class SignedVerifierClientTests(unittest.TestCase):
    def setup_client(self, **transport_kwargs):
        selected_profile = profile()
        signing_key = Ed25519PrivateKey.generate()
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        transport = InProcessSignedTransport(
            selected_profile, signing_key, **transport_kwargs
        )
        client = SignedVerifierClient(
            selected_profile, transport, {KEY_ID: public_key}
        )
        return client, transport, public_key

    def enrolled_client(self, *, mutate=None, trust_decision=False):
        selected_profile = profile()
        authority_key = Ed25519PrivateKey.generate()
        verifier_key = Ed25519PrivateKey.generate()
        authority_public_key = authority_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        verifier_public_key = verifier_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        now = datetime.now(timezone.utc).replace(microsecond=0)
        fields = {
            "enrollment_id": "enroll-exp681-test",
            "authority_key_id": AUTHORITY_KEY_ID,
            "endpoint_url": VERIFIER_ENDPOINT,
            "verifier_id": selected_profile.expected_verifier_id,
            "verifier_profile_digest": selected_profile.profile_digest,
            "verifier_key_id": selected_profile.signer_key_id,
            "verifier_public_key": verifier_public_key,
            "worker_host_id": WORKER_HOST_ID,
            "verifier_host_id": VERIFIER_HOST_ID,
            "host_separation_evidence_digest": "sha256:" + "4" * 64,
            "signing_key": authority_key,
            "issued_at": now,
            "expires_at": now + timedelta(days=1),
        }
        if mutate is not None:
            mutate(fields)
        enrollment_bytes = build_signed_verifier_trust_enrollment(**fields)
        host_trust_decision_bytes = None
        if trust_decision:
            host_trust_decision_bytes = build_signed_verifier_host_trust_decision(
                decision_id="synthetic-host-review-exp681",
                authority_key_id=AUTHORITY_KEY_ID,
                enrollment_digest=sha256_bytes(enrollment_bytes),
                endpoint_url=VERIFIER_ENDPOINT,
                verifier_id=selected_profile.expected_verifier_id,
                verifier_profile_digest=selected_profile.profile_digest,
                verifier_key_id=selected_profile.signer_key_id,
                worker_host_id=WORKER_HOST_ID,
                verifier_host_id=VERIFIER_HOST_ID,
                host_separation_evidence_digest=fields[
                    "host_separation_evidence_digest"
                ],
                signing_key=authority_key,
                issued_at=now,
                expires_at=now + timedelta(hours=1),
            )
        service_transport = InProcessSignedTransport(selected_profile, verifier_key)

        class ServiceHTTPSConnection(FakeHTTPSConnection):
            def request(self, method, path, *, body, headers):
                super().request(method, path, body=body, headers=headers)
                self.response = FakeHTTPSResponse(
                    body=service_transport.request(body)
                )

        connection = ServiceHTTPSConnection()
        transport = SignedVerifierHTTPSTransport(
            VERIFIER_ENDPOINT,
            connection_factory=lambda host, *, port, timeout, context: connection.configure(
                host, port=port, timeout=timeout, context=context
            ),
        )
        client = SignedVerifierClient.from_trust_enrollment(
            selected_profile,
            transport,
            enrollment_bytes,
            trusted_authority_keys={AUTHORITY_KEY_ID: authority_public_key},
            expected_endpoint_url=VERIFIER_ENDPOINT,
            expected_worker_host_id=WORKER_HOST_ID,
            expected_verifier_host_id=VERIFIER_HOST_ID,
            host_trust_decision_bytes=host_trust_decision_bytes,
            now=now,
        )
        return client, transport, service_transport, enrollment_bytes, authority_key

    def test_exact_signed_response_is_validated_once_and_remains_audit_only(self):
        client, transport, _public_key = self.setup_client()
        prepared = prepared_input()

        attestation = client.verify(prepared)

        self.assertEqual(len(transport.calls), 1)
        invocation = parse_signed_verifier_invocation(transport.calls[0])
        self.assertEqual(invocation.verifier_profile_digest, profile().profile_digest)
        self.assertTrue(invocation.request_bytes)
        self.assertEqual(attestation.signed_request_bytes, invocation.request_bytes)
        self.assertEqual(
            hashlib.sha256(attestation.signed_request_bytes).hexdigest(),
            attestation.request_digest.removeprefix("sha256:"),
        )
        nonce = invocation.invocation_nonce
        self.assertEqual(len(nonce), 64)
        self.assertEqual(attestation.invocation_nonce, nonce)
        self.assertEqual(attestation.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertTrue(attestation.signature_valid)
        self.assertEqual(
            hashlib.sha256(attestation.signed_response_bytes).hexdigest(),
            attestation.attestation_digest.removeprefix("sha256:"),
        )
        self.assertIsNone(attestation.trust_enrollment_bytes)
        self.assertIsNone(attestation.host_trust_decision_bytes)
        self.assertNotIn(attestation.signed_response_bytes.decode(), repr(attestation))
        self.assertNotIn(attestation.signed_request_bytes.decode(), repr(attestation))
        self.assertFalse(attestation.independent_host_trust_established)
        self.assertIsNone(attestation.trust_enrollment_digest)
        self.assertIn("audit_only", client.limitations)
        self.assertIn("verifier_key_supplied_directly", client.limitations)
        self.assertIsNone(client.trust_enrollment_digest)

    def test_enrolled_client_uses_bound_key_and_remains_audit_only(self):
        client, _transport, service_transport, enrollment_bytes, _authority_key = (
            self.enrolled_client()
        )

        attestation = client.verify(prepared_input())

        self.assertEqual(len(service_transport.calls), 1)
        self.assertEqual(client.trust_enrollment_digest, sha256_bytes(enrollment_bytes))
        self.assertIn("out_of_band_enrollment_validated", client.limitations)
        self.assertIn("independent_host_trust_not_established", client.limitations)
        self.assertIn("audit_only", client.limitations)
        self.assertTrue(attestation.signature_valid)
        self.assertFalse(attestation.independent_host_trust_established)
        self.assertEqual(
            attestation.trust_enrollment_digest, sha256_bytes(enrollment_bytes)
        )
        self.assertEqual(attestation.trust_enrollment_bytes, enrollment_bytes)
        self.assertIsNone(attestation.host_trust_decision_bytes)
        self.assertIsNone(attestation.host_trust_decision_digest)

    def test_explicit_authority_decision_promotes_only_the_bound_host(self):
        client, _transport, service_transport, enrollment_bytes, _authority_key = (
            self.enrolled_client(trust_decision=True)
        )

        attestation = client.verify(prepared_input())

        self.assertEqual(len(service_transport.calls), 1)
        self.assertTrue(attestation.signature_valid)
        self.assertTrue(attestation.independent_host_trust_established)
        self.assertEqual(attestation.trust_enrollment_digest, sha256_bytes(enrollment_bytes))
        self.assertEqual(attestation.trust_enrollment_bytes, enrollment_bytes)
        self.assertEqual(
            sha256_bytes(attestation.host_trust_decision_bytes),
            attestation.host_trust_decision_digest,
        )
        self.assertTrue(
            attestation.host_trust_decision_digest.startswith("sha256:")
        )
        self.assertIn(
            "independent_host_trust_authority_decision_validated",
            client.limitations,
        )
        self.assertNotIn("audit_only", client.limitations)

    def test_unrelated_trust_decision_fails_configuration_before_transport(self):
        selected_profile = profile()
        signing_key = Ed25519PrivateKey.generate()
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        service_transport = InProcessSignedTransport(selected_profile, signing_key)

        class ServiceHTTPSConnection(FakeHTTPSConnection):
            def request(self, method, path, *, body, headers):
                super().request(method, path, body=body, headers=headers)
                self.response = FakeHTTPSResponse(body=service_transport.request(body))

        _client, _transport, _service, enrollment_bytes, authority_key = (
            self.enrolled_client()
        )
        authority_public_key = authority_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        invalid_decision = build_signed_verifier_host_trust_decision(
            decision_id="synthetic-host-review-wrong-evidence",
            authority_key_id=AUTHORITY_KEY_ID,
            enrollment_digest=sha256_bytes(enrollment_bytes),
            endpoint_url=VERIFIER_ENDPOINT,
            verifier_id=selected_profile.expected_verifier_id,
            verifier_profile_digest=selected_profile.profile_digest,
            verifier_key_id=selected_profile.signer_key_id,
            worker_host_id=WORKER_HOST_ID,
            verifier_host_id=VERIFIER_HOST_ID,
            host_separation_evidence_digest="sha256:" + "5" * 64,
            signing_key=authority_key,
            issued_at=datetime.now(timezone.utc).replace(microsecond=0),
            expires_at=datetime.now(timezone.utc).replace(microsecond=0)
            + timedelta(hours=1),
        )
        connection = ServiceHTTPSConnection()
        transport = SignedVerifierHTTPSTransport(
            VERIFIER_ENDPOINT,
            connection_factory=lambda host, *, port, timeout, context: connection.configure(
                host, port=port, timeout=timeout, context=context
            ),
        )
        with self.assertRaises(SignedVerifierClientError):
            SignedVerifierClient.from_trust_enrollment(
                selected_profile,
                transport,
                enrollment_bytes,
                trusted_authority_keys={AUTHORITY_KEY_ID: authority_public_key},
                expected_endpoint_url=VERIFIER_ENDPOINT,
                expected_worker_host_id=WORKER_HOST_ID,
                expected_verifier_host_id=VERIFIER_HOST_ID,
                host_trust_decision_bytes=invalid_decision,
            )
        self.assertEqual(service_transport.calls, [])

    def test_enrollment_configuration_mismatch_fails_before_transport(self):
        mutations = (
            lambda fields: fields.update(verifier_key_id="another-key-id"),
            lambda fields: fields.update(
                verifier_profile_digest="sha256:" + "f" * 64
            ),
            lambda fields: fields.update(
                endpoint_url="https://other.example.com/v1/verify"
            ),
            lambda fields: fields.update(verifier_id="another-verifier"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                with self.assertRaises(SignedVerifierClientError):
                    self.enrolled_client(mutate=mutate)

        _client, _transport, service_transport, enrollment_bytes, authority_key = (
            self.enrolled_client()
        )
        mismatched_transport = SignedVerifierHTTPSTransport(
            "https://different.example.com/v1/verify",
            connection_factory=lambda *_args, **_kwargs: self.fail(
                "mismatched endpoint must not dispatch"
            ),
        )
        with self.assertRaises(SignedVerifierClientError):
            SignedVerifierClient.from_trust_enrollment(
                profile(),
                mismatched_transport,
                enrollment_bytes,
                trusted_authority_keys={
                    AUTHORITY_KEY_ID: authority_key.public_key().public_bytes(
                        serialization.Encoding.Raw,
                        serialization.PublicFormat.Raw,
                    )
                },
                expected_endpoint_url=VERIFIER_ENDPOINT,
                expected_worker_host_id=WORKER_HOST_ID,
                expected_verifier_host_id=VERIFIER_HOST_ID,
            )
        self.assertEqual(service_transport.calls, [])

        _client, _https_transport, service_transport, enrollment_bytes, authority_key = (
            self.enrolled_client()
        )
        with self.assertRaises(SignedVerifierClientError):
            SignedVerifierClient.from_trust_enrollment(
                profile(),
                service_transport,
                enrollment_bytes,
                trusted_authority_keys={
                    AUTHORITY_KEY_ID: authority_key.public_key().public_bytes(
                        serialization.Encoding.Raw,
                        serialization.PublicFormat.Raw,
                    )
                },
                expected_endpoint_url=VERIFIER_ENDPOINT,
                expected_worker_host_id=WORKER_HOST_ID,
                expected_verifier_host_id=VERIFIER_HOST_ID,
            )
        self.assertEqual(service_transport.calls, [])

    def test_enrollment_rejects_wrong_hosts_authority_and_expiry_before_dispatch(self):
        for expected_worker, expected_verifier in (
            ("other-worker", VERIFIER_HOST_ID),
            (WORKER_HOST_ID, "other-verifier"),
        ):
            _client, transport, _service_transport, enrollment_bytes, authority_key = (
                self.enrolled_client()
            )
            with self.subTest(
                expected_worker=expected_worker,
                expected_verifier=expected_verifier,
            ):
                with self.assertRaises(SignedVerifierClientError):
                    SignedVerifierClient.from_trust_enrollment(
                        profile(),
                        transport,
                        enrollment_bytes,
                        trusted_authority_keys={
                            AUTHORITY_KEY_ID: authority_key.public_key().public_bytes(
                                serialization.Encoding.Raw,
                                serialization.PublicFormat.Raw,
                            )
                        },
                        expected_endpoint_url=VERIFIER_ENDPOINT,
                        expected_worker_host_id=expected_worker,
                        expected_verifier_host_id=expected_verifier,
                    )
            self.assertEqual(_service_transport.calls, [])

        _client, transport, service_transport, enrollment_bytes, _authority_key = (
            self.enrolled_client()
        )
        with self.assertRaises(SignedVerifierClientError):
            SignedVerifierClient.from_trust_enrollment(
                profile(),
                transport,
                enrollment_bytes,
                trusted_authority_keys={AUTHORITY_KEY_ID: bytes(32)},
                expected_endpoint_url=VERIFIER_ENDPOINT,
                expected_worker_host_id=WORKER_HOST_ID,
                expected_verifier_host_id=VERIFIER_HOST_ID,
            )
        self.assertEqual(service_transport.calls, [])

        def expired(fields):
            moment = fields["issued_at"]
            fields.update(
                issued_at=moment - timedelta(days=3),
                expires_at=moment - timedelta(days=2),
            )

        with self.assertRaises(SignedVerifierClientError):
            self.enrolled_client(mutate=expired)

    def test_bad_profile_request_is_rejected_before_transport(self):
        client, transport, _public_key = self.setup_client()
        changed = replace(prepared_input(), test_timeout_seconds=31)

        with self.assertRaises(SignedVerifierClientError):
            client.verify(changed)

        self.assertEqual(transport.calls, [])

    def test_service_handler_rejects_wrong_profile_before_verifier(self):
        selected_profile = profile()
        calls = []

        class CountingVerifier:
            def verify(self, prepared):
                calls.append(prepared)
                return AcceptingVerifier(selected_profile).verify(prepared)

        invocation = serialize_signed_verifier_invocation(
            serialize_verifier_request(
                VerifierProcessRequest.from_verifier_input(prepared_input())
            ),
            invocation_nonce="c" * 64,
            verifier_profile_digest="sha256:" + "f" * 64,
        )
        with self.assertRaises(SignedVerifierServiceError):
            handle_signed_verifier_invocation(
                invocation,
                profile=selected_profile,
                verifier=CountingVerifier(),
                signing_key=Ed25519PrivateKey.generate(),
                issued_at=datetime.now(timezone.utc),
            )
        self.assertEqual(calls, [])

    def test_wrong_nonce_and_tampered_signature_fail_without_retry(self):
        cases = (
            {"nonce_override": "b" * 64},
            {
                "mutate_response": lambda raw: _with_bad_signature(raw)
            },
        )
        for kwargs in cases:
            with self.subTest(kwargs=tuple(kwargs)):
                client, transport, _public_key = self.setup_client(**kwargs)
                with self.assertRaises(SignedVerifierClientError):
                    client.verify(prepared_input())
                self.assertEqual(len(transport.calls), 1)

    def test_validly_resigned_wrong_profile_digest_is_rejected(self):
        client, transport, _public_key = self.setup_client()

        def rewrite_profile(raw: bytes) -> bytes:
            envelope = json.loads(raw)
            envelope["verifier_profile_digest"] = "sha256:" + "f" * 64
            envelope.pop("signature")
            envelope["signature"] = transport.signing_key.sign(
                verifier_attestation_signing_bytes(envelope)
            ).hex()
            return canonical_json(envelope)

        transport.mutate_response = rewrite_profile
        with self.assertRaises(SignedVerifierClientError):
            client.verify(prepared_input())
        self.assertEqual(len(transport.calls), 1)

    def test_oversized_or_non_byte_response_is_rejected(self):
        for response in (b"x" * (MAX_ATTESTATION_BYTES + 1), bytearray(b"bad")):
            client, transport, _public_key = self.setup_client(
                mutate_response=lambda _raw, value=response: value
            )
            with self.assertRaises(SignedVerifierClientError):
                client.verify(prepared_input())
            self.assertEqual(len(transport.calls), 1)

    def test_transport_failure_is_sanitized_and_not_retried(self):
        class FailingTransport:
            def __init__(self) -> None:
                self.calls = 0

            def request(self, _invocation_bytes):
                self.calls += 1
                raise RuntimeError("do not disclose transport internals")

        failing = FailingTransport()
        client = SignedVerifierClient(
            profile(), failing, {KEY_ID: b"k" * 32}
        )
        with self.assertRaisesRegex(
            SignedVerifierClientError,
            "^signed verifier client: request or response rejected$",
        ) as caught:
            client.verify(prepared_input())
        self.assertNotIn("disclose", str(caught.exception))
        self.assertEqual(failing.calls, 1)

    def test_bad_trust_configuration_fails_at_construction(self):
        transport = InProcessSignedTransport(
            profile(), Ed25519PrivateKey.generate()
        )
        for keys in ({}, {"other-key": b"k" * 32}, {KEY_ID: b"short"}):
            with self.subTest(keys=tuple(keys)):
                with self.assertRaises(SignedVerifierClientError):
                    SignedVerifierClient(profile(), transport, keys)
        self.assertEqual(transport.calls, [])

    def test_caller_key_mapping_is_copied(self):
        selected_profile = profile()
        signing_key = Ed25519PrivateKey.generate()
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        keys = {KEY_ID: public_key}
        transport = InProcessSignedTransport(selected_profile, signing_key)
        client = SignedVerifierClient(selected_profile, transport, keys)
        keys[KEY_ID] = b"x" * 32

        self.assertTrue(client.verify(prepared_input()).signature_valid)

    def test_subprocess_transport_round_trips_exact_bytes_without_parent_environment(self):
        repository_path = str(ROOT)
        echo = (
            sys.executable,
            "-c",
            "import os,sys; "
            f"assert os.getcwd() != {repository_path!r}; "
            "assert os.environ.get('AGENT00X_TEST_CANARY') is None; "
            "sys.stdout.buffer.write(sys.stdin.buffer.read())",
        )
        transport = SignedVerifierSubprocessTransport(echo, timeout_seconds=2)
        invocation = b'{"schema":"synthetic-test-record"}'

        with patch.dict(os.environ, {"AGENT00X_TEST_CANARY": "not-for-child"}):
            self.assertEqual(transport.request(invocation), invocation)

    def test_signed_client_accepts_exact_synthetic_attestation_from_child_process(self):
        selected_profile = profile()
        synthetic_seed = bytes(range(32))
        signing_key = Ed25519PrivateKey.from_private_bytes(synthetic_seed)
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        source_root = str(ROOT / "src")
        service_script = f"""
import sys
sys.path.insert(0, {source_root!r})
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app_contracts.executor import VerifierResult, VerifierVerdict
from app_contracts.signed_verifier_service import VerifierProfile, handle_signed_verifier_invocation
profile = VerifierProfile(
    repository_id='fixture/repository',
    base_commit={'a' * 40!r},
    snapshot_tree_digest={TREE_DIGEST!r},
    snapshot_file_count=1,
    allowed_change_paths=('src.py',),
    test_command=('python3', '-m', 'unittest'),
    test_timeout_seconds=30,
    verifier_image_id={'sha256:' + '1' * 64!r},
    verifier_code_digest={'sha256:' + '2' * 64!r},
    signer_key_id={KEY_ID!r},
)
class PassingVerifier:
    def verify(self, prepared):
        return VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id=profile.expected_verifier_id,
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
            evidence_origin='local_test',
        )
response = handle_signed_verifier_invocation(
    sys.stdin.buffer.read(),
    profile=profile,
    verifier=PassingVerifier(),
    signing_key=Ed25519PrivateKey.from_private_bytes(bytes(range(32))),
    issued_at=datetime.now(timezone.utc),
)
sys.stdout.buffer.write(response)
"""
        transport = SignedVerifierSubprocessTransport(
            (sys.executable, "-c", service_script), timeout_seconds=5
        )
        client = SignedVerifierClient(
            selected_profile, transport, {KEY_ID: public_key}
        )

        attestation = client.verify(prepared_input())

        self.assertTrue(attestation.signature_valid)
        self.assertFalse(attestation.independent_host_trust_established)
        self.assertEqual(attestation.verifier_result.verdict, VerifierVerdict.PASS)

    def test_subprocess_transport_rejects_bad_config_and_input_before_spawn(self):
        invalid_commands = (
            [sys.executable, "-c", "pass"],
            ("python3", "-c", "pass"),
            (sys.executable, "-c", "pass", "\0"),
        )
        for command in invalid_commands:
            with self.subTest(command=repr(command)[:40]):
                with self.assertRaises(SignedVerifierSubprocessTransportError):
                    SignedVerifierSubprocessTransport(command)
        for timeout in (0, float("nan"), 301, True):
            with self.subTest(timeout=timeout):
                with self.assertRaises(SignedVerifierSubprocessTransportError):
                    SignedVerifierSubprocessTransport(
                        (sys.executable, "-c", "pass"),
                        timeout_seconds=timeout,
                    )

        transport = SignedVerifierSubprocessTransport(
            (sys.executable, "-c", "raise SystemExit('must not run')")
        )
        with patch(
            "app_contracts.signed_verifier_client.asyncio.create_subprocess_exec"
        ) as create_process:
            for invocation in (
                None,
                bytearray(b"record"),
                b"",
                b"x" * (MAX_SIGNED_VERIFIER_INVOCATION_BYTES + 1),
            ):
                with self.subTest(input_type=type(invocation).__name__):
                    with self.assertRaises(SignedVerifierSubprocessTransportError):
                        transport.request(invocation)
            create_process.assert_not_called()

    def test_subprocess_transport_bounds_stdout_and_sanitizes_nonzero_exit(self):
        oversized = SignedVerifierSubprocessTransport(
            (
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'x' * "
                f"{MAX_ATTESTATION_BYTES + 1})",
            ),
            timeout_seconds=5,
        )
        with self.assertRaisesRegex(
            SignedVerifierSubprocessTransportError,
            "^signed verifier transport: response limit exceeded$",
        ):
            oversized.request(b"record")

        failing = SignedVerifierSubprocessTransport(
            (
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('private diagnostic'); "
                "raise SystemExit(7)",
            ),
            timeout_seconds=2,
        )
        with self.assertRaisesRegex(
            SignedVerifierSubprocessTransportError,
            "^signed verifier transport: process request failed$",
        ) as caught:
            failing.request(b"record")
        self.assertNotIn("private diagnostic", str(caught.exception))

    def test_subprocess_transport_kills_child_after_timeout_without_retry(self):
        transport = SignedVerifierSubprocessTransport(
            (sys.executable, "-c", "import time; time.sleep(5)"),
            timeout_seconds=0.05,
        )
        with self.assertRaisesRegex(
            SignedVerifierSubprocessTransportError,
            "^signed verifier transport: process request failed$",
        ):
            transport.request(b"record")


class FakeHTTPSResponse:
    def __init__(
        self,
        status=200,
        content_type="application/json",
        body=b"signed",
        content_length=None,
    ):
        self.status = status
        self._content_type = content_type
        self._body = body
        self._content_length = content_length
        self.read_limit = None
        self.closed = False

    def getheader(self, name):
        if name == "Content-Type":
            return self._content_type
        if name == "Content-Length":
            return self._content_length
        return None

    def read(self, limit):
        self.read_limit = limit
        return self._body[:limit]

    def close(self):
        self.closed = True


class FakeHTTPSConnection:
    def __init__(self, response=None, failure=None, delay_seconds=0):
        self.response = response or FakeHTTPSResponse()
        self.failure = failure
        self.delay_seconds = delay_seconds
        self.request_data = None
        self.closed = False
        self.configuration = None

    def configure(self, host, *, port, timeout, context):
        self.configuration = (host, port, timeout, context)
        return self

    def request(self, method, path, *, body, headers):
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.failure is not None:
            raise self.failure
        self.request_data = (method, path, body, headers)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class SignedVerifierHTTPSTransportTests(unittest.TestCase):
    ENDPOINT = "https://verifier.example.com/v1/verify"

    def make_transport(self, connection, *, timeout_seconds=4.5):
        def factory(host, *, port, timeout, context):
            return connection.configure(
                host, port=port, timeout=timeout, context=context
            )

        return SignedVerifierHTTPSTransport(
            self.ENDPOINT,
            timeout_seconds=timeout_seconds,
            connection_factory=factory,
        )

    def test_one_shot_exchange_uses_fixed_request_and_verified_tls(self):
        response = FakeHTTPSResponse(body=b"attestation")
        connection = FakeHTTPSConnection(response)
        transport = self.make_transport(connection)

        self.assertEqual(transport.endpoint_url, self.ENDPOINT)

        self.assertEqual(transport.request(b"invocation"), b"attestation")

        host, port, timeout, context = connection.configuration
        self.assertEqual((host, port, timeout), ("verifier.example.com", 443, 4.5))
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.cert_store_stats()["x509_ca"], 1)
        method, path, body, headers = connection.request_data
        self.assertEqual((method, path, body), ("POST", "/v1/verify", b"invocation"))
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Content-Length"], str(len(b"invocation")))
        self.assertNotIn("Authorization", headers)
        self.assertEqual(response.read_limit, MAX_ATTESTATION_BYTES + 1)
        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)
        with self.assertRaisesRegex(
            SignedVerifierHTTPSTransportError,
            "^signed verifier HTTPS transport: attempt limit exceeded$",
        ):
            transport.request(b"invocation")

    def test_https_transport_composes_with_client_without_trust_promotion(self):
        selected_profile = profile()
        signing_key = Ed25519PrivateKey.generate()
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        service_transport = InProcessSignedTransport(
            selected_profile, signing_key
        )

        class ServiceHTTPSConnection(FakeHTTPSConnection):
            def request(self, method, path, *, body, headers):
                super().request(method, path, body=body, headers=headers)
                self.response = FakeHTTPSResponse(
                    body=service_transport.request(body)
                )

        connection = ServiceHTTPSConnection()
        transport = self.make_transport(connection)
        client = SignedVerifierClient(
            selected_profile, transport, {KEY_ID: public_key}
        )

        attestation = client.verify(prepared_input())

        self.assertTrue(attestation.signature_valid)
        self.assertFalse(attestation.independent_host_trust_established)
        self.assertIn("audit_only", client.limitations)
        self.assertEqual(len(service_transport.calls), 1)

    def test_rejects_endpoint_shapes_that_can_change_origin_or_route(self):
        for endpoint in (
            "http://verifier.example.com/v1/verify",
            "https://user@verifier.example.com/v1/verify",
            "https://verifier.example.com/v1/verify?",
            "https://verifier.example.com/v1/verify#",
            "https://verifier.example.com/v1/other",
            "https://verifier.example.com:444/v1/verify",
            "https://verifier.example.com:/v1/verify",
            "https://verifier.example.com:0443/v1/verify",
            "https://127.0.0.1/v1/verify",
            "https://localhost/v1/verify",
            "https://service.local/v1/verify",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(
                    SignedVerifierHTTPSTransportError,
                    "^signed verifier HTTPS transport: configuration rejected$",
                ):
                    SignedVerifierHTTPSTransport(endpoint)

    def test_rejects_invalid_timeouts_and_invocations_before_network(self):
        for timeout in (0, -1, float("nan"), float("inf"), 30.1, True):
            with self.subTest(timeout=timeout):
                with self.assertRaises(SignedVerifierHTTPSTransportError):
                    SignedVerifierHTTPSTransport(
                        self.ENDPOINT, timeout_seconds=timeout
                    )

        connection = FakeHTTPSConnection()
        transport = self.make_transport(connection)
        for invocation in (
            None,
            bytearray(b"invocation"),
            b"",
            b"x" * (MAX_SIGNED_VERIFIER_INVOCATION_BYTES + 1),
        ):
            with self.subTest(input_type=type(invocation).__name__):
                with self.assertRaises(SignedVerifierHTTPSTransportError):
                    transport.request(invocation)
        self.assertIsNone(connection.request_data)
        self.assertEqual(transport.request(b"valid"), b"signed")

    def test_rejects_status_media_type_empty_and_oversized_responses(self):
        failures = (
            FakeHTTPSResponse(status=302, body=b"redirect"),
            FakeHTTPSResponse(content_type="application/json; charset=utf-8"),
            FakeHTTPSResponse(body=b""),
            FakeHTTPSResponse(body=b"x" * (MAX_ATTESTATION_BYTES + 1)),
            FakeHTTPSResponse(content_length=str(MAX_ATTESTATION_BYTES + 1)),
            FakeHTTPSResponse(content_length="-1"),
        )
        for response in failures:
            with self.subTest(status=response.status, size=len(response._body)):
                connection = FakeHTTPSConnection(response)
                transport = self.make_transport(connection)
                with self.assertRaisesRegex(
                    SignedVerifierHTTPSTransportError,
                    "^signed verifier HTTPS transport: response rejected$",
                ):
                    transport.request(b"invocation")
                self.assertTrue(response.closed)
                self.assertTrue(connection.closed)

    def test_total_exchange_deadline_is_enforced_without_retry(self):
        connection = FakeHTTPSConnection(delay_seconds=0.15)
        transport = self.make_transport(connection, timeout_seconds=0.05)
        with self.assertRaisesRegex(
            SignedVerifierHTTPSTransportError,
            "^signed verifier HTTPS transport: request timed out$",
        ):
            transport.request(b"invocation")
        self.assertTrue(connection.closed)
        with self.assertRaises(SignedVerifierHTTPSTransportError):
            transport.request(b"invocation")

    def test_sanitizes_io_failures_and_does_not_retry(self):
        connection = FakeHTTPSConnection(
            failure=RuntimeError("private transport diagnostic")
        )
        transport = self.make_transport(connection)
        with self.assertRaisesRegex(
            SignedVerifierHTTPSTransportError,
            "^signed verifier HTTPS transport: request failed$",
        ) as caught:
            transport.request(b"invocation")
        self.assertNotIn("private transport diagnostic", str(caught.exception))
        self.assertTrue(connection.closed)
        with self.assertRaises(SignedVerifierHTTPSTransportError):
            transport.request(b"invocation")

    def test_dns_wait_is_bounded_and_late_result_is_not_used(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def slow_getaddrinfo(*args, **kwargs):
            started.set()
            try:
                release.wait(1)
                return [
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        6,
                        "",
                        ("192.0.2.10", 443),
                    )
                ]
            finally:
                finished.set()

        deadline = time.monotonic() + 0.05
        expired = threading.Event()
        with patch(
            "app_contracts.signed_verifier_client.socket.getaddrinfo",
            side_effect=slow_getaddrinfo,
        ):
            with self.assertRaisesRegex(
                SignedVerifierHTTPSTransportError,
                "^signed verifier HTTPS transport: request timed out$",
            ):
                from app_contracts.signed_verifier_client import (
                    _resolve_verifier_addresses,
                )

                _resolve_verifier_addresses(
                    "verifier.example.com", 443, deadline, expired
                )
            self.assertTrue(started.is_set())
            self.assertTrue(expired.is_set())
            release.set()
            self.assertTrue(finished.wait(1))


class SignedVerifierHTTPSTransportLoopbackTests(unittest.TestCase):
    ENDPOINT = "https://verifier.example.com/v1/verify"

    def create_certificate(self, openssl, directory, name, dns_name):
        certificate = Path(directory) / f"{name}-cert.pem"
        private_key = Path(directory) / f"{name}-key.pem"
        subprocess.run(
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(private_key),
                "-out",
                str(certificate),
                "-days",
                "1",
                "-nodes",
                "-subj",
                f"/CN={dns_name}",
                "-addext",
                f"subjectAltName=DNS:{dns_name}",
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        return certificate, private_key

    def start_server(self, certificate, private_key, *, stall=False):
        request_received = threading.Event()
        release_handler = threading.Event()
        handler_finished = threading.Event()
        requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", "-1"))
                    body = self.rfile.read(length)
                    requests.append((self.path, dict(self.headers), body))
                    request_received.set()
                    if stall:
                        release_handler.wait(2)
                    response_body = b'{"transport":"loopback"}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response_body)))
                    self.end_headers()
                    self.wfile.write(response_body)
                except OSError:
                    pass
                finally:
                    handler_finished.set()

            def log_message(self, _format, *args):
                return

        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(certificate, private_key)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        server.block_on_close = False
        server.socket = server_context.wrap_socket(server.socket, server_side=True)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        return (
            server,
            server_thread,
            request_received,
            release_handler,
            handler_finished,
            requests,
        )

    def make_transport(self, server, trusted_certificate, *, timeout_seconds=1):
        def factory(host, *, port, timeout, context):
            self.assertEqual(host, "verifier.example.com")
            self.assertEqual(port, 443)
            if trusted_certificate is not None:
                context.load_verify_locations(cafile=trusted_certificate)
            connection = http.client.HTTPSConnection(
                host,
                port=server.server_port,
                timeout=timeout,
                context=context,
            )

            def connect_to_loopback(_address, connect_timeout, source_address=None):
                self.assertIsNone(source_address)
                return socket.create_connection(
                    ("127.0.0.1", server.server_port),
                    timeout=connect_timeout,
                )

            connection._create_connection = connect_to_loopback
            return connection

        return SignedVerifierHTTPSTransport(
            self.ENDPOINT,
            timeout_seconds=timeout_seconds,
            connection_factory=factory,
        )

    def stop_server(self, state):
        server, thread, _received, release, _finished, _requests = state
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(1)

    def test_real_tls_http_exchange_and_certificate_failures_are_closed(self):
        openssl = shutil.which("openssl")
        if openssl is None:
            self.skipTest("openssl is unavailable for ephemeral TLS fixture")

        with tempfile.TemporaryDirectory(prefix="verifier-loopback-tls-") as directory:
            matching_certificate, matching_key = self.create_certificate(
                openssl, directory, "matching", "verifier.example.com"
            )
            wrong_certificate, wrong_key = self.create_certificate(
                openssl, directory, "wrong-host", "other.example.com"
            )

            success_server = self.start_server(matching_certificate, matching_key)
            try:
                server, _thread, received, _release, finished, requests = success_server
                transport = self.make_transport(server, matching_certificate)
                body = transport.request(b"canonical invocation")
                self.assertEqual(body, b'{"transport":"loopback"}')
                self.assertTrue(received.wait(1))
                self.assertTrue(finished.wait(1))
                self.assertEqual(len(requests), 1)
                path, headers, request_body = requests[0]
                self.assertEqual(path, "/v1/verify")
                self.assertEqual(request_body, b"canonical invocation")
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(headers["Accept"], "application/json")
                self.assertNotIn("Authorization", headers)
            finally:
                self.stop_server(success_server)

            wrong_host_server = self.start_server(wrong_certificate, wrong_key)
            try:
                server, _thread, received, _release, _finished, _requests = wrong_host_server
                transport = self.make_transport(server, wrong_certificate)
                with self.assertRaisesRegex(
                    SignedVerifierHTTPSTransportError,
                    "^signed verifier HTTPS transport: request failed$",
                ):
                    transport.request(b"canonical invocation")
                self.assertFalse(received.is_set())
            finally:
                self.stop_server(wrong_host_server)

            untrusted_server = self.start_server(matching_certificate, matching_key)
            try:
                server, _thread, received, _release, _finished, _requests = untrusted_server
                transport = self.make_transport(server, None)
                with self.assertRaisesRegex(
                    SignedVerifierHTTPSTransportError,
                    "^signed verifier HTTPS transport: request failed$",
                ):
                    transport.request(b"canonical invocation")
                self.assertFalse(received.is_set())
            finally:
                self.stop_server(untrusted_server)

    def test_real_loopback_stall_is_interrupted_by_total_deadline(self):
        openssl = shutil.which("openssl")
        if openssl is None:
            self.skipTest("openssl is unavailable for ephemeral TLS fixture")

        with tempfile.TemporaryDirectory(prefix="verifier-loopback-stall-") as directory:
            certificate, private_key = self.create_certificate(
                openssl, directory, "matching", "verifier.example.com"
            )
            state = self.start_server(certificate, private_key, stall=True)
            server, _thread, received, _release, _finished, _requests = state
            transport = self.make_transport(
                server, certificate, timeout_seconds=0.2
            )
            started = time.monotonic()
            try:
                with self.assertRaisesRegex(
                    SignedVerifierHTTPSTransportError,
                    "^signed verifier HTTPS transport: request timed out$",
                ):
                    transport.request(b"canonical invocation")
                elapsed = time.monotonic() - started
                self.assertTrue(received.is_set())
                self.assertLess(elapsed, 1.0)
                with self.assertRaises(SignedVerifierHTTPSTransportError):
                    transport.request(b"canonical invocation")
            finally:
                self.stop_server(state)


if __name__ == "__main__":
    unittest.main()
