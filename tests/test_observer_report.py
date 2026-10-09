from __future__ import annotations

import hashlib
import io
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from app_contracts.observation_store import SQLiteObservationStore
from app_contracts.observer_artifact_store import SQLiteObserverArtifactStore
from app_contracts.observer_report import (
    MAX_ARTIFACT_REFERENCES,
    HistoryReportError,
    build_history_report,
    report_from_sqlite,
)
from app_contracts.digests import canonical_json
import report_observation_history as report_cli


SECRET_TEXT = "SYNTHETIC-private-rationale-marker"


def event(event_id: str, sequence: int, event_type: str = "tool_requested", **extra) -> dict:
    result = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": event_type,
        "process_id": "process-report-demo",
        "run_id": "run-report-demo",
        "branch_id": "branch-main",
        "task_id": "task-report-demo",
        "agent_id": "agent-worker-001",
        "sequence": sequence,
        "occurred_at": "2026-10-08T12:00:00Z",
        "recorded_at": "2026-10-08T12:00:01Z",
        "classification": "internal",
        "redaction_status": "complete",
    }
    result.update(extra)
    return result


def checkpoint(*, completeness="complete") -> dict:
    return {
        "schema_version": 1,
        "checkpoint_id": "checkpoint-report-demo",
        "kind": "tool_call",
        "process_id": "process-report-demo",
        "run_id": "run-report-demo",
        "branch_id": "branch-main",
        "agent_id": "agent-worker-001",
        "trigger_event_id": "event-report-first",
        "event_cursor": 0,
        "state_ref": "artifact://states/report-demo-000",
        "completeness": completeness,
        "restore_mode": "simulation",
        "created_at": "2026-10-08T12:00:02Z",
    }


