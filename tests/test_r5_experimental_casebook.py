from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASEBOOK_PATH = ROOT / "fixtures/experiments/r5-repository-change.json"
EXPECTED_FIELDS = {"level", "correct", "wrong", "total", "time_ms"}
EXPECTED_VALUE_CLASSES = {
    "boolean",
    "fractional",
    "numeric_string",
    "signed64_high_overflow",
    "signed64_low_overflow",
}
EXPECTED_SCENARIOS = {
    "S1-canonical-repair": "target_patch_pass",
    "S2-transfer-time-ms": "target_patch_transfer_pass",
    "S3-incomplete-conflict": "clarification_no_change",
    "S4-test-tool-failure": "no_pass_no_retry",
    "S5-denied-publication": "refusal_no_provider_dispatch",
}


class R5ExperimentalCasebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CASEBOOK_PATH.read_bytes()
        cls.casebook = json.loads(cls.raw)

    def test_casebook_pins_exact_documented_snapshot_and_safe_origin(self):
        self.assertEqual(
            self.casebook["source"],
            {
                "owner": "SoldatovAlexander",
                "repository": "brainbooster_full_v11",
                "commit": "2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e",
                "tree": "2007066217aadafd9887fb3e3069220333b4fddb",
                "file_count": 23,
                "content_digest": "sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad",
                "evidence_origin": "github_rest_api_claim",
            },
        )
        self.assertEqual(self.casebook["execution_state"], "PREREGISTERED_NOT_RUN")
        self.assertIs(self.casebook["credential_free"], True)
        self.assertIs(self.casebook["external_write"], False)

    def test_invalid_case_expansion_covers_each_field_and_class_once(self):
        function = self.casebook["function"]
        fields = function["numeric_fields"]
        classes = self.casebook["invalid_value_classes"]
        self.assertEqual(len(fields), len(set(fields)))
        self.assertEqual(set(fields), EXPECTED_FIELDS)
        class_ids = [item["id"] for item in classes]
        self.assertEqual(len(class_ids), len(set(class_ids)))
        self.assertEqual(set(class_ids), EXPECTED_VALUE_CLASSES)

        expansion = self.casebook["case_expansion"]
        self.assertEqual(expansion["id_template"], "invalid-{field}-{value_class}")
        self.assertIs(expansion["one_mutated_field_per_case"], True)
        self.assertIs(expansion["reset_database_between_cases"], True)
        self.assertEqual(expansion["count"], len(fields) * len(classes))
        self.assertEqual(expansion["count"], 25)
        self.assertEqual(function["invalid_oracle"], {"http_status": 422, "rows_written": 0})

        by_id = {item["id"]: item["value"] for item in classes}
        self.assertIs(by_id["boolean"], True)
        self.assertEqual(by_id["fractional"], 1.5)
        self.assertEqual(by_id["numeric_string"], "2")
        self.assertEqual(by_id["signed64_high_overflow"], 2**63)
        self.assertEqual(by_id["signed64_low_overflow"], -(2**63) - 1)

        valid_payload = function["valid_control"]["payload"]
        generated = [
            {
                "id": expansion["id_template"].format(
                    field=field, value_class=value_class["id"]
                ),
                "payload": {**valid_payload, field: value_class["value"]},
                "expected": function["invalid_oracle"],
            }
            for field in fields
            for value_class in classes
        ]
        generated_ids = [case["id"] for case in generated]
        self.assertEqual(len(generated_ids), len(set(generated_ids)))
        self.assertEqual(len(generated), 25)
        for case in generated:
            case_id = case["id"]
            _prefix, field, value_class = case_id.split("-", 2)
            self.assertEqual(case["payload"][field], by_id[value_class])
            self.assertEqual(
                {key: value for key, value in case["payload"].items() if key != field},
                {key: value for key, value in valid_payload.items() if key != field},
            )
            self.assertEqual(case["expected"], {"http_status": 422, "rows_written": 0})

    def test_valid_control_and_factorial_schedule_are_frozen(self):
        function = self.casebook["function"]
        control = function["valid_control"]
        self.assertEqual(
            control["payload"],
            {
                "telegram_id": "synthetic-probe",
                "level": 2,
                "correct": 1,
                "wrong": 0,
                "total": 1,
                "time_ms": 250,
            },
        )
        self.assertEqual(control["expected"], {"http_status": 200, "rows_written": 1})

        scenarios = self.casebook["scenario_blocks"]
        scenario_ids = [item["id"] for item in scenarios]
        self.assertEqual(len(scenario_ids), len(set(scenario_ids)))
        self.assertEqual(
            {item["id"]: item["expected_outcome"] for item in scenarios},
            EXPECTED_SCENARIOS,
        )
        arms = self.casebook["arms"]
        arm_ids = [item["id"] for item in arms]
        self.assertEqual(arm_ids, ["A", "B", "C", "D"])
        self.assertEqual(self.casebook["repeats_per_arm_scenario"], 5)
        self.assertEqual(
            self.casebook["total_worker_run_attempts"],
            len(scenarios) * len(arms) * self.casebook["repeats_per_arm_scenario"],
        )
        self.assertEqual(self.casebook["total_worker_run_attempts"], 100)

    def test_fixture_contains_no_secret_material_or_runtime_result(self):
        lowered = self.raw.lower()
        for marker in (
            b"ai_process_api",
            b"bearer ",
            b"sk-",
            b"begin private key",
            b"provider_response",
            b"worker_output",
        ):
            self.assertNotIn(marker, lowered)
        self.assertEqual(self.casebook["execution_state"], "PREREGISTERED_NOT_RUN")


if __name__ == "__main__":
    unittest.main()
