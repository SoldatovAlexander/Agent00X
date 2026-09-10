from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.validator import ContractValidationError, validate


def load_schema() -> dict:
    with (ROOT / "schemas" / "observation-event.schema.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def valid_event() -> dict:
    return {
        "schema_version": 1,
        "event_id": "event-observer-demo-001",
        "event_type": "tool_requested",
        "process_id": "process-observer-demo",
        "run_id": "run-observer-demo-001",
        "branch_id": "branch-main",
        "task_id": "task-observer-demo",
        "agent_id": "agent-worker-001",
        "parent_agent_id": "agent-supervisor-001",
        "sequence": 7,
        "occurred_at": "2026-09-07T12:00:00Z",
        "recorded_at": "2026-09-07T12:00:01Z",
        "causal_event_ids": ["event-observer-demo-000"],
        "checkpoint_id": "checkpoint-observer-demo-001",
        "invocation_id": "invocation-observer-demo-001",
        "state_version": 3,
        "agent_build_id": "build-reference-worker-v1",
        "procedure_version": "procedure-repository-change-v1",
        "input_refs": ["artifact://snapshots/observer-demo"],
        "decision_or_tool": "workspace.read",
        "safe_parameters": {"path": "calculator.py", "max_bytes": 4096},
        "rationale": "Read the declared workspace file before proposing a change.",
        "expected_result": "File content is available for the change proposal.",
        "authority_refs": ["artifact://grants/observer-demo"],
        "status": "pending",
        "classification": "internal",
        "redaction_status": "complete",
    }


class ObservationEventContractTests(unittest.TestCase):
    def test_valid_event_conforms_to_schema(self):
        validate(valid_event(), load_schema())

    def test_unknown_field_is_rejected(self):
        event = valid_event()
        event["unexpected_field"] = "not-allowed"
        with self.assertRaisesRegex(ContractValidationError, "unknown fields"):
            validate(event, load_schema())

    def test_invalid_event_type_is_rejected(self):
        event = valid_event()
        event["event_type"] = "model_dreamed"
        with self.assertRaisesRegex(ContractValidationError, "not in enum"):
            validate(event, load_schema())

    def test_invalid_event_id_is_rejected(self):
        event = valid_event()
        event["event_id"] = "not-an-event-id"
        with self.assertRaisesRegex(ContractValidationError, "pattern mismatch"):
            validate(event, load_schema())

    def test_invalid_timestamp_is_rejected(self):
        event = valid_event()
        event["occurred_at"] = "not-a-time"
        with self.assertRaisesRegex(ContractValidationError, "invalid date-time"):
            validate(event, load_schema())

    def test_service_identity_is_accepted_without_secrets_or_prompts(self):
        event = valid_event()
        event["agent_id"] = "service-collector-001"
        del event["parent_agent_id"]
        validate(event, load_schema())
        payload = json.dumps(event)
        for forbidden in ("token", "secret", "BEGIN PRIVATE KEY", "system prompt"):
            self.assertNotIn(forbidden, payload)
        self.assertEqual(copy.deepcopy(event)["agent_id"], "service-collector-001")


if __name__ == "__main__":
    unittest.main()
