from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest import mock

from scripts import prepare_staged_verifier_request_exp2217 as prepared_stage
from scripts import run_signed_verifier_saved_stage_exp2253 as core
from scripts import run_signed_verifier_saved_stage_exp2962 as profile
from scripts.record_verifier_trust_signature_exp2196 import (
    ENROLLMENT_ARTIFACT_EXP2955,
    HOST_DECISION_ARTIFACT_EXP2956,
)


class RunSignedVerifierSavedStageExp2962Tests(unittest.TestCase):
    def setUp(self):
        self.core_original = {
            name: getattr(core, name)
            for name in (
                "CARD_ID", "GATE", "AUTHORIZATION_EXPIRES_AT", "STAGE_DATABASE",
                "ARTIFACT_DATABASE", "BOOTSTRAP_PATH", "ENROLLMENT_ARTIFACT",
                "HOST_DECISION_ARTIFACT", "OUTPUT_PATH", "ATTEMPT_PATH",
                "EVIDENCE_RECEIPT_PATH", "EXPECTED_REQUEST_DIGEST", "STAGED_CHANGE_DIGEST",
            )
        }
        self.prepared_original = {
            name: getattr(prepared_stage, name)
            for name in ("STAGE_DATABASE", "ARTIFACT_DATABASE", "STAGED_CHANGE_DIGEST")
        }

    def tearDown(self):
        for name, value in self.core_original.items():
            setattr(core, name, value)
        for name, value in self.prepared_original.items():
            setattr(prepared_stage, name, value)

    def test_wrapper_pins_exp2915_stage_and_successor_trust_artifacts(self):
        profile.configure()
        self.assertEqual(profile.CARD_ID, "EXP-2962")
        self.assertEqual(profile.GATE, "RUN EXP-2962 ONCE")
        self.assertEqual(profile.STAGE_DATABASE.name, "EXP-2915-stage.sqlite3")
        self.assertEqual(profile.ARTIFACT_DATABASE.name, "EXP-2915-artifacts.sqlite3")
        self.assertEqual(profile.STAGE_DIGEST, "sha256:ac1c28ebeb908d971baad950a83ce60ed795435cedfc796c198a590522189a1b")
        self.assertEqual(profile.ARTIFACT_DIGEST, "sha256:146abcc35d054952a8ef941b9c40599e2ae1322a36b56294ec1753fe66d40e48")
        self.assertEqual(profile.REQUEST_DIGEST, "sha256:86bdaebfcad6ed61bfaaa44fc69f5dcc6606d958f8c387b5bfeb8ff47d664613")
        self.assertEqual(core.ENROLLMENT_ARTIFACT, ENROLLMENT_ARTIFACT_EXP2955)
        self.assertEqual(core.HOST_DECISION_ARTIFACT, HOST_DECISION_ARTIFACT_EXP2956)
        self.assertEqual(core.BOOTSTRAP_PATH, profile.BOOTSTRAP_PATH)
        self.assertEqual(prepared_stage.STAGED_CHANGE_DIGEST, profile.STAGE_DIGEST)

    def test_main_rejects_any_result_not_bound_to_exact_request(self):
        with mock.patch.object(
            core,
            "replay_once",
            return_value={
                "stage_digest": profile.STAGE_DIGEST,
                "stage_artifact_digest": profile.ARTIFACT_DIGEST,
                "process_id": profile.PROCESS_ID,
                "request_digest": "sha256:" + "0" * 64,
            },
        ), mock.patch("builtins.print") as output:
            self.assertEqual(profile.main(), 2)
        output.assert_called_once_with("EXP2962_RESULT_PIN_MISMATCH", file=mock.ANY)

    def test_main_requires_bound_saved_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "receipt.json"
            with mock.patch.object(profile, "RECEIPT_PATH", receipt), mock.patch.object(
                core,
                "replay_once",
                return_value={
                    "stage_digest": profile.STAGE_DIGEST,
                    "stage_artifact_digest": profile.ARTIFACT_DIGEST,
                    "process_id": profile.PROCESS_ID,
                    "request_digest": profile.REQUEST_DIGEST,
                    "verdict": "pass",
                    "status": "verified",
                },
            ), mock.patch("builtins.print") as output:
                self.assertEqual(profile.main(), 2)
            output.assert_called_once_with("EXP2962_EVIDENCE_RECEIPT_MISSING", file=mock.ANY)

    def test_main_reports_success_only_when_exact_receipt_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "receipt.json"
            receipt.write_text("{}\n", encoding="ascii")
            with mock.patch.object(profile, "RECEIPT_PATH", receipt), mock.patch.object(
                core,
                "replay_once",
                return_value={
                    "stage_digest": profile.STAGE_DIGEST,
                    "stage_artifact_digest": profile.ARTIFACT_DIGEST,
                    "process_id": profile.PROCESS_ID,
                    "request_digest": profile.REQUEST_DIGEST,
                    "verdict": "pass",
                    "status": "verified",
                },
            ), mock.patch("builtins.print") as output:
                self.assertEqual(profile.main(), 0)
            output.assert_called_once_with(
                "EXP2962_REPLAY_RECEIPT_CONFIRMED|verdict=pass|signature=valid|host_decision=bound"
            )

    def test_main_surfaces_only_sanitized_core_failure(self):
        with mock.patch.object(
            core, "replay_once", side_effect=core.ReplayError("EXP2253_GATE_REJECTED")
        ), mock.patch("builtins.print") as output:
            self.assertEqual(profile.main(), 2)
        output.assert_called_once_with("EXP2962_GATE_REJECTED", file=mock.ANY)


if __name__ == "__main__":
    unittest.main()
