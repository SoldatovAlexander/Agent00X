from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
import sys
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
from app_contracts.signed_verifier_protocol import (
    MAX_SIGNED_VERIFIER_INVOCATION_BYTES,
    serialize_signed_verifier_invocation,
)
from app_contracts.signed_verifier_service import VerifierProfile
from app_contracts.signed_verifier_service_cli import main
from app_contracts.verifier_attestation import (
    MAX_ATTESTATION_BYTES,
    verify_signed_verifier_response,
)
from app_contracts.verifier_process import (
    VerifierProcessRequest,
    serialize_verifier_request,
)


NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)
SNAPSHOT_FILES = (("src.py", "100644", b"verified base"),)
TREE_DIGEST = verifier_snapshot_tree_digest(SNAPSHOT_FILES)
SEED = bytes(range(32)).hex()


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
        signer_key_id="synthetic-service-key-v1",
    )


def prepared_input() -> VerifierInput:
    return VerifierInput(
        process_id="process-signed-service-cli-001",
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
        snapshot_claim_digest=sha256_bytes(b"snapshot claim"),
    )


def invocation_bytes(selected_profile: VerifierProfile) -> bytes:
    request_bytes = serialize_verifier_request(
        VerifierProcessRequest.from_verifier_input(prepared_input())
    )
    return serialize_signed_verifier_invocation(
        request_bytes,
        invocation_nonce="b" * 64,
        verifier_profile_digest=selected_profile.profile_digest,
    )


class Source:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        self.events.append("source")
        return SEED


class PassingVerifier:
    def __init__(self, selected_profile: VerifierProfile, events: list[str]) -> None:
        self.profile = selected_profile
        self.events = events
        self.calls = 0

    def verify(self, prepared: VerifierInput) -> VerifierResult:
        self.calls += 1
        self.events.append("verify")
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


class TTYInput(BytesIO):
    def isatty(self) -> bool:
        return True


class SignedVerifierServiceCLITests(unittest.TestCase):
    def test_valid_one_shot_returns_only_signed_response_after_pass(self):
        selected_profile = profile()
        events: list[str] = []
        source = Source(events)
        verifier = PassingVerifier(selected_profile, events)
        output = BytesIO()
        errors = StringIO()

        with patch(
            "app_contracts.signed_verifier_service_cli.BRAINBOOSTER_VERIFIER_PROFILE",
            selected_profile,
        ):
            status = main(
                argv=[],
                stdin=BytesIO(invocation_bytes(selected_profile)),
                stdout=output,
                stderr=errors,
                verifier_factory=lambda: verifier,
                credential_source_factory=lambda: source,
                now_factory=lambda: NOW,
            )

        signing_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SEED))
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        attestation = verify_signed_verifier_response(
            output.getvalue(),
            prepared_input(),
            expected_invocation_nonce="b" * 64,
            expected_verifier_profile_digest=selected_profile.profile_digest,
            trusted_public_keys={selected_profile.signer_key_id: public_key},
            now=NOW,
        )
        self.assertEqual(status, 0)
        self.assertEqual(events, ["verify", "source"])
        self.assertEqual(source.calls, 1)
        self.assertTrue(attestation.signature_valid)
        self.assertNotIn(SEED.encode("ascii"), output.getvalue())
        self.assertEqual(errors.getvalue(), "")

    def test_invalid_request_is_redacted_and_does_not_resolve_signer(self):
        selected_profile = profile()
        events: list[str] = []
        source = Source(events)
        verifier = PassingVerifier(selected_profile, events)
        output = BytesIO()
        errors = StringIO()

        with patch(
            "app_contracts.signed_verifier_service_cli.BRAINBOOSTER_VERIFIER_PROFILE",
            selected_profile,
        ):
            status = main(
                argv=[],
                stdin=BytesIO(b"synthetic secret sentinel"),
                stdout=output,
                stderr=errors,
                verifier_factory=lambda: verifier,
                credential_source_factory=lambda: source,
                now_factory=lambda: NOW,
            )

        self.assertEqual(status, 2)
        self.assertEqual(output.getvalue(), b"")
        self.assertEqual(errors.getvalue(), _ERROR_MARKER_FOR_TEST)
        self.assertNotIn("sentinel", errors.getvalue())
        self.assertEqual(events, [])

    def test_oversized_or_tty_input_fails_before_factories(self):
        for input_stream in (
            BytesIO(b"x" * (MAX_SIGNED_VERIFIER_INVOCATION_BYTES + 1)),
            TTYInput(b"unused"),
        ):
            with self.subTest(input_type=type(input_stream).__name__):
                output = BytesIO()
                errors = StringIO()
                calls: list[str] = []
                status = main(
                    argv=[],
                    stdin=input_stream,
                    stdout=output,
                    stderr=errors,
                    verifier_factory=lambda: calls.append("verifier"),
                    credential_source_factory=lambda: calls.append("source"),
                )
                self.assertEqual(status, 2)
                self.assertEqual(output.getvalue(), b"")
                self.assertEqual(errors.getvalue(), _ERROR_MARKER_FOR_TEST)
                self.assertEqual(calls, [])

    def test_cli_rejects_all_arguments_without_invoking_dependencies(self):
        output = BytesIO()
        errors = StringIO()
        calls: list[str] = []
        status = main(
            argv=["--profile", "caller-selected"],
            stdin=BytesIO(invocation_bytes(profile())),
            stdout=output,
            stderr=errors,
            verifier_factory=lambda: calls.append("verifier"),
            credential_source_factory=lambda: calls.append("source"),
        )
        self.assertEqual(status, 2)
        self.assertEqual(output.getvalue(), b"")
        self.assertEqual(errors.getvalue(), _ERROR_MARKER_FOR_TEST)
        self.assertEqual(calls, [])

    def test_oversized_handler_response_is_never_written(self):
        selected_profile = profile()
        output = BytesIO()
        errors = StringIO()
        with patch(
            "app_contracts.signed_verifier_service_cli.BRAINBOOSTER_VERIFIER_PROFILE",
            selected_profile,
        ):
            status = main(
                argv=[],
                stdin=BytesIO(invocation_bytes(selected_profile)),
                stdout=output,
                stderr=errors,
                verifier_factory=lambda: object(),
                credential_source_factory=lambda: Source([]),
                handler=lambda *args, **kwargs: b"x" * (MAX_ATTESTATION_BYTES + 1),
                now_factory=lambda: NOW,
            )
        self.assertEqual(status, 2)
        self.assertEqual(output.getvalue(), b"")
        self.assertEqual(errors.getvalue(), _ERROR_MARKER_FOR_TEST)


_ERROR_MARKER_FOR_TEST = "signed verifier service: request or execution rejected\n"


if __name__ == "__main__":
    unittest.main()
