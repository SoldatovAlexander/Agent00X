from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from app_contracts.brainbooster_target_profile import VERIFIER_CONTEXT_MODULES
from app_contracts.local_model_observer_gate import (
    LocalModelObserverGateError,
    journal_local_model_preflight,
)
from app_contracts.observation_store import ObservationStore, ObservationStoreError
from app_contracts.observer_runtime import JournaledProposalWorker
from build_verifier_host_bundle import _collect_members, build_bundle


def fixed_ids():
    values = iter(f"{number:08x}" for number in range(1, 40))
    return lambda: next(values)


def fixed_clock():
    return lambda: datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def make_journal(store, process_id="process-local-model-observer-001"):
    return JournaledProposalWorker(
        SimpleNamespace(propose=lambda _request: None),
        store,
        process_id=process_id,
        task_id="task-local-model-observer-001",
        id_factory=fixed_ids(),
        clock=fixed_clock(),
    )


class LocalModelObserverGateTests(unittest.TestCase):
    def test_success_is_causally_journaled_and_metadata_is_redacted(self):
        store = ObservationStore()
        journal = make_journal(store)
        metadata = SimpleNamespace(
            version="0.40.3", model="qwen2.5-coder:7b", model_digest="a" * 64
        )
        self.assertIs(
            journal_local_model_preflight(
                journal, lambda: metadata, process_id="process-local-model-observer-001"
            ),
            metadata,
        )
        events = [
            event
            for event in store.events()
            if event.get("decision_or_tool") == "LocalOllamaMetadataPreflight.inspect"
        ]
        self.assertEqual([event["event_type"] for event in events], [
            "tool_requested", "tool_completed"
        ])
        self.assertEqual([event["status"] for event in events], ["pending", "ok"])
        self.assertEqual(events[1]["causal_event_ids"], [events[0]["event_id"]])
        self.assertEqual(events[0]["agent_id"], "service-model-channel")
        self.assertNotIn("0.40.3", repr(events))
        self.assertNotIn("a" * 64, repr(events))

    def test_failure_records_only_fixed_error_code(self):
        store = ObservationStore()
        journal = make_journal(store)
        secret = "SYNTHETIC-METADATA-ERROR-CONTENT"

        def fail():
            raise RuntimeError(secret)

        with self.assertRaises(LocalModelObserverGateError):
            journal_local_model_preflight(
                journal, fail, process_id="process-local-model-observer-001"
            )
        events = store.events()
        terminal = events[-1]
        self.assertEqual(terminal["event_type"], "tool_failed")
        self.assertEqual(terminal["error_code"], "local-model-preflight-failed")
        self.assertNotIn(secret, repr(events))

    def test_resume_or_repeat_cannot_dispatch_a_second_time(self):
        store = ObservationStore()
        journal = make_journal(store)
        process_id = "process-local-model-observer-001"
        run_id = journal.observer_reference()["run_id"]
        journal_local_model_preflight(journal, lambda: True, process_id=process_id)
        journal.finish_agent_invocation(status="ok")
        resumed = JournaledProposalWorker.resume_existing(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id=process_id,
            run_id=run_id,
        )
        calls = []
        with self.assertRaises(LocalModelObserverGateError):
            journal_local_model_preflight(
                resumed, lambda: calls.append("called"), process_id=process_id
            )
        self.assertEqual(calls, [])

    def test_one_shot_journal_refusal_blocks_dispatch(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint_and_intent_once(self, checkpoint, intent):
                raise ObservationStoreError("synthetic refusal")

        store = RefusingStore()
        journal = make_journal(store)
        calls = []
        with self.assertRaises(LocalModelObserverGateError):
            journal_local_model_preflight(
                journal,
                lambda: calls.append("called"),
                process_id="process-local-model-observer-001",
            )
        self.assertEqual(calls, [])
        self.assertEqual(len(store.events()), 1)
        self.assertEqual(store.events()[0]["event_type"], "agent_started")
        self.assertEqual(len(store.checkpoints()), 0)

    def test_worker_gate_module_is_not_in_verifier_context_or_bundle(self):
        self.assertNotIn("local_model_observer_gate.py", VERIFIER_CONTEXT_MODULES)
        _archive, _digest, _members, _size = build_bundle(ROOT)
        from scripts import build_verifier_host_bundle  # noqa: PLC0415

        names = {member.name for member in _collect_members(ROOT)}
        self.assertNotIn(
            "src/app_contracts/local_model_observer_gate.py",
            names,
        )


if __name__ == "__main__":
    unittest.main()
