from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.learning_correction import check_version
from app_contracts.validator import ContractValidationError
from test_observer_contracts import valid_correction


class LearningCorrectionVersionTests(unittest.TestCase):
    def test_self_supersede_is_rejected(self):
        correction = valid_correction()
        correction["supersedes"] = correction["correction_id"]
        with self.assertRaisesRegex(ContractValidationError, "cannot supersede itself"):
            check_version(correction)

    def test_invalid_version_is_rejected(self):
        for bad in (0, -2, "1", 1.0, True, None):
            with self.subTest(version=bad):
                correction = valid_correction()
                correction["version"] = bad
                with self.assertRaisesRegex(ContractValidationError, "version is invalid"):
                    check_version(correction)

    def test_non_mapping_correction_denied_without_payload(self):
        for bad in (None, [], "correction", 42):
            with self.subTest(correction=type(bad).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "^correction: version is invalid$"
                ):
                    check_version(bad)

    def test_malformed_correction_identity_denied_without_leak(self):
        for bad in (123, None, "", ["correction-observer-demo-001"]):
            with self.subTest(identity=type(bad).__name__):
                correction = valid_correction()
                correction["correction_id"] = bad
                correction["supersedes"] = "correction-observer-demo-000"
                with self.assertRaisesRegex(
                    ContractValidationError, "^correction: correction identity is invalid$"
                ) as raised:
                    check_version(correction)
                self.assertNotIn("observer-demo", str(raised.exception))

    def test_malformed_supersedes_reference_is_denied(self):
        for bad in (123, ["correction-observer-demo-000"], "", {"ref": "x"}):
            with self.subTest(reference=type(bad).__name__):
                correction = valid_correction()
                correction["supersedes"] = bad
                with self.assertRaisesRegex(
                    ContractValidationError, "^correction: supersedes reference is invalid$"
                ):
                    check_version(correction)
        check_version(valid_correction())

    def test_malformed_correction_roots_denied_deterministically(self):
        for bad in (
            {"version": [1]},
            {"version": {"n": 1}},
            {"version": 2, "supersedes": ["correction-observer-demo-000"]},
            {},
        ):
            with self.subTest(correction=bad):
                with self.assertRaises(ContractValidationError) as raised:
                    check_version(bad)
                self.assertNotIsInstance(raised.exception, (TypeError, AttributeError, KeyError))
        check_version(valid_correction())

    def test_malformed_correction_roots_denied_without_raw_error(self):
        for bad in (None, ["correction"], "correction", 42, {("version", 1)}):
            with self.subTest(root=type(bad).__name__):
                with self.assertRaises(ContractValidationError) as raised:
                    check_version(bad)
                self.assertNotIsInstance(raised.exception, (TypeError, AttributeError, KeyError))
        missing_version = valid_correction()
        del missing_version["version"]
        with self.assertRaisesRegex(ContractValidationError, "^correction: version is invalid$"):
            check_version(missing_version)
        check_version(valid_correction())

    def test_valid_correction_passes_unmutated(self):
        correction = valid_correction()
        correction["supersedes"] = "correction-observer-demo-000"
        before = copy.deepcopy(correction)
        check_version(correction)
        self.assertEqual(correction, before)

    def test_validator_holds_no_privilege_fields(self):
        import app_contracts.learning_correction as module
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("capability", "credential", "token", "approval"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
