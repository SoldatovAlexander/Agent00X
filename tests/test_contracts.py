from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.validator import ContractValidationError, validate, validate_schema
from app_contracts.chain import validate_chain
from app_contracts.digests import canonical_json, sha256_digest


SCHEMAS = {
    "process_contract": "process-contract.schema.json",
    "identity": "identity.schema.json",
    "capability_grant": "capability-grant.schema.json",
    "delegation_receipt": "delegation-receipt.schema.json",
    "trust_profile": "trust-profile.schema.json",
    "canonical_envelope": "canonical-envelope.schema.json",
    "task_contract": "task-contract.schema.json",
    "evidence_bundle": "evidence-bundle.schema.json",
    "verification_report": "verification-report.schema.json",
    "staged_change": "staged-change.schema.json",
    "approval": "approval.schema.json",
    "intent": "publish-pull-request-intent.schema.json",
    "policy_decision": "policy-decision.schema.json",
    "actuator_request": "actuator-request.schema.json",
    "credential_use_grant": "credential-use-grant.schema.json",
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

    def test_approval_binds_full_canonical_intent_digest(self):
        self.assertEqual(
            self.chain["approval"]["approved_intent_digest"],
            sha256_digest(self.chain["intent"]),
        )
        validate(self.chain["approval"], self.schemas["approval"])
        validate_chain(self.chain)

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

    def test_non_boolean_taint_markers_denied_without_value(self):
        for bad in ("yes", "", 1, 0, None, ["tainted"]):
            with self.subTest(marker=type(bad).__name__):
                chain = json.loads(json.dumps(self.chain))
                chain["canonical_envelope"]["security"]["tainted"] = bad
                with self.assertRaisesRegex(
                    ContractValidationError, "^chain: taint marker is not a boolean$"
                ) as raised:
                    validate_chain(chain)
                self.assertNotIn("process-demo-001", str(raised.exception))
        tainted = json.loads(json.dumps(self.chain))
        tainted["canonical_envelope"]["security"]["tainted"] = True
        with self.assertRaisesRegex(ContractValidationError, "tainted envelope cannot authorize"):
            validate_chain(tainted)
        validate_chain(self.chain)

    def test_tainted_envelope_cannot_authorize(self):
        envelope = json.loads(json.dumps(self.chain["canonical_envelope"]))
        envelope["security"]["tainted"] = True
        envelope["security"]["permitted_uses"] = ["analysis"]
        envelope["security"]["forbidden_uses"] = ["authorization", "credential-access"]
        validate(envelope, self.schemas["canonical_envelope"])
        self.assertNotIn("authorization", envelope["security"]["permitted_uses"])
        self.assertIn("authorization", envelope["security"]["forbidden_uses"])

    def test_malformed_chain_roots_denied_without_raw_error(self):
        for bad in (None, "chain", 42, [["process_contract"]]):
            with self.subTest(root=type(bad).__name__):
                with self.assertRaises(ContractValidationError) as raised:
                    validate_chain(bad)
                self.assertNotIsInstance(raised.exception, (TypeError, AttributeError, KeyError))
        validate_chain(self.chain)

    def test_empty_binding_values_denied_without_payload(self):
        victims = [
            ("process_contract", "process_id"),
            ("approval", "repository_id"),
            ("intent", "staged_change_digest"),
        ]
        for name, field in victims:
            with self.subTest(member=name):
                chain = json.loads(json.dumps(self.chain))
                chain[name][field] = ""
                with self.assertRaisesRegex(
                    ContractValidationError, f"^chain: {name} has empty binding value$"
                ) as raised:
                    validate_chain(chain)
                self.assertNotIn("process-demo-001", str(raised.exception))
        validate_chain(self.chain)

    def test_unhashable_binding_values_denied_without_details(self):
        victims = [
            ("staged_change", "process_id", ["process-demo-001"]),
            ("approval", "repository_id", {"repo": 1}),
            ("intent", "staged_change_digest", ["sha256:" + "a" * 64]),
            ("policy_decision", "staged_change_digest", None),
            ("action_receipt", "process_id", ("process-demo-001",)),
        ]
        for name, field, bad in victims:
            with self.subTest(member=name):
                chain = json.loads(json.dumps(self.chain))
                chain[name][field] = bad
                with self.assertRaisesRegex(
                    ContractValidationError, f"^chain: {name} has non-string binding value$"
                ) as raised:
                    validate_chain(chain)
                self.assertNotIn("process-demo-001", str(raised.exception))
        validate_chain(self.chain)

    def test_malformed_chain_entries_denied_without_details(self):
        for broken in (
            {"capability_grant": None},
            {"delegation_receipt": ["not-a-mapping"]},
            {"capability_grant": "grant"},
        ):
            with self.subTest(broken=sorted(broken)):
                chain = json.loads(json.dumps(self.chain))
                chain.update(broken)
                with self.assertRaisesRegex(ContractValidationError, "^chain: malformed contracts "):
                    validate_chain(chain)
        with self.assertRaisesRegex(ContractValidationError, "^chain: chain is malformed$"):
            validate_chain(["not-a-chain"])
        validate_chain(self.chain)

    def test_incomplete_member_contracts_denied_without_raw_error(self):
        victims = [
            ("staged_change", "process_id"),
            ("approval", "approval_id"),
            ("intent", "branch_namespace"),
            ("delegation_receipt", "actions"),
            ("canonical_envelope", "security"),
            ("action_receipt", "idempotency_key"),
        ]
        for name, field in victims:
            with self.subTest(member=name):
                chain = json.loads(json.dumps(self.chain))
                del chain[name][field]
                with self.assertRaises(ContractValidationError) as raised:
                    validate_chain(chain)
                self.assertNotIsInstance(raised.exception, (KeyError, TypeError, AttributeError))
        validate_chain(self.chain)

    def test_malformed_member_values_denied_without_details(self):
        chain = json.loads(json.dumps(self.chain))
        chain["delegation_receipt"]["actions"] = {"write": True}
        with self.assertRaisesRegex(ContractValidationError, "^chain: delegation actions is malformed$"):
            validate_chain(chain)
        chain = json.loads(json.dumps(self.chain))
        chain["delegation_receipt"]["remaining_delegation_depth"] = "plenty"
        with self.assertRaisesRegex(ContractValidationError, "^chain: delegation remaining_delegation_depth is malformed$"):
            validate_chain(chain)

    def test_delegation_cannot_expand_actions(self):
        chain = json.loads(json.dumps(self.chain))
        chain["delegation_receipt"]["actions"].append("workspace.patch")
        with self.assertRaisesRegex(ContractValidationError, "delegation expands actions"):
            validate_chain(chain)

    def test_delegation_depth_must_decrease(self):
        chain = json.loads(json.dumps(self.chain))
        chain["delegation_receipt"]["remaining_delegation_depth"] = 1
        with self.assertRaisesRegex(ContractValidationError, "depth is not reduced"):
            validate_chain(chain)

    def test_approval_rejects_unknown_control_fields(self):
        schema = self.schemas["approval"]
        validate(self.chain["approval"], schema)
        for field in ("capability", "credential", "token", "grant"):
            with self.subTest(field=field):
                forged = json.loads(json.dumps(self.chain["approval"]))
                forged[field] = "injected-value"
                with self.assertRaisesRegex(ContractValidationError, f"unknown fields.*{field}"):
                    validate(forged, schema)
        self.assertNotIn("capability", json.dumps(schema["properties"]))

    def test_credential_grant_rejects_token_value(self):
        grant = json.loads(json.dumps(self.chain["credential_use_grant"]))
        grant["token"] = "canary-secret"
        with self.assertRaisesRegex(ContractValidationError, "unknown fields.*token"):
            validate(grant, self.schemas["credential_use_grant"])

    def test_credential_grant_is_bound_to_actuator_request(self):
        self.assertEqual(
            self.chain["credential_use_grant"]["request_digest"],
            sha256_digest(self.chain["actuator_request"]),
        )

    def test_mutated_actuator_request_invalidates_credential_grant(self):
        chain = json.loads(json.dumps(self.chain))
        chain["actuator_request"]["title_artifact_ref"] = "artifact://pr/changed/title"
        with self.assertRaises(ContractValidationError):
            validate_chain(chain)

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
        runtime_module = __import__("test_runtime_store")
        known_tests |= {
            name for name in dir(runtime_module.RuntimeStoreTests)
            if name.startswith("test_")
        }
        authority_module = __import__("test_authority")
        known_tests |= {
            name for name in dir(authority_module.AuthorityTests)
            if name.startswith("test_")
        }
        gateway_module = __import__("test_gateway")
        known_tests |= {
            name for name in dir(gateway_module.GatewayTests)
            if name.startswith("test_")
        }
        actuator_module = __import__("test_actuator")
        known_tests |= {
            name for name in dir(actuator_module.ActuatorTests)
            if name.startswith("test_")
        }
        publication_module = __import__("test_publication")
        known_tests |= {
            name for name in dir(publication_module.PublicationRecoveryTests)
            if name.startswith("test_")
        }
        adversarial_module = __import__("test_adversarial")
        known_tests |= {
            name for name in dir(adversarial_module.AdversarialFlowTests)
            if name.startswith("test_")
        }
        broker_module = __import__("test_broker")
        known_tests |= {
            name for name in dir(broker_module.BrokerTests)
            if name.startswith("test_")
        }
        secret_scan_module = __import__("test_secret_scan")
        known_tests |= {
            name for name in dir(secret_scan_module.CanaryCredentialTests)
            if name.startswith("test_")
        }
        threat_module = __import__("test_threat_corpus")
        known_tests |= {
            name for name in dir(threat_module.ThreatCorpusTests)
            if name.startswith("test_")
        }
        sandbox_module = __import__("test_sandbox")
        known_tests |= {
            name for name in dir(sandbox_module.SandboxTests)
            if name.startswith("test_")
        }
        for invariant in invariants:
            self.assertTrue(invariant["enforcement"])
            self.assertTrue(invariant["tests"])
            for test_name in invariant["tests"]:
                if not test_name.startswith("planned:"):
                    self.assertIn(test_name, known_tests)


class SchemaStructureTests(unittest.TestCase):
    def test_malformed_required_is_rejected_before_instance_check(self):
        schema = {"type": "object", "required": "field", "properties": {"field": {"type": "string"}}}
        with self.assertRaisesRegex(RuntimeError, "invalid schema declaration.*required"):
            validate({"field": "value"}, schema)
        with self.assertRaisesRegex(RuntimeError, "invalid schema declaration.*required"):
            validate_schema(schema)

    def test_malformed_properties_is_rejected_before_instance_check(self):
        schema = {"type": "object", "properties": ["field"]}
        with self.assertRaisesRegex(RuntimeError, "invalid schema declaration.*properties"):
            validate({"field": "value"}, schema)

    def test_truthy_additional_properties_string_does_not_widen_payload(self):
        schema = {
            "type": "object",
            "properties": {"field": {"type": "string"}},
            "additionalProperties": "false",
        }
        with self.assertRaisesRegex(RuntimeError, "invalid schema declaration.*additionalProperties"):
            validate({"field": "value", "evil": "payload"}, schema)

    def test_all_project_schema_files_are_structurally_valid(self):
        for schema_file in sorted((ROOT / "schemas").glob("*.schema.json")):
            with self.subTest(schema=schema_file.name):
                validate_schema(load_json(schema_file))

    def test_boolean_is_not_a_number(self):
        for schema in ({"type": "integer"}, {"type": "integer", "minimum": 0}, {"minimum": 0}):
            for value in (True, False):
                with self.subTest(schema=schema, value=value):
                    with self.assertRaises(ContractValidationError):
                        validate(value, schema)
        validate(0, {"type": "integer", "minimum": 0})
        validate(7, {"type": "integer", "minimum": 0})
        validate(True, {"type": "boolean"})

    def test_boolean_identity_in_numeric_enum(self):
        with self.assertRaisesRegex(ContractValidationError, "not in enum") as raised:
            validate(True, {"enum": [1]})
        self.assertNotIn("True", str(raised.exception))
        with self.assertRaises(ContractValidationError):
            validate(False, {"enum": [0]})
        with self.assertRaises(ContractValidationError):
            validate(True, {"type": "integer", "enum": [1]})
        validate(1, {"enum": [1]})
        validate(True, {"enum": [True, False]})
        validate(False, {"enum": [True, False]})


class CanonicalDigestTests(unittest.TestCase):
    def test_digest_ignores_mapping_key_order(self):
        first = {"process_id": "process-demo-001", "nested": {"b": 2, "a": 1}}
        second = {"nested": {"a": 1, "b": 2}, "process_id": "process-demo-001"}
        self.assertEqual(sha256_digest(first), sha256_digest(second))
        self.assertTrue(sha256_digest(first).startswith("sha256:"))

    def test_digest_supports_unicode_without_escapes(self):
        payload = {"text": "привет 🌐"}
        encoded = canonical_json(payload)
        self.assertIn("🌐".encode("utf-8"), encoded)
        self.assertNotIn(b"\\u", encoded)
        self.assertEqual(sha256_digest(payload), sha256_digest(dict(payload)))

    def test_nan_and_infinity_have_no_digest(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    canonical_json({"value": bad})
                with self.assertRaises(ValueError):
                    sha256_digest({"value": bad})
                with self.assertRaises(ValueError):
                    sha256_digest(bad)


def check_schema_ids(entries: dict[str, str]) -> None:
    seen: dict[str, str] = {}
    for filename in sorted(entries):
        schema_id = entries[filename]
        if schema_id in seen:
            raise ValueError(f"duplicate $id {schema_id!r} in {seen[schema_id]} and {filename}")
        seen[schema_id] = filename
    for filename in sorted(entries):
        schema_id = entries[filename]
        expected = f"https://agent-process.local/schemas/{filename}"
        if not schema_id or schema_id != expected:
            raise ValueError(f"schema {filename} has non-canonical $id: {schema_id!r}")


class SchemaIdTests(unittest.TestCase):
    def test_project_schema_ids_are_unique_and_canonical(self):
        entries = {path.name: load_json(path)["$id"] for path in sorted((ROOT / "schemas").glob("*.schema.json"))}
        self.assertGreaterEqual(len(entries), 20)
        check_schema_ids(entries)

    def test_exotic_object_keys_denied_without_repr(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        for bad in ({1: "x"}, {(1, 2): "y"}, {None: "z"}, {True: "w"},
                    {("caller-secret-001",): "v"}):
            with self.subTest(keys=list(bad)):
                with self.assertRaisesRegex(
                    ContractValidationError, "^\\$: object keys must be strings$"
                ) as raised:
                    validate(bad, schema)
                self.assertNotIn("caller-secret-001", str(raised.exception))
        validate({"a": "x"}, schema)

    def test_nested_unknown_field_rejected_without_value(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "outer": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"known": {"type": "string"}},
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"known": {"type": "string"}},
                    },
                },
            },
        }
        validate({"outer": {"known": "a"}, "items": [{"known": "b"}]}, schema)
        with self.assertRaisesRegex(
            ContractValidationError, "^\\$\\.outer: unknown fields \\['injected'\\]$"
        ) as raised:
            validate({"outer": {"known": "a", "injected": "caller-secret-001"}}, schema)
        self.assertNotIn("caller-secret-001", str(raised.exception))
        with self.assertRaisesRegex(
            ContractValidationError, "^\\$\\.items\\[0\\]: unknown fields \\['injected'\\]$"
        ) as items_raised:
            validate({"items": [{"known": "b", "injected": "caller-secret-002"}]}, schema)
        self.assertNotIn("caller-secret-002", str(items_raised.exception))

    def test_non_mapping_roots_fail_as_contract_errors(self):
        schema = {
            "type": "object",
            "required": ["a"],
            "properties": {"a": {"type": "string"}},
            "additionalProperties": False,
        }
        for bad in (None, 42, [1], "x", True, (("a", "b"),), 3.5):
            with self.subTest(root=type(bad).__name__):
                with self.assertRaises(ContractValidationError) as raised:
                    validate(bad, schema)
                self.assertNotIsInstance(raised.exception, (TypeError, AttributeError))
        validate({"a": "x"}, schema)

    def test_invalid_mapping_keys_fail_without_representation(self):
        for bad in ({1: "a", "b": 2}, {(1, 2): "x"}, {frozenset({"k"}): "y"}):
            with self.subTest(keys=type(next(iter(bad))).__name__):
                with self.assertRaisesRegex(ValueError, "^canonical JSON is not encodable$") as raised:
                    sha256_digest(bad)
                self.assertNotIsInstance(raised.exception, TypeError)
        self.assertEqual(sha256_digest({"b": 2, "a": 1}), sha256_digest({"a": 1, "b": 2}))

    def test_malformed_enum_declaration_rejected_before_instance_check(self):
        for bad in ("allow", 42, {"allow": True}, [], None):
            with self.subTest(enum=bad):
                schema = {"enum": bad}
                with self.assertRaisesRegex(RuntimeError, "invalid schema declaration.*enum"):
                    validate_schema(schema)
                with self.assertRaisesRegex(RuntimeError, "invalid schema declaration.*enum"):
                    validate("allow", schema)
        validate("allow", {"enum": ["allow", "deny"]})

    def test_malformed_type_declaration_rejected_before_instance_check(self):
        for bad in ("number", "", None, 123, ["string"], {"type": "string"}):
            with self.subTest(declaration=bad):
                schema = {"type": bad}
                with self.assertRaisesRegex(RuntimeError, "invalid schema declaration.*unsupported type"):
                    validate_schema(schema)
                with self.assertRaisesRegex(RuntimeError, "invalid schema declaration.*unsupported type"):
                    validate("anything", schema)
        validate("anything", {"type": "string"})

    def test_duplicate_schema_id_is_detected(self):
        with self.assertRaisesRegex(ValueError, "duplicate \\$id"):
            check_schema_ids({
                "a.schema.json": "https://agent-process.local/schemas/a.schema.json",
                "b.schema.json": "https://agent-process.local/schemas/a.schema.json",
            })

    def test_malformed_schema_id_is_detected(self):
        for bad in ("", "https://example.com/schemas/a.schema.json", "a.schema.json"):
            with self.subTest(schema_id=bad):
                with self.assertRaisesRegex(ValueError, "non-canonical \\$id"):
                    check_schema_ids({"a.schema.json": bad})


if __name__ == "__main__":
    unittest.main()
