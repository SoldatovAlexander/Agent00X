from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.deepseek_worker import build_chat_completions_payload
from scripts import r5_worker_input
from scripts.r5_context_renderer import render_blinded_ordered_context_bundle


class R5WorkerInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = render_blinded_ordered_context_bundle()
        cls.casebook = r5_worker_input._read_fixed_inputs()[0]
        cls.source = r5_worker_input.SOURCE_PATH.read_bytes()
        cls.scenarios = {
            item["id"]: item for item in cls.casebook["scenario_blocks"]
        }
        cls.runs = {item["attempt_id"]: item for item in cls.casebook["run_order"]}

    def test_all_100_inputs_bind_pins_path_and_exact_model_payload(self):
        self.assertEqual(len(self.runs), 100)
        self.assertEqual(
            hashlib.sha256(self.source).hexdigest(), r5_worker_input.SOURCE_SHA256
        )
        self.assertEqual(len(self.source), r5_worker_input.SOURCE_SIZE)
        task_ids = set()
        for attempt_id, run in self.runs.items():
            with self.subTest(attempt_id=attempt_id):
                task = r5_worker_input.build_r5_worker_input(attempt_id)
                task_ids.add(task.task_id)
                self.assertEqual(task.task_id, "task-" + attempt_id.lower())
                self.assertEqual(
                    task.repository_id,
                    "SoldatovAlexander/brainbooster_full_v11",
                )
                self.assertEqual(
                    task.base_commit, "2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e"
                )
                self.assertEqual(
                    task.snapshot_tree_digest,
                    "sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad",
                )
                self.assertEqual(task.snapshot_origin, "github_codeload_archive")
                self.assertEqual(task.declared_change_paths, ("backend/routes.py",))
                self.assertEqual(
                    task.context_files,
                    (("backend/routes.py", self.source.decode("utf-8")),),
                )

                context = self.bundle[run["arm_id"]].decode("ascii").rstrip("\n")
                expected_instruction = (
                    self.scenarios[run["scenario_id"]]["prompt"]
                    + "\n\nContext file: r5-context.json\n"
                    + context
                )
                control = self.scenarios[run["scenario_id"]][
                    "model_visible_control_context"
                ]
                if control is not None:
                    import json

                    expected_instruction += (
                        "\n\nContext file: r5-scenario-control.json\n"
                        + json.dumps(
                            control,
                            ensure_ascii=True,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                self.assertEqual(task.task_instruction, expected_instruction)

                payload = build_chat_completions_payload(task)
                user_content = payload["messages"][1]["content"]
                self.assertEqual(
                    user_content,
                    expected_instruction
                    + "\n\nContext file: backend/routes.py\n"
                    + self.source.decode("utf-8"),
                )
                self.assertNotIn(attempt_id, user_content)
                self.assertNotIn(run["scenario_id"], user_content)
                self.assertNotIn("arm_id", user_content)
                self.assertNotIn(
                    self.scenarios[run["scenario_id"]]["expected_outcome"],
                    user_content,
                )
        self.assertEqual(len(task_ids), 100)

    def test_source_mismatch_and_unknown_attempt_fail_closed(self):
        with self.assertRaises(r5_worker_input.R5WorkerInputError):
            r5_worker_input.build_r5_worker_input("R5-101")
        with tempfile.TemporaryDirectory() as directory:
            bad_source = Path(directory) / "routes.py"
            bad_source.write_bytes(b"not the pinned route")
            with mock.patch.object(r5_worker_input, "SOURCE_PATH", bad_source):
                with self.assertRaises(r5_worker_input.R5WorkerInputError):
                    r5_worker_input.build_r5_worker_input("R5-001")

    def test_corrected_provenance_does_not_change_model_visible_payload(self):
        for attempt_id in self.runs:
            with self.subTest(attempt_id=attempt_id):
                task = r5_worker_input.build_r5_worker_input(attempt_id)
                old_metadata = replace(task, snapshot_origin="github_rest_api_claim")
                self.assertEqual(
                    build_chat_completions_payload(task),
                    build_chat_completions_payload(old_metadata),
                )

    def test_casebook_digest_and_control_context_are_fixed(self):
        self.assertEqual(
            hashlib.sha256(r5_worker_input.CASEBOOK_PATH.read_bytes()).hexdigest(),
            r5_worker_input.CASEBOOK_SHA256,
        )
        for scenario_id, expected in r5_worker_input._CONTROL_CONTEXTS.items():
            self.assertEqual(
                self.scenarios[scenario_id]["model_visible_control_context"],
                expected,
            )
        for scenario_id in (
            "S1-canonical-repair",
            "S2-transfer-time-ms",
        ):
            self.assertIsNone(
                self.scenarios[scenario_id]["model_visible_control_context"]
            )


if __name__ == "__main__":
    unittest.main()
