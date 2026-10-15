from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import r5_context_renderer as renderer


EXPECTED_CORRECTION = (
    "все database-bound numeric inputs валидируются строго как целые signed-64 "
    "значения до записи; некорректное или непредставимое значение даёт HTTP "
    "422 и ноль новых строк; корректный payload сохраняет прежнее поведение"
)
EXPECTED_ORDERED_CONTEXTS = {
    "A": (2418, "fe7c4b86c2f31c215a03719057de2a5f50a3f80df57f354396881a157718e873"),
    "B": (2416, "c4e4c24bbd780699e7be092bfe8af630f64d703f296d385be1c99dd16329f473"),
    "C": (3338, "30f5e53abbc42bd267423d19c6a9140da135c5d8c066ac1cbf930c46307ecdc4"),
    "D": (3336, "b7d4f2b878a08f92309e40c46c46f264042a4051edf35054c47299f9722e0321"),
}


class R5ContextRendererTests(unittest.TestCase):
    def _context(self, layout: str, correction: bool) -> tuple[bytes, dict]:
        raw = renderer.render_context(layout=layout, correction=correction)
        return raw, json.loads(raw)

    def _facts(self, context: dict) -> list[dict]:
        if context["layout"] == "flat":
            return context["facts"]
        return [fact for group in context["fact_groups"] for fact in group["facts"]]

    def test_structured_and_flat_layouts_keep_identical_fact_objects(self):
        _structured_raw, structured = self._context("structured", False)
        _flat_raw, flat = self._context("flat", False)
        structured_facts = sorted(self._facts(structured), key=lambda fact: fact["id"])
        flat_facts = sorted(self._facts(flat), key=lambda fact: fact["id"])
        self.assertEqual(structured_facts, flat_facts)
        ids = [fact["id"] for fact in structured_facts]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), renderer._EXPECTED_FACT_IDS)
        self.assertEqual(structured["source"], flat["source"])
        self.assertEqual(structured["scope_note"], flat["scope_note"])
        self.assertEqual(structured["security_limits"], flat["security_limits"])
        self.assertEqual(structured["tokenizer_status"], "not_measured")
        self.assertEqual(flat["tokenizer_status"], "not_measured")

    def test_correction_is_added_once_only_to_correction_arms(self):
        _, structured_no = self._context("structured", False)
        _, flat_no = self._context("flat", False)
        _, structured_yes = self._context("structured", True)
        _, flat_yes = self._context("flat", True)
        self.assertNotIn("learning_correction", structured_no)
        self.assertNotIn("learning_correction", flat_no)
        self.assertEqual(renderer._CORRECTION, EXPECTED_CORRECTION)
        self.assertEqual(structured_yes["learning_correction"], EXPECTED_CORRECTION)
        self.assertEqual(flat_yes["learning_correction"], EXPECTED_CORRECTION)
        self.assertEqual(
            {key: value for key, value in structured_yes.items() if key != "learning_correction"},
            structured_no,
        )
        self.assertEqual(
            {key: value for key, value in flat_yes.items() if key != "learning_correction"},
            flat_no,
        )

    def test_context_bytes_are_canonical_and_digest_is_repeatable(self):
        first = renderer.render_context(layout="structured", correction=True)
        second = renderer.render_context(layout="structured", correction=True)
        self.assertEqual(first, second)
        self.assertEqual(renderer.context_digest(first), renderer.context_digest(second))
        self.assertTrue(first.endswith(b"\n"))
        parsed = json.loads(first)
        self.assertEqual(
            first,
            (json.dumps(parsed, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"),
        )

    def test_blinded_candidate_keeps_facts_once_and_blinds_the_arm(self):
        outputs = {
            (layout, correction): json.loads(
                renderer.render_blinded_context(
                    layout=layout, correction=correction
                )
            )
            for layout in ("structured", "flat")
            for correction in (False, True)
        }
        structured = outputs[("structured", False)]
        flat = outputs[("flat", False)]
        structured_facts = [fact for group in structured["facts"] for fact in group]
        flat_facts = flat["facts"]
        ids = [fact["id"] for fact in structured_facts]
        self.assertEqual(len(ids), 6)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), renderer._EXPECTED_FACT_IDS)
        self.assertEqual(
            sorted(structured_facts, key=lambda fact: fact["id"]),
            sorted(flat_facts, key=lambda fact: fact["id"]),
        )
        self.assertEqual(structured["schema"], "agent00x-r5-blinded-context/v1")
        self.assertNotIn("layout", structured)
        self.assertNotIn("layout", flat)
        self.assertEqual(structured["category_labels"], flat["category_labels"])
        self.assertEqual(structured["fact_order"], flat["fact_order"])
        self.assertEqual(structured["fact_order"], sorted(ids))
        for common_key in ("source", "scope_note", "security_limits", "tokenizer_status"):
            self.assertEqual(structured[common_key], flat[common_key])
        expected_groups = [
            sorted(fact_ids)
            for _group_id, fact_ids in renderer._GROUPS
        ]
        self.assertEqual(
            [[fact["id"] for fact in group] for group in structured["facts"]],
            expected_groups,
        )
        self.assertNotIn("learning_correction", structured)
        self.assertNotIn("learning_correction", flat)
        self.assertEqual(
            outputs[("structured", True)]["learning_correction"],
            EXPECTED_CORRECTION,
        )
        self.assertEqual(
            outputs[("flat", True)]["learning_correction"], EXPECTED_CORRECTION
        )

    def test_blinded_candidate_is_canonical_and_repeatable(self):
        first = renderer.render_blinded_context(layout="flat", correction=True)
        second = renderer.render_blinded_context(layout="flat", correction=True)
        self.assertEqual(first, second)
        self.assertEqual(renderer.context_digest(first), renderer.context_digest(second))
        parsed = json.loads(first)
        expected = (
            json.dumps(
                parsed,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii")
        self.assertEqual(first, expected)

    def test_blinded_candidate_rejects_invalid_layout_and_inventory(self):
        with self.assertRaises(renderer.ContextRenderError):
            renderer.render_blinded_context(layout="unknown", correction=False)
        with self.assertRaises(renderer.ContextRenderError):
            renderer.render_blinded_context(layout="flat", correction=1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            invalid = json.loads(renderer.INVENTORY_PATH.read_text(encoding="utf-8"))
            invalid["facts"].pop()
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises(renderer.ContextRenderError):
                renderer.render_blinded_context(
                    layout="structured", correction=False, inventory_path=path
                )

    def test_blinded_bundle_independently_preserves_four_arm_integrity(self):
        bundle = renderer.render_blinded_context_bundle()
        self.assertEqual(set(bundle), {"A", "B", "C", "D"})
        parsed = {arm: json.loads(raw) for arm, raw in bundle.items()}
        expected_ids = sorted(renderer._EXPECTED_FACT_IDS)
        expected_facts = sorted(
            json.loads(renderer.INVENTORY_PATH.read_bytes())["facts"],
            key=lambda fact: fact["id"],
        )
        for arm, context in parsed.items():
            structured = arm in {"A", "C"}
            correction = arm in {"C", "D"}
            self.assertNotIn("layout", context)
            self.assertEqual(context["fact_order"], expected_ids)
            self.assertEqual(context["schema"], "agent00x-r5-blinded-context/v1")
            objects = (
                [fact for group in context["facts"] for fact in group]
                if structured
                else context["facts"]
            )
            ids = [fact["id"] for fact in objects]
            self.assertEqual(len(ids), 6)
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(set(ids), renderer._EXPECTED_FACT_IDS)
            self.assertEqual(sorted(objects, key=lambda fact: fact["id"]), expected_facts)
            if structured:
                expected_groups = [
                    sorted(fact_ids) for _group_id, fact_ids in renderer._GROUPS
                ]
                self.assertEqual(
                    [[fact["id"] for fact in group] for group in context["facts"]],
                    expected_groups,
                )
            self.assertEqual(
                "learning_correction" in context,
                correction,
            )
            if correction:
                self.assertEqual(context["learning_correction"], EXPECTED_CORRECTION)
        for structured_arm, flat_arm in (("A", "B"), ("C", "D")):
            structured_context = parsed[structured_arm]
            flat_context = parsed[flat_arm]
            self.assertEqual(
                sorted(
                    [fact for group in structured_context["facts"] for fact in group],
                    key=lambda fact: fact["id"],
                ),
                flat_context["facts"],
            )
            for key in (
                "schema",
                "source",
                "scope_note",
                "security_limits",
                "tokenizer_status",
                "category_labels",
                "fact_order",
            ):
                self.assertEqual(structured_context[key], flat_context[key])
        self.assertEqual(bundle, renderer.render_blinded_context_bundle())

    def test_blinded_bundle_fails_closed_for_invalid_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            invalid = json.loads(renderer.INVENTORY_PATH.read_text(encoding="utf-8"))
            invalid["source"]["commit"] = "0" * 40
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises(renderer.ContextRenderError):
                renderer.render_blinded_context_bundle(inventory_path=path)

    def test_ordered_v4_bundle_matches_the_exact_measured_contexts(self):
        original_before = renderer.render_blinded_context_bundle()
        bundle = renderer.render_blinded_ordered_context_bundle()
        original_after = renderer.render_blinded_context_bundle()
        self.assertEqual(original_before, original_after)
        self.assertEqual(set(bundle), {"A", "B", "C", "D"})

        parsed = {arm: json.loads(raw) for arm, raw in bundle.items()}
        expected_facts = json.loads(renderer.INVENTORY_PATH.read_bytes())["facts"]
        expected_by_id = {fact["id"]: fact for fact in expected_facts}
        groups = [
            sorted(fact_ids)
            for _group_id, fact_ids in renderer._GROUPS
        ]
        structured_order = [fact_id for group in groups for fact_id in group]
        flat_order = sorted(expected_by_id)

        for arm, raw in bundle.items():
            structured = arm in {"A", "C"}
            correction = arm in {"C", "D"}
            context = parsed[arm]
            expected_order = structured_order if structured else flat_order
            size, digest = EXPECTED_ORDERED_CONTEXTS[arm]
            self.assertEqual(len(raw), size)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            self.assertEqual(context["schema"], "agent00x-r5-blinded-context/v4")
            self.assertEqual(context["fact_order"], expected_order)
            self.assertEqual([fact["id"] for fact in context["facts"]], expected_order)
            self.assertEqual(
                sorted(context["facts"], key=lambda fact: fact["id"]),
                sorted(expected_facts, key=lambda fact: fact["id"]),
            )
            self.assertNotIn("layout", context)
            self.assertNotIn("arm", context)
            self.assertEqual("learning_correction" in context, correction)
            if correction:
                self.assertEqual(context["learning_correction"], EXPECTED_CORRECTION)
            self.assertEqual(raw.count(b"\n\n"), 2 if structured else 0)

        for left, right in (("A", "B"), ("C", "D")):
            for key in (
                "source", "scope_note", "security_limits", "tokenizer_status",
                "category_labels",
            ):
                self.assertEqual(parsed[left][key], parsed[right][key])
            excluded = {"schema", "facts", "fact_order"}
            if "learning_correction" in parsed[left]:
                excluded.add("learning_correction")
            self.assertEqual(
                {key: value for key, value in parsed[left].items() if key not in excluded},
                {key: value for key, value in parsed[right].items() if key not in excluded},
            )
        self.assertEqual(bundle, renderer.render_blinded_ordered_context_bundle())

    def test_ordered_v4_bundle_fails_closed_for_invalid_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            invalid = json.loads(renderer.INVENTORY_PATH.read_text(encoding="utf-8"))
            invalid["source"]["commit"] = "0" * 40
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises(renderer.ContextRenderError):
                renderer.render_blinded_ordered_context_bundle(inventory_path=path)

    def test_invalid_layout_and_mutated_inventory_fail_closed(self):
        with self.assertRaises(renderer.ContextRenderError):
            renderer.render_context(layout="unknown", correction=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            valid = json.loads(renderer.INVENTORY_PATH.read_text(encoding="utf-8"))
            mutated_inventories = []
            wrong_pin = json.loads(json.dumps(valid))
            wrong_pin["source"]["commit"] = "0" * 40
            mutated_inventories.append(wrong_pin)
            missing_fact = json.loads(json.dumps(valid))
            missing_fact["facts"].pop()
            mutated_inventories.append(missing_fact)
            duplicate_id = json.loads(json.dumps(valid))
            duplicate_id["facts"][1]["id"] = duplicate_id["facts"][0]["id"]
            mutated_inventories.append(duplicate_id)
            unknown_id = json.loads(json.dumps(valid))
            unknown_id["facts"][0]["id"] = "route.unknown"
            mutated_inventories.append(unknown_id)
            for mutated in mutated_inventories:
                path.write_text(json.dumps(mutated), encoding="utf-8")
                with self.assertRaises(renderer.ContextRenderError):
                    renderer.render_context(
                        layout="flat", correction=False, inventory_path=path
                    )


if __name__ == "__main__":
    unittest.main()
