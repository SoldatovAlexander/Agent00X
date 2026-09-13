from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.memory_summary import check_interval, check_sources
from app_contracts.validator import ContractValidationError
from test_observer_contracts import valid_summary


class MemorySummaryIntervalTests(unittest.TestCase):
    def test_malformed_source_members_denied_without_values(self):
        for bad_refs in ([123], [None], [True], [""], ["artifact://a", 42]):
            with self.subTest(refs=bad_refs):
                summary = valid_summary()
                summary["source_refs"] = bad_refs
                with self.assertRaisesRegex(
                    ContractValidationError, "^summary: source refs are invalid$"
                ) as raised:
                    check_sources(summary)
                self.assertNotIn("artifact", str(raised.exception))
        check_sources(valid_summary())

    def test_unhashable_source_members_denied_without_set_error(self):
        for bad_refs in ([["artifact://a"]], [{"ref": "artifact://a"}], [["a"], ["a"]]):
            with self.subTest(refs=bad_refs):
                summary = valid_summary()
                summary["source_refs"] = bad_refs
                with self.assertRaises(ContractValidationError) as raised:
                    check_sources(summary)
                self.assertNotIsInstance(raised.exception, TypeError)
        check_sources(valid_summary())

    def test_non_mapping_summary_denied_deterministically(self):
        for bad in (None, [], "summary", 42):
            with self.subTest(summary=type(bad).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "^summary: summary is malformed$"
                ):
                    check_interval(bad)
                with self.assertRaisesRegex(
                    ContractValidationError, "^summary: summary is malformed$"
                ):
                    check_sources(bad)
        check_interval(valid_summary())
        check_sources(valid_summary())

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

    def test_non_string_boundary_denied_without_source_leak(self):
        for bad in (123, None, ["2026-03-01T00:00:00Z"]):
            with self.subTest(boundary=type(bad).__name__):
                summary = valid_summary()
                summary["period_start"] = bad
                with self.assertRaisesRegex(
                    ContractValidationError, "^summary: period boundary is invalid$"
                ) as raised:
                    check_interval(summary)
                self.assertNotIn("Three tool calls", str(raised.exception))

    def test_invalid_boundary_is_rejected(self):
        summary = valid_summary()
        summary["period_start"] = "March 2026"
        with self.assertRaisesRegex(ContractValidationError, "period boundary is invalid"):
            check_interval(summary)

    def test_malformed_source_shapes_denied_without_payload(self):
        for bad in ({"ref": "artifact://x"}, "artifact://x", None, [{"ref": "artifact://x"}]):
            with self.subTest(sources=type(bad).__name__):
                summary = valid_summary()
                summary["source_refs"] = bad
                with self.assertRaisesRegex(
                    ContractValidationError, "^summary: source refs are invalid$"
                ) as raised:
                    check_sources(summary)
                self.assertNotIn("Three tool calls", str(raised.exception))
        check_sources(valid_summary())

    def test_duplicate_source_reference_is_rejected_without_content(self):
        summary = valid_summary()
        summary["source_refs"] = [
            "artifact://events/observer-demo-2026-03",
            "artifact://events/observer-demo-2026-03",
        ]
        with self.assertRaisesRegex(
            ContractValidationError, "duplicate source reference"
        ) as raised:
            check_sources(summary)
        self.assertNotIn(summary["content"], str(raised.exception))

    def test_distinct_source_references_stay_accepted(self):
        summary = valid_summary()
        check_sources(summary)
        self.assertEqual(summary["source_digest"], "sha256:" + "a" * 64)

    def test_validator_carries_no_secret_bearing_fields(self):
        import app_contracts.memory_summary as module
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("token", "secret", "credential", "password"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
