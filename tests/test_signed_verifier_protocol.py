from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.executor import VerifierInput, verifier_snapshot_tree_digest
from app_contracts.signed_verifier_protocol import (
    MAX_SIGNED_VERIFIER_INVOCATION_BYTES,
    SIGNED_VERIFIER_INVOCATION_SCHEMA,
    SignedVerifierProtocolError,
    parse_signed_verifier_invocation,
    serialize_signed_verifier_invocation,
)
from app_contracts.verifier_process import (
    VerifierProcessRequest,
    serialize_verifier_request,
)


NONCE = "a" * 64
PROFILE_DIGEST = "sha256:" + "b" * 64
SNAPSHOT_FILES = (("src.py", "100644", b"base"),)
TREE_DIGEST = verifier_snapshot_tree_digest(SNAPSHOT_FILES)


def request_bytes() -> bytes:
    prepared = VerifierInput(
        process_id="process-wire-001",
        repository_id="fixture/repository",
        base_commit="c" * 40,
        snapshot_tree_digest=TREE_DIGEST,
        declared_change_paths=("src.py",),
        verified_contents=(("src.py", "candidate"),),
        test_command=("python3", "-m", "unittest"),
        test_timeout_seconds=30,
        patch_digest=sha256_bytes(b"patch"),
        evidence_digest=sha256_bytes(b"evidence"),
        verification_digest=sha256_bytes(b"verification"),
        verified_contents_digest=sha256_digest((("src.py", "candidate"),)),
        replay_result_digest=sha256_bytes(b"replay"),
        snapshot_files=SNAPSHOT_FILES,
        snapshot_claim_digest=sha256_bytes(b"claim"),
    )
    return serialize_verifier_request(VerifierProcessRequest.from_verifier_input(prepared))


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


class SignedVerifierProtocolTests(unittest.TestCase):
    def test_canonical_invocation_round_trips_exact_nested_request(self):
        nested = request_bytes()
        encoded = serialize_signed_verifier_invocation(
            nested,
            invocation_nonce=NONCE,
            verifier_profile_digest=PROFILE_DIGEST,
        )

        parsed = parse_signed_verifier_invocation(encoded)

        self.assertEqual(parsed.request_bytes, nested)
        self.assertEqual(parsed.invocation_nonce, NONCE)
        self.assertEqual(parsed.verifier_profile_digest, PROFILE_DIGEST)
        self.assertIn(SIGNED_VERIFIER_INVOCATION_SCHEMA.encode(), encoded)
        self.assertNotIn(nested, encoded)

    def test_duplicate_fields_noncanonical_outer_json_and_bad_base64_fail(self):
        nested = request_bytes()
        base64_request = base64.b64encode(nested).decode("ascii")
        duplicate = (
            b'{"invocation_nonce":"' + NONCE.encode()
            + b'","invocation_nonce":"' + NONCE.encode()
            + b'","request_base64":"' + base64_request.encode()
            + b'","schema":"signed-verifier-invocation/v1",'
            + b'"verifier_profile_digest":"' + PROFILE_DIGEST.encode() + b'"}'
        )
        valid = serialize_signed_verifier_invocation(
            nested, invocation_nonce=NONCE, verifier_profile_digest=PROFILE_DIGEST
        )
        outer_value = json.loads(valid)
        outer_value["request_base64"] += "="
        bad_base64 = canonical_json(outer_value)
        for raw in (duplicate, valid + b" ", bad_base64):
            with self.subTest(length=len(raw)):
                with self.assertRaisesRegex(
                    SignedVerifierProtocolError,
                    "^signed verifier protocol: invocation is invalid$",
                ):
                    parse_signed_verifier_invocation(raw)

    def test_malformed_nested_request_and_invocation_fields_are_rejected(self):
        with self.assertRaisesRegex(
            SignedVerifierProtocolError,
            "^signed verifier protocol: invocation is invalid$",
        ):
            serialize_signed_verifier_invocation(
                request_bytes() + b" ",
                invocation_nonce=NONCE,
                verifier_profile_digest=PROFILE_DIGEST,
            )
        for kwargs in (
            {"invocation_nonce": "bad"},
            {"verifier_profile_digest": "bad"},
        ):
            with self.subTest(kwargs=kwargs):
                arguments = {
                    "invocation_nonce": NONCE,
                    "verifier_profile_digest": PROFILE_DIGEST,
                }
                arguments.update(kwargs)
                with self.assertRaises(SignedVerifierProtocolError):
                    serialize_signed_verifier_invocation(request_bytes(), **arguments)

    def test_empty_nonbyte_and_over_limit_envelopes_are_rejected(self):
        for raw in (
            None,
            bytearray(b"{}"),
            b"",
            b"x" * (MAX_SIGNED_VERIFIER_INVOCATION_BYTES + 1),
        ):
            with self.subTest(type=type(raw).__name__):
                with self.assertRaisesRegex(
                    SignedVerifierProtocolError,
                    "^signed verifier protocol: invocation is invalid$",
                ):
                    parse_signed_verifier_invocation(raw)


if __name__ == "__main__":
    unittest.main()
