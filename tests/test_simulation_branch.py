from __future__ import annotations

import base64
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.observation_store import ObservationStore, SQLiteObservationStore
from app_contracts.digests import canonical_json, sha256_bytes
from app_contracts.observer_artifact_store import (
    ObserverArtifactStoreError,
    SQLiteObserverArtifactStore,
)
from app_contracts.simulation_branch import (
    SimulationBranchError,
    create_simulation_branch,
    materialize_simulation_workspace,
)


def source_event(event_id="event-simulation-source-001"):
    return {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "tool_completed",
        "process_id": "process-simulation-001",
        "run_id": "run-simulation-source-001",
        "branch_id": "branch-simulation-source-001",
        "task_id": "task-simulation-001",
        "agent_id": "agent-worker-001",
        "sequence": 0,
        "occurred_at": "2026-10-08T12:00:00Z",
        "recorded_at": "2026-10-08T12:00:01Z",
        "classification": "internal",
        "redaction_status": "complete",
    }


def source_checkpoint():
    return {
        "schema_version": 1,
        "checkpoint_id": "checkpoint-simulation-source-001",
        "kind": "tool_call",
        "process_id": "process-simulation-001",
        "run_id": "run-simulation-source-001",
        "branch_id": "branch-simulation-source-001",
        "agent_id": "agent-worker-001",
        "trigger_event_id": "event-simulation-source-001",
        "event_cursor": 0,
        "state_ref": "artifact://states/simulation-001",
        "completeness": "complete",
        "restore_mode": "simulation",
        "created_at": "2026-10-08T12:00:02Z",
    }


def correction():
    return {
        "schema_version": 1,
        "correction_id": "correction-simulation-001",
        "version": 1,
        "checkpoint_id": "checkpoint-simulation-source-001",
        "target_event_id": "event-simulation-source-001",
        "author_id": "human-reviewer-001",
        "created_at": "2026-10-08T12:01:00Z",
        "error_description": "The synthetic action selected the wrong local fixture.",
        "explanation": "The task scope requires the declared fixture only.",
        "expected_action": "Select only the declared local fixture.",
        "applicability": "Synthetic repository-change fixture tests.",
        "evidence_refs": ["artifact://evidence/simulation-001"],
        "review_status": "proposed",
    }


def populated_store():
    store = ObservationStore()
    store.append(source_event())
    store.record_checkpoint(source_checkpoint())
    return store


def workspace_manifest(files):
    records = []
    for path, content in files:
        records.append(
            {
                "path": path,
                "content_base64": base64.b64encode(content).decode("ascii"),
                "content_digest": sha256_bytes(content),
            }
        )
    return {"schema": "workspace-manifest/v1", "files": records}


def save_manifest(database, manifest):
    with SQLiteObserverArtifactStore(database) as store:
        return store.put_json(
            canonical_json(manifest),
            classification="internal",
            redaction_status="complete",
        ).artifact_ref


