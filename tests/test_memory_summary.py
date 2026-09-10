from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.memory_summary import check_interval
from app_contracts.validator import ContractValidationError
from test_observer_contracts import valid_summary


class MemorySummaryIntervalTests(unittest.TestCase):
    def test_reversed_interval_is_rejected(self):
        summary = valid_summary()
        summary["period_start"], summary["period_end"] = summary["period_end"], summary["period_start"]
        with self.assertRaisesRegex(ContractValidationError, "period_end is before period_start"):
            check_interval(summary)

    def test_equal_instant_is_accepted_as_zero_length_summary(self):
        summary = valid_summary()
        summary["period_end"] = summary["period_start"]
        check_interval(summary)

    def test_forward_interval_is_accepted_without_mutation(self):
        summary = valid_summary()
        before = copy.deepcopy(summary)
        check_interval(summary)
        self.assertEqual(summary, before)

    def test_invalid_boundary_is_rejected(self):
        summary = valid_summary()
        summary["period_start"] = "March 2026"
        with self.assertRaisesRegex(ContractValidationError, "period boundary is invalid"):
            check_interval(summary)

    def test_validator_carries_no_secret_bearing_fields(self):
        import app_contracts.memory_summary as module
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("token", "secret", "credential", "password"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
