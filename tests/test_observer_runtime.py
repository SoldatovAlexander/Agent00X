from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import (
    ExecutionRequest,
    ExecutionStatus,
    VerifierResult,
    VerifierVerdict,
    WorkerProposal,
    WorkerTerminalOutcome,
    run_local_execution,
)
from app_contracts.brainbooster_target_profile import (
    PINNED_HTTP_DB_FAILURE_CODES,
    PINNED_HTTP_DB_TEST_COMMAND,
)
from app_contracts.observation_store import (
    ObservationStore,
    ObservationStoreError,
    SQLiteObservationStore,
)
from app_contracts.observer_report import build_history_report, report_from_sqlite
from app_contracts.observer_runtime import (
    VerifierCallFailedError,
    VerifierJournalError,
    VerifierOutcomeUnknownError,
    JournaledProposalWorker,
    SandboxCallFailedError,
    SandboxJournalError,
    SandboxOutcomeUnknownError,
    SnapshotPinDecisionError,
    SnapshotPinDecisionOutcomeUnknownError,
    ExecutionAuthorizationJournalError,
    ExecutionAuthorizationOutcomeUnknownError,
    ControlledPublicationJournalError,
    ControlledPublicationOutcomeUnknownError,
    JournaledModelChannel,
    SnapshotJournalError,
    SnapshotOutcomeUnknownError,
    StageCallFailedError,
    StageJournalError,
    StageOutcomeUnknownError,
    WorkerJournalError,
    WorkerOutcomeUnknownError,
    WorkerProposalFailedError,
)


def fixed_ids():
    values = iter(f"{number:08x}" for number in range(1, 33))
    return lambda: next(values)


def fixed_clock():
    return lambda: datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


