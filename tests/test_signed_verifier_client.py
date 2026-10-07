from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

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
)
from app_contracts.signed_verifier_service import (
    SignedVerifierServiceError,
    VerifierProfile,
    handle_signed_verifier_invocation,
)
from app_contracts.signed_verifier_protocol import (
    parse_signed_verifier_invocation,
    serialize_signed_verifier_invocation,
)
from app_contracts.verifier_attestation import MAX_ATTESTATION_BYTES
from app_contracts.verifier_attestation import verifier_attestation_signing_bytes
from app_contracts.verifier_process import (
    VerifierProcessRequest,
    serialize_verifier_request,
)


KEY_ID = "synthetic-client-key-v1"
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
    ) -> None:
        self.profile = selected_profile
        self.signing_key = signing_key
        self.mutate_response = mutate_response
        self.nonce_override = nonce_override
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

    def test_exact_signed_response_is_validated_once_and_remains_audit_only(self):
        client, transport, _public_key = self.setup_client()
        prepared = prepared_input()

        attestation = client.verify(prepared)

        self.assertEqual(len(transport.calls), 1)
        invocation = parse_signed_verifier_invocation(transport.calls[0])
        self.assertEqual(invocation.verifier_profile_digest, profile().profile_digest)
        self.assertTrue(invocation.request_bytes)
        nonce = invocation.invocation_nonce
        self.assertEqual(len(nonce), 64)
        self.assertEqual(attestation.invocation_nonce, nonce)
        self.assertEqual(attestation.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertTrue(attestation.signature_valid)
        self.assertFalse(attestation.independent_host_trust_established)
        self.assertIn("audit_only", client.limitations)

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


if __name__ == "__main__":
    unittest.main()