class SimulationBranchTests(unittest.TestCase):
    def create(self, store, *, checkpoint=None, correction_value=None, **kwargs):
        return create_simulation_branch(
            store,
            checkpoint_id=(checkpoint or source_checkpoint())["checkpoint_id"],
            correction=correction() if correction_value is None else correction_value,
            run_id=kwargs.pop("run_id", "run-simulation-child-001"),
            branch_id=kwargs.pop("branch_id", "branch-simulation-child-001"),
            clock=lambda: datetime(2026, 10, 8, 12, 2, tzinfo=timezone.utc),
            **kwargs,
        )

    def test_declares_new_simulation_branch_without_mutating_source_history(self):
        store = populated_store()
        original_events = store.events()
        original_checkpoints = store.checkpoints()

        result = self.create(store)

        self.assertEqual(result.source_run_id, "run-simulation-source-001")
        self.assertEqual(result.source_branch_id, "branch-simulation-source-001")
        self.assertEqual(result.source_event_id, "event-simulation-source-001")
        self.assertEqual(result.run_id, "run-simulation-child-001")
        self.assertEqual(result.branch_id, "branch-simulation-child-001")
        self.assertEqual(result.event_id, "event-branch-simulation-child-001")
        self.assertEqual(result.observer_cursor, len(original_events))
        self.assertEqual(store.events()[: len(original_events)], original_events)
        self.assertEqual(store.checkpoints(), original_checkpoints)
        branch_event = store.events()[-1]
        self.assertEqual(branch_event["event_type"], "branch_created")
        self.assertEqual(branch_event["sequence"], 0)
        self.assertEqual(branch_event["causal_event_ids"], [result.source_event_id])
        self.assertEqual(branch_event["checkpoint_id"], result.source_checkpoint_id)
        self.assertEqual(branch_event["redaction_status"], "complete")

    def test_duplicate_branch_id_is_refused_without_journal_mutation(self):
        store = populated_store()
        self.create(store)
        before = store.events()
        with self.assertRaisesRegex(SimulationBranchError, "identifier already exists"):
            self.create(store)
        self.assertEqual(store.events(), before)

    def test_partial_or_non_simulation_checkpoint_is_refused(self):
        for field, value in (
            ("completeness", "partial"),
            ("restore_mode", "supervised"),
            ("restore_mode", "none"),
            ("in_flight_invocation_ids", ["invocation-simulation-001"]),
            ("pending_action_ref", "artifact://actions/pending-001"),
            ("external_effect_refs", ["artifact://effects/known-001"]),
        ):
            with self.subTest(field=field, value=value):
                store = ObservationStore()
                store.append(source_event())
                checkpoint = source_checkpoint()
                checkpoint[field] = value
                store.record_checkpoint(checkpoint)
                before = store.events()
                with self.assertRaises(SimulationBranchError):
                    self.create(store, checkpoint=checkpoint)
                self.assertEqual(store.events(), before)

    def test_invalid_or_foreign_correction_is_refused(self):
        for mutate in (
            lambda value: value.update(checkpoint_id="checkpoint-foreign-001"),
            lambda value: value.update(target_event_id="event-foreign-target-001"),
            lambda value: value.update(review_status="approved", unexpected=True),
        ):
            with self.subTest(mutate=mutate):
                store = populated_store()
                bad_correction = correction()
                mutate(bad_correction)
                before = store.events()
                with self.assertRaises(SimulationBranchError):
                    self.create(store, correction_value=bad_correction)
                self.assertEqual(store.events(), before)

    def test_existing_target_from_another_run_is_refused(self):
        store = populated_store()
        foreign_event = source_event("event-simulation-foreign-001")
        foreign_event["run_id"] = "run-simulation-foreign-001"
        foreign_event["branch_id"] = "branch-simulation-foreign-001"
        foreign_event["sequence"] = 0
        store.append(foreign_event)
        bad_correction = correction()
        bad_correction["target_event_id"] = foreign_event["event_id"]
        before = store.events()
        with self.assertRaisesRegex(SimulationBranchError, "outside checkpoint history"):
            self.create(store, correction_value=bad_correction)
        self.assertEqual(store.events(), before)

    def test_duplicate_run_id_and_invalid_identifiers_are_refused(self):
        store = populated_store()
        before = store.events()
        for kwargs in (
            {"run_id": "run-simulation-source-001"},
            {"branch_id": "branch-simulation-source-001"},
            {"run_id": "bad", "branch_id": "branch-simulation-child-002"},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SimulationBranchError):
                    self.create(store, **kwargs)
                self.assertEqual(store.events(), before)

    def test_sqlite_branch_event_survives_reopen_and_source_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "observer.sqlite3"
            with SQLiteObservationStore(database) as store:
                store.append(source_event())
                store.record_checkpoint(source_checkpoint())
                original = store.events()
                result = self.create(store)
                self.assertEqual(store.events()[0], original[0])
                self.assertEqual(result.observer_cursor, 1)
            with SQLiteObservationStore(database) as reopened:
                events = reopened.events()
                self.assertEqual([item["sequence"] for item in events], [0, 0])
                self.assertEqual(events[0], original[0])
                self.assertEqual(events[1]["event_type"], "branch_created")

    def test_api_has_no_dispatch_or_external_callback_parameter(self):
        calls = []
        signature = inspect.signature(create_simulation_branch)
        self.assertNotIn("dispatch", signature.parameters)
        self.assertNotIn("worker", signature.parameters)
        store = populated_store()
        before = store.events()
        with self.assertRaises(TypeError):
            create_simulation_branch(
                store,
                checkpoint_id=source_checkpoint()["checkpoint_id"],
                correction=correction(),
                run_id="run-simulation-child-001",
                branch_id="branch-simulation-child-001",
                dispatch=lambda: calls.append("external effect"),
            )
        self.assertEqual(calls, [])
        self.assertEqual(store.events(), before)

    def test_materializes_valid_simulation_workspace_in_memory_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts_database = root / "artifacts.sqlite3"
            manifest = workspace_manifest(
                (
                    ("backend/routes.py", b"def handler(): return 200\n"),
                    ("tests/test_routes.py", b"assert True\n"),
                )
            )
            manifest_ref = save_manifest(artifacts_database, manifest)
            artifacts_before = artifacts_database.read_bytes()
            directory_entries_before = {item.name for item in root.iterdir()}
            checkpoint = source_checkpoint()
            checkpoint["workspace_manifest_ref"] = manifest_ref
            observer = populated_store()
            events_before = observer.events()
            checkpoints_before = observer.checkpoints()

            with SQLiteObserverArtifactStore(
                artifacts_database, read_only=True
            ) as artifact_reader:
                result = materialize_simulation_workspace(checkpoint, artifact_reader)
                self.assertTrue(artifact_reader.read_only)

            self.assertEqual(
                dict(result.files),
                {
                    "backend/routes.py": b"def handler(): return 200\n",
                    "tests/test_routes.py": b"assert True\n",
                },
            )
            self.assertEqual(result.checkpoint_id, checkpoint["checkpoint_id"])
            self.assertEqual(result.manifest_ref, manifest_ref)
            self.assertEqual(
                result.manifest_digest,
                sha256_bytes(canonical_json(manifest)),
            )
            self.assertNotIn("return 200", repr(result))
            evidence = result.evidence()
            self.assertEqual(evidence["file_count"], 2)
            self.assertFalse(evidence["external_effects_replayed"])
            self.assertNotIn("return 200", json.dumps(evidence))
            self.assertEqual(artifacts_database.read_bytes(), artifacts_before)
            self.assertEqual(
                {item.name for item in root.iterdir()}, directory_entries_before
            )
            self.assertEqual(observer.events(), events_before)
            self.assertEqual(observer.checkpoints(), checkpoints_before)

    def test_materializer_requires_read_only_store_and_eligible_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "artifacts.sqlite3"
            manifest_ref = save_manifest(
                database, workspace_manifest((("src.py", b"safe\n"),))
            )
            checkpoint = source_checkpoint()
            checkpoint["workspace_manifest_ref"] = manifest_ref
            with SQLiteObserverArtifactStore(database) as writable:
                before = database.read_bytes()
                with self.assertRaisesRegex(
                    SimulationBranchError, "workspace is unavailable"
                ):
                    materialize_simulation_workspace(checkpoint, writable)
                self.assertEqual(database.read_bytes(), before)

            for field, value in (
                ("completeness", "partial"),
                ("restore_mode", "supervised"),
                ("in_flight_invocation_ids", ["invocation-simulation-001"]),
                ("pending_action_ref", "artifact://actions/pending-001"),
                ("external_effect_refs", ["artifact://effects/known-001"]),
            ):
                ineligible = dict(checkpoint)
                ineligible[field] = value
                with self.subTest(field=field):
                    with SQLiteObserverArtifactStore(
                        database, read_only=True
                    ) as reader:
                        with self.assertRaisesRegex(
                            SimulationBranchError, "workspace is unavailable"
                        ):
                            materialize_simulation_workspace(ineligible, reader)

    def test_materializer_fails_closed_for_bad_manifests_and_paths(self):
        bad_manifests = (
            workspace_manifest((("../escape.py", b"x"),)),
            workspace_manifest((("src/../escape.py", b"x"),)),
            workspace_manifest((("/absolute.py", b"x"),)),
            workspace_manifest((("src\\routes.py", b"x"),)),
            workspace_manifest(((".env", b"x"),)),
            workspace_manifest((("src/.control", b"x"),)),
            workspace_manifest((("credentials.json", b"x"),)),
            workspace_manifest((("CON", b"x"),)),
            workspace_manifest((("a" * 129, b"x"),)),
            workspace_manifest((("a" * 1025, b"x"),)),
            workspace_manifest((("src//routes.py", b"x"),)),
            workspace_manifest((("Src/Routes.py", b"x"), ("src/routes.PY", b"y"))),
            {
                "schema": "workspace-manifest/v1",
                "files": [{
                    "path": "link.py",
                    "content_base64": base64.b64encode(b"target").decode("ascii"),
                    "content_digest": sha256_bytes(b"target"),
                    "mode": "120000",
                }],
            },
            {
                "schema": "workspace-manifest/v1",
                "files": [{
                    "path": "src.py",
                    "content_base64": "%%%",
                    "content_digest": sha256_bytes(b"x"),
                }],
            },
            {
                "schema": "workspace-manifest/v1",
                "files": [{
                    "path": "src.py",
                    "content_base64": base64.b64encode(b"x").decode("ascii"),
                    "content_digest": sha256_bytes(b"different"),
                }],
            },
            workspace_manifest((("src.py", b"-----BEGIN PRIVATE KEY-----"),)),
            {"schema": "workspace-manifest/v1", "files": []},
            {"schema": "workspace-manifest/v1", "files": [
                {"path": "empty.py", "content_base64": "", "content_digest": sha256_bytes(b"")}
            ] * 65},
            workspace_manifest(
                (
                    ("src/a.py", b"a" * (50 * 1024)),
                    ("src/b.py", b"b" * (50 * 1024)),
                    ("src/c.py", b"c" * (50 * 1024)),
                )
            ),
            workspace_manifest((("src/large.py", b"x" * (100 * 1024)),)),
        )
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "artifacts.sqlite3"
            refs = []
            for index, manifest in enumerate(bad_manifests):
                with self.subTest(artifact_index=index):
                    refs.append(save_manifest(database, manifest))
            checkpoint = source_checkpoint()
            for reference in refs:
                checkpoint["workspace_manifest_ref"] = reference
                with self.subTest(reference=reference):
                    with SQLiteObserverArtifactStore(
                        database, read_only=True
                    ) as reader:
                        with self.assertRaisesRegex(
                            SimulationBranchError, "workspace is unavailable"
                        ) as raised:
                            materialize_simulation_workspace(checkpoint, reader)
                        self.assertNotIn("PRIVATE KEY", str(raised.exception))

            checkpoint["workspace_manifest_ref"] = "artifact://sha256/" + "0" * 64
            with SQLiteObserverArtifactStore(database, read_only=True) as reader:
                with self.assertRaisesRegex(
                    SimulationBranchError, "workspace is unavailable"
                ):
                    materialize_simulation_workspace(checkpoint, reader)

            with self.assertRaisesRegex(
                ObserverArtifactStoreError, "content rejected"
            ):
                save_manifest(
                    database,
                    workspace_manifest((("src/too-large.py", b"x" * (200 * 1024)),)),
                )


if __name__ == "__main__":
    unittest.main()
