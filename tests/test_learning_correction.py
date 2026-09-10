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
