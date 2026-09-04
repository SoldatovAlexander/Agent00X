from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.validator import ContractValidationError, validate
from app_contracts.chain import validate_chain
from app_contracts.digests import sha256_digest


SCHEMAS = {
    "process_contract": "process-contract.schema.json",
    "canonical_envelope": "canonical-envelope.schema.json",
    "task_contract": "task-contract.schema.json",
    "evidence_bundle": "evidence-bundle.schema.json",
    "verification_report": "verification-report.schema.json",
    "staged_change": "staged-change.schema.json",
    "approval": "approval.schema.json",
    "intent": "publish-pull-request-intent.schema.json",
    "policy_decision": "policy-decision.schema.json",
    "action_receipt": "action-receipt.schema.json",
}


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            name: load_json(ROOT / "schemas" / filename)
            for name, filename in SCHEMAS.items()
        }
        cls.chain = load_json(ROOT / "fixtures" / "valid" / "mvp-chain.json")

    def test_valid_chain_conforms_to_all_schemas(self):
        for name, schema in self.schemas.items():
            with self.subTest(contract=name):
                validate(self.chain[name], schema)

    def test_secret_field_is_rejected(self):
        intent = load_json(ROOT / "fixtures" / "invalid" / "intent-with-token.json")
        with self.assertRaisesRegex(ContractValidationError, "unknown fields.*token"):
            validate(intent, self.schemas["intent"])

    def test_arbitrary_operation_is_rejected(self):
        intent = load_json(ROOT / "fixtures" / "invalid" / "intent-arbitrary-operation.json")
        with self.assertRaisesRegex(ContractValidationError, "expected constant"):
            validate(intent, self.schemas["intent"])

    def test_chain_binds_same_process_repository_digest_and_approval(self):
        validate_chain(self.chain)

    def test_idempotency_key_is_bound_to_process_and_staged_digest(self):
        intent = self.chain["intent"]
        expected = f"publish/{intent['process_id']}/{intent['staged_change_digest']}"
        self.assertEqual(intent["idempotency_key"], expected)
        self.assertEqual(self.chain["action_receipt"]["idempotency_key"], expected)

    def test_staged_digest_is_computed_from_canonical_content(self):
        expected = sha256_digest(self.chain["staged_change"])
        self.assertEqual(self.chain["approval"]["staged_change_digest"], expected)

    def test_mutated_staged_change_invalidates_chain(self):
        chain = json.loads(json.dumps(self.chain))
        chain["staged_change"]["patch_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ContractValidationError, "patch_digest mismatch"):
            validate_chain(chain)

    def test_mutated_evidence_invalidates_chain(self):
        chain = json.loads(json.dumps(self.chain))
        chain["evidence_bundle"]["limitations"].append("New unresolved limitation")
        with self.assertRaisesRegex(ContractValidationError, "evidence digest mismatch"):
            validate_chain(chain)

    def test_failed_verification_cannot_be_staged(self):
        chain = json.loads(json.dumps(self.chain))
        chain["verification_report"]["verdict"] = "fail"
        with self.assertRaises(ContractValidationError):
            validate_chain(chain)

    def test_tainted_envelope_cannot_authorize(self):
        envelope = json.loads(json.dumps(self.chain["canonical_envelope"]))
        envelope["security"]["tainted"] = True
        envelope["security"]["permitted_uses"] = ["analysis"]
        envelope["security"]["forbidden_uses"] = ["authorization", "credential-access"]
        validate(envelope, self.schemas["canonical_envelope"])
        self.assertNotIn("authorization", envelope["security"]["permitted_uses"])
        self.assertIn("authorization", envelope["security"]["forbidden_uses"])

    def test_invariant_catalog_has_unique_ids_and_test_links(self):
        catalog = load_json(ROOT / "policies" / "invariants.json")
        invariants = catalog["invariants"]
        ids = [item["id"] for item in invariants]
        self.assertEqual(len(ids), len(set(ids)))
        known_tests = {name for name in dir(self) if name.startswith("test_")}
        state_module = __import__("test_state_machine")
        known_tests |= {
            name for name in dir(state_module.StateMachineTests)
            if name.startswith("test_")
        }
        for invariant in invariants:
            self.assertTrue(invariant["enforcement"])
            self.assertTrue(invariant["tests"])
            for test_name in invariant["tests"]:
                if not test_name.startswith("planned:"):
                    self.assertIn(test_name, known_tests)


if __name__ == "__main__":
    unittest.main()
