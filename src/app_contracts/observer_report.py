"""Read-only structural history reports for the local observer journal.

Reports intentionally omit free-text event payloads. They describe only rows
verified in one local SQLite journal and always disclose that collector
coverage and external/artifact state are not independently known.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any

from .digests import sha256_digest
from .brainbooster_target_profile import PINNED_HTTP_DB_FAILURE_CODES
from .observer_artifact_store import (
    ArtifactResolution,
    ObserverArtifactStoreError,
    SQLiteObserverArtifactStore,
)
from .observation_store import CHECKPOINT_SCHEMA, EVENT_SCHEMA
from .validator import validate


MAX_DATABASE_BYTES = 256 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_RECORD_BYTES = 1024 * 1024
MAX_ARTIFACT_REFERENCES = 10_000
_ID_PATTERNS = {
    "process_id": re.compile(r"^process-[a-z0-9-]{1,120}$"),
    "run_id": re.compile(r"^run-[a-z0-9-]{1,120}$"),
    "branch_id": re.compile(r"^branch-[a-z0-9-]{1,120}$"),
}
_SAFE_ARTIFACT_REF = re.compile(r"artifact://[A-Za-z0-9_./-]{1,256}\Z")
_EVENT_COLUMNS = {"event_id", "cursor", "event_json", "digest"}
_CHECKPOINT_COLUMNS = {"checkpoint_id", "cursor", "checkpoint_json", "digest"}
_TERMINAL_TOOL_EVENTS = frozenset(
    {"tool_completed", "tool_failed", "tool_denied", "outcome_unknown"}
)


class HistoryReportError(ValueError):
    """A journal cannot be safely represented as a structural report."""


def _safe_error() -> HistoryReportError:
    return HistoryReportError("history report: journal is unavailable")


def _read_only_rows(path: str | Path) -> tuple[list[tuple[int, dict]], list[tuple[int, dict]]]:
    """Read and verify one existing SQLite journal without creating sidecars."""

    try:
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise ValueError
        source = source.resolve(strict=True)
        if source.stat().st_size > MAX_DATABASE_BYTES:
            raise ValueError
        if Path(f"{source}-wal").exists() or Path(f"{source}-shm").exists():
            raise ValueError
        uri = f"{source.as_uri()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, timeout=1)
        connection.row_factory = sqlite3.Row
        try:
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise ValueError
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables != {"observation_events", "observation_checkpoints"}:
                raise ValueError
            for table, expected in (
                ("observation_events", _EVENT_COLUMNS),
                ("observation_checkpoints", _CHECKPOINT_COLUMNS),
            ):
                actual = {
                    row[1]
                    for row in connection.execute(f"PRAGMA table_info({table})")
                }
                if actual != expected:
                    raise ValueError

            events: list[tuple[int, dict]] = []
            for expected_cursor, row in enumerate(
                connection.execute(
                    "SELECT event_id, cursor, event_json, digest "
                    "FROM observation_events ORDER BY cursor"
                )
            ):
                if len(events) >= MAX_RECORDS or len(row["event_json"].encode("utf-8")) > MAX_RECORD_BYTES:
                    raise ValueError
                event = json.loads(row["event_json"])
                validate(event, EVENT_SCHEMA)
                if (
                    type(row["cursor"]) is not int
                    or row["cursor"] != expected_cursor
                    or row["event_id"] != event["event_id"]
                    or row["digest"] != sha256_digest(event)
                ):
                    raise ValueError
                events.append((row["cursor"], event))

            checkpoints: list[tuple[int, dict]] = []
            event_by_id = {event["event_id"]: (cursor, event) for cursor, event in events}
            for expected_cursor, row in enumerate(
                connection.execute(
                    "SELECT checkpoint_id, cursor, checkpoint_json, digest "
                    "FROM observation_checkpoints ORDER BY cursor"
                )
            ):
                if len(events) + len(checkpoints) >= MAX_RECORDS or len(row["checkpoint_json"].encode("utf-8")) > MAX_RECORD_BYTES:
                    raise ValueError
                checkpoint = json.loads(row["checkpoint_json"])
                validate(checkpoint, CHECKPOINT_SCHEMA)
                trigger = event_by_id.get(checkpoint["trigger_event_id"])
                if (
                    type(row["cursor"]) is not int
                    or row["cursor"] != expected_cursor
                    or row["checkpoint_id"] != checkpoint["checkpoint_id"]
                    or row["digest"] != sha256_digest(checkpoint)
                    or trigger is None
                    or checkpoint["event_cursor"] != trigger[0]
                    or any(
                        checkpoint[field] != trigger[1][field]
                        for field in ("process_id", "run_id", "branch_id")
                    )
                ):
                    raise ValueError
                checkpoints.append((row["cursor"], checkpoint))
            return events, checkpoints
        finally:
            connection.close()
    except Exception:
        raise _safe_error() from None


def _validate_selector(name: str, value: str | None) -> None:
    if value is not None and (type(value) is not str or not _ID_PATTERNS[name].fullmatch(value)):
        raise HistoryReportError("history report: selector is invalid")


def _parse_recorded_time(value: object) -> datetime:
    """Parse one timezone-aware RFC3339 timestamp and normalize it to UTC."""

    try:
        if type(value) is not str or not value or len(value) > 64:
            raise ValueError
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except Exception:
        raise HistoryReportError("history report: timestamp is invalid") from None


def build_history_report(
    events: list[tuple[int, dict]],
    checkpoints: list[tuple[int, dict]],
    *,
    process_id: str | None = None,
    run_id: str | None = None,
    branch_id: str | None = None,
    as_of_cursor: int | None = None,
    as_of_recorded_at: str | None = None,
    about_occurred_at: str | None = None,
    artifact_resolver: object | None = None,
) -> dict[str, Any]:
    """Build a deterministic partial report from verified journal rows."""

    if len(events) + len(checkpoints) > MAX_RECORDS:
        raise HistoryReportError("history report: journal is unavailable")
    try:
        for expected_cursor, item in enumerate(events):
            cursor, event = item
            if type(cursor) is not int or cursor != expected_cursor:
                raise ValueError
            validate(event, EVENT_SCHEMA)
        event_by_id = {event["event_id"]: (cursor, event) for cursor, event in events}
        if len(event_by_id) != len(events):
            raise ValueError
        for expected_cursor, item in enumerate(checkpoints):
            cursor, checkpoint = item
            trigger = event_by_id.get(checkpoint.get("trigger_event_id"))
            if (
                type(cursor) is not int
                or cursor != expected_cursor
                or trigger is None
            ):
                raise ValueError
            validate(checkpoint, CHECKPOINT_SCHEMA)
            if (
                checkpoint["event_cursor"] != trigger[0]
                or any(
                    checkpoint[field] != trigger[1][field]
                    for field in ("process_id", "run_id", "branch_id")
                )
            ):
                raise ValueError
    except Exception:
        raise HistoryReportError("history report: journal is unavailable") from None

    for name, value in (
        ("process_id", process_id),
        ("run_id", run_id),
        ("branch_id", branch_id),
    ):
        _validate_selector(name, value)
    temporal_selectors = sum(
        value is not None
        for value in (as_of_cursor, as_of_recorded_at, about_occurred_at)
    )
    if temporal_selectors > 1:
        raise HistoryReportError("history report: temporal selector is invalid")
    cutoff = (
        _parse_recorded_time(as_of_recorded_at)
        if as_of_recorded_at is not None
        else None
    )
    about_cutoff = (
        _parse_recorded_time(about_occurred_at)
        if about_occurred_at is not None
        else None
    )
    if as_of_cursor is not None and (
        type(as_of_cursor) is not int
        or as_of_cursor < 0
        or (events and as_of_cursor > events[-1][0])
        or (not events and as_of_cursor != 0)
    ):
        raise HistoryReportError("history report: cursor is invalid")

    all_events = [event for _, event in events]
    cursor_by_event_id = {event["event_id"]: cursor for cursor, event in events}
    selected: list[tuple[int, dict]] = []
    for cursor, event in events:
        if as_of_cursor is not None and cursor > as_of_cursor:
            continue
        if cutoff is not None and _parse_recorded_time(event["recorded_at"]) > cutoff:
            continue
        if (
            about_cutoff is not None
            and _parse_recorded_time(event["occurred_at"]) > about_cutoff
        ):
            continue
        if process_id is not None and event["process_id"] != process_id:
            continue
        if run_id is not None and event["run_id"] != run_id:
            continue
        if branch_id is not None and event["branch_id"] != branch_id:
            continue
        selected.append((cursor, event))
    selected_ids = {event["event_id"] for _, event in selected}
    all_ids = {event["event_id"] for event in all_events}
    selected_checkpoints = [
        (cursor, checkpoint)
        for cursor, checkpoint in checkpoints
        if (as_of_cursor is None or checkpoint["event_cursor"] <= as_of_cursor)
        and (
            cutoff is None
            or (
                checkpoint["trigger_event_id"] in selected_ids
                and _parse_recorded_time(checkpoint["created_at"]) <= cutoff
            )
        )
        and (
            about_cutoff is None
            or (
                checkpoint["trigger_event_id"] in selected_ids
                and _parse_recorded_time(checkpoint["created_at"]) <= about_cutoff
            )
        )
        and (process_id is None or checkpoint["process_id"] == process_id)
        and (run_id is None or checkpoint["run_id"] == run_id)
        and (branch_id is None or checkpoint["branch_id"] == branch_id)
    ]

    if artifact_resolver is not None and not callable(
        getattr(artifact_resolver, "resolve", None)
    ):
        raise HistoryReportError("history report: artifact resolver is invalid")

    facts: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = [
        {"code": "collector_coverage_unverified", "event_ids": []}
    ]
    temporally_unverified_event_ids: set[str] = set()
    if cutoff is not None:
        gaps.append({"code": "recorded_timestamps_unattested", "event_ids": []})
    if about_cutoff is not None:
        gaps.append({"code": "occurred_timestamps_unattested", "event_ids": []})
        if selected_checkpoints:
            gaps.append(
                {
                    "code": "checkpoint_availability_at_time_unverified",
                    "event_ids": sorted(
                        checkpoint["trigger_event_id"]
                        for _, checkpoint in selected_checkpoints
                    ),
                }
            )
    resolved_artifacts: dict[str, ArtifactResolution] = {}
    artifact_reference_count = 0
    by_run: dict[tuple[str, str, str], list[tuple[int, dict]]] = {}
    invocations: dict[str, list[tuple[int, dict]]] = {}
    agent_lifecycle: dict[
        tuple[str, str, str, str, str],
        dict[str, list[tuple[int, dict]]],
    ] = {}
    for cursor, event in selected:
        fact: dict[str, Any] = {
            "cursor": cursor,
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "process_id": event["process_id"],
            "run_id": event["run_id"],
            "branch_id": event["branch_id"],
            "task_id": event["task_id"],
            "agent_id": event["agent_id"],
            "sequence": event["sequence"],
            "occurred_at": event["occurred_at"],
            "recorded_at": event["recorded_at"],
            "classification": event["classification"],
            "redaction_status": event["redaction_status"],
        }
        if about_cutoff is not None:
            fact["recorded_after_about_time"] = (
                _parse_recorded_time(event["recorded_at"]) > about_cutoff
            )
        for field in ("status", "checkpoint_id", "invocation_id"):
            if field in event:
                fact[field] = event[field]
        safe_parameters = event.get("safe_parameters")
        if (
            event.get("decision_or_tool")
            in {
                "SandboxSession.run.target-tests",
                "SandboxSession.run.verifier-replay",
            }
            and type(safe_parameters) is dict
            and type(safe_parameters.get("sandbox_return_code")) is int
            and -255 <= safe_parameters["sandbox_return_code"] <= 255
        ):
            fact["sandbox_return_code"] = safe_parameters["sandbox_return_code"]
        if (
            event.get("decision_or_tool") == "SandboxSession.run.target-tests"
            and type(safe_parameters) is dict
            and type(safe_parameters.get("sandbox_failure_code")) is str
            and safe_parameters["sandbox_failure_code"] in PINNED_HTTP_DB_FAILURE_CODES
        ):
            fact["sandbox_failure_code"] = safe_parameters["sandbox_failure_code"]
        if "causal_event_ids" in event:
            fact["causal_event_ids"] = list(event["causal_event_ids"])
        for field in ("input_refs", "output_refs"):
            if field in event:
                safe_refs = [
                    reference
                    for reference in event[field]
                    if type(reference) is str
                    and _SAFE_ARTIFACT_REF.fullmatch(reference) is not None
                ]
                if len(safe_refs) == len(event[field]):
                    fact[field] = safe_refs
                else:
                    gaps.append(
                        {
                            "code": "artifact_reference_invalid",
                            "event_ids": [event["event_id"]],
                        }
                    )
        facts.append(fact)
        by_run.setdefault(
            (event["process_id"], event["run_id"], event["branch_id"]), []
        ).append((cursor, event))
        invocation_id = event.get("invocation_id")
        if invocation_id:
            invocations.setdefault(invocation_id, []).append((cursor, event))
        if event["event_type"] == "tool_requested" and not invocation_id:
            gaps.append({"code": "tool_invocation_id_missing", "event_ids": [event["event_id"]]})
        if event["event_type"] in {"agent_started", "agent_finished"}:
            invocation_id = event.get("invocation_id")
            if type(invocation_id) is not str:
                gaps.append(
                    {
                        "code": "agent_invocation_id_missing",
                        "event_ids": [event["event_id"]],
                    }
                )
                if event["event_type"] == "agent_started":
                    gaps.append(
                        {
                            "code": "agent_terminal_event_missing",
                            "event_ids": [event["event_id"]],
                        }
                    )
            else:
                agent_key = (
                    event["process_id"],
                    event["run_id"],
                    event["branch_id"],
                    event["agent_id"],
                    invocation_id,
                )
                lifecycle = agent_lifecycle.setdefault(
                    agent_key, {"started": [], "finished": []}
                )
                lifecycle[
                    "started"
                    if event["event_type"] == "agent_started"
                    else "finished"
                ].append((cursor, event))
        if event["redaction_status"] == "redacted":
            gaps.append({"code": "event_content_redacted", "event_ids": [event["event_id"]]})
        if event["event_type"] == "outcome_unknown" or event.get("status") == "unknown":
            gaps.append({"code": "external_outcome_unknown", "event_ids": [event["event_id"]]})
        for causal_id in event.get("causal_event_ids", ()):
            if causal_id not in all_ids:
                gaps.append({"code": "causal_reference_missing", "event_ids": [event["event_id"]]})
            else:
                if cursor_by_event_id[causal_id] >= cursor:
                    gaps.append(
                        {
                            "code": "causal_reference_not_prior",
                            "event_ids": [event["event_id"]],
                            "referenced_event_ids": [causal_id],
                        }
                    )
                if causal_id not in selected_ids:
                    gaps.append(
                        {
                            "code": "causal_reference_out_of_view",
                            "event_ids": [event["event_id"]],
                        }
                    )
        artifact_refs = tuple(event.get("input_refs", ())) + tuple(
            event.get("output_refs", ())
        )
        if artifact_refs:
            if about_cutoff is not None:
                temporally_unverified_event_ids.add(event["event_id"])
            artifact_reference_count += len(artifact_refs)
            if artifact_reference_count > MAX_ARTIFACT_REFERENCES:
                raise HistoryReportError(
                    "history report: artifact reference limit exceeded"
                )
            unresolved = False
            for artifact_ref in artifact_refs:
                if (
                    type(artifact_ref) is not str
                    or _SAFE_ARTIFACT_REF.fullmatch(artifact_ref) is None
                ):
                    unresolved = True
                    continue
                if artifact_ref in resolved_artifacts:
                    continue
                if cutoff is not None:
                    unresolved = True
                    temporally_unverified_event_ids.add(event["event_id"])
                    continue
                if artifact_resolver is None:
                    unresolved = True
                    continue
                if len(resolved_artifacts) >= MAX_ARTIFACT_REFERENCES:
                    raise HistoryReportError(
                        "history report: artifact reference limit exceeded"
                    )
                try:
                    resolution = artifact_resolver.resolve(artifact_ref)
                    if (
                        type(resolution) is not ArtifactResolution
                        or resolution.artifact_ref != artifact_ref
                        or type(resolution.content_digest) is not str
                        or re.fullmatch(r"sha256:[0-9a-f]{64}", resolution.content_digest) is None
                        or type(resolution.content_bytes) is not int
                        or not 0 < resolution.content_bytes <= MAX_RECORD_BYTES
                    ):
                        raise ValueError
                    resolved_artifacts[artifact_ref] = resolution
                except Exception:
                    unresolved = True
            if unresolved:
                gaps.append(
                    {
                        "code": "artifact_content_unresolved",
                        "event_ids": [event["event_id"]],
                    }
                )

    checkpoint_facts: list[dict[str, Any]] = []
    checkpoint_reference_fields = (
        "state_ref",
        "context_manifest_ref",
        "workspace_manifest_ref",
        "configuration_refs",
        "authority_refs",
        "pending_action_ref",
        "external_effect_refs",
    )
    for _, checkpoint in selected_checkpoints:
        safe_checkpoint_refs: dict[str, list[str]] = {}
        checkpoint_refs: list[str] = []
        invalid_reference = False
        unresolved_reference = False
        for field in checkpoint_reference_fields:
            if field not in checkpoint:
                continue
            raw_refs = checkpoint[field]
            refs = tuple(raw_refs) if type(raw_refs) is list else (raw_refs,)
            checkpoint_refs.extend(refs)
            safe_refs = [
                reference
                for reference in refs
                if type(reference) is str
                and _SAFE_ARTIFACT_REF.fullmatch(reference) is not None
            ]
            if len(safe_refs) != len(refs):
                invalid_reference = True
            else:
                safe_checkpoint_refs[field] = safe_refs

        artifact_reference_count += len(checkpoint_refs)
        if about_cutoff is not None and checkpoint_refs:
            temporally_unverified_event_ids.add(checkpoint["trigger_event_id"])
        if artifact_reference_count > MAX_ARTIFACT_REFERENCES:
            raise HistoryReportError(
                "history report: artifact reference limit exceeded"
            )
        for artifact_ref in checkpoint_refs:
            if (
                type(artifact_ref) is not str
                or _SAFE_ARTIFACT_REF.fullmatch(artifact_ref) is None
            ):
                unresolved_reference = True
                continue
            if artifact_ref in resolved_artifacts:
                continue
            if cutoff is not None:
                unresolved_reference = True
                temporally_unverified_event_ids.add(checkpoint["trigger_event_id"])
                continue
            if artifact_resolver is None:
                unresolved_reference = True
                continue
            if len(resolved_artifacts) >= MAX_ARTIFACT_REFERENCES:
                raise HistoryReportError(
                    "history report: artifact reference limit exceeded"
                )
            try:
                resolution = artifact_resolver.resolve(artifact_ref)
                if (
                    type(resolution) is not ArtifactResolution
                    or resolution.artifact_ref != artifact_ref
                    or type(resolution.content_digest) is not str
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", resolution.content_digest) is None
                    or type(resolution.content_bytes) is not int
                    or not 0 < resolution.content_bytes <= MAX_RECORD_BYTES
                ):
                    raise ValueError
                resolved_artifacts[artifact_ref] = resolution
            except Exception:
                unresolved_reference = True

        if invalid_reference:
            gaps.append(
                {
                    "code": "artifact_reference_invalid",
                    "event_ids": [checkpoint["trigger_event_id"]],
                    "checkpoint_ids": [checkpoint["checkpoint_id"]],
                }
            )
        if unresolved_reference:
            gaps.append(
                {
                    "code": "artifact_content_unresolved",
                    "event_ids": [checkpoint["trigger_event_id"]],
                    "checkpoint_ids": [checkpoint["checkpoint_id"]],
                }
            )

        checkpoint_fact = {
            "cursor": _,
            "checkpoint_id": checkpoint["checkpoint_id"],
            "kind": checkpoint["kind"],
            "event_cursor": checkpoint["event_cursor"],
            "trigger_event_id": checkpoint["trigger_event_id"],
            "completeness": checkpoint["completeness"],
            "restore_mode": checkpoint["restore_mode"],
        }
        if safe_checkpoint_refs:
            checkpoint_fact["artifact_refs"] = safe_checkpoint_refs
        checkpoint_facts.append(checkpoint_fact)
        if checkpoint["completeness"] == "partial":
            gaps.append(
                {
                    "code": "checkpoint_partial",
                    "event_ids": [checkpoint["trigger_event_id"]],
                }
            )

    for run_events in by_run.values():
        sequences = sorted(event["sequence"] for _, event in run_events)
        expected = list(range(0, sequences[-1] + 1)) if sequences else []
        missing = sorted(set(expected) - set(sequences))
        duplicated = sorted(number for number, count in Counter(sequences).items() if count > 1)
        if missing or duplicated:
            gaps.append(
                {
                    "code": "event_sequence_gap",
                    "event_ids": [event["event_id"] for _, event in run_events],
                    "missing_sequences": missing,
                    "duplicate_sequences": duplicated,
                }
            )

    for lifecycle in agent_lifecycle.values():
        starts = lifecycle["started"]
        finishes = lifecycle["finished"]
        lifecycle_ids = [
            event["event_id"] for _, event in sorted(starts + finishes)
        ]
        if len(starts) > 1 or len(finishes) > 1:
            gaps.append(
                {
                    "code": "agent_lifecycle_pair_ambiguous",
                    "event_ids": lifecycle_ids,
                }
            )
        if starts and not finishes:
            gaps.append(
                {
                    "code": "agent_terminal_event_missing",
                    "event_ids": [event["event_id"] for _, event in starts],
                }
            )
        if finishes and not starts:
            gaps.append(
                {
                    "code": "agent_start_event_missing",
                    "event_ids": [event["event_id"] for _, event in finishes],
                }
            )
        if len(starts) == 1 and len(finishes) == 1:
            start_cursor, start_event = starts[0]
            finish_cursor, finish_event = finishes[0]
            if (
                start_cursor >= finish_cursor
                or start_event["event_id"]
                not in finish_event.get("causal_event_ids", ())
            ):
                gaps.append(
                    {
                        "code": "agent_lifecycle_causality_missing",
                        "event_ids": [
                            start_event["event_id"],
                            finish_event["event_id"],
                        ],
                    }
                )

    for invocation_id, invocation_events in invocations.items():
        requested = [event for _, event in invocation_events if event["event_type"] == "tool_requested"]
        terminal = [event for _, event in invocation_events if event["event_type"] in _TERMINAL_TOOL_EVENTS]
        if requested and not terminal:
            gaps.append(
                {
                    "code": "tool_invocation_outcome_missing",
                    "event_ids": [event["event_id"] for event in requested],
                }
            )

    if temporally_unverified_event_ids:
        gaps.append(
            {
                "code": "artifact_availability_at_time_unverified",
                "event_ids": sorted(temporally_unverified_event_ids),
            }
        )

    gaps.sort(key=lambda gap: (gap["code"], tuple(gap["event_ids"])))
    return {
        "schema_version": 1,
        "source": {
            "kind": "sqlite_observation_journal",
            "trust": "local_unattested",
            "scope": "verified_loaded_rows_only",
        },
        "snapshot": {
            "as_of_cursor": as_of_cursor,
            "as_of_recorded_at": (
                cutoff.isoformat().replace("+00:00", "Z")
                if cutoff is not None
                else None
            ),
            "about_occurred_at": (
                about_cutoff.isoformat().replace("+00:00", "Z")
                if about_cutoff is not None
                else None
            ),
            "event_count": len(facts),
            "checkpoint_count": len(selected_checkpoints),
            "completeness": "partial",
        },
        "facts": facts,
        "resolved_artifacts": [
            {
                "artifact_ref": item.artifact_ref,
                "content_digest": item.content_digest,
                "content_bytes": item.content_bytes,
            }
            for _, item in sorted(resolved_artifacts.items())
        ],
        "checkpoints": checkpoint_facts,
        "gaps": gaps,
    }


def report_from_sqlite(
    path: str | Path,
    *,
    process_id: str | None = None,
    run_id: str | None = None,
    branch_id: str | None = None,
    as_of_cursor: int | None = None,
    as_of_recorded_at: str | None = None,
    about_occurred_at: str | None = None,
    artifact_database: str | Path | None = None,
) -> dict[str, Any]:
    events, checkpoints = _read_only_rows(path)
    if artifact_database is None:
        return build_history_report(
            events,
            checkpoints,
            process_id=process_id,
            run_id=run_id,
            branch_id=branch_id,
            as_of_cursor=as_of_cursor,
            as_of_recorded_at=as_of_recorded_at,
            about_occurred_at=about_occurred_at,
        )
    try:
        with SQLiteObserverArtifactStore(artifact_database, read_only=True) as artifacts:
            return build_history_report(
                events,
                checkpoints,
                process_id=process_id,
                run_id=run_id,
                branch_id=branch_id,
                as_of_cursor=as_of_cursor,
                as_of_recorded_at=as_of_recorded_at,
                about_occurred_at=about_occurred_at,
                artifact_resolver=artifacts,
            )
    except ObserverArtifactStoreError:
        raise HistoryReportError("history report: artifact store is unavailable") from None
