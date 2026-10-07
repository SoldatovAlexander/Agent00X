from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
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
from app_contracts.signed_verifier_service import (
    BRAINBOOSTER_VERIFIER_PROFILE,
    SignedVerifierServiceError,
    VerifierProfile,
    create_brainbooster_verifier_runner,
    run_signed_verifier_request,
)
from app_contracts.brainbooster_target_profile import (
    PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
)
from app_contracts.verifier_container import (
    DockerContainerVerifier,
    VerifierContainerConfig,
)
from app_contracts.verifier_process import VerifierProcessError
from app_contracts.verifier_attestation import verify_signed_verifier_response
from app_contracts.verifier_process import (
    VerifierProcessRequest,
    serialize_verifier_request,
)


NONCE = "a" * 64
PROFILE_DIGEST_A = "sha256:" + "1" * 64
PROFILE_DIGEST_B = "sha256:" + "2" * 64
KEY_ID = "synthetic-service-key-v1"
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
        verifier_image_id=PROFILE_DIGEST_A,
        verifier_code_digest=PROFILE_DIGEST_B,
        signer_key_id=KEY_ID,
    )


def prepared_input() -> VerifierInput:
    return VerifierInput(
        process_id="process-signed-verifier-service-001",
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


class SpyVerifier:
    def __init__(self, *, verifier_id: str | None = None) -> None:
        self.calls: list[VerifierInput] = []
        self.verifier_id = verifier_id

    def verify(self, prepared: VerifierInput) -> VerifierResult:
        self.calls.append(prepared)
        return VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id=self.verifier_id or profile().expected_verifier_id,
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
            evidence_origin="local_test",
        )


class SignedVerifierServiceTests(unittest.TestCase):
    def test_brainbooster_runner_factory_uses_only_pinned_configuration(self):
        with patch("app_contracts.verifier_container.subprocess.Popen") as popen:
            runner = create_brainbooster_verifier_runner("/usr/bin/docker")

        self.assertIs(type(runner), DockerContainerVerifier)
        self.assertIs(type(runner._config), VerifierContainerConfig)
        self.assertEqual(runner._config.docker_executable, "/usr/bin/docker")
        self.assertEqual(
            runner._config.runtime_image_id,
            BRAINBOOSTER_VERIFIER_PROFILE.verifier_image_id,
        )
        self.assertEqual(
            runner._config.verifier_code_digest,
            BRAINBOOSTER_VERIFIER_PROFILE.verifier_code_digest,
        )
        self.assertEqual(
            runner._config.timeout_seconds,
            PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
        )
        popen.assert_not_called()

    def test_brainbooster_runner_factory_rejects_relative_executable_without_process(self):
        with patch("app_contracts.verifier_container.subprocess.Popen") as popen:
            with self.assertRaises(VerifierProcessError):
                create_brainbooster_verifier_runner("docker")

        popen.assert_not_called()

    def test_brainbooster_profile_is_bound_to_the_selected_target_contract(self):
        self.assertEqual(
            BRAINBOOSTER_VERIFIER_PROFILE.repository_id,
            "SoldatovAlexander/brainbooster_full_v11",
        )
        self.assertEqual(
            BRAINBOOSTER_VERIFIER_PROFILE.base_commit,
            "2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e",
        )
        self.assertEqual(BRAINBOOSTER_VERIFIER_PROFILE.snapshot_file_count, 23)
        self.assertEqual(
            BRAINBOOSTER_VERIFIER_PROFILE.allowed_change_paths,
            ("backend/routes.py",),
        )

    def test_profile_digest_covers_runtime_and_test_contract(self):
        base = profile()
        self.assertNotEqual(
            base.profile_digest,
            replace(base, test_timeout_seconds=31).profile_digest,
        )
        self.assertNotEqual(
            base.profile_digest,
            replace(base, signer_key_id="rotated-key-v2").profile_digest,
        )
        self.assertNotEqual(
            base.profile_digest,
            replace(base, verifier_code_digest="sha256:" + "3" * 64).profile_digest,
        )

    def test_exact_profile_run_returns_verifiable_bound_signature(self):
        fixed_profile = profile()
        prepared = prepared_input()
        request = VerifierProcessRequest.from_verifier_input(prepared)
        request_bytes = serialize_verifier_request(request)
        verifier = SpyVerifier()
        signing_key = Ed25519PrivateKey.generate()
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        issued_at = datetime.now(timezone.utc)

        envelope_bytes = run_signed_verifier_request(
            request_bytes,
            invocation_nonce=NONCE,
            profile=fixed_profile,
            verifier=verifier,
            signing_key=signing_key,
            issued_at=issued_at,
        )
        attestation = verify_signed_verifier_response(
            envelope_bytes,
            prepared,
            expected_invocation_nonce=NONCE,
            expected_verifier_profile_digest=fixed_profile.profile_digest,
            trusted_public_keys={KEY_ID: public_key},
            now=issued_at,
        )
        self.assertEqual(len(verifier.calls), 1)
        self.assertEqual(verifier.calls[0], prepared)
        self.assertTrue(attestation.signature_valid)
        self.assertFalse(attestation.independent_host_trust_established)
        self.assertEqual(attestation.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertEqual(attestation.invocation_nonce, NONCE)

    def test_request_outside_profile_is_rejected_before_verifier_call(self):
        changes = (
            {"repository_id": "other/repository"},
            {"base_commit": "b" * 40},
            {
                "snapshot_files": (("src.py", "100644", b"other base"),),
                "snapshot_tree_digest": verifier_snapshot_tree_digest(
                    (("src.py", "100644", b"other base"),)
                ),
            },
            {"declared_change_paths": ("other.py",)},
            {"verified_contents": (("other.py", "candidate contents"),)},
            {"test_command": ("python3", "-c", "exit(0)")},
            {"test_timeout_seconds": 29},
        )
        for change in changes:
            with self.subTest(change=change):
                prepared = replace(prepared_input(), **change)
                request_bytes = serialize_verifier_request(
                    VerifierProcessRequest.from_verifier_input(prepared)
                )
                verifier = SpyVerifier()
                with self.assertRaises(SignedVerifierServiceError):
                    run_signed_verifier_request(
                        request_bytes,
                        invocation_nonce=NONCE,
                        profile=profile(),
                        verifier=verifier,
                        signing_key=Ed25519PrivateKey.generate(),
                        issued_at=datetime.now(timezone.utc),
                    )
                self.assertEqual(verifier.calls, [])

    def test_wrong_runtime_identity_is_not_signed(self):
        prepared = prepared_input()
        request_bytes = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(prepared)
        )
        verifier = SpyVerifier(verifier_id="caller-controlled-verifier-id")
        with self.assertRaises(SignedVerifierServiceError):
            run_signed_verifier_request(
                request_bytes,
                invocation_nonce=NONCE,
                profile=profile(),
                verifier=verifier,
                signing_key=Ed25519PrivateKey.generate(),
                issued_at=datetime.now(timezone.utc),
            )
        self.assertEqual(len(verifier.calls), 1)


if __name__ == "__main__":
    unittest.main()