class ObserverHistoryReportTests(unittest.TestCase):
    def test_empty_journal_is_read_only_and_never_claims_complete_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "empty.sqlite3"
            with SQLiteObservationStore(database):
                pass
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            report = report_from_sqlite(database)
            after = hashlib.sha256(database.read_bytes()).hexdigest()
            self.assertEqual(before, after)
            self.assertEqual(report["snapshot"]["event_count"], 0)
            self.assertEqual(report["snapshot"]["completeness"], "partial")
            self.assertEqual(
                report["gaps"], [{"code": "collector_coverage_unverified", "event_ids": []}]
            )
            self.assertFalse(Path(f"{database}-wal").exists())
            self.assertFalse(Path(f"{database}-shm").exists())

    def test_report_is_deterministic_redacted_and_exposes_structural_gaps(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "history.sqlite3"
            first = event(
                "event-report-first",
                0,
                invocation_id="invocation-report-001",
                status="pending",
                rationale=SECRET_TEXT,
                decision_or_tool="tool args must not be rendered",
            )
            second = event(
                "event-report-second",
                2,
                "outcome_unknown",
                invocation_id="invocation-report-001",
                causal_event_ids=["event-not-recorded"],
                input_refs=["artifact://inputs/report-demo-000"],
                redaction_status="redacted",
                rationale=SECRET_TEXT,
            )
            with SQLiteObservationStore(database) as store:
                store.append(first)
                store.append(second)
                store.record_checkpoint(checkpoint(completeness="partial"))

            before = hashlib.sha256(database.read_bytes()).hexdigest()
            result = report_from_sqlite(database)
            rendered = json.dumps(result, sort_keys=True, separators=(",", ":"))
            again = report_from_sqlite(database)
            self.assertEqual(result, again)
            self.assertNotIn(SECRET_TEXT, rendered)
            self.assertNotIn("tool args must not be rendered", rendered)
            self.assertNotIn("rationale", rendered)
            self.assertEqual([item["cursor"] for item in result["facts"]], [0, 1])
            self.assertEqual(result["source"]["trust"], "local_unattested")
            self.assertEqual(result["snapshot"]["completeness"], "partial")
            codes = [gap["code"] for gap in result["gaps"]]
            self.assertIn("event_sequence_gap", codes)
            self.assertIn("causal_reference_missing", codes)
            self.assertIn("external_outcome_unknown", codes)
            self.assertIn("event_content_redacted", codes)
            self.assertIn("checkpoint_partial", codes)
            self.assertIn("artifact_content_unresolved", codes)
            self.assertNotIn("tool_invocation_outcome_missing", codes)
            gap = next(gap for gap in result["gaps"] if gap["code"] == "event_sequence_gap")
            self.assertEqual(gap["missing_sequences"], [1])
            self.assertEqual(before, hashlib.sha256(database.read_bytes()).hexdigest())

    def test_report_resolves_only_digest_bound_artifact_metadata_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "history.sqlite3"
            artifacts = Path(temporary) / "artifacts.sqlite3"
            payload = canonical_json({"fixture": "synthetic-payload-not-for-report"})
            with SQLiteObserverArtifactStore(artifacts) as store:
                record = store.put_json(
                    payload, classification="internal", redaction_status="complete"
                )
            with SQLiteObservationStore(database) as store:
                store.append(
                    event(
                        "event-report-first",
                        0,
                        input_refs=[record.artifact_ref],
                    )
                )

            report = report_from_sqlite(database, artifact_database=artifacts)
            rendered = json.dumps(report, sort_keys=True, separators=(",", ":"))
            self.assertEqual(
                report["resolved_artifacts"],
                [
                    {
                        "artifact_ref": record.artifact_ref,
                        "content_digest": record.content_digest,
                        "content_bytes": record.content_bytes,
                    }
                ],
            )
            self.assertNotIn("artifact_content_unresolved", [g["code"] for g in report["gaps"]])
            self.assertIn("collector_coverage_unverified", [g["code"] for g in report["gaps"]])
            self.assertEqual(report["snapshot"]["completeness"], "partial")
            self.assertNotIn(payload.decode(), rendered)

            unresolved = report_from_sqlite(database)
            self.assertIn(
                "artifact_content_unresolved",
                [gap["code"] for gap in unresolved["gaps"]],
            )

    def test_report_resolves_all_checkpoint_reference_fields_without_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "history.sqlite3"
            artifacts = Path(temporary) / "artifacts.sqlite3"
            payloads = [
                canonical_json({"checkpoint_fixture": field})
                for field in range(7)
            ]
            with SQLiteObserverArtifactStore(artifacts) as artifact_store:
                records = [
                    artifact_store.put_json(
                        payload,
                        classification="internal",
                        redaction_status="complete",
                    )
                    for payload in payloads
                ]
            references = [record.artifact_ref for record in records]
            source_checkpoint = checkpoint()
            source_checkpoint.update(
                {
                    "state_ref": references[0],
                    "context_manifest_ref": references[1],
                    "workspace_manifest_ref": references[2],
                    "configuration_refs": [references[3]],
                    "authority_refs": [references[4]],
                    "pending_action_ref": references[5],
                    "external_effect_refs": [references[6]],
                }
            )
            with SQLiteObservationStore(database) as journal:
                journal.append(event("event-report-first", 0))
                journal.record_checkpoint(source_checkpoint)

            report = report_from_sqlite(database, artifact_database=artifacts)
            self.assertEqual(
                {item["artifact_ref"] for item in report["resolved_artifacts"]},
                set(references),
            )
            checkpoint_fact = report["checkpoints"][0]
            self.assertEqual(
                set(checkpoint_fact["artifact_refs"]),
                {
                    "state_ref",
                    "context_manifest_ref",
                    "workspace_manifest_ref",
                    "configuration_refs",
                    "authority_refs",
                    "pending_action_ref",
                    "external_effect_refs",
                },
            )
            self.assertNotIn(
                "artifact_content_unresolved", [gap["code"] for gap in report["gaps"]]
            )
            rendered = json.dumps(report, sort_keys=True, separators=(",", ":"))
            for payload in payloads:
                self.assertNotIn(payload.decode(), rendered)
            self.assertEqual(report["snapshot"]["completeness"], "partial")

    def test_report_redacts_invalid_artifact_reference_and_keeps_gap(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "history.sqlite3"
            unsafe_ref = 'artifact://api_key="SYNTHETIC_PRIVATE_MARKER_123456"'
            with SQLiteObservationStore(database) as store:
                store.append(
                    event("event-report-first", 0, input_refs=[unsafe_ref])
                )

            report = report_from_sqlite(database)
            rendered = json.dumps(report, sort_keys=True, separators=(",", ":"))
            codes = [gap["code"] for gap in report["gaps"]]
            self.assertIn("artifact_reference_invalid", codes)
            self.assertIn("artifact_content_unresolved", codes)
            self.assertNotIn(unsafe_ref, rendered)
            self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", rendered)
            self.assertNotIn("input_refs", report["facts"][0])

    def test_report_bounds_total_artifact_references(self):
        source = event(
            "event-report-first",
            0,
            input_refs=["artifact://inputs/report-demo-000"]
            * (MAX_ARTIFACT_REFERENCES + 1),
        )
        with self.assertRaisesRegex(
            HistoryReportError, "artifact reference limit exceeded"
        ):
            build_history_report([(0, source)], [])

        source_without_refs = event("event-report-first", 0)
        source_checkpoint = checkpoint()
        source_checkpoint["configuration_refs"] = [
            "artifact://inputs/report-demo-000"
        ] * (MAX_ARTIFACT_REFERENCES + 1)
        with self.assertRaisesRegex(
            HistoryReportError, "artifact reference limit exceeded"
        ):
            build_history_report(
                [(0, source_without_refs)], [(0, source_checkpoint)]
            )

    def test_cli_resolves_artifacts_without_printing_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            history = Path(temporary) / "history.sqlite3"
            artifact_db = Path(temporary) / "artifacts.sqlite3"
            payload = canonical_json({"fixture": "CLI_CONTENT_MARKER"})
            with SQLiteObserverArtifactStore(artifact_db) as store:
                record = store.put_json(
                    payload, classification="public", redaction_status="complete"
                )
            with SQLiteObservationStore(history) as store:
                store.append(
                    event("event-report-first", 0, output_refs=[record.artifact_ref])
                )
            output = io.StringIO()
            self.assertEqual(
                report_cli.main(
                    [str(history), "--artifact-database", str(artifact_db)],
                    stdout=output,
                ),
                0,
            )
            self.assertIn(record.artifact_ref, output.getvalue())
            self.assertNotIn("CLI_CONTENT_MARKER", output.getvalue())

    def test_as_of_and_scope_filters_do_not_include_later_or_other_run_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "history.sqlite3"
            first = event(
                "event-report-first", 0, invocation_id="invocation-report-001"
            )
            interleaved = event(
                "event-report-subagent",
                1,
                "decision_applied",
                agent_id="service-subagent-001",
            )
            later = event(
                "event-report-second",
                2,
                "tool_completed",
                invocation_id="invocation-report-001",
                status="ok",
            )
            other = event(
                "event-report-other",
                0,
                "agent_started",
                run_id="run-another-demo",
                agent_id="agent-other-001",
            )
            with SQLiteObservationStore(database) as store:
                store.append(first)
                store.append(interleaved)
                store.append(later)
                store.append(other)
                store.record_checkpoint(checkpoint())
            report = report_from_sqlite(
                database,
                process_id="process-report-demo",
                run_id="run-report-demo",
                branch_id="branch-main",
                as_of_cursor=0,
            )
            self.assertEqual([fact["event_id"] for fact in report["facts"]], ["event-report-first"])
            self.assertEqual(report["snapshot"]["event_count"], 1)
            self.assertEqual(report["snapshot"]["checkpoint_count"], 1)
            self.assertIn(
                "tool_invocation_outcome_missing",
                [gap["code"] for gap in report["gaps"]],
            )
            complete_run = report_from_sqlite(database, run_id="run-report-demo")
            self.assertNotIn(
                "event_sequence_gap",
                [gap["code"] for gap in complete_run["gaps"]],
            )
            with self.assertRaisesRegex(HistoryReportError, "selector is invalid"):
                report_from_sqlite(database, process_id="secret-value")
            with self.assertRaisesRegex(HistoryReportError, "cursor is invalid"):
                report_from_sqlite(database, as_of_cursor=99)
            with self.assertRaisesRegex(HistoryReportError, "cursor is invalid"):
                report_from_sqlite(database, as_of_cursor=True)

    def test_report_flags_causal_references_to_self_or_later_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "forward-causality.sqlite3"
            first = event(
                "event-report-first",
                0,
                causal_event_ids=["event-report-first", "event-report-second"],
            )
            second = event("event-report-second", 1, "tool_completed")
            with SQLiteObservationStore(database) as store:
                store.append(first)
                store.append(second)

            report = report_from_sqlite(database)
            gaps = [gap for gap in report["gaps"] if gap["code"] == "causal_reference_not_prior"]
            self.assertEqual(
                gaps,
                [
                    {
                        "code": "causal_reference_not_prior",
                        "event_ids": ["event-report-first"],
                        "referenced_event_ids": ["event-report-first"],
                    },
                    {
                        "code": "causal_reference_not_prior",
                        "event_ids": ["event-report-first"],
                        "referenced_event_ids": ["event-report-second"],
                    },
                ],
            )

    def test_digest_or_checkpoint_reference_corruption_fails_without_repair(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "corrupt.sqlite3"
            with SQLiteObservationStore(database) as store:
                store.append(event("event-report-first", 0))
                store.record_checkpoint(checkpoint())
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    "UPDATE observation_events SET event_json = ? WHERE event_id = ?",
                    (json.dumps(event("event-report-first", 0, rationale="tampered")), "event-report-first"),
                )
            with self.assertRaisesRegex(
                HistoryReportError, "^history report: journal is unavailable$"
            ):
                report_from_sqlite(database)
            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    "SELECT event_json FROM observation_events WHERE event_id = ?",
                    ("event-report-first",),
                ).fetchone()
            self.assertIn("tampered", row[0])

            bad_checkpoint = Path(temporary) / "checkpoint-corrupt.sqlite3"
            with SQLiteObservationStore(bad_checkpoint) as store:
                store.append(event("event-report-first", 0))
                store.record_checkpoint(checkpoint())
            with closing(sqlite3.connect(bad_checkpoint)) as connection, connection:
                connection.execute(
                    "UPDATE observation_checkpoints SET cursor = 9 WHERE checkpoint_id = ?",
                    ("checkpoint-report-demo",),
                )
            with self.assertRaisesRegex(
                HistoryReportError, "^history report: journal is unavailable$"
            ):
                report_from_sqlite(bad_checkpoint)

    def test_cli_emits_only_fixed_error_for_bad_journal_and_bad_selector(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "invalid.sqlite3"
            database.write_text("not a database", encoding="utf-8")
            output = io.StringIO()
            self.assertEqual(report_cli.main([str(database)], stdout=output), 2)
            self.assertEqual(
                output.getvalue(),
                '{"reason":"history-report-unavailable","status":"error"}\n',
            )

            valid = Path(temporary) / "valid.sqlite3"
            with SQLiteObservationStore(valid):
                pass
            output = io.StringIO()
            self.assertEqual(
                report_cli.main([str(valid), "--run-id", "bad selector"], stdout=output),
                2,
            )
            self.assertEqual(
                output.getvalue(),
                '{"reason":"history-report-unavailable","status":"error"}\n',
            )


if __name__ == "__main__":
    unittest.main()
