from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.observation_store import EventConflictError, ObservationStore
from app_contracts.validator import ContractValidationError


def valid_event(event_id: str = "event-store-demo-001", sequence: int = 0) -> dict:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "tool_requested",
        "process_id": "process-store-demo",
        "run_id": "run-store-demo-001",
        "branch_id": "branch-main",
        "task_id": "task-store-demo",
        "agent_id": "agent-worker-001",
        "sequence": sequence,
        "occurred_at": "2026-09-07T12:00:00Z",
        "recorded_at": "2026-09-07T12:00:01Z",
        "classification": "internal",
        "redaction_status": "complete",
    }


def valid_checkpoint(trigger_event_id: str = "event-store-demo-001", cursor: int = 0) -> dict:
    return {
        "schema_version": 1,
        "checkpoint_id": "checkpoint-store-demo-001",
        "kind": "tool_call",
        "process_id": "process-store-demo",
        "run_id": "run-store-demo-001",
        "branch_id": "branch-main",
        "agent_id": "agent-worker-001",
        "trigger_event_id": trigger_event_id,
        "event_cursor": cursor,
        "state_ref": "artifact://states/store-demo-000",
        "completeness": "complete",
        "restore_mode": "simulation",
        "created_at": "2026-09-07T12:00:02Z",
    }


class ObservationStoreTests(unittest.TestCase):
    def test_accepts_only_schema_valid_events(self):
        store = ObservationStore()
        cursor = store.append(valid_event())
        self.assertEqual(cursor, 0)
        self.assertEqual(len(store), 1)
        broken = valid_event(event_id="event-store-demo-002")
        broken["event_type"] = "model_dreamed"
        with self.assertRaises(ContractValidationError):
            store.append(broken)
        self.assertEqual(len(store), 1)

    def test_duplicate_id_with_same_content_is_idempotent(self):
        store = ObservationStore()
        first = store.append(valid_event())
        second = store.append(copy.deepcopy(valid_event()))
        self.assertEqual(first, second)
        self.assertEqual(len(store), 1)
        self.assertEqual(len(store.events()), 1)

    def test_duplicate_id_with_different_content_is_rejected(self):
        store = ObservationStore()
        store.append(valid_event())
        altered = valid_event()
        altered["sequence"] = 99
        with self.assertRaisesRegex(EventConflictError, "event id conflict"):
            store.append(altered)
        self.assertEqual(len(store), 1)

    def test_reads_return_insertion_order_without_mutable_state(self):
        store = ObservationStore()
        store.append(valid_event("event-store-demo-001", 0))
        store.append(valid_event("event-store-demo-002", 1))
        snapshot = store.events()
        self.assertEqual([event["event_id"] for event in snapshot], ["event-store-demo-001", "event-store-demo-002"])
        snapshot[0]["sequence"] = 999
        self.assertEqual(store.events()[0]["sequence"], 0)


    def test_valid_checkpoint_reference_is_accepted_without_payload(self):
        store = ObservationStore()
        store.append(valid_event("event-store-demo-001", 0))
        result = store.check_checkpoint(valid_checkpoint())
        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)

    def test_missing_trigger_event_is_rejected(self):
        store = ObservationStore()
        store.append(valid_event("event-store-demo-001", 0))
        with self.assertRaisesRegex(ContractValidationError, "unknown trigger event"):
            store.check_checkpoint(valid_checkpoint(trigger_event_id="event-store-demo-999"))

    def test_cursor_beyond_journal_end_is_rejected(self):
        store = ObservationStore()
        store.append(valid_event("event-store-demo-001", 0))
        with self.assertRaisesRegex(ContractValidationError, "beyond journal end"):
            store.check_checkpoint(valid_checkpoint(cursor=5))


if __name__ == "__main__":
    unittest.main()
