from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app_contracts.executor import VerifierInput, VerifierResult, VerifierVerdict, verifier_snapshot_tree_digest
from app_contracts.verifier_attestation import (
    VerifierAttestationError,
    new_verifier_invocation_nonce,
    verify_signed_verifier_response,
    verifier_attestation_signing_bytes,
)
from app_contracts.verifier_process import (
    VerifierProcessRequest,
    VerifierProcessResponse,
    digest_verifier_request,
)
from app_contracts.validator import ContractValidationError, validate


KEY_ID = "test-verifier-key-v1"
NONCE = "a" * 64
OTHER_NONCE = "b" * 64
PROFILE_DIGEST = "sha256:" + "c" * 64


def valid_input() -> VerifierInput:
    snapshot_files = (("calculator.py", "100644", b"base fixture"),)
    return VerifierInput(
        process_id="process-attestation-001",
        repository_id="fixture-repository",
        base_commit="d" * 40,
        snapshot_tree_digest=verifier_snapshot_tree_digest(snapshot_files),
        declared_change_paths=("calculator.py",),
        verified_contents=(("calculator.py", "verified source contents"),),
        test_command=("python3", "-m", "unittest"),
        test_timeout_seconds=30,
        patch_digest="sha256:" + "1" * 64,
        evidence_digest="sha256:" + "2" * 64,
        verification_digest="sha256:" + "3" * 64,
        verified_contents_digest="sha256:" + "4" * 64,
        replay_result_digest="sha256:" + "5" * 64,
        snapshot_files=snapshot_files,
    )


def fixture():
    prepared = valid_input()
    request = VerifierProcessRequest.from_verifier_input(prepared)
    result = VerifierResult(
        process_id=prepared.process_id,
        base_commit=prepared.base_commit,
        snapshot_tree_digest=prepared.snapshot_tree_digest,
        replay_result_digest=prepared.replay_result_digest,
        verifier_id="fixture-verifier",
        patch_digest=prepared.patch_digest,
        evidence_digest=prepared.evidence_digest,
        verification_digest=prepared.verification_digest,
        verified_contents_digest=prepared.verified_contents_digest,
        verdict=VerifierVerdict.PASS,
    )
    response = VerifierProcessResponse.from_verifier_result(
        result, digest_verifier_request(request)
    )
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    envelope = {
        "schema": "signed-verifier-response/v1",
        "key_id": KEY_ID,
        "invocation_nonce": NONCE,
        "request_digest": digest_verifier_request(request),
        "verifier_profile_digest": PROFILE_DIGEST,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "response": asdict(response),
    }
    signature = private_key.sign(verifier_attestation_signing_bytes(envelope))
    envelope["signature"] = signature.hex()
    return prepared, envelope, public_key, now


