from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "fixtures/experiments/r5-fact-inventory.json"
PINNED_COMMIT = "2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e"


class R5FactInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = INVENTORY_PATH.read_bytes()
        cls.inventory = json.loads(cls.raw)

    def test_inventory_source_is_bound_to_the_preregistered_public_pin(self):
        source = self.inventory["source"]
        self.assertEqual(self.inventory["schema"], "agent00x-r5-fact-inventory/v1")
        self.assertEqual(source["owner"], "SoldatovAlexander")
        self.assertEqual(source["repository"], "brainbooster_full_v11")
        self.assertEqual(source["commit"], PINNED_COMMIT)
        self.assertEqual(source["tree"], "2007066217aadafd9887fb3e3069220333b4fddb")
        self.assertEqual(source["path"], "backend/routes.py")
        self.assertEqual(source["retrieval"], "public-read-only")
        self.assertIs(source["signature_verified"], False)
        self.assertEqual(
            source["url"],
            "https://raw.githubusercontent.com/SoldatovAlexander/brainbooster_full_v11/"
            + PINNED_COMMIT
            + "/backend/routes.py",
        )

    def test_fact_ids_and_source_line_ranges_are_complete_and_bounded(self):
        facts = self.inventory["facts"]
        fact_ids = [fact["id"] for fact in facts]
        self.assertEqual(len(fact_ids), len(set(fact_ids)))
        self.assertEqual(
            set(fact_ids),
            {
                "route.method-and-path",
                "route.telegram-default",
                "route.numeric-fields",
                "route.no-visible-numeric-validation",
                "route.database-write",
                "route.success-response",
            },
        )
        for fact in facts:
            self.assertIn(fact["kind"], {"source-observation", "bounded-inference"})
            self.assertTrue(fact["statement"])
            first, last = fact["source_lines"]
            self.assertIs(type(first), int)
            self.assertIs(type(last), int)
            self.assertLessEqual(1, first)
            self.assertLessEqual(first, last)
            self.assertLessEqual(last, 24)
        inferred = next(
            fact for fact in facts if fact["id"] == "route.no-visible-numeric-validation"
        )
        self.assertEqual(inferred["kind"], "bounded-inference")

    def test_inventory_does_not_embed_source_code_or_secret_markers(self):
        lowered = self.raw.lower()
        for marker in (
            b"ai_process_api",
            b"bearer ",
            b"begin private key",
            b"conn.execute(",
            b"def save_session",
        ):
            self.assertNotIn(marker, lowered)
        self.assertIn(b"does not assert runtime", lowered)


if __name__ == "__main__":
    unittest.main()
