"""Durable SQLite process state and append-only transition audit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .state_machine import ProcessState, TransitionEvidence, transition
from .validator import ContractValidationError


class ProcessStoreError(RuntimeError):
    pass


class ProcessNotFound(ProcessStoreError):
    pass


class VersionConflict(ProcessStoreError):
    pass


@dataclass(frozen=True)
class ProcessRecord:
    process_id: str
    state: ProcessState
    version: int
    updated_at: str


class SQLiteProcessStore:
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS processes (
                    process_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS process_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    process_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    previous_state TEXT,
                    state TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    UNIQUE(process_id, sequence),
                    FOREIGN KEY(process_id) REFERENCES processes(process_id)
                )"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS process_events_no_update
                   BEFORE UPDATE ON process_events
                   BEGIN SELECT RAISE(ABORT, 'process events are append-only'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS process_events_no_delete
                   BEFORE DELETE ON process_events
                   BEGIN SELECT RAISE(ABORT, 'process events are append-only'); END"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    process_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    result TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY(process_id) REFERENCES processes(process_id)
                )"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                   BEFORE UPDATE ON audit_events
                   BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                   BEFORE DELETE ON audit_events
                   BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END"""
            )

    def create(self, process_id: str, *, now: datetime | None = None) -> ProcessRecord:
        timestamp = _timestamp(now)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO processes(process_id, state, version, updated_at) VALUES (?, ?, 0, ?)",
                    (process_id, ProcessState.RECEIVED.value, timestamp),
                )
                self._connection.execute(
                    """INSERT INTO process_events
                       (process_id, sequence, previous_state, state, evidence_json, occurred_at)
                       VALUES (?, 0, NULL, ?, ?, ?)""",
                    (process_id, ProcessState.RECEIVED.value, "{}", timestamp),
                )
        except sqlite3.IntegrityError as exc:
            raise ProcessStoreError(f"process already exists: {process_id}") from exc
        return self.get(process_id)

    def get(self, process_id: str) -> ProcessRecord:
        row = self._connection.execute(
            "SELECT process_id, state, version, updated_at FROM processes WHERE process_id = ?",
            (process_id,),
        ).fetchone()
        if row is None:
            raise ProcessNotFound(process_id)
        return ProcessRecord(row["process_id"], ProcessState(row["state"]), row["version"], row["updated_at"])

    def advance(
        self,
        process_id: str,
        target: ProcessState,
        evidence: TransitionEvidence,
        *,
        expected_version: int,
        now: datetime | None = None,
    ) -> ProcessRecord:
        current = self.get(process_id)
        if current.version != expected_version:
            raise VersionConflict(f"expected version {expected_version}, found {current.version}")
        next_state = transition(current.state, target, evidence)
        timestamp = _timestamp(now)
        evidence_json = json.dumps(evidence.__dict__, sort_keys=True, separators=(",", ":"))
        next_version = current.version + 1
        with self._connection:
            updated = self._connection.execute(
                """UPDATE processes SET state = ?, version = ?, updated_at = ?
                   WHERE process_id = ? AND version = ?""",
                (next_state.value, next_version, timestamp, process_id, expected_version),
            )
            if updated.rowcount != 1:
                raise VersionConflict(f"concurrent update for {process_id}")
            self._connection.execute(
                """INSERT INTO process_events
                   (process_id, sequence, previous_state, state, evidence_json, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (process_id, next_version, current.state.value, next_state.value, evidence_json, timestamp),
            )
        return self.get(process_id)

    def events(self, process_id: str) -> list[dict[str, object]]:
        self.get(process_id)
        rows = self._connection.execute(
            """SELECT event_id, sequence, previous_state, state, evidence_json, occurred_at
               FROM process_events WHERE process_id = ? ORDER BY sequence""",
            (process_id,),
        ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "sequence": row["sequence"],
                "previous_state": row["previous_state"],
                "state": row["state"],
                "evidence": json.loads(row["evidence_json"]),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def append_audit_event(
        self,
        process_id: str,
        *,
        actor_id: str,
        event_type: str,
        input_digest: str,
        result: str,
        reason_codes: tuple[str, ...],
        now: datetime | None = None,
    ) -> None:
        _validate_reason_codes(reason_codes)
        self.get(process_id)
        with self._connection:
            self._connection.execute(
                """INSERT INTO audit_events
                   (process_id, actor_id, event_type, input_digest, result, reason_codes_json, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    process_id, actor_id, event_type, input_digest, result,
                    json.dumps(reason_codes, separators=(",", ":")), _timestamp(now),
                ),
            )

    def audit_events(self, process_id: str) -> list[dict[str, object]]:
        self.get(process_id)
        rows = self._connection.execute(
            """SELECT event_id, actor_id, event_type, input_digest, result, reason_codes_json, occurred_at
               FROM audit_events WHERE process_id = ? ORDER BY event_id""",
            (process_id,),
        ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "actor_id": row["actor_id"],
                "event_type": row["event_type"],
                "input_digest": row["input_digest"],
                "result": row["result"],
                "reason_codes": json.loads(row["reason_codes_json"]),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteProcessStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


_MAX_REASON_CODE_LENGTH = 128


def _validate_reason_codes(reason_codes: object) -> None:
    """Fail closed on non-string, empty or oversized audit reason codes."""

    if (
        not isinstance(reason_codes, (list, tuple))
        or not reason_codes
        or any(
            not isinstance(code, str) or not code or len(code) > _MAX_REASON_CODE_LENGTH
            for code in reason_codes
        )
    ):
        raise ContractValidationError("audit: reason code is invalid")


def _timestamp(value: datetime | None) -> str:
    moment = value or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