class ObserverRuntimeTests(unittest.TestCase):
    def test_invocation_and_run_finish_are_explicit_one_shot_events(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-lifecycle-demo",
            task_id="task-lifecycle-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        started = store.events()[0]
        self.assertTrue(started["invocation_id"].startswith("invocation-"))
        with self.assertRaises(WorkerJournalError):
            JournaledProposalWorker.resume_existing(
                SimpleNamespace(propose=lambda _request: None),
                store,
                process_id="process-lifecycle-demo",
                run_id=started["run_id"],
                id_factory=fixed_ids(),
                clock=fixed_clock(),
            )

        invocation_ref = run.finish_agent_invocation(status="ok")
        with self.assertRaises(WorkerJournalError):
            run.finish_agent_invocation(status="ok")
        run_ref = run.finish_run(status="ok")
        with self.assertRaises(WorkerJournalError):
            run.finish_run(status="ok")
        with self.assertRaises(WorkerJournalError):
            run.record_snapshot_pin_decision(True)
        with self.assertRaises(WorkerJournalError):
            JournaledProposalWorker.resume_existing(
                SimpleNamespace(propose=lambda _request: None),
                store,
                process_id="process-lifecycle-demo",
                run_id=run_ref["run_id"],
                id_factory=fixed_ids(),
                clock=fixed_clock(),
            )

        events = store.events()
        self.assertEqual(events[-2]["event_type"], "agent_finished")
        self.assertEqual(events[-2]["invocation_id"], started["invocation_id"])
        self.assertEqual(events[-2]["causal_event_ids"], [started["event_id"]])
        self.assertEqual(events[-1]["event_type"], "run_finished")
        self.assertEqual(events[-1]["status"], "ok")
        self.assertEqual(invocation_ref["as_of_cursor"], len(events) - 2)
        self.assertEqual(run_ref["as_of_cursor"], len(events) - 1)

        report = build_history_report(
            list(enumerate(events)), list(enumerate(store.checkpoints()))
        )
        self.assertEqual(report["facts"][-1]["event_type"], "run_finished")
        self.assertFalse(any("approval" in str(fact).lower() for fact in report["facts"][-1:]))

    def test_finish_refuses_unresolved_intent(self):
        class TerminalFailureStore(ObservationStore):
            def append(self, event):
                if event.get("event_type") == "decision_applied":
                    raise RuntimeError("synthetic append failure")
                return super().append(event)

        store = TerminalFailureStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-unresolved-demo",
            task_id="task-unresolved-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        with self.assertRaises(SnapshotPinDecisionOutcomeUnknownError):
            run.record_snapshot_pin_decision(True)
        with self.assertRaises(WorkerJournalError):
            run.finish_agent_invocation(status="ok")
        self.assertEqual(store.events()[-1]["event_type"], "decision_proposed")

    def test_legacy_resume_preserves_missing_lifecycle_gap_and_links_new_start(self):
        store = ObservationStore()
        legacy_start = {
            "schema_version": 1,
            "event_id": "event-legacy-start",
            "event_type": "agent_started",
            "process_id": "process-legacy-demo",
            "run_id": "run-legacy-demo",
            "branch_id": "branch-main",
            "task_id": "task-legacy-demo",
            "agent_id": "service-worker",
            "sequence": 0,
            "occurred_at": "2026-10-19T00:00:00Z",
            "recorded_at": "2026-10-19T00:00:00Z",
            "classification": "internal",
            "redaction_status": "complete",
        }
        store.append(legacy_start)
        resumed = JournaledProposalWorker.resume_existing(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-legacy-demo",
            run_id="run-legacy-demo",
            id_factory=lambda values=iter(("legacy0001", "legacy0002")): next(values),
            clock=fixed_clock(),
        )
        events = store.events()
        self.assertNotIn("invocation_id", events[0])
        self.assertEqual(events[1]["event_type"], "agent_started")
        self.assertEqual(events[1]["sequence"], 1)
        self.assertEqual(events[1]["causal_event_ids"], [legacy_start["event_id"]])
        self.assertEqual(resumed.observer_reference()["as_of_cursor"], 1)
        report = build_history_report(
            list(enumerate(events)), list(enumerate(store.checkpoints()))
        )
        self.assertIn(
            "agent_invocation_id_missing",
            {gap["code"] for gap in report["gaps"]},
        )

    def test_resume_rejects_repeated_agent_invocation_id(self):
        store = ObservationStore()
        first = {
            "schema_version": 1,
            "event_id": "event-repeat-start-one",
            "event_type": "agent_started",
            "process_id": "process-repeat-demo",
            "run_id": "run-repeat-demo",
            "branch_id": "branch-main",
            "task_id": "task-repeat-demo",
            "agent_id": "service-worker",
            "sequence": 0,
            "occurred_at": "2026-10-19T00:00:00Z",
            "recorded_at": "2026-10-19T00:00:00Z",
            "invocation_id": "invocation-repeat-demo",
            "classification": "internal",
            "redaction_status": "complete",
        }
        second = dict(first)
        second.update(
            {
                "event_id": "event-repeat-start-two",
                "sequence": 1,
                "causal_event_ids": [first["event_id"]],
            }
        )
        store.append(first)
        store.append(second)
        with self.assertRaises(WorkerJournalError):
            JournaledProposalWorker.resume_existing(
                SimpleNamespace(propose=lambda _request: None),
                store,
                process_id="process-repeat-demo",
                run_id="run-repeat-demo",
                id_factory=fixed_ids(),
                clock=fixed_clock(),
            )
        self.assertEqual(len(store.events()), 2)

    def test_resume_rejects_tampered_event_and_checkpoint_causality(self):
        for tamper in ("event", "checkpoint"):
            with self.subTest(tamper=tamper):
                store = ObservationStore()
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: None),
                    store,
                    process_id=f"process-causality-{tamper}",
                    task_id=f"task-causality-{tamper}",
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                run.record_snapshot_pin_decision(True)
                run.finish_agent_invocation(status="ok")
                run_id = run.observer_reference()["run_id"]
                if tamper == "event":
                    terminal_index = next(
                        index for index, event in enumerate(store._events)
                        if event.get("event_type") == "decision_applied"
                    )
                    store._events[terminal_index]["causal_event_ids"] = ["event-foreign"]
                else:
                    store._checkpoints[0]["trigger_event_id"] = "event-foreign"
                before = len(store.events())
                with self.assertRaises(WorkerJournalError):
                    JournaledProposalWorker.resume_existing(
                        SimpleNamespace(propose=lambda _request: None),
                        store,
                        process_id=f"process-causality-{tamper}",
                        run_id=run_id,
                        id_factory=fixed_ids(),
                        clock=fixed_clock(),
                    )
                self.assertEqual(len(store.events()), before)

    def test_model_channel_is_checkpointed_without_retaining_request_or_response(self):
        store = ObservationStore()
        calls = []
        private_request = "private-model-request-marker"
        private_response = "private-model-response-marker"

        class ModelChannel:
            def create_chat_completion(self, payload, *, timeout_seconds):
                events = store.events()
                calls.append((payload, timeout_seconds, events[-1]["event_type"]))
                return {"private_response": private_response}

        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-model-call-001",
            task_id="task-model-call-001",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        channel = JournaledModelChannel(ModelChannel())
        channel.bind(run)
        payload = {"messages": [{"content": private_request}]}

        result = channel.create_chat_completion(payload, timeout_seconds=17)

        self.assertEqual(result, {"private_response": private_response})
        self.assertEqual(calls, [(payload, 17, "tool_requested")])
        events = store.events()
        model_events = [
            event for event in events
            if event.get("decision_or_tool") == "ModelChannel.create_chat_completion"
        ]
        self.assertEqual([event["event_type"] for event in model_events], [
            "tool_requested", "tool_completed"
        ])
        self.assertEqual(model_events[0]["status"], "pending")
        self.assertEqual(model_events[1]["status"], "ok")
        self.assertEqual(
            model_events[1]["causal_event_ids"], [model_events[0]["event_id"]]
        )
        serialized_events = repr(events)
        self.assertNotIn(private_request, serialized_events)
        self.assertNotIn(private_response, serialized_events)
        self.assertEqual(run.observer_reference()["as_of_cursor"], 2)

        with self.assertRaises(ControlledPublicationJournalError):
            channel.create_chat_completion(payload, timeout_seconds=17)
        self.assertEqual(len(calls), 1)
        run.finish_agent_invocation(status="ok")

        resumed = JournaledProposalWorker.resume_existing(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-model-call-001",
            run_id=run.observer_reference()["run_id"],
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        resumed_channel = JournaledModelChannel(ModelChannel())
        resumed_channel.bind(resumed)
        with self.assertRaises(ControlledPublicationJournalError):
            resumed_channel.create_chat_completion(payload, timeout_seconds=17)
        self.assertEqual(len(calls), 1)

    def test_model_channel_cannot_dispatch_until_bound_to_observer_run(self):
        calls = []

        class ModelChannel:
            def create_chat_completion(self, payload, *, timeout_seconds):
                calls.append(True)
                return None

        channel = JournaledModelChannel(ModelChannel())
        with self.assertRaises(ControlledPublicationJournalError):
            channel.create_chat_completion({}, timeout_seconds=1)
        self.assertEqual(calls, [])

    def test_terminal_worker_result_journals_only_fixed_outcome_code(self):
        store = ObservationStore()
        worker = JournaledProposalWorker(
            SimpleNamespace(
                propose=lambda _request: WorkerTerminalOutcome(
                    "blocked", "target_test_outcome_unknown"
                )
            ),
            store,
            process_id="process-terminal-outcome-001",
            task_id="task-terminal-outcome-001",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        result = worker.propose(
            SimpleNamespace(
                process_id="process-terminal-outcome-001",
                task_id="task-terminal-outcome-001",
            )
        )
        self.assertEqual(result.outcome, "blocked")
        completed = [
            event
            for event in store.events()
            if event.get("event_type") == "tool_completed"
        ]
        self.assertEqual(len(completed), 1)
        self.assertEqual(
            completed[0]["safe_parameters"], {"worker_outcome": "blocked"}
        )
        self.assertNotIn("target_test_outcome_unknown", str(completed[0]))

    def test_terminal_worker_result_journal_failure_is_unknown(self):
        class FailTerminalStore(ObservationStore):
            def append(self, event):
                if event.get("event_type") == "tool_completed":
                    raise RuntimeError("synthetic journal failure")
                return super().append(event)

        store = FailTerminalStore()
        worker = JournaledProposalWorker(
            SimpleNamespace(
                propose=lambda _request: WorkerTerminalOutcome(
                    "denied", "publication_not_authorized"
                )
            ),
            store,
            process_id="process-terminal-journal-001",
            task_id="task-terminal-journal-001",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        with self.assertRaises(WorkerOutcomeUnknownError):
            worker.propose(
                SimpleNamespace(
                    process_id="process-terminal-journal-001",
                    task_id="task-terminal-journal-001",
                )
            )

    def test_resume_existing_preserves_run_sequence_and_one_shot_flags(self):
        store = ObservationStore()
        original = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-resume-001",
            task_id="task-resume-001",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        self.assertTrue(original.record_snapshot_pin_decision(True))
        original.finish_agent_invocation(status="ok")
        before = original.observer_reference()
        resumed = JournaledProposalWorker.resume_existing(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-resume-001",
            run_id=before["run_id"],
            id_factory=(lambda values=iter(
                tuple(f"resume{number:04d}" for number in range(1, 25))
            ): next(values)),
            clock=fixed_clock(),
        )
        self.assertEqual(resumed.observer_reference()["run_id"], before["run_id"])
        self.assertEqual(resumed.observer_reference()["as_of_cursor"], before["as_of_cursor"] + 1)
        with self.assertRaises(SnapshotPinDecisionError):
            resumed.record_snapshot_pin_decision(True)
        self.assertTrue(
            resumed.run_controlled_step(
                "Approval.validate", lambda: True, process_id="process-resume-001"
            )
        )
        events = store.events()
        run_events = [event for event in events if event["run_id"] == before["run_id"]]
        self.assertEqual(
            [event["sequence"] for event in run_events],
            list(range(len(run_events))),
        )
        self.assertEqual(resumed.observer_reference()["run_id"], before["run_id"])
        self.assertGreater(
            resumed.observer_reference()["as_of_cursor"], before["as_of_cursor"]
        )

    def test_resume_existing_rejects_foreign_pending_or_publication_history(self):
        store = ObservationStore()
        original = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-resume-002",
            task_id="task-resume-002",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run_id = original.observer_reference()["run_id"]
        with self.assertRaises(WorkerJournalError):
            JournaledProposalWorker.resume_existing(
                SimpleNamespace(propose=lambda _request: None),
                store,
                process_id="process-other-002",
                run_id=run_id,
            )

        class LoseDecisionTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-publication-observer"
                    and event.get("event_type") == "decision_applied"
                ):
                    raise RuntimeError("synthetic terminal loss")
                return super().append(event)

        pending_store = LoseDecisionTerminalStore()
        pending_run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            pending_store,
            process_id="process-resume-003",
            task_id="task-resume-003",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        pending_id = pending_run.observer_reference()["run_id"]
        with self.assertRaises(ControlledPublicationOutcomeUnknownError):
            pending_run.run_controlled_step(
                "Approval.validate",
                lambda: True,
                process_id="process-resume-003",
            )
        with self.assertRaises(WorkerJournalError):
            JournaledProposalWorker.resume_existing(
                SimpleNamespace(propose=lambda _request: None),
                pending_store,
                process_id="process-resume-003",
                run_id=pending_id,
            )

        original.run_local_mock_publication(
            lambda: "mock receipt", process_id="process-resume-002"
        )
        with self.assertRaises(WorkerJournalError):
            JournaledProposalWorker.resume_existing(
                SimpleNamespace(propose=lambda _request: None),
                store,
                process_id="process-resume-002",
                run_id=run_id,
            )

    def test_resume_publication_claim_is_one_shot_across_sqlite_handles(self):
        with tempfile.TemporaryDirectory(prefix="observer-resume-claim-") as temporary:
            path = Path(temporary) / "observer.sqlite3"
            with SQLiteObservationStore(path) as initial_store:
                original = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: None),
                    initial_store,
                    process_id="process-resume-004",
                    task_id="task-resume-004",
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                original.finish_agent_invocation(status="ok")
                run_id = original.observer_reference()["run_id"]

            left_store = SQLiteObservationStore(path)
            right_store = SQLiteObservationStore(path)
            try:
                left = JournaledProposalWorker.resume_existing(
                    SimpleNamespace(propose=lambda _request: None),
                    left_store,
                    process_id="process-resume-004",
                    run_id=run_id,
                )
                with self.assertRaises(WorkerJournalError):
                    JournaledProposalWorker.resume_existing(
                        SimpleNamespace(propose=lambda _request: None),
                        right_store,
                        process_id="process-resume-004",
                        run_id=run_id,
                    )
                calls = []
                left.run_local_mock_publication(
                    lambda: calls.append("first") or "mock receipt",
                    process_id="process-resume-004",
                )
                with self.assertRaises(ControlledPublicationJournalError):
                    left.run_local_mock_publication(
                        lambda: calls.append("duplicate") or "mock receipt",
                        process_id="process-resume-004",
                    )
                self.assertEqual(calls, ["first"])
            finally:
                left_store.close()
                right_store.close()

    def test_controlled_publication_steps_have_fixed_redacted_outcomes(self):
        steps = (
            "Approval.validate",
            "PolicyEngine.evaluate",
            "Gateway.authorize",
            "CredentialBroker.open-channel",
            "Publication.dispatch",
        )
        for index, step in enumerate(steps):
            with self.subTest(step=step):
                store = ObservationStore()
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: None),
                    store,
                    process_id="process-publication-gate-001",
                    task_id="task-publication-gate-001",
                    id_factory=(
                        lambda values=iter(
                            f"{number:08x}" for number in range(index * 40 + 1, index * 40 + 33)
                        ): next(values)
                    ),
                    clock=fixed_clock(),
                )
                called = []
                self.assertEqual(
                    run.run_controlled_step(
                        step,
                        lambda: called.append(step) or True,
                        process_id="process-publication-gate-001",
                    ),
                    True,
                )
                self.assertEqual(called, [step])
                events = [
                    event for event in store.events()
                    if event.get("agent_id") == "service-publication-observer"
                ]
                self.assertEqual(len(events), 2)
                self.assertEqual(events[0]["status"], "pending")
                self.assertEqual(events[1]["status"], "ok")
                self.assertEqual(events[1]["causal_event_ids"], [events[0]["event_id"]])
                self.assertEqual(events[0]["decision_or_tool"], step)
                self.assertEqual(events[1]["decision_or_tool"], step)

    def test_resume_preserves_worker_proposal_validation_one_shot_flag(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-proposal-validation-resume",
            task_id="task-proposal-validation-resume",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run_id = run.observer_reference()["run_id"]
        run.run_controlled_step(
            "WorkerProposal.validate",
            lambda: True,
            process_id="process-proposal-validation-resume",
        )
        run.finish_agent_invocation(status="ok")
        resumed = JournaledProposalWorker.resume_existing(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-proposal-validation-resume",
            run_id=run_id,
        )
        with self.assertRaises(ControlledPublicationJournalError):
            resumed.run_controlled_step(
                "WorkerProposal.validate",
                lambda: True,
                process_id="process-proposal-validation-resume",
            )
        self.assertTrue(
            resumed.run_controlled_step(
                "Approval.validate",
                lambda: True,
                process_id="process-proposal-validation-resume",
            )
        )

    def test_resume_preserves_prepared_binding_validation_one_shot_flag(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-prepared-binding-resume",
            task_id="task-prepared-binding-resume",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run_id = run.observer_reference()["run_id"]
        run.run_controlled_step(
            "PreparedChange.validate-binding",
            lambda: True,
            process_id="process-prepared-binding-resume",
        )
        run.finish_agent_invocation(status="ok")
        resumed = JournaledProposalWorker.resume_existing(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-prepared-binding-resume",
            run_id=run_id,
        )
        with self.assertRaises(ControlledPublicationJournalError):
            resumed.run_controlled_step(
                "PreparedChange.validate-binding",
                lambda: True,
                process_id="process-prepared-binding-resume",
            )
        self.assertTrue(
            resumed.run_controlled_step(
                "Approval.validate",
                lambda: True,
                process_id="process-prepared-binding-resume",
            )
        )

    def test_resume_preserves_sandbox_snapshot_binding_one_shot_flag(self):
        store = ObservationStore()
        process_id = "process-sandbox-binding-resume"
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id=process_id,
            task_id="task-sandbox-binding-resume",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run_id = run.observer_reference()["run_id"]
        run.run_controlled_step(
            "SandboxSnapshot.validate-binding",
            lambda: True,
            process_id=process_id,
        )
        run.finish_agent_invocation(status="ok")
        resumed = JournaledProposalWorker.resume_existing(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id=process_id,
            run_id=run_id,
        )
        with self.assertRaises(ControlledPublicationJournalError):
            resumed.run_controlled_step(
                "SandboxSnapshot.validate-binding",
                lambda: True,
                process_id=process_id,
            )
        self.assertTrue(
            resumed.run_controlled_step(
                "Approval.validate",
                lambda: True,
                process_id=process_id,
            )
        )

    def test_resume_preserves_proposal_application_one_shot_flag(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-proposal-application-resume",
            task_id="task-proposal-application-resume",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run_id = run.observer_reference()["run_id"]
        run.run_controlled_step(
            "PreparedChange.apply-proposal",
            lambda: True,
            process_id="process-proposal-application-resume",
        )
        run.finish_agent_invocation(status="ok")
        resumed = JournaledProposalWorker.resume_existing(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-proposal-application-resume",
            run_id=run_id,
        )
        with self.assertRaises(ControlledPublicationJournalError):
            resumed.run_controlled_step(
                "PreparedChange.apply-proposal",
                lambda: True,
                process_id="process-proposal-application-resume",
            )
        self.assertTrue(
            resumed.run_controlled_step(
                "Approval.validate",
                lambda: True,
                process_id="process-proposal-application-resume",
            )
        )

    def test_controlled_publication_gate_journal_refusal_blocks_each_dispatch(self):
        class RefusingStepStore(ObservationStore):
            blocked_state_ref = ""

            def record_checkpoint_and_intent(self, checkpoint, intent):
                if checkpoint["state_ref"].endswith(self.blocked_state_ref):
                    raise ObservationStoreError("synthetic step refusal")
                return super().record_checkpoint_and_intent(checkpoint, intent)

        steps = (
            "Approval.validate",
            "PolicyEngine.evaluate",
            "Gateway.authorize",
            "CredentialBroker.open-channel",
            "Publication.dispatch",
        )
        for index, step in enumerate(steps):
            with self.subTest(step=step):
                store = RefusingStepStore()
                store.blocked_state_ref = f"publication-{step.lower().replace('.', '-')}"
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: None),
                    store,
                    process_id="process-publication-gate-002",
                    task_id="task-publication-gate-002",
                    id_factory=(
                        lambda values=iter(
                            f"{number:08x}" for number in range(index * 40 + 1, index * 40 + 33)
                        ): next(values)
                    ),
                    clock=fixed_clock(),
                )
                called = []
                with self.assertRaises(ControlledPublicationJournalError):
                    run.run_controlled_step(
                        step,
                        lambda: called.append(step) or True,
                        process_id="process-publication-gate-002",
                    )
                self.assertEqual(called, [])

    def test_controlled_publication_terminal_loss_is_unknown_without_retry(self):
        class LoseTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-publication-observer"
                    and event.get("event_type") == "tool_completed"
                ):
                    raise RuntimeError("synthetic terminal loss")
                return super().append(event)

        store = LoseTerminalStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-publication-gate-003",
            task_id="task-publication-gate-003",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        calls = []
        with self.assertRaises(ControlledPublicationOutcomeUnknownError):
            run.run_controlled_step(
                "Publication.dispatch",
                lambda: calls.append("published") or object(),
                process_id="process-publication-gate-003",
            )
        self.assertEqual(calls, ["published"])
        self.assertFalse(run.publication_dispatch_completed_cleanly())

    def test_publication_dispatch_exception_is_recorded_as_unknown(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-publication-unknown-001",
            task_id="task-publication-unknown-001",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        with self.assertRaisesRegex(OSError, "synthetic lost response"):
            run.run_controlled_step(
                "Publication.dispatch",
                lambda: (_ for _ in ()).throw(OSError("synthetic lost response")),
                process_id="process-publication-unknown-001",
            )
        publication_terminal = [
            event for event in store.events()
            if event.get("decision_or_tool") == "Publication.dispatch"
            and event.get("event_type") == "outcome_unknown"
        ]
        self.assertEqual(len(publication_terminal), 1)
        self.assertEqual(publication_terminal[0]["status"], "unknown")
        self.assertFalse(run.publication_dispatch_completed_cleanly())

    def test_controlled_gate_denial_is_redacted_and_does_not_continue(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-publication-gate-004",
            task_id="task-publication-gate-004",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        marker = "SYNTHETIC-APPROVAL-DETAIL"
        calls = []

        def reject():
            calls.append("checked")
            raise RuntimeError(marker)

        with self.assertRaisesRegex(RuntimeError, marker):
            run.run_controlled_step(
                "Approval.validate",
                reject,
                process_id="process-publication-gate-004",
            )
        self.assertEqual(calls, ["checked"])
        events = [
            event for event in store.events()
            if event.get("agent_id") == "service-publication-observer"
        ]
        self.assertEqual(events[-1]["event_type"], "decision_applied")
        self.assertEqual(events[-1]["status"], "denied")
        self.assertEqual(events[-1]["error_code"], "publication-gate-denied")
        self.assertNotIn(marker, repr(events))

    def test_execution_authorization_is_checkpointed_before_permit_consumption(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-execution-auth-001",
            task_id="task-execution-auth-001",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        calls = []

        def consume():
            events = store.events()
            self.assertEqual(events[-1]["event_type"], "decision_proposed")
            self.assertEqual(events[-1]["decision_or_tool"], "RemoteExecutionPermit.consume")
            self.assertEqual(len(store.checkpoints()), 1)
            calls.append("consumed")

        self.assertTrue(run.record_execution_authorization(consume))
        events = store.events()
        self.assertEqual(calls, ["consumed"])
        self.assertEqual(
            [event["event_type"] for event in events],
            ["agent_started", "decision_proposed", "decision_applied"],
        )
        self.assertEqual(events[-1]["status"], "ok")
        self.assertEqual(events[-1]["causal_event_ids"], [events[-2]["event_id"]])
        self.assertNotIn("card", repr(events))
        with self.assertRaises(ExecutionAuthorizationJournalError):
            run.record_execution_authorization(consume)

    def test_execution_authorization_denial_and_journal_failures_are_bounded(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint(self, _checkpoint):
                raise ObservationStoreError("synthetic authorization gate refusal")

        class LoseTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-execution-authorizer"
                    and event.get("event_type") == "decision_applied"
                ):
                    raise RuntimeError("SYNTHETIC-authorization-terminal-loss")
                return super().append(event)

        denied_store = ObservationStore()
        denied_run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            denied_store,
            process_id="process-execution-auth-002",
            task_id="task-execution-auth-002",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        self.assertFalse(
            denied_run.record_execution_authorization(
                lambda: (_ for _ in ()).throw(RuntimeError("SECRET-CANARY"))
            )
        )
        denied = denied_store.events()[-1]
        self.assertEqual(denied["event_type"], "decision_applied")
        self.assertEqual(denied["status"], "denied")
        self.assertEqual(denied["error_code"], "execution-authorization-unavailable")
        self.assertNotIn("SECRET-CANARY", repr(denied_store.events()))

        for store, error_type in (
            (RefusingStore(), ExecutionAuthorizationJournalError),
            (LoseTerminalStore(), ExecutionAuthorizationOutcomeUnknownError),
        ):
            with self.subTest(error=error_type.__name__):
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: None),
                    store,
                    process_id="process-execution-auth-003",
                    task_id="task-execution-auth-003",
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                calls = []
                with self.assertRaises(error_type):
                    run.record_execution_authorization(
                        lambda: calls.append("consumed")
                    )
                self.assertEqual(calls, [] if isinstance(store, RefusingStore) else ["consumed"])

    def test_snapshot_pin_decision_is_bounded_and_checkpointed(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-snapshot-pin-001",
            task_id="task-snapshot-pin-001",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )

        self.assertTrue(run.record_snapshot_pin_decision(True))
        events = store.events()
        checkpoints = store.checkpoints()
        self.assertEqual(
            [event["event_type"] for event in events],
            ["agent_started", "decision_proposed", "decision_applied"],
        )
        self.assertEqual(events[1]["decision_or_tool"], "PinnedSnapshot.validate-fixed-pin")
        self.assertEqual(events[2]["status"], "ok")
        self.assertEqual(events[2]["causal_event_ids"], [events[1]["event_id"]])
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0]["kind"], "decision")
        serialized = repr(events) + repr(checkpoints)
        for marker in ("OwnerCanary", "RepoCanary", "commit-canary", "digest-canary"):
            self.assertNotIn(marker, serialized)
        with self.assertRaises(SnapshotPinDecisionError):
            run.record_snapshot_pin_decision(True)

    def test_rejected_snapshot_pin_decision_is_recorded(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-snapshot-pin-002",
            task_id="task-snapshot-pin-002",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )

        self.assertFalse(run.record_snapshot_pin_decision(False))
        events = store.events()
        self.assertEqual(events[-1]["event_type"], "decision_applied")
        self.assertEqual(events[-1]["status"], "denied")
        self.assertEqual(events[-1]["error_code"], "pinned-snapshot-rejected")

    def test_snapshot_pin_decision_gate_refusal_and_unknown_terminal_fail_closed(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint(self, _checkpoint):
                raise RuntimeError("synthetic gate refusal")

        class LoseDecisionTerminalStore(ObservationStore):
            def append(self, event):
                if event.get("event_type") == "decision_applied":
                    raise RuntimeError("synthetic storage loss")
                return super().append(event)

        for store, expected in (
            (RefusingStore(), SnapshotPinDecisionError),
            (LoseDecisionTerminalStore(), SnapshotPinDecisionOutcomeUnknownError),
        ):
            with self.subTest(error=expected.__name__):
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: None),
                    store,
                    process_id="process-snapshot-pin-003",
                    task_id="task-snapshot-pin-003",
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                with self.assertRaises(expected):
                    run.record_snapshot_pin_decision(True)

    def test_worker_intent_and_checkpoint_are_persisted_before_proposal(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "observations.sqlite3"
            with SQLiteObservationStore(database) as store:
                class FakeWorker:
                    calls = 0

                    def propose(self, worker_input):
                        self.calls += 1
                        events = store.events()
                        checkpoints = store.checkpoints()
                        self_before = [event["event_type"] for event in events]
                        if self_before != ["agent_started", "tool_requested"]:
                            raise AssertionError("intent was not persisted first")
                        if len(checkpoints) != 1:
                            raise AssertionError("checkpoint was not persisted first")
                        return {"synthetic-proposal": True}

                worker = FakeWorker()
                wrapped = JournaledProposalWorker(
                    worker,
                    store,
                    process_id="process-observer-demo",
                    task_id="task-observer-demo",
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                result = wrapped.propose(
                    type(
                        "WorkerInput",
                        (),
                        {
                            "process_id": "process-observer-demo",
                            "task_id": "task-observer-demo",
                        },
                    )()
                )
                self.assertEqual(result, {"synthetic-proposal": True})
                self.assertEqual(worker.calls, 1)
                events = store.events()
                self.assertEqual(
                    [event["event_type"] for event in events],
                    ["agent_started", "tool_requested", "tool_completed"],
                )
                self.assertEqual(events[1]["status"], "pending")
                self.assertEqual(events[2]["status"], "ok")
                self.assertEqual(events[2]["causal_event_ids"], [events[1]["event_id"]])
                report = report_from_sqlite(database)
                self.assertEqual(report["snapshot"]["event_count"], 3)
                self.assertEqual(report["snapshot"]["checkpoint_count"], 1)

    def test_executor_uses_journaled_worker_adapter(self):
        source = ROOT / "fixtures" / "repository" / "project"
        calculator = (source / "calculator.py").read_text(encoding="utf-8")
        process_id = "process-observed-executor"
        task_id = "task-observed-executor"
        request = ExecutionRequest(
            process_id=process_id,
            task_id=task_id,
            repository_id="fixture-repository",
            base_commit="fixture-observer-base",
            snapshot_path=source,
            allowed_commands=frozenset({Path(sys.executable).name}),
            declared_change_paths=("calculator.py",),
            test_command=(sys.executable, "-c", "pass"),
        )
        store = ObservationStore()
        worker_failures = []

        class FakeWorker:
            def propose(self, worker_input):
                try:
                    events = store.events()
                    if [event["event_type"] for event in events] != [
                        "agent_started",
                        "tool_requested",
                        "tool_completed",
                        "tool_requested",
                    ]:
                        raise AssertionError("sandbox creation was not observed first")
                    if events[-3]["decision_or_tool"] != "SandboxBackend.create.target-execution":
                        raise AssertionError("executor bypassed the sandbox lifecycle gate")
                    if len(store.checkpoints()) != 2:
                        raise AssertionError("sandbox creation lacked a checkpoint")
                    return WorkerProposal((("calculator.py", calculator + "\n# observed\n"),))
                except Exception as exc:
                    worker_failures.append(repr(exc))
                    raise

        class FakeVerifier:
            def verify(self, prepared):
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="synthetic-observer-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        result = run_local_execution(
            request,
            FakeWorker(),
            verifier=FakeVerifier(),
            observation_store=store,
        )
        self.assertEqual(worker_failures, [])
        self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
        events = store.events()
        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "agent_started",
                "tool_requested",
                "tool_completed",
                "tool_requested",
                "tool_completed",
                "decision_proposed",
                "decision_applied",
                "decision_proposed",
                "decision_applied",
                "tool_requested",
                "tool_completed",
                "decision_proposed",
                "decision_applied",
                "tool_requested",
                "tool_completed",
                "tool_requested",
                "tool_completed",
                "agent_finished",
            ],
        )
        self.assertEqual([event["sequence"] for event in events], list(range(18)))
        self.assertEqual(events[-1]["status"], "ok")
        self.assertEqual(
            events[-1]["invocation_id"], events[0]["invocation_id"]
        )
        self.assertEqual(len({event["run_id"] for event in events}), 1)
        self.assertEqual(events[1]["decision_or_tool"], "SandboxBackend.create.target-execution")
        self.assertEqual(events[5]["decision_or_tool"], "WorkerProposal.validate")
        self.assertEqual(events[7]["decision_or_tool"], "PreparedChange.apply-proposal")
        self.assertEqual(
            events[9]["decision_or_tool"], "SandboxSession.run.target-tests"
        )
        self.assertEqual(
            events[11]["decision_or_tool"], "PreparedChange.validate-binding"
        )
        self.assertEqual(events[13]["decision_or_tool"], "IndependentVerifier.verify")
        self.assertEqual(events[15]["decision_or_tool"], "SandboxSession.close.target-execution")
        self.assertEqual(len(store.checkpoints()), 8)

    def test_executor_sandbox_create_gate_refusal_prevents_backend_call(self):
        class RefusingStore(ObservationStore):
            def record_checkpoint(self, _checkpoint):
                raise RuntimeError("synthetic lifecycle gate refusal")

        class FakeBackend:
            calls = 0

            def create(self, *_args):
                self.calls += 1
                raise AssertionError("backend create must be gated")

        store = RefusingStore()
        backend = FakeBackend()
        request = ExecutionRequest(
            process_id="process-sandbox-create-gate",
            task_id="task-sandbox-create-gate",
            repository_id="fixture-repository",
            base_commit="fixture-observer-base",
            snapshot_path=ROOT / "fixtures" / "repository" / "project",
            allowed_commands=frozenset({Path(sys.executable).name}),
            declared_change_paths=("calculator.py",),
            test_command=(sys.executable, "-c", "pass"),
        )
        result = run_local_execution(
            request,
            SimpleNamespace(propose=lambda _request: None),
            verifier=SimpleNamespace(verify=lambda _request: None),
            sandbox_backend=backend,
            observation_store=store,
        )
        self.assertEqual(result.failure_code, "sandbox-observation-gate-failed")
        self.assertEqual(backend.calls, 0)

    def test_executor_fails_closed_on_verifier_gate_and_unknown_outcome(self):
        source = ROOT / "fixtures" / "repository" / "project"
        calculator = (source / "calculator.py").read_text(encoding="utf-8")
        request = ExecutionRequest(
            process_id="process-verifier-gate",
            task_id="task-verifier-gate",
            repository_id="fixture-repository",
            base_commit="fixture-observer-base",
            snapshot_path=source,
            allowed_commands=frozenset({Path(sys.executable).name}),
            declared_change_paths=("calculator.py",),
            test_command=(sys.executable, "-c", "pass"),
        )

        class FakeWorker:
            calls = 0

            def propose(self, _worker_input):
                self.calls += 1
                return WorkerProposal((("calculator.py", calculator + "\n# observed\n"),))

        class FakeVerifier:
            calls = 0

            def verify(self, prepared):
                self.calls += 1
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="synthetic-observer-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        class FailVerifierGateStore(ObservationStore):
            def record_checkpoint_and_intent(self, checkpoint, intent):
                if intent.get("decision_or_tool") == "IndependentVerifier.verify":
                    raise RuntimeError("SYNTHETIC-verifier-store-error")
                self.record_checkpoint(checkpoint)
                return self.append(intent)

        class LoseVerifierOutcomeStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-independent-verifier"
                    and event.get("event_type") == "tool_completed"
                ):
                    raise RuntimeError("SYNTHETIC-verifier-outcome-error")
                return super().append(event)

        for store, expected_code, expected_verifier_calls in (
            (FailVerifierGateStore(), "verifier-observation-gate-failed", 0),
            (LoseVerifierOutcomeStore(), "verifier-outcome-unknown", 1),
        ):
            with self.subTest(code=expected_code):
                worker, verifier = FakeWorker(), FakeVerifier()
                result = run_local_execution(
                    request,
                    worker,
                    verifier=verifier,
                    observation_store=store,
                )
                self.assertEqual(result.status, ExecutionStatus.FAILED)
                self.assertEqual(result.failure_code, expected_code)
                self.assertEqual(worker.calls, 1)
                self.assertEqual(verifier.calls, expected_verifier_calls)

    def test_pre_dispatch_journal_failure_never_calls_worker(self):
        class FailingGateStore(ObservationStore):
            def record_checkpoint_and_intent(self, _checkpoint, _intent):
                raise RuntimeError("SYNTHETIC-secret-error-marker")

        store = FailingGateStore()

        class FakeWorker:
            calls = 0

            def propose(self, _worker_input):
                self.calls += 1
                return None

        worker = FakeWorker()
        wrapped = JournaledProposalWorker(
            worker,
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        with self.assertRaises(WorkerJournalError) as raised:
            wrapped.propose(
                type(
                    "WorkerInput",
                    (),
                    {
                        "process_id": "process-observer-demo",
                        "task_id": "task-observer-demo",
                    },
                )()
            )
        self.assertEqual(worker.calls, 0)
        self.assertNotIn("SYNTHETIC-secret-error-marker", str(raised.exception))
        self.assertEqual([event["event_type"] for event in store.events()], ["agent_started"])

    def test_worker_failure_is_sanitized_and_prior_intent_blocks_retry(self):
        store = ObservationStore()

        class FakeWorker:
            calls = 0

            def propose(self, _worker_input):
                self.calls += 1
                raise RuntimeError("SYNTHETIC-secret-error-marker")

        worker = FakeWorker()
        input_value = type(
            "WorkerInput",
            (),
            {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
        )()
        wrapped = JournaledProposalWorker(
            worker,
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        with self.assertRaises(WorkerProposalFailedError) as raised:
            wrapped.propose(input_value)
        self.assertNotIn("SYNTHETIC-secret-error-marker", str(raised.exception))
        self.assertEqual(store.events()[-1]["event_type"], "tool_failed")
        self.assertEqual(store.events()[-1]["error_code"], "worker-call-failed")
        self.assertEqual(worker.calls, 1)
        with self.assertRaisesRegex(WorkerJournalError, "attempt already recorded"):
            JournaledProposalWorker(
                worker,
                store,
                process_id="process-observer-demo",
                task_id="task-observer-demo",
                id_factory=fixed_ids(),
                clock=fixed_clock(),
            )
        self.assertEqual(worker.calls, 1)

    def test_verifier_pre_dispatch_failure_never_calls_verifier(self):
        class FailSecondGateStore(ObservationStore):
            def record_checkpoint_and_intent(self, checkpoint, intent):
                if intent.get("decision_or_tool") == "IndependentVerifier.verify":
                    raise RuntimeError("SYNTHETIC-verifier-store-secret")
                self.record_checkpoint(checkpoint)
                return self.append(intent)

        store = FailSecondGateStore()
        worker = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        input_value = type(
            "WorkerInput",
            (),
            {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
        )()
        worker.propose(input_value)
        calls = []
        verifier = type(
            "Verifier",
            (),
            {"verify": lambda _self, _value: calls.append("called")},
        )()
        with self.assertRaises(VerifierJournalError) as raised:
            worker.verifier(verifier).verify(object())
        self.assertEqual(calls, [])
        self.assertNotIn("SYNTHETIC-verifier-store-secret", str(raised.exception))
        self.assertEqual(
            [event["event_type"] for event in store.events()],
            ["agent_started", "tool_requested", "tool_completed"],
        )

    def test_sandbox_nonzero_is_bounded_and_command_output_is_not_journaled(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        input_value = type(
            "WorkerInput",
            (),
            {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
        )()
        run.propose(input_value)

        class FakeSession:
            def run(self, argv, timeout_seconds=30):
                return SimpleNamespace(
                    argv=tuple(argv),
                    returncode=7,
                    stdout="SYNTHETIC-STDOUT-CANARY",
                    stderr="SYNTHETIC-STDERR-CANARY",
                )

        command = ["python3", "-c", "SYNTHETIC-ARGV-CANARY"]
        expected = SimpleNamespace(
            argv=tuple(command),
            returncode=7,
            stdout="SYNTHETIC-STDOUT-CANARY",
            stderr="SYNTHETIC-STDERR-CANARY",
        )
        session = run.sandbox_session(FakeSession(), purpose="target-tests")
        result = session.run(command, timeout_seconds=17)
        self.assertEqual(result, expected)
        event = store.events()[-1]
        self.assertEqual(event["event_type"], "tool_failed")
        self.assertEqual(event["error_code"], "sandbox-command-nonzero")
        self.assertEqual(event["safe_parameters"], {"sandbox_return_code": 7})
        journal = repr(store.events())
        for canary in (
            "SYNTHETIC-ARGV-CANARY",
            "SYNTHETIC-STDOUT-CANARY",
            "SYNTHETIC-STDERR-CANARY",
        ):
            self.assertNotIn(canary, journal)

    def test_sandbox_return_code_is_recorded_only_for_bounded_exact_integers(self):
        for returncode in (True, False, -256, 256, 1.5, "7", None):
            with self.subTest(returncode=repr(returncode)):
                store = ObservationStore()
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: "synthetic"),
                    store,
                    process_id="process-sandbox-return-code",
                    task_id="task-sandbox-return-code",
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                run.propose(
                    SimpleNamespace(
                        process_id="process-sandbox-return-code",
                        task_id="task-sandbox-return-code",
                    )
                )

                class FakeSession:
                    def run(self, argv, timeout_seconds=30):
                        return SimpleNamespace(
                            argv=tuple(argv), returncode=returncode,
                            stdout="SYNTHETIC-OUTPUT-CANARY",
                            stderr="SYNTHETIC-ERROR-CANARY",
                        )

                run.sandbox_session(FakeSession(), purpose="target-tests").run(
                    ["python3", "-c", "synthetic"], timeout_seconds=1
                )
                event = store.events()[-1]
                self.assertNotIn("safe_parameters", event)
                self.assertNotIn("SYNTHETIC-OUTPUT-CANARY", repr(store.events()))
                self.assertNotIn("SYNTHETIC-ERROR-CANARY", repr(store.events()))

    def test_fixed_target_probe_persists_only_all_allowlisted_failure_codes(self):
        marker_prefix = "agent00x:test-failure:"
        self.assertEqual(len(PINNED_HTTP_DB_FAILURE_CODES), 57)
        for index, code in enumerate(sorted(PINNED_HTTP_DB_FAILURE_CODES)):
            with self.subTest(code=code):
                store = ObservationStore()
                process_id = f"process-target-diagnostic-{index:03d}"
                task_id = f"task-target-diagnostic-{index:03d}"
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: "synthetic"),
                    store,
                    process_id=process_id,
                    task_id=task_id,
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                run.propose(SimpleNamespace(process_id=process_id, task_id=task_id))

                class FakeSession:
                    def run(self, argv, timeout_seconds=30):
                        return SimpleNamespace(
                            argv=tuple(argv),
                            returncode=1,
                            stdout=marker_prefix + code + "\n",
                            stderr="SYNTHETIC-RAW-STDERR-CANARY",
                        )

                run.sandbox_session(FakeSession(), purpose="target-tests").run(
                    PINNED_HTTP_DB_TEST_COMMAND, timeout_seconds=30
                )
                event = store.events()[-1]
                self.assertEqual(
                    event["safe_parameters"],
                    {"sandbox_return_code": 1, "sandbox_failure_code": code},
                )
                serialized = repr(store.events())
                self.assertNotIn(marker_prefix, serialized)
                self.assertNotIn("SYNTHETIC-RAW-STDERR-CANARY", serialized)

    def test_target_probe_failure_marker_rejects_unknown_extra_and_wrong_scope(self):
        marker = "agent00x:test-failure:valid-row\n"
        invalid_stdout = (
            "agent00x:test-failure:unknown-code\n",
            marker + "EXTRA-RAW-OUTPUT-CANARY\n",
            marker.rstrip("\n"),
            "agent00x:test-failure:SECRET-TOKEN\n",
        )
        for index, stdout in enumerate(invalid_stdout):
            with self.subTest(stdout_index=index):
                store = ObservationStore()
                process_id = f"process-target-marker-negative-{index:03d}"
                task_id = f"task-target-marker-negative-{index:03d}"
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: "synthetic"),
                    store,
                    process_id=process_id,
                    task_id=task_id,
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                run.propose(SimpleNamespace(process_id=process_id, task_id=task_id))

                class FakeSession:
                    def run(self, argv, timeout_seconds=30):
                        return SimpleNamespace(argv=tuple(argv), returncode=1, stdout=stdout, stderr="")

                run.sandbox_session(FakeSession(), purpose="target-tests").run(
                    PINNED_HTTP_DB_TEST_COMMAND, timeout_seconds=30
                )
                self.assertNotIn("sandbox_failure_code", store.events()[-1].get("safe_parameters", {}))
                self.assertNotIn("EXTRA-RAW-OUTPUT-CANARY", repr(store.events()))

        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: "synthetic"),
            store,
            process_id="process-target-marker-wrong-scope",
            task_id="task-target-marker-wrong-scope",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run.propose(SimpleNamespace(
            process_id="process-target-marker-wrong-scope",
            task_id="task-target-marker-wrong-scope",
        ))

        class FakeSession:
            def run(self, argv, timeout_seconds=30):
                return SimpleNamespace(
                    argv=tuple(argv), returncode=1, stdout=marker, stderr=""
                )

        run.sandbox_session(FakeSession(), purpose="verifier-replay").run(
            PINNED_HTTP_DB_TEST_COMMAND, timeout_seconds=30
        )
        self.assertNotIn(
            "sandbox_failure_code", store.events()[-1].get("safe_parameters", {})
        )

    def test_sandbox_success_records_zero_return_code(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: "synthetic"),
            store,
            process_id="process-sandbox-return-zero",
            task_id="task-sandbox-return-zero",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run.propose(
            SimpleNamespace(
                process_id="process-sandbox-return-zero",
                task_id="task-sandbox-return-zero",
            )
        )

        class FakeSession:
            def run(self, argv, timeout_seconds=30):
                return SimpleNamespace(returncode=0, stdout="", stderr="")

        run.sandbox_session(FakeSession(), purpose="target-tests").run(
            ["python3", "-c", "synthetic"], timeout_seconds=1
        )
        event = store.events()[-1]
        self.assertEqual(event["event_type"], "tool_completed")
        self.assertEqual(event["safe_parameters"], {"sandbox_return_code": 0})

    def test_sandbox_return_code_persists_without_command_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sandbox-history.sqlite3"
            with SQLiteObservationStore(database) as store:
                run = JournaledProposalWorker(
                    SimpleNamespace(propose=lambda _request: "synthetic"),
                    store,
                    process_id="process-sandbox-sqlite-code",
                    task_id="task-sandbox-sqlite-code",
                    id_factory=fixed_ids(),
                    clock=fixed_clock(),
                )
                run.propose(
                    SimpleNamespace(
                        process_id="process-sandbox-sqlite-code",
                        task_id="task-sandbox-sqlite-code",
                    )
                )

                class FakeSession:
                    def run(self, argv, timeout_seconds=30):
                        return SimpleNamespace(
                            argv=tuple(argv), returncode=1,
                            stdout="agent00x:test-failure:valid-row\nSYNTHETIC-PERSIST-STDOUT-CANARY",
                            stderr="SYNTHETIC-PERSIST-STDERR-CANARY",
                        )

                result = run.sandbox_session(
                    FakeSession(), purpose="target-tests"
                ).run(PINNED_HTTP_DB_TEST_COMMAND, timeout_seconds=1)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(
                    store.events()[-1]["safe_parameters"],
                    {"sandbox_return_code": 1},
                )
            database_bytes = database.read_bytes()
            report = json.dumps(report_from_sqlite(database), sort_keys=True)
            for canary in (
                b"SYNTHETIC-PERSIST-STDOUT-CANARY",
                b"SYNTHETIC-PERSIST-STDERR-CANARY",
            ):
                self.assertNotIn(canary, database_bytes)
                self.assertNotIn(canary.decode(), report)

    def test_sandbox_lifecycle_is_journaled_in_order_and_redacted(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-sandbox-lifecycle-001",
            task_id="task-sandbox-lifecycle-001",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )

        class FakeSession:
            snapshot = Path("/tmp/SNAPSHOT-PATH-CANARY")
            workspace = Path("/tmp/WORKSPACE-PATH-CANARY")

            def __init__(self):
                self.closed = 0

            def run(self, *_args, **_kwargs):
                return SimpleNamespace(returncode=0)

            def close(self):
                self.closed += 1

        class FakeBackend:
            def __init__(self):
                self.calls = 0
                self.session = FakeSession()

            def create(self, _snapshot, _allowed_commands):
                self.calls += 1
                self.assert_create_checkpoint()
                return self.session

            def assert_create_checkpoint(self):
                events = store.events()
                if events[-1]["decision_or_tool"] != "SandboxBackend.create.target-execution":
                    raise AssertionError("create intent was not journaled")
                if len(store.checkpoints()) != 1:
                    raise AssertionError("create checkpoint is missing")

        backend = FakeBackend()
        session = run.sandbox_backend(backend).create(
            Path("/tmp/INPUT-PATH-CANARY"), {"python3"}
        )
        session.run(("python3", "ARG-CANARY"))
        session.close()
        events = store.events()
        self.assertEqual(backend.calls, 1)
        self.assertEqual(backend.session.closed, 1)
        self.assertEqual(
            [event["decision_or_tool"] for event in events if event["event_type"] == "tool_requested"],
            [
                "SandboxBackend.create.target-execution",
                "SandboxSession.run.target-tests",
                "SandboxSession.close.target-execution",
            ],
        )
        self.assertEqual([event["sequence"] for event in events], list(range(7)))
        self.assertEqual(len({event["run_id"] for event in events}), 1)
        serialized = repr(events) + repr(store.checkpoints())
        for marker in (
            "SNAPSHOT-PATH-CANARY",
            "WORKSPACE-PATH-CANARY",
            "INPUT-PATH-CANARY",
            "ARG-CANARY",
        ):
            self.assertNotIn(marker, serialized)

    def test_sandbox_close_still_runs_if_close_checkpoint_is_refused(self):
        class RefuseCloseStore(ObservationStore):
            refuse = False

            def record_checkpoint(self, checkpoint):
                if self.refuse:
                    raise ObservationStoreError("synthetic close journal refusal")
                return super().record_checkpoint(checkpoint)

        store = RefuseCloseStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-sandbox-lifecycle-002",
            task_id="task-sandbox-lifecycle-002",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        session_calls = []
        backend = SimpleNamespace(
            create=lambda *_args: SimpleNamespace(
                run=lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
                close=lambda: session_calls.append("closed"),
            )
        )
        session = run.sandbox_backend(backend).create(Path("/snapshot"), {"python3"})
        store.refuse = True
        with self.assertRaises(SandboxOutcomeUnknownError):
            session.close()
        self.assertEqual(session_calls, ["closed"])
        self.assertNotIn("SYNTHETIC-close-journal-refusal", repr(store.events()))

    def test_unknown_sandbox_create_outcome_best_effort_closes_without_retry(self):
        class LoseCreateTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-sandbox-lifecycle"
                    and event.get("event_type") == "tool_completed"
                ):
                    raise RuntimeError("SYNTHETIC-create-terminal-loss")
                return super().append(event)

        store = LoseCreateTerminalStore()
        run = JournaledProposalWorker(
            SimpleNamespace(propose=lambda _request: None),
            store,
            process_id="process-sandbox-lifecycle-003",
            task_id="task-sandbox-lifecycle-003",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        calls = []
        session = SimpleNamespace(
            run=lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
            close=lambda: calls.append("closed"),
        )
        backend = SimpleNamespace(create=lambda *_args: calls.append("created") or session)
        wrapped = run.sandbox_backend(backend)
        with self.assertRaises(SandboxOutcomeUnknownError):
            wrapped.create(Path("/snapshot"), {"python3"})
        self.assertEqual(calls, ["created", "closed"])
        with self.assertRaises(SandboxJournalError):
            wrapped.create(Path("/snapshot"), {"python3"})

    def test_sandbox_gate_failure_prevents_command_dispatch(self):
        class FailSandboxGateStore(ObservationStore):
            def record_checkpoint_and_intent(self, checkpoint, intent):
                if intent.get("decision_or_tool", "").startswith("SandboxSession.run."):
                    raise RuntimeError("SYNTHETIC-sandbox-store-error")
                self.record_checkpoint(checkpoint)
                return self.append(intent)

        store = FailSandboxGateStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run.propose(
            type(
                "WorkerInput",
                (),
                {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
            )()
        )
        calls = []
        session = run.sandbox_session(
            type("Session", (), {"run": lambda _self, *_args, **_kwargs: calls.append(True)})(),
            purpose="target-tests",
        )
        with self.assertRaises(SandboxJournalError):
            session.run(("python3", "-c", "pass"))
        self.assertEqual(calls, [])
        self.assertNotIn("SYNTHETIC-sandbox-store-error", repr(store.events()))

    def test_unknown_sandbox_terminal_prevents_command_retry(self):
        class LoseSandboxTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-sandbox"
                    and event.get("event_type") in {"tool_completed", "tool_failed"}
                ):
                    raise RuntimeError("SYNTHETIC-sandbox-result-error")
                return super().append(event)

        store = LoseSandboxTerminalStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run.propose(
            type(
                "WorkerInput",
                (),
                {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
            )()
        )
        calls = []

        class FakeSession:
            def run(self, *_args, **_kwargs):
                calls.append(True)
                return SimpleNamespace(returncode=0, stdout="", stderr="")

        session = run.sandbox_session(FakeSession(), purpose="target-tests")
        with self.assertRaises(SandboxOutcomeUnknownError) as raised:
            session.run(("python3", "-c", "pass"))
        self.assertNotIn("SYNTHETIC-sandbox-result-error", str(raised.exception))
        with self.assertRaises(SandboxJournalError):
            session.run(("python3", "-c", "pass"))
        self.assertEqual(calls, [True])

    def test_stage_save_and_readback_share_run_without_persisting_artifact(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run.propose(
            type(
                "WorkerInput",
                (),
                {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
            )()
        )
        artifact = SimpleNamespace(
            staged_change_digest="sha256:" + "f" * 64,
            content="SYNTHETIC-STAGE-CONTENT-CANARY",
        )
        calls = []

        class FakeStageSink:
            def save(self, value):
                calls.append(("save", value))
                return value

            def load(self, digest):
                calls.append(("load", digest))
                return artifact

        sink = run.stage_sink(FakeStageSink())
        self.assertIs(sink.save(artifact), artifact)
        self.assertIs(
            sink.load("sha256:" + "f" * 64),
            artifact,
        )
        events = store.events()
        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "agent_started",
                "tool_requested",
                "tool_completed",
                "tool_requested",
                "tool_completed",
                "tool_requested",
                "tool_completed",
            ],
        )
        self.assertEqual(events[3]["decision_or_tool"], "StagedArtifactStore.save")
        self.assertEqual(events[5]["decision_or_tool"], "StagedArtifactStore.load")
        self.assertEqual(events[3]["causal_event_ids"], [events[2]["event_id"]])
        self.assertEqual(events[5]["causal_event_ids"], [events[4]["event_id"]])
        self.assertEqual([event["sequence"] for event in events], list(range(7)))
        self.assertNotIn("SYNTHETIC-STAGE-CONTENT-CANARY", repr(events))
        self.assertEqual(len(store.checkpoints()), 3)

    def test_stage_gate_failure_prevents_save_dispatch(self):
        class FailStageGateStore(ObservationStore):
            def record_checkpoint_and_intent(self, checkpoint, intent):
                if intent.get("decision_or_tool") == "StagedArtifactStore.save":
                    raise RuntimeError("SYNTHETIC-stage-gate-secret")
                self.record_checkpoint(checkpoint)
                return self.append(intent)

        store = FailStageGateStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run.propose(
            type(
                "WorkerInput",
                (),
                {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
            )()
        )
        calls = []
        sink = run.stage_sink(
            type(
                "StageSink",
                (),
                {"save": lambda _self, _value: calls.append("save"), "load": lambda *_args: None},
            )()
        )
        with self.assertRaises(StageJournalError) as raised:
            sink.save(SimpleNamespace(content="SYNTHETIC-STAGE-CONTENT"))
        self.assertEqual(calls, [])
        self.assertNotIn("SYNTHETIC-stage-gate-secret", str(raised.exception))

    def test_unknown_stage_save_outcome_prevents_retry(self):
        class LoseStageTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-stage-store"
                    and event.get("event_type") in {"tool_completed", "tool_failed"}
                ):
                    raise RuntimeError("SYNTHETIC-stage-result-secret")
                return super().append(event)

        store = LoseStageTerminalStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run.propose(
            type(
                "WorkerInput",
                (),
                {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
            )()
        )
        calls = []

        class FakeStageSink:
            def save(self, value):
                calls.append("save")
                return value

            def load(self, _digest):
                calls.append("load")
                return None

        sink = run.stage_sink(FakeStageSink())
        with self.assertRaises(StageOutcomeUnknownError) as raised:
            sink.save(object())
        self.assertNotIn("SYNTHETIC-stage-result-secret", str(raised.exception))
        with self.assertRaises(StageJournalError):
            sink.save(object())
        self.assertEqual(calls, ["save"])

    def test_stage_failure_records_fixed_code_without_exception_text(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        run.propose(
            type(
                "WorkerInput",
                (),
                {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
            )()
        )

        class FailingStageSink:
            def save(self, _artifact):
                raise RuntimeError("SYNTHETIC-STAGE-EXCEPTION-CANARY")

            def load(self, _digest):
                return None

        sink = run.stage_sink(FailingStageSink())
        with self.assertRaises(StageCallFailedError) as raised:
            sink.save(object())
        self.assertNotIn("SYNTHETIC-STAGE-EXCEPTION-CANARY", str(raised.exception))
        self.assertEqual(store.events()[-1]["event_type"], "tool_failed")
        self.assertEqual(store.events()[-1]["error_code"], "stage-call-failed")
        self.assertNotIn("SYNTHETIC-STAGE-EXCEPTION-CANARY", repr(store.events()))

    def test_snapshot_intake_calls_join_same_run_without_persisting_payloads(self):
        store = ObservationStore()
        worker_calls = []

        class FakeWorker:
            def propose(self, worker_input):
                worker_calls.append(worker_input)
                return "synthetic proposal"

        run = JournaledProposalWorker(
            FakeWorker(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        transport_calls = []

        class FakeTransport:
            def __call__(self, method, url, headers, max_bytes, *, allow_redirects):
                transport_calls.append((method, url, headers, max_bytes, allow_redirects))
                return {"status": 200, "body": b"SYNTHETIC-SNAPSHOT-BODY-CANARY"}

        url = "https://api.github.com/repos/PrivateOwner/PrivateRepo/commits/" + "a" * 40
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        transport = run.snapshot_transport(FakeTransport())
        response = transport("GET", url, headers, 4096, allow_redirects=False)
        self.assertEqual(response["status"], 200)
        self.assertEqual(len(transport_calls), 1)

        class FakeRawCommitSource:
            def __call__(self, claim):
                self.claim = claim
                return b"SYNTHETIC-RAW-COMMIT-CANARY"

        raw_source = run.raw_commit_source(FakeRawCommitSource())
        self.assertEqual(
            raw_source(SimpleNamespace(repository="PrivateRepo", oid="b" * 40)),
            b"SYNTHETIC-RAW-COMMIT-CANARY",
        )
        proposal = run.propose(
            type(
                "WorkerInput",
                (),
                {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
            )()
        )
        self.assertEqual(proposal, "synthetic proposal")
        self.assertEqual(len(worker_calls), 1)
        events = store.events()
        self.assertEqual([event["sequence"] for event in events], list(range(7)))
        self.assertEqual(events[0]["event_type"], "agent_started")
        self.assertEqual(events[1]["decision_or_tool"], "GitHubSnapshot.GET.commit")
        self.assertEqual(
            events[1]["causal_event_ids"], [events[0]["event_id"]]
        )
        self.assertEqual(
            events[3]["decision_or_tool"], "GitHubRawCommitObjectSource.read"
        )
        self.assertEqual(
            events[3]["causal_event_ids"], [events[2]["event_id"]]
        )
        self.assertEqual(events[5]["decision_or_tool"], "ProposalWorker.propose")
        self.assertEqual(events[5]["causal_event_ids"], [events[4]["event_id"]])
        self.assertEqual(len({event["run_id"] for event in events}), 1)
        for canary in (
            "PrivateOwner",
            "PrivateRepo",
            "SYNTHETIC-SNAPSHOT-BODY-CANARY",
            "SYNTHETIC-RAW-COMMIT-CANARY",
        ):
            self.assertNotIn(canary, repr(events))
        self.assertEqual(len(store.checkpoints()), 3)

    def test_snapshot_route_rejection_and_gate_failure_prevent_dispatch(self):
        class FailSnapshotGateStore(ObservationStore):
            def record_checkpoint_and_intent(self, checkpoint, intent):
                if intent.get("decision_or_tool") == "GitHubSnapshot.GET.commit":
                    raise RuntimeError("SYNTHETIC-SNAPSHOT-GATE-ERROR")
                self.record_checkpoint(checkpoint)
                return self.append(intent)

        store = FailSnapshotGateStore()
        calls = []
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: None})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        transport = run.snapshot_transport(
            type("Transport", (), {"__call__": lambda *_args, **_kwargs: calls.append(True)})()
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        with self.assertRaises(SnapshotJournalError):
            transport(
                "GET",
                "https://api.github.com/repos/Owner/Repo/commits/" + "a" * 40,
                headers,
                4096,
                allow_redirects=False,
            )
        self.assertEqual(calls, [])
        self.assertNotIn("SYNTHETIC-SNAPSHOT-GATE-ERROR", repr(store.events()))

        safe_store = ObservationStore()
        safe_run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: None})(),
            safe_store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        untrusted_calls = []
        untrusted = safe_run.snapshot_transport(
            type("Transport", (), {"__call__": lambda *_args, **_kwargs: untrusted_calls.append(True)})()
        )
        with self.assertRaises(SnapshotJournalError):
            untrusted(
                "GET",
                "https://evil.example/repos/Owner/Repo/commits/" + "a" * 40,
                headers,
                4096,
                allow_redirects=False,
            )
        self.assertEqual(untrusted_calls, [])

    def test_snapshot_transport_allowlists_commit_tree_and_blob_endpoint_shapes(self):
        store = ObservationStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: None})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        calls = []

        class FakeTransport:
            def __call__(self, method, url, headers, max_bytes, *, allow_redirects):
                calls.append((method, url, allow_redirects))
                return {"status": 200}

        transport = run.snapshot_transport(FakeTransport())
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        base = "https://api.github.com/repos/Owner/Repo"
        requests = (
            (base + "/commits/" + "a" * 40, "GitHubSnapshot.GET.commit"),
            (base + "/git/trees/" + "b" * 40 + "?recursive=1", "GitHubSnapshot.GET.tree"),
            (base + "/git/blobs/" + "c" * 40, "GitHubSnapshot.GET.blob"),
        )
        for url, _label in requests:
            transport("GET", url, headers, 4096, allow_redirects=False)

        labels = [
            event.get("decision_or_tool")
            for event in store.events()
            if event.get("event_type") == "tool_requested"
        ]
        self.assertEqual(labels, [label for _, label in requests])
        self.assertEqual(len(calls), 3)

        for url in (
            base + "/git/trees/" + "b" * 40,
            base + "/git/trees/" + "b" * 40 + "?recursive=1&extra=1",
            base + "/git/blobs/" + "c" * 40 + "?download=1",
        ):
            with self.subTest(url=url), self.assertRaises(SnapshotJournalError):
                transport("GET", url, headers, 4096, allow_redirects=False)
        self.assertEqual(len(calls), 3)

    def test_unknown_snapshot_terminal_blocks_transport_reuse(self):
        class LoseSnapshotTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-snapshot-intake"
                    and event.get("event_type") == "tool_completed"
                ):
                    raise RuntimeError("SYNTHETIC-SNAPSHOT-RESULT-CANARY")
                return super().append(event)

        store = LoseSnapshotTerminalStore()
        run = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: None})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        calls = []
        transport = run.snapshot_transport(
            type(
                "Transport",
                (),
                {"__call__": lambda *_args, **_kwargs: calls.append(True) or {"status": 200}},
            )()
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        with self.assertRaises(SnapshotOutcomeUnknownError) as raised:
            transport(
                "GET",
                "https://api.github.com/repos/Owner/Repo/commits/" + "a" * 40,
                headers,
                4096,
                allow_redirects=False,
            )
        self.assertNotIn("SYNTHETIC-SNAPSHOT-RESULT-CANARY", str(raised.exception))
        with self.assertRaises(SnapshotJournalError):
            transport(
                "GET",
                "https://api.github.com/repos/Owner/Repo/commits/" + "a" * 40,
                headers,
                4096,
                allow_redirects=False,
            )
        self.assertEqual(calls, [True])

    def test_verifier_failure_records_only_fixed_failure_metadata(self):
        store = ObservationStore()
        worker = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        input_value = type(
            "WorkerInput",
            (),
            {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
        )()
        worker.propose(input_value)

        class FailingVerifier:
            def verify(self, _value):
                raise RuntimeError("SYNTHETIC-verifier-secret-output")

        with self.assertRaises(VerifierCallFailedError):
            worker.verifier(FailingVerifier()).verify(object())
        events = store.events()
        self.assertEqual(events[-1]["event_type"], "tool_failed")
        self.assertEqual(events[-1]["error_code"], "verifier-call-failed")
        self.assertNotIn("SYNTHETIC-verifier-secret-output", repr(events))

    def test_unrecorded_verifier_outcome_is_unknown_and_not_retried(self):
        class LoseVerifierTerminalStore(ObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-independent-verifier"
                    and event.get("event_type") == "tool_completed"
                ):
                    raise RuntimeError("SYNTHETIC-verifier-secret-output")
                return super().append(event)

        store = LoseVerifierTerminalStore()
        worker = JournaledProposalWorker(
            type("Worker", (), {"propose": lambda _self, _value: "synthetic"})(),
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        input_value = type(
            "WorkerInput",
            (),
            {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
        )()
        worker.propose(input_value)
        calls = []
        verifier = type(
            "Verifier",
            (),
            {"verify": lambda _self, _value: calls.append("called") or "result"},
        )()
        journaled = worker.verifier(verifier)
        with self.assertRaises(VerifierOutcomeUnknownError) as raised:
            journaled.verify(object())
        self.assertNotIn("SYNTHETIC-verifier-secret-output", str(raised.exception))
        self.assertEqual(calls, ["called"])
        with self.assertRaises(VerifierJournalError):
            journaled.verify(object())
        self.assertEqual(calls, ["called"])
        self.assertEqual(
            [event["event_type"] for event in store.events()],
            ["agent_started", "tool_requested", "tool_completed", "tool_requested"],
        )

    def test_success_without_terminal_record_is_unknown_and_blocks_retry(self):
        class LostOutcomeStore(ObservationStore):
            def append(self, event):
                if event.get("event_type") == "tool_completed":
                    raise RuntimeError("SYNTHETIC-secret-error-marker")
                return super().append(event)

        store = LostOutcomeStore()

        class FakeWorker:
            calls = 0

            def propose(self, _worker_input):
                self.calls += 1
                return {"proposal": "not persisted"}

        worker = FakeWorker()
        input_value = type(
            "WorkerInput",
            (),
            {"process_id": "process-observer-demo", "task_id": "task-observer-demo"},
        )()
        wrapped = JournaledProposalWorker(
            worker,
            store,
            process_id="process-observer-demo",
            task_id="task-observer-demo",
            id_factory=fixed_ids(),
            clock=fixed_clock(),
        )
        with self.assertRaises(WorkerOutcomeUnknownError) as raised:
            wrapped.propose(input_value)
        self.assertNotIn("SYNTHETIC-secret-error-marker", str(raised.exception))
        self.assertEqual(worker.calls, 1)
        self.assertEqual(
            [event["event_type"] for event in store.events()],
            ["agent_started", "tool_requested"],
        )
        with self.assertRaisesRegex(WorkerJournalError, "attempt already recorded"):
            JournaledProposalWorker(
                worker,
                store,
                process_id="process-observer-demo",
                task_id="task-observer-demo",
                id_factory=fixed_ids(),
                clock=fixed_clock(),
            )
        self.assertEqual(worker.calls, 1)


if __name__ == "__main__":
    unittest.main()
