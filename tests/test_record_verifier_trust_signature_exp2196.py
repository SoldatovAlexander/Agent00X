from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import record_verifier_trust_signature_exp2196 as recorder


class RecordVerifierTrustSignatureExp2196Tests(unittest.TestCase):
    def test_exact_card_kinds_artifact_ids_and_paths(self):
        self.assertEqual(
            recorder._SPECS,
            {
                "EXP-2196": (
                    "enrollment",
                    "agent00x-enrollment-exp2196",
                    recorder.EVIDENCE_DIR / "verifier-enrollment-exp2196.json",
                    recorder.EVIDENCE_DIR / "verifier-enrollment-exp2196-artifact.json",
                ),
                "EXP-2197": (
                    "host-decision",
                    "agent00x-host-decision-exp2197",
                    recorder.EVIDENCE_DIR / "verifier-host-decision-exp2197.json",
                    recorder.EVIDENCE_DIR / "verifier-host-decision-exp2197-artifact.json",
                ),
                "EXP-2258": (
                    "enrollment",
                    "agent00x-enrollment-exp2258",
                    recorder.ENROLLMENT_REPORT_EXP2258,
                    recorder.ENROLLMENT_ARTIFACT_EXP2258,
                ),
                "EXP-2259": (
                    "host-decision",
                    "agent00x-host-decision-exp2259",
                    recorder.HOST_DECISION_REPORT_EXP2259,
                    recorder.HOST_DECISION_ARTIFACT_EXP2259,
                ),
                "EXP-2271": (
                    "enrollment",
                    "agent00x-enrollment-exp2271",
                    recorder.ENROLLMENT_REPORT_EXP2271,
                    recorder.ENROLLMENT_ARTIFACT_EXP2271,
                ),
                "EXP-2272": (
                    "host-decision",
                    "agent00x-host-decision-exp2272",
                    recorder.HOST_DECISION_REPORT_EXP2272,
                    recorder.HOST_DECISION_ARTIFACT_EXP2272,
                ),
                "EXP-2381": (
                    "enrollment",
                    "agent00x-enrollment-exp2271",
                    recorder.ENROLLMENT_REPORT_EXP2381,
                    recorder.ENROLLMENT_ARTIFACT_EXP2381,
                ),
                "EXP-2382": (
                    "host-decision",
                    "agent00x-host-decision-exp2272",
                    recorder.HOST_DECISION_REPORT_EXP2382,
                    recorder.HOST_DECISION_ARTIFACT_EXP2382,
                ),
                "EXP-2401": (
                    "enrollment",
                    "agent00x-enrollment-exp2401",
                    recorder.ENROLLMENT_REPORT_EXP2401,
                    recorder.ENROLLMENT_ARTIFACT_EXP2401,
                ),
                "EXP-2403": (
                    "host-decision",
                    "agent00x-host-decision-exp2403",
                    recorder.HOST_DECISION_REPORT_EXP2403,
                    recorder.HOST_DECISION_ARTIFACT_EXP2403,
                ),
                "EXP-2485": (
                    "enrollment",
                    "agent00x-enrollment-exp2485",
                    recorder.ENROLLMENT_REPORT_EXP2485,
                    recorder.ENROLLMENT_ARTIFACT_EXP2485,
                ),
                "EXP-2488": (
                    "host-decision",
                    "agent00x-host-decision-exp2488",
                    recorder.HOST_DECISION_REPORT_EXP2488,
                    recorder.HOST_DECISION_ARTIFACT_EXP2488,
                ),
                "EXP-2544": (
                    "enrollment",
                    "agent00x-enrollment-exp2544",
                    recorder.ENROLLMENT_REPORT_EXP2544,
                    recorder.ENROLLMENT_ARTIFACT_EXP2544,
                ),
                "EXP-2547": (
                    "host-decision",
                    "agent00x-host-decision-exp2547",
                    recorder.HOST_DECISION_REPORT_EXP2547,
                    recorder.HOST_DECISION_ARTIFACT_EXP2547,
                ),
                "EXP-2843": (
                    "enrollment",
                    "agent00x-enrollment-exp2843",
                    recorder.ENROLLMENT_REPORT_EXP2843,
                    recorder.ENROLLMENT_ARTIFACT_EXP2843,
                ),
                "EXP-2844": (
                    "host-decision",
                    "agent00x-host-decision-exp2844",
                    recorder.HOST_DECISION_REPORT_EXP2844,
                    recorder.HOST_DECISION_ARTIFACT_EXP2844,
                ),
                "EXP-2955": (
                    "enrollment",
                    "agent00x-enrollment-exp2974",
                    recorder.ENROLLMENT_REPORT_EXP2955,
                    recorder.ENROLLMENT_ARTIFACT_EXP2955,
                ),
                "EXP-2956": (
                    "host-decision",
                    "agent00x-host-decision-exp2975",
                    recorder.HOST_DECISION_REPORT_EXP2956,
                    recorder.HOST_DECISION_ARTIFACT_EXP2956,
                ),
            },
        )
    def test_records_only_verified_exp2196_response_exclusively_at_0600(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            artifact_path = root / "artifact.json"
            artifact = b'{"schema":"verifier-trust-enrollment/v1"}\n'
            digest = "sha256:" + hashlib.sha256(artifact).hexdigest()
            expected_id = "agent00x-enrollment-exp2196"
            verified = {
                "artifact_base64": base64.b64encode(artifact).decode("ascii"),
                "artifact_digest": digest,
                "artifact_id": expected_id,
                "authority_key_set_digest": recorder.AUTHORITY_KEY_SET_DIGEST,
                "authority_signature_valid": True,
                "independent_host_trust_established": False,
                "kind": "enrollment",
            }
            verified_raw = json.dumps(
                verified, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
            spec = ("enrollment", expected_id, report_path, artifact_path)
            with (
                mock.patch.dict(recorder._SPECS, {"EXP-2196": spec}),
                mock.patch.object(recorder, "verify_response", return_value=verified_raw),
                mock.patch.object(recorder, "_verification_args", return_value=object()),
            ):
                self.assertEqual(
                    recorder.record_signature_response("EXP-2196", b"signature response"),
                    ("enrollment", digest),
                )
            self.assertEqual(artifact_path.read_bytes(), artifact)
            self.assertEqual(report_path.read_bytes(), verified_raw)
            self.assertEqual(artifact_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(report_path.stat().st_mode & 0o777, 0o600)

    def test_host_decision_binds_to_the_recorded_enrollment_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "enrollment-report.json"
            report_path.write_text(
                json.dumps({"artifact_digest": "sha256:" + "a" * 64}),
                encoding="utf-8",
            )
            with mock.patch.dict(
                recorder._SPECS,
                {
                    "EXP-2196": (
                        "enrollment",
                        "agent00x-enrollment-exp2196",
                        report_path,
                        root / "enrollment-artifact.json",
                    )
                },
            ):
                args = recorder._verification_args("EXP-2197")
            self.assertEqual(args.kind, "host-decision")
            self.assertEqual(args.expected_enrollment_digest, "sha256:" + "a" * 64)
            self.assertEqual(args.enrollment_artifact, str(root / "enrollment-artifact.json"))
            self.assertEqual(args.expected_verifier_host_id, "testdev")
            self.assertEqual(args.expected_host_separation_evidence_digest, recorder.SEPARATION_DIGEST)

    def test_exp2259_host_decision_binds_only_exp2258_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "enrollment-report.json"
            report_path.write_text(
                json.dumps({"artifact_digest": "sha256:" + "b" * 64}),
                encoding="utf-8",
            )
            artifact_path = root / "enrollment-artifact.json"
            with mock.patch.dict(
                recorder._SPECS,
                {
                    "EXP-2271": (
                        "enrollment",
                        "agent00x-enrollment-exp2271",
                        report_path,
                        artifact_path,
                    )
                },
            ):
                args = recorder._verification_args("EXP-2272")
            self.assertEqual(args.expected_enrollment_digest, "sha256:" + "b" * 64)
            self.assertEqual(args.enrollment_artifact, str(artifact_path))

    def test_exp2547_host_decision_binds_only_fresh_exp2544_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "enrollment-report.json"
            report_path.write_text(
                json.dumps({"artifact_digest": "sha256:" + "f" * 64}),
                encoding="utf-8",
            )
            enrollment_artifact = root / "enrollment-artifact.json"
            with mock.patch.dict(
                recorder._SPECS,
                {
                    "EXP-2544": (
                        "enrollment",
                        "agent00x-enrollment-exp2544",
                        report_path,
                        enrollment_artifact,
                    )
                },
            ):
                args = recorder._verification_args("EXP-2547")
            self.assertEqual(args.kind, "host-decision")
            self.assertEqual(args.expected_enrollment_digest, "sha256:" + "f" * 64)
            self.assertEqual(args.enrollment_artifact, str(enrollment_artifact))
            self.assertEqual(args.expected_verifier_host_id, "testdev")
            self.assertEqual(
                args.expected_host_separation_evidence_digest,
                recorder.SEPARATION_DIGEST,
            )

    def test_exp2844_host_decision_binds_only_exp2843_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "enrollment-report.json"
            report_path.write_text(
                json.dumps({"artifact_digest": "sha256:" + "e" * 64}),
                encoding="utf-8",
            )
            enrollment_artifact = root / "enrollment-artifact.json"
            with mock.patch.dict(
                recorder._SPECS,
                {
                    "EXP-2843": (
                        "enrollment",
                        "agent00x-enrollment-exp2843",
                        report_path,
                        enrollment_artifact,
                    )
                },
            ):
                args = recorder._verification_args("EXP-2844")
            self.assertEqual(args.kind, "host-decision")
            self.assertEqual(args.expected_enrollment_digest, "sha256:" + "e" * 64)
            self.assertEqual(args.enrollment_artifact, str(enrollment_artifact))
            self.assertEqual(args.expected_verifier_host_id, "testdev")

    def test_exp2956_host_decision_binds_only_exp2955_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "enrollment-report.json"
            report_path.write_text(
                json.dumps({"artifact_digest": "sha256:" + "d" * 64}),
                encoding="utf-8",
            )
            artifact_path = root / "enrollment-artifact.json"
            with mock.patch.dict(
                recorder._SPECS,
                {
                    "EXP-2955": (
                        "enrollment",
                        "agent00x-enrollment-exp2974",
                        report_path,
                        artifact_path,
                    )
                },
            ):
                args = recorder._verification_args("EXP-2956")
            self.assertEqual(args.kind, "host-decision")
            self.assertEqual(args.expected_enrollment_digest, "sha256:" + "d" * 64)
            self.assertEqual(args.enrollment_artifact, str(artifact_path))
            self.assertEqual(args.expected_verifier_host_id, "testdev")

    def test_exp2382_host_decision_binds_only_fresh_exp2381_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "enrollment-report.json"
            report_path.write_text(
                json.dumps({"artifact_digest": "sha256:" + "c" * 64}),
                encoding="utf-8",
            )
            artifact_path = root / "enrollment-artifact.json"
            with mock.patch.dict(
                recorder._SPECS,
                {
                    "EXP-2381": (
                        "enrollment",
                        "agent00x-enrollment-exp2271",
                        report_path,
                        artifact_path,
                    )
                },
            ):
                args = recorder._verification_args("EXP-2382")
            self.assertEqual(args.expected_enrollment_digest, "sha256:" + "c" * 64)
            self.assertEqual(args.enrollment_artifact, str(artifact_path))

    def test_exp2403_host_decision_binds_only_fresh_exp2401_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "enrollment-report.json"
            report_path.write_text(
                json.dumps({"artifact_digest": "sha256:" + "d" * 64}),
                encoding="utf-8",
            )
            artifact_path = root / "enrollment-artifact.json"
            with mock.patch.dict(
                recorder._SPECS,
                {"EXP-2401": (
                    "enrollment",
                    "agent00x-enrollment-exp2401",
                    report_path,
                    artifact_path,
                )},
            ):
                args = recorder._verification_args("EXP-2403")
            self.assertEqual(args.expected_enrollment_digest, "sha256:" + "d" * 64)
            self.assertEqual(args.enrollment_artifact, str(artifact_path))

    def test_unlisted_or_mismatched_signature_response_fails_without_writes(self):
        with mock.patch.object(recorder, "verify_response") as verify:
            with self.assertRaisesRegex(ValueError, "VERIFIER_TRUST_RECORD_REJECTED"):
                recorder.record_signature_response("EXP-2198", b"{}")
            verify.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            artifact_path = root / "artifact.json"
            wrong = {
                "artifact_base64": base64.b64encode(b"wrong").decode("ascii"),
                "artifact_digest": "sha256:" + "0" * 64,
                "artifact_id": "agent00x-enrollment-exp2196",
                "authority_key_set_digest": recorder.AUTHORITY_KEY_SET_DIGEST,
                "authority_signature_valid": True,
                "independent_host_trust_established": False,
                "kind": "enrollment",
            }
            with (
                mock.patch.dict(
                    recorder._SPECS,
                    {"EXP-2196": ("enrollment", wrong["artifact_id"], report_path, artifact_path)},
                ),
                mock.patch.object(
                    recorder,
                    "verify_response",
                    return_value=json.dumps(wrong).encode("ascii"),
                ),
                mock.patch.object(recorder, "_verification_args", return_value=object()),
            ):
                with self.assertRaisesRegex(ValueError, "VERIFIER_TRUST_RECORD_REJECTED"):
                    recorder.record_signature_response("EXP-2196", b"response")
            self.assertFalse(report_path.exists())
            self.assertFalse(artifact_path.exists())


if __name__ == "__main__":
    unittest.main()