class VerifierAttestationTests(unittest.TestCase):
    def verify(self, envelope, prepared, public_key, now, **overrides):
        return verify_signed_verifier_response(
            json.dumps(
                envelope,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            prepared,
            expected_invocation_nonce=overrides.get("nonce", NONCE),
            expected_verifier_profile_digest=overrides.get(
                "profile_digest", PROFILE_DIGEST
            ),
            trusted_public_keys=overrides.get("keys", {KEY_ID: public_key}),
            now=overrides.get("now", now),
        )

    def test_valid_signature_binds_response_request_profile_and_nonce(self):
        prepared, envelope, public_key, now = fixture()
        result = self.verify(envelope, prepared, public_key, now)
        self.assertTrue(result.signature_valid)
        self.assertFalse(result.independent_host_trust_established)
        self.assertEqual(result.key_id, KEY_ID)
        self.assertEqual(result.invocation_nonce, NONCE)
        self.assertEqual(result.verifier_profile_digest, PROFILE_DIGEST)
        self.assertEqual(result.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertRegex(result.attestation_digest, r"^sha256:[0-9a-f]{64}$")

    def test_wrong_nonce_profile_request_or_key_fails_closed(self):
        prepared, envelope, public_key, now = fixture()
        cases = (
            {"nonce": OTHER_NONCE},
            {"profile_digest": "sha256:" + "e" * 64},
            {"keys": {"unknown-key": public_key}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(VerifierAttestationError):
                    self.verify(envelope, prepared, public_key, now, **overrides)

        changed = deepcopy(envelope)
        changed["request_digest"] = "sha256:" + "f" * 64
        with self.assertRaises(VerifierAttestationError):
            self.verify(changed, prepared, public_key, now)

        with self.assertRaises(VerifierAttestationError):
            self.verify(
                envelope,
                prepared,
                public_key,
                now,
                keys={f"fixture-{index}": public_key for index in range(33)},
            )

    def test_signature_detects_mutated_result_or_attestation_metadata(self):
        prepared, envelope, public_key, now = fixture()
        for field, value in (
            ("key_id", "different-key"),
            ("verifier_profile_digest", "sha256:" + "e" * 64),
            ("issued_at", (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")),
        ):
            changed = deepcopy(envelope)
            changed[field] = value
            with self.subTest(field=field):
                with self.assertRaises(VerifierAttestationError):
                    self.verify(changed, prepared, public_key, now)
        changed = deepcopy(envelope)
        changed["response"]["verifier_result"]["verdict"] = "fail"
        with self.assertRaises(VerifierAttestationError):
            self.verify(changed, prepared, public_key, now)
        changed = deepcopy(envelope)
        changed["signature"] = "0" * 128
        with self.assertRaises(VerifierAttestationError):
            self.verify(changed, prepared, public_key, now)

    def test_replayed_response_stale_and_future_attestations_are_rejected(self):
        prepared, envelope, public_key, now = fixture()
        with self.assertRaises(VerifierAttestationError):
            self.verify(envelope, prepared, public_key, now, nonce=OTHER_NONCE)

        stale = deepcopy(envelope)
        stale["issued_at"] = (now - timedelta(minutes=6)).isoformat().replace(
            "+00:00", "Z"
        )
        with self.assertRaises(VerifierAttestationError):
            self.verify(stale, prepared, public_key, now)

        future = deepcopy(envelope)
        future["issued_at"] = (now + timedelta(minutes=2)).isoformat().replace(
            "+00:00", "Z"
        )
        with self.assertRaises(VerifierAttestationError):
            self.verify(future, prepared, public_key, now)

    def test_malformed_envelope_and_untrusted_key_shapes_are_redacted(self):
        prepared, envelope, public_key, now = fixture()
        malformed = deepcopy(envelope)
        malformed["extra"] = "not allowed"
        for candidate, keys in (
            (malformed, {KEY_ID: public_key}),
            (envelope, {KEY_ID: b"short"}),
            ({**envelope, "signature": "0"}, {KEY_ID: public_key}),
        ):
            with self.subTest(candidate_keys=len(keys)):
                with self.assertRaises(VerifierAttestationError) as raised:
                    self.verify(candidate, prepared, public_key, now, keys=keys)
                self.assertNotIn(envelope["signature"], str(raised.exception))

    def test_signing_bytes_are_domain_separated_and_do_not_accept_unknown_fields(self):
        _prepared, envelope, _public_key, _now = fixture()
        unsigned = {key: value for key, value in envelope.items() if key != "signature"}
        payload = verifier_attestation_signing_bytes(unsigned)
        self.assertTrue(payload.startswith(b"agent00x-signed-verifier-response-ed25519-v1\0"))
        with self.assertRaises(VerifierAttestationError):
            verifier_attestation_signing_bytes({**unsigned, "unexpected": True})

    def test_parser_rejects_noncanonical_duplicate_and_oversized_envelopes(self):
        prepared, envelope, public_key, now = fixture()
        encoded = json.dumps(
            envelope, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.verify(envelope, prepared, public_key, now)
        for raw in (
            encoded + b" ",
            b'{"schema":"a","schema":"b"}',
            b"x" * 2_100_001,
        ):
            with self.subTest(size=len(raw)):
                with self.assertRaises(VerifierAttestationError):
                    verify_signed_verifier_response(
                        raw,
                        prepared,
                        expected_invocation_nonce=NONCE,
                        expected_verifier_profile_digest=PROFILE_DIGEST,
                        trusted_public_keys={KEY_ID: public_key},
                        now=now,
                    )

    def test_invocation_nonce_is_fresh_256_bit_hex(self):
        first = new_verifier_invocation_nonce()
        second = new_verifier_invocation_nonce()
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertRegex(second, r"^[0-9a-f]{64}$")
        self.assertNotEqual(first, second)

    def test_schema_accepts_valid_envelope_and_rejects_extra_or_bad_digest(self):
        _prepared, envelope, _public_key, _now = fixture()
        schema_path = ROOT / "schemas" / "signed-verifier-response.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        instance = json.loads(
            json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        )
        validate(instance, schema)

        with self.assertRaises(ContractValidationError):
            validate({**instance, "unexpected": True}, schema)
        invalid = deepcopy(instance)
        invalid["request_digest"] = "not-a-digest"
        with self.assertRaises(ContractValidationError):
            validate(invalid, schema)


if __name__ == "__main__":
    unittest.main()
