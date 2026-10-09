from __future__ import annotations

import unittest

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.verifier_provenance import (
    VerifiedStageVerifierProvenance,
    VerifierProvenanceError,
    is_verified_stage_verifier_provenance,
    verify_staged_verifier_provenance,
)


class VerifierProvenanceTests(unittest.TestCase):
    def test_invalid_stage_and_authority_key_input_fail_with_fixed_error(self):
        with self.assertRaisesRegex(
            VerifierProvenanceError,
            "^verifier provenance: stage evidence verification failed$",
        ) as invalid_stage:
            verify_staged_verifier_provenance(
                object(), trusted_authority_keys={"synthetic": b"x" * 32}
            )
        self.assertNotIn("synthetic", str(invalid_stage.exception))

        with self.assertRaisesRegex(
            VerifierProvenanceError,
            "^verifier provenance: stage evidence verification failed$",
        ) as invalid_keys:
            verify_staged_verifier_provenance(
                object(), trusted_authority_keys={"secret-looking-key-id": b"bad"}
            )
        self.assertNotIn("secret-looking-key-id", str(invalid_keys.exception))

    def test_verified_provenance_marker_cannot_be_forged_by_constructor(self):
        fabricated = VerifiedStageVerifierProvenance(
            verifier_attestation_digest="sha256:" + "0" * 64,
            verifier_key_id="synthetic-verifier",
            verifier_profile_digest="sha256:" + "1" * 64,
            verifier_request_digest="sha256:" + "2" * 64,
            verifier_trust_enrollment_digest="sha256:" + "3" * 64,
            verifier_host_trust_decision_digest="sha256:" + "4" * 64,
            enrollment_authority_key_id="synthetic-authority",
            decision_authority_key_id="synthetic-authority",
            attestation_issued_at="2026-10-09T00:00:00Z",
            _verification_token=object(),
        )
        self.assertFalse(is_verified_stage_verifier_provenance(fabricated))
        self.assertFalse(is_verified_stage_verifier_provenance(object()))


if __name__ == "__main__":
    unittest.main()
