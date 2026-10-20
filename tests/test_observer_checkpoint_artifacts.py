from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.brainbooster_target_profile import VERIFIER_CONTEXT_MODULES
from app_contracts.observation_store import (
    ObservationStoreError,
    ObservationStore,
    PreDispatchError,
    run_gated_dispatch,
)
from app_contracts.observer_artifact_store import (
    ArtifactResolution,
    SQLiteObserverArtifactStore,
)
from app_contracts.observer_checkpoint_artifacts import (
    ArtifactCapturingObservationStore,
)
from app_contracts.observer_report import build_history_report
from app_contracts.observer_runtime import JournaledProposalWorker
from app_contracts.worker_cli import _observer_report_for_cli


def _event(event_id: str, *, event_type: str, sequence: int, **extra) -> dict:
    result = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": event_type,
        "process_id": "process-artifact-demo",
        "run_id": "run-artifact-demo-0001",
        "branch_id": "branch-main",
        "task_id": "task-artifact-demo",
        "agent_id": "service-worker",
        "sequence": sequence,
        "occurred_at": "2026-10-20T12:00:00Z",
        "recorded_at": "2026-10-20T12:00:00Z",
        "classification": "internal",
        "redaction_status": "complete",
    }
    result.update(extra)
    return result


def _checkpoint() -> dict:
    return {
        "schema_version": 1,
        "checkpoint_id": "checkpoint-artifact-demo-0001",
        "kind": "tool_call",
        "process_id": "process-artifact-demo",
        "run_id": "run-artifact-demo-0001",
        "branch_id": "branch-main",
        "agent_id": "service-worker",
        "trigger_event_id": "event-artifact-start",
        "event_cursor": 0,
        "state_ref": "artifact://observer-state/run-artifact-demo-0001/worker-call",
        "completeness": "partial",
        "restore_mode": "none",
        "created_at": "2026-10-20T12:00:00Z",
    }


