from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.gateway import GatewayPath, classify
from app_contracts.validator import ContractValidationError, validate


class ThreatCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads((ROOT / "fixtures" / "threats" / "mvp-security-cases.json").read_text())

    def test_case_ids_are_unique_and_gateway_outcomes_match(self):
        cases = self.corpus["cases"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            with self.subTest(case=case["id"]):
                decision = classify({
                    "intent": {"operation": case["operation"]},
                    "destination": {"port": case["port"]},
                    "source": {"protocol": case["protocol"]},
                    "security": {"tainted": case["tainted"], "sensitivity": "internal"},
                }, policy_available=case["policy_available"])
                self.assertEqual(decision.path, GatewayPath(case["expected_path"]))
                self.assertEqual(decision.allowed, case["expected_allowed"])

    def test_contract_injection_case_rejects_credential_field(self):
        intent = json.loads((ROOT / "fixtures" / "valid" / "mvp-chain.json").read_text())["intent"]
        intent["authorization"] = "injected-value"
        schema = json.loads((ROOT / "schemas" / "publish-pull-request-intent.schema.json").read_text())
        with self.assertRaisesRegex(ContractValidationError, "unknown fields.*authorization"):
            validate(intent, schema)


if __name__ == "__main__":
    unittest.main()
