from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import VerifierInput, VerifierResult, VerifierVerdict
from app_contracts.verifier_process import (
    VERIFIER_PROCESS_SCHEMA_VERSION,
    VerifierProcessError,
    VerifierProcessRequest,
    VerifierProcessResponse,
    serialize_verifier_request,
)


def valid_verifier_input() -> VerifierInput:
    return VerifierInput(
        process_id="process-local-001",
        repository_id="fixture-repository",
        base_commit="a" * 40,
        snapshot_tree_digest="sha256:" + "1" * 64,
        declared_change_paths=("calculator.py",),
        verified_contents=(("calculator.py", "verified source contents"),),
        test_command=("python3", "-m", "unittest"),
        test_timeout_seconds=30,
        patch_digest="sha256:" + "2" * 64,
        evidence_digest="sha256:" + "3" * 64,
        verification_digest="sha256:" + "4" * 64,
        verified_contents_digest="sha256:" + "5" * 64,
        replay_result_digest="sha256:" + "6" * 64,
    )


def valid_verifier_result() -> VerifierResult:
    prepared = valid_verifier_input()
    return VerifierResult(
        process_id=prepared.process_id,
        base_commit=prepared.base_commit,
        snapshot_tree_digest=prepared.snapshot_tree_digest,
        replay_result_digest=prepared.replay_result_digest,
        verifier_id="local-fixture-verifier",
        patch_digest=prepared.patch_digest,
        evidence_digest=prepared.evidence_digest,
        verification_digest=prepared.verification_digest,
        verified_contents_digest=prepared.verified_contents_digest,
        verdict=VerifierVerdict.PASS,
    )


class VerifierProcessRecordTests(unittest.TestCase):
    def test_request_record_is_versioned_and_has_only_verifier_input_fields(self):
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())

        self.assertEqual(request.schema_version, VERIFIER_PROCESS_SCHEMA_VERSION)
        payload = asdict(request)
        self.assertEqual(set(payload), {"schema_version", "verifier_input"})
        self.assertEqual(
            set(payload["verifier_input"]),
            {
                "process_id", "repository_id", "base_commit", "snapshot_tree_digest",
                "declared_change_paths", "verified_contents", "test_command",
                "test_timeout_seconds", "patch_digest", "evidence_digest",
                "verification_digest", "verified_contents_digest", "evidence_origin",
                "replay_result_digest",
            },
        )
        serialized = repr(payload)
        for forbidden_field in (
            "snapshot_path", "workspace", "environment", "stdout", "stderr",
            "credential", "capability",
        ):
            self.assertNotIn(forbidden_field, serialized)

    def test_response_record_contains_only_bounded_verifier_result_fields(self):
        response = VerifierProcessResponse.from_verifier_result(valid_verifier_result())

        self.assertEqual(response.schema_version, VERIFIER_PROCESS_SCHEMA_VERSION)
        payload = asdict(response)
        self.assertEqual(set(payload), {"schema_version", "verifier_result"})
        self.assertEqual(
            set(payload["verifier_result"]),
            {
                "process_id", "base_commit", "snapshot_tree_digest", "replay_result_digest",
                "verifier_id", "patch_digest", "evidence_digest", "verification_digest",
                "verified_contents_digest", "verdict", "blocker_codes", "evidence_origin",
            },
        )
        self.assertNotIn("verified source contents", repr(payload))

    def test_records_are_immutable_and_reject_invalid_types_or_versions(self):
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        response = VerifierProcessResponse.from_verifier_result(valid_verifier_result())

        with self.assertRaises(FrozenInstanceError):
            request.schema_version = 2  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            response.verifier_result = valid_verifier_result()  # type: ignore[misc]
        for bad_version in (True, 0, "1"):
            with self.subTest(record="request", version=bad_version):
                with self.assertRaisesRegex(
                    VerifierProcessError, "^verifier process: request version is invalid$"
                ):
                    VerifierProcessRequest(bad_version, valid_verifier_input())
            with self.subTest(record="response", version=bad_version):
                with self.assertRaisesRegex(
                    VerifierProcessError, "^verifier process: response version is invalid$"
                ):
                    VerifierProcessResponse(bad_version, valid_verifier_result())

        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request shape is invalid$"
        ):
            VerifierProcessRequest.from_verifier_input({"verified_contents": "forged"})
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: response shape is invalid$"
        ):
            VerifierProcessResponse.from_verifier_result({"verdict": "pass"})

    def test_request_serialization_is_canonical_utf8_and_does_not_mutate_input(self):
        request = VerifierProcessRequest.from_verifier_input(
            VerifierInput(
                **{
                    **valid_verifier_input().__dict__,
                    "verified_contents": (("calculator.py", "café"),),
                }
            )
        )
        original = request.verifier_input

        first = serialize_verifier_request(request)
        second = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(
                VerifierInput(**request.verifier_input.__dict__)
            )
        )

        self.assertIsInstance(first, bytes)
        self.assertEqual(first, second)
        self.assertIn("café".encode("utf-8"), first)
        self.assertNotIn(b"\\u00e9", first)
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(request.verifier_input, original)
        self.assertFalse(first.endswith(b"\n"))

    def test_request_serialization_rejects_non_json_values_without_echo(self):
        malformed_input = VerifierInput(
            **{
                **valid_verifier_input().__dict__,
                "test_command": ("python3", object()),
            }
        )
        with self.assertRaisesRegex(
            VerifierProcessError,
            "^verifier process: request serialization failed$",
        ) as raised:
            serialize_verifier_request(
                VerifierProcessRequest.from_verifier_input(malformed_input)
            )
        self.assertNotIn("object at", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