class ObserverCheckpointArtifactTests(unittest.TestCase):
    def test_adapter_stays_outside_the_pinned_verifier_import_closure(self):
        self.assertNotIn(
            "observer_checkpoint_artifacts.py", VERIFIER_CONTEXT_MODULES
        )

    def test_atomic_checkpoint_write_resolves_only_bounded_pending_action_artifact(self):
        with tempfile.TemporaryDirectory(prefix="observer-checkpoint-artifacts-") as root:
            journal = ObservationStore()
            journal.append(
                _event("event-artifact-start", event_type="agent_started", sequence=0)
            )
            artifact_path = Path(root) / "artifacts.sqlite3"
            with SQLiteObserverArtifactStore(artifact_path) as artifacts:
                store = ArtifactCapturingObservationStore(journal, artifacts)
                intent = _event(
                    "event-artifact-intent",
                    event_type="tool_requested",
                    sequence=1,
                    checkpoint_id="checkpoint-artifact-demo-0001",
                    invocation_id="invocation-artifact-demo-0001",
                    causal_event_ids=["event-artifact-start"],
                    decision_or_tool="ProposalWorker.propose",
                    expected_result="SYNTHETIC-FREE-TEXT-CANARY",
                    status="pending",
                    rationale="SYNTHETIC-PRIVATE-CANARY",
                )
                dispatched = Mock(return_value="ok")
                run_gated_dispatch(
                    store,
                    checkpoint=_checkpoint(),
                    intent_event=intent,
                    dispatch=dispatched,
                )

                saved_checkpoint = journal.checkpoints()[0]
                pending_ref = saved_checkpoint["pending_action_ref"]
                state_ref = saved_checkpoint["state_ref"]
                resolution = artifacts.resolve(pending_ref)
                state_resolution = artifacts.resolve(state_ref)
                report = build_history_report(
                    list(enumerate(journal.events())),
                    list(enumerate(journal.checkpoints())),
                    run_id="run-artifact-demo-0001",
                    artifact_resolver=artifacts,
                )
                report_json = json.dumps(report, sort_keys=True)
                payload = json.loads(artifacts.read_json(pending_ref))
                state_payload = json.loads(artifacts.read_json(state_ref))

            dispatched.assert_called_once_with()
            self.assertEqual(
                state_payload["schema"], "observer-logical-state/v1"
            )
            self.assertTrue(state_ref.startswith("artifact://sha256/"))
            self.assertEqual(state_payload["scope"], "checkpoint-metadata-only")
            self.assertEqual(state_payload["capture_mode"], "metadata_only")
            self.assertFalse(state_payload["restorable"])
            self.assertIn("model_internal_state", state_payload["unavailable_components"])
            self.assertEqual(state_payload["pending_action_ref"], pending_ref)
            self.assertEqual(saved_checkpoint["completeness"], "partial")
            self.assertEqual(saved_checkpoint["restore_mode"], "none")
            self.assertEqual(
                payload["schema"], "observer-pending-action/v1"
            )
            self.assertEqual(
                payload["scope"], "checkpoint-metadata-and-intent-only"
            )
            self.assertEqual(
                payload["intent"],
                {
                    "event_id": "event-artifact-intent",
                    "event_type": "tool_requested",
                    "sequence": 1,
                    "decision_or_tool": "ProposalWorker.propose",
                },
            )
            self.assertNotIn("SYNTHETIC-PRIVATE-CANARY", report_json)
            self.assertNotIn("SYNTHETIC-FREE-TEXT-CANARY", report_json)
            resolved = {
                artifact["artifact_ref"]: artifact["content_digest"]
                for artifact in report["resolved_artifacts"]
            }
            self.assertEqual(resolved[pending_ref], resolution.content_digest)
            self.assertEqual(resolved[state_ref], state_resolution.content_digest)
            gap_codes = {gap["code"] for gap in report["gaps"]}
            self.assertIn(
                "checkpoint_state_metadata_only",
                gap_codes,
            )
            self.assertNotIn("artifact_content_unresolved", gap_codes)
            self.assertIn("checkpoint_partial", gap_codes)

    def test_artifact_failure_blocks_dispatch_before_journal_write(self):
        journal = ObservationStore()
        journal.append(
            _event("event-artifact-start", event_type="agent_started", sequence=0)
        )
        artifact_store = Mock()
        artifact_store.put_json.side_effect = RuntimeError("synthetic failure")
        store = ArtifactCapturingObservationStore(journal, artifact_store)
        dispatched = Mock()
        with self.assertRaisesRegex(
            PreDispatchError, "checkpoint artifact unavailable"
        ):
            run_gated_dispatch(
                store,
                checkpoint=_checkpoint(),
                intent_event=_event(
                    "event-artifact-intent",
                    event_type="tool_requested",
                    sequence=1,
                    checkpoint_id="checkpoint-artifact-demo-0001",
                    invocation_id="invocation-artifact-demo-0001",
                    causal_event_ids=["event-artifact-start"],
                    decision_or_tool="ProposalWorker.propose",
                    status="pending",
                ),
                dispatch=dispatched,
            )
        dispatched.assert_not_called()
        self.assertEqual(len(journal.events()), 1)
        self.assertEqual(len(journal.checkpoints()), 0)

    def test_state_manifest_failure_blocks_journal_and_dispatch(self):
        journal = ObservationStore()
        journal.append(
            _event("event-state-failure-start", event_type="agent_started", sequence=0)
        )

        class FailSecondArtifact:
            def __init__(self):
                self.calls = 0
                self.resolutions = {}

            def put_json(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    encoded = _args[0]
                    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
                    resolution = ArtifactResolution(
                        "artifact://sha256/" + digest.removeprefix("sha256:"),
                        digest,
                        len(encoded),
                    )
                    self.resolutions[resolution.artifact_ref] = resolution
                    return resolution
                raise RuntimeError("synthetic state failure")

            def resolve(self, artifact_ref):
                return self.resolutions[artifact_ref]

        artifact_store = FailSecondArtifact()
        store = ArtifactCapturingObservationStore(journal, artifact_store)
        dispatched = Mock()
        with self.assertRaisesRegex(
            PreDispatchError, "checkpoint artifact unavailable"
        ):
            run_gated_dispatch(
                store,
                checkpoint=_checkpoint(),
                intent_event=_event(
                    "event-state-failure-intent",
                    event_type="tool_requested",
                    sequence=1,
                    checkpoint_id="checkpoint-artifact-demo-0001",
                    invocation_id="invocation-state-failure-0001",
                    causal_event_ids=["event-state-failure-start"],
                    decision_or_tool="ProposalWorker.propose",
                    status="pending",
                ),
                dispatch=dispatched,
            )
        dispatched.assert_not_called()
        self.assertEqual(artifact_store.calls, 2)
        self.assertEqual(len(journal.events()), 1)
        self.assertEqual(len(journal.checkpoints()), 0)

    def test_worker_cli_report_uses_attached_resolver_and_keeps_true_gaps(self):
        with tempfile.TemporaryDirectory(prefix="observer-checkpoint-cli-") as root:
            journal = ObservationStore()
            with SQLiteObserverArtifactStore(Path(root) / "artifacts.sqlite3") as artifacts:
                store = ArtifactCapturingObservationStore(journal, artifacts)
                worker = JournaledProposalWorker(
                    Mock(propose=Mock()),
                    store,
                    process_id="process-artifact-cli",
                    task_id="task-artifact-cli",
                    id_factory=iter(
                        ["12345678", "abcdefgh", "87654321", "ijklmnop"]
                    ).__next__,
                )
                start = journal.events()[0]
                run_id = worker.observer_reference()["run_id"]
                checkpoint = {
                    **_checkpoint(),
                    "checkpoint_id": "checkpoint-artifact-cli-0001",
                    "process_id": "process-artifact-cli",
                    "run_id": run_id,
                    "trigger_event_id": start["event_id"],
                    "state_ref": f"artifact://observer-state/{run_id}/worker-call",
                }
                intent = {
                    **_event(
                        "event-artifact-cli-intent",
                        event_type="tool_requested",
                        sequence=1,
                        decision_or_tool="ProposalWorker.propose",
                        status="pending",
                    ),
                    "process_id": "process-artifact-cli",
                    "run_id": run_id,
                    "task_id": "task-artifact-cli",
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "invocation_id": "invocation-artifact-cli-0001",
                    "causal_event_ids": [start["event_id"]],
                }
                store.record_checkpoint_and_intent(checkpoint, intent)

                with patch.object(artifacts, "resolve", wraps=artifacts.resolve) as resolve:
                    summary = _observer_report_for_cli(worker, store)

                self.assertGreaterEqual(resolve.call_count, 2)
                self.assertEqual(summary["completeness"], "partial")
                self.assertIn(
                    "collector_coverage_unverified", summary["gap_codes"]
                )
                self.assertNotIn("artifact_content_unresolved", summary["gap_codes"])
                self.assertIn(
                    "checkpoint_state_metadata_only", summary["gap_codes"]
                )
                self.assertIn("checkpoint_partial", summary["gap_codes"])

    def test_free_text_operation_names_and_preexisting_pending_refs_are_rejected(self):
        class ArtifactSink:
            def put_json(self, *_args, **_kwargs):
                raise AssertionError("unsafe metadata reached artifact store")

            def resolve(self, *_args, **_kwargs):
                raise AssertionError("unsafe metadata reached artifact store")

        journal = ObservationStore()
        store = ArtifactCapturingObservationStore(journal, ArtifactSink())
        checkpoint = _checkpoint()
        intent = _event(
            "event-artifact-intent",
            event_type="tool_requested",
            sequence=1,
            decision_or_tool="not a fixed operation",
        )
        with self.assertRaisesRegex(
            ObservationStoreError, "pending-action metadata unavailable"
        ):
            store.record_checkpoint_and_intent(checkpoint, intent)


if __name__ == "__main__":
    unittest.main()
