from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_contracts.deepseek_worker import build_chat_completions_payload
from app_contracts.digests import canonical_json, sha256_bytes
from scripts import r5_batch_selection
from scripts.r5_batch_selection import (
    EXPECTED_FIRST_FIVE,
    R5BatchSelectionError,
    select_first_five_attempts,
    select_r5_attempts,
)


class R5BatchSelectionTests(unittest.TestCase):
    def test_selects_exact_preregistered_first_five_and_binds_inputs(self) -> None:
        selected = select_first_five_attempts()

        self.assertEqual(len(selected), 5)
        self.assertEqual(tuple(item.attempt_id for item in selected), EXPECTED_FIRST_FIVE)
        self.assertEqual(
            tuple(
                (item.scenario_id, item.arm_id, item.repeat)
                for item in selected
            ),
            (
                ("S1-canonical-repair", "A", 3),
                ("S4-test-tool-failure", "C", 5),
                ("S5-denied-publication", "D", 4),
                ("S1-canonical-repair", "A", 1),
                ("S4-test-tool-failure", "A", 4),
            ),
        )
        for item in selected:
            payload = build_chat_completions_payload(item.worker_input)
            self.assertEqual(item.casebook_digest, "sha256:" + r5_batch_selection.CASEBOOK_SHA256)
            self.assertRegex(item.source_digest, r"\Asha256:[0-9a-f]{64}\Z")
            self.assertRegex(item.context_digest, r"\Asha256:[0-9a-f]{64}\Z")
            self.assertEqual(item.input_digest, sha256_bytes(canonical_json(payload)))
            self.assertEqual(item.worker_input.declared_change_paths, ("backend/routes.py",))
            self.assertNotIn(item.attempt_id, payload["messages"][1]["content"])
            self.assertNotIn(item.scenario_id, payload["messages"][1]["content"])
            self.assertNotIn("arm_id", payload["messages"][1]["content"])
            self.assertNotIn("expected_outcome", payload["messages"][1]["content"])

    def test_repr_does_not_expose_model_input(self) -> None:
        item = select_first_five_attempts()[0]
        rendered = repr(item)
        self.assertIn("R5-001", rendered)
        self.assertNotIn("Исправь наблюдаемый", rendered)
        self.assertNotIn("backend/routes.py", rendered)
        self.assertNotIn("r5-context.json", rendered)

    def test_selects_exact_pending_ids_in_requested_order(self) -> None:
        selected = select_r5_attempts(("R5-005", "R5-002", "R5-006"))
        self.assertEqual(
            tuple(item.attempt_id for item in selected),
            ("R5-005", "R5-002", "R5-006"),
        )
        for item in selected:
            self.assertEqual(item.worker_input.task_id, "task-" + item.attempt_id.lower())

    def test_exact_selection_rejects_duplicates_missing_ids_and_more_than_five(self) -> None:
        for attempt_ids in (
            ("R5-002", "R5-002"),
            ("R5-101",),
            ("R5-001", "R5-002", "R5-003", "R5-004", "R5-005", "R5-006"),
        ):
            with self.subTest(attempt_ids=attempt_ids):
                with self.assertRaises(R5BatchSelectionError):
                    select_r5_attempts(attempt_ids)

    def test_rejects_changed_casebook_before_building_any_input(self) -> None:
        original = r5_batch_selection.CASEBOOK_PATH.read_bytes()
        casebook = json.loads(original)
        casebook["run_order"][0]["attempt_id"] = "R5-002"
        changed = json.dumps(casebook, ensure_ascii=False, sort_keys=True).encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "casebook.json"
            path.write_bytes(changed)
            with (
                patch.object(r5_batch_selection, "CASEBOOK_PATH", path),
                patch.object(
                    r5_batch_selection,
                    "CASEBOOK_SHA256",
                    hashlib.sha256(changed).hexdigest(),
                ),
                patch.object(r5_batch_selection, "build_r5_worker_input") as builder,
            ):
                with self.assertRaises(R5BatchSelectionError):
                    select_first_five_attempts()
                builder.assert_not_called()

    def test_rejects_malformed_or_incomplete_schedule(self) -> None:
        original = r5_batch_selection.CASEBOOK_PATH.read_bytes()
        casebook = json.loads(original)
        casebook["run_order"].pop()
        changed = json.dumps(casebook, ensure_ascii=False, sort_keys=True).encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "casebook.json"
            path.write_bytes(changed)
            with (
                patch.object(r5_batch_selection, "CASEBOOK_PATH", path),
                patch.object(
                    r5_batch_selection,
                    "CASEBOOK_SHA256",
                    hashlib.sha256(changed).hexdigest(),
                ),
                patch.object(r5_batch_selection, "build_r5_worker_input") as builder,
            ):
                with self.assertRaises(R5BatchSelectionError):
                    select_first_five_attempts()
                builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
