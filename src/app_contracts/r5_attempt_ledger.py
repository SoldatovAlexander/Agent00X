"""Append-only, no-repeat ledger for bounded R5 Worker attempts.

The ledger contains only schedule identity, fixed state/reason values, and
content digests. It has no Worker, model, credential, provider, or network
capability.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import threading

from .repository_process import SAFE_TARGET_TEST_FAILURE_CODES


_ATTEMPT_ID = re.compile(r"R5-(?:00[1-9]|0[1-9][0-9]|100)\Z")
_FIRST_FIVE = ("R5-001", "R5-002", "R5-003", "R5-004", "R5-005")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_STATES = frozenset({"PENDING", "CLAIMED", "COMPLETED", "UNKNOWN"})
_OUTCOMES = frozenset({"verified", "failed", "needs_input", "blocked", "denied"})
_UNKNOWN_PHASE_REASONS = frozenset(
    {
        "input-validation-error",
        "executor-uncaught-error",
        "result-validation-error",
        "executor-request-rejected",
        "executor-worker-rejected",
        "executor-sandbox-rejected",
        "executor-snapshot-rejected",
        "executor-preparation-rejected",
        "executor-verifier-rejected",
        "executor-stage-rejected",
        "executor-marker-unmapped",
        "executor-value-error",
        "executor-type-error",
        "executor-os-error",
        "executor-runtime-error",
        "executor-key-error",
        "executor-attribute-error",
        "executor-workspace-error",
        "executor-contract-invalid",
        "executor-test-result-malformed",
    }
)
R5_EXECUTION_FAILURE_REASONS = frozenset(
    {
        "observation-gate-failed",
        "sandbox-command-failed",
        "sandbox-create-failed",
        "sandbox-observation-gate-failed",
        "sandbox-outcome-unknown",
        "stage-observation-gate-failed",
        "stage-operation-failed",
        "stage-outcome-unknown",
        "stage-persistence-failed",
        "verification-replay-failed",
        "verifier-attestation-invalid",
        "verifier-failed",
        "verifier-not-pass",
        "verifier-observation-gate-failed",
        "verifier-outcome-unknown",
        "verifier-trust-unestablished",
        "worker-failed",
        "worker-outcome-unknown",
        "worker-proposal-invalid",
        "target-tests-failed",
        "target-test-readiness-exit",
        "target-test-readiness-timeout",
        "target-test-overflow-status",
        "target-test-overflow-no-write",
        "target-test-valid-status",
        "target-test-valid-body",
        "target-test-valid-row",
    }
) | SAFE_TARGET_TEST_FAILURE_CODES
_REASONS = frozenset(
    {
        "none",
        "execution-failed",
        "worker-clarification",
        "worker-blocked",
        "worker-denied",
        "worker-error",
        "pipeline-error",
        "interrupted",
        "result-unavailable",
    }
) | R5_EXECUTION_FAILURE_REASONS | _UNKNOWN_PHASE_REASONS
_UNKNOWN_REASONS = frozenset(
    {"interrupted", "result-unavailable", "pipeline-error"}
) | _UNKNOWN_PHASE_REASONS
_SCHEMA_VERSION = 1


class R5AttemptLedgerError(ValueError):
    """A fixed, redacted ledger error."""


@dataclass(frozen=True)
class R5AttemptRecord:
    attempt_id: str
    state: str
    input_digest: str | None
    result_digest: str | None
    outcome: str | None
    reason_code: str | None


class SQLiteR5AttemptLedger:
    """Create or reopen one caller-selected SQLite ledger without replay."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self._connection = connection
        self._closed = False
        self._lock = threading.RLock()

    @classmethod
    def create(
        cls, path: Path | str, *, allowed_attempt_ids: tuple[str, ...]
    ) -> "SQLiteR5AttemptLedger":
        destination = _validate_new_path(path)
        attempts = _validate_attempt_ids(allowed_attempt_ids)
        if attempts != _FIRST_FIVE:
            raise R5AttemptLedgerError("R5 attempt ledger: attempt list rejected")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(destination, flags, 0o600)
            os.close(descriptor)
        except Exception:
            raise R5AttemptLedgerError("R5 attempt ledger: destination unavailable") from None
        try:
            connection = sqlite3.connect(
                str(destination), timeout=5.0, isolation_level=None,
                check_same_thread=False,
            )
            _set_connection_profile(connection)
            connection.executescript(
                """
                CREATE TABLE ledger_meta (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    schema_version INTEGER NOT NULL,
                    allowed_attempt_ids TEXT NOT NULL
                );
                CREATE TABLE attempts (
                    attempt_id TEXT PRIMARY KEY
                );
                CREATE TABLE attempt_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                    state TEXT NOT NULL CHECK(state IN ('CLAIMED','COMPLETED','UNKNOWN')),
                    input_digest TEXT NOT NULL,
                    result_digest TEXT,
                    outcome TEXT,
                    reason_code TEXT,
                    CHECK(
                        (state = 'CLAIMED' AND result_digest IS NULL AND outcome IS NULL AND reason_code IS NULL)
                        OR (state = 'COMPLETED' AND result_digest IS NOT NULL AND outcome IS NOT NULL AND reason_code IS NOT NULL)
                        OR (state = 'UNKNOWN' AND outcome IS NULL AND reason_code IS NOT NULL)
                    )
                );
                CREATE INDEX attempt_events_by_attempt ON attempt_events(attempt_id, event_id);
                CREATE TRIGGER attempt_events_no_update BEFORE UPDATE ON attempt_events
                    BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER attempt_events_no_delete BEFORE DELETE ON attempt_events
                    BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER attempts_no_update BEFORE UPDATE ON attempts
                    BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER attempts_no_delete BEFORE DELETE ON attempts
                    BEGIN SELECT RAISE(ABORT, 'append only'); END;
                PRAGMA user_version = 1;
                """
            )
            connection.execute(
                "INSERT INTO ledger_meta(singleton, schema_version, allowed_attempt_ids) VALUES (1, ?, ?)",
                (_SCHEMA_VERSION, json.dumps(attempts, separators=(",", ":"))),
            )
            connection.executemany(
                "INSERT INTO attempts(attempt_id) VALUES (?)",
                [(attempt_id,) for attempt_id in attempts],
            )
            return cls(destination, connection)
        except Exception:
            try:
                connection.close()
            except Exception:
                pass
            raise R5AttemptLedgerError("R5 attempt ledger: initialization failed") from None

    @classmethod
    def open_existing(cls, path: Path | str) -> "SQLiteR5AttemptLedger":
        source = _validate_existing_path(path)
        try:
            connection = sqlite3.connect(
                f"file:{source.as_posix()}?mode=rw", uri=True, timeout=5.0,
                isolation_level=None, check_same_thread=False,
            )
            _set_connection_profile(connection)
            _validate_existing_schema(connection)
            return cls(source, connection)
        except Exception:
            try:
                connection.close()
            except Exception:
                pass
            raise R5AttemptLedgerError("R5 attempt ledger: existing ledger rejected") from None

    def claim(self, attempt_id: str, input_digest: str) -> None:
        """Atomically spend a pending ID before the caller invokes its Worker."""

        _validate_digest(input_digest)
        with self._lock:
            self._ensure_open()
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                known = self._connection.execute(
                    "SELECT 1 FROM attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                last = self._connection.execute(
                    "SELECT state FROM attempt_events WHERE attempt_id=? "
                    "ORDER BY event_id DESC LIMIT 1",
                    (attempt_id,),
                ).fetchone()
                if known is None or last is not None:
                    self._connection.execute("ROLLBACK")
                    raise R5AttemptLedgerError("R5 attempt ledger: claim unavailable")
                self._connection.execute(
                    "INSERT INTO attempt_events(attempt_id,state,input_digest) "
                    "VALUES (?, 'CLAIMED', ?)",
                    (attempt_id, input_digest),
                )
                self._connection.execute("COMMIT")
            except R5AttemptLedgerError:
                raise
            except Exception:
                try:
                    self._connection.execute("ROLLBACK")
                except Exception:
                    pass
                raise R5AttemptLedgerError("R5 attempt ledger: claim failed") from None

    def complete(
        self,
        attempt_id: str,
        *,
        result_digest: str,
        outcome: str,
        reason_code: str = "none",
    ) -> None:
        _validate_digest(result_digest)
        if outcome not in _OUTCOMES or reason_code not in _REASONS:
            raise R5AttemptLedgerError("R5 attempt ledger: result rejected")
        self._transition(
            attempt_id,
            state="COMPLETED",
            result_digest=result_digest,
            outcome=outcome,
            reason_code=reason_code,
        )

    def mark_unknown(
        self,
        attempt_id: str,
        *,
        reason_code: str,
        result_digest: str | None = None,
    ) -> None:
        if reason_code not in _UNKNOWN_REASONS:
            raise R5AttemptLedgerError("R5 attempt ledger: result rejected")
        if result_digest is not None:
            _validate_digest(result_digest)
        self._transition(
            attempt_id,
            state="UNKNOWN",
            result_digest=result_digest,
            outcome=None,
            reason_code=reason_code,
        )

    def get(self, attempt_id: str) -> R5AttemptRecord:
        self._ensure_open()
        try:
            return _read_record(self._connection, attempt_id)
        except Exception:
            raise R5AttemptLedgerError("R5 attempt ledger: record unavailable") from None

    def records(self) -> tuple[R5AttemptRecord, ...]:
        self._ensure_open()
        try:
            ids = self._connection.execute(
                "SELECT attempt_id FROM attempts ORDER BY attempt_id"
            ).fetchall()
            return tuple(_read_record(self._connection, row[0]) for row in ids)
        except Exception:
            raise R5AttemptLedgerError("R5 attempt ledger: records unavailable") from None

    def extend_allowed_attempt_ids(self, additional_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Atomically append later scheduled IDs without changing prior evidence."""

        additions = _validate_attempt_ids(additional_ids)
        with self._lock:
            self._ensure_open()
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                meta = self._connection.execute(
                    "SELECT allowed_attempt_ids FROM ledger_meta WHERE singleton=1"
                ).fetchone()
                if type(meta) is not tuple or type(meta[0]) is not str:
                    raise ValueError
                current = _validate_attempt_ids(tuple(json.loads(meta[0])))
                if not current or set(current).intersection(additions):
                    raise ValueError
                if additions != tuple(
                    sorted(additions, key=lambda value: int(value[3:]))
                ) or int(additions[0][3:]) <= int(current[-1][3:]):
                    raise ValueError
                updated = current + additions
                if updated != tuple(sorted(updated, key=lambda value: int(value[3:]))):
                    raise ValueError
                actual = tuple(
                    row[0]
                    for row in self._connection.execute(
                        "SELECT attempt_id FROM attempts ORDER BY attempt_id"
                    ).fetchall()
                )
                if actual != tuple(sorted(current)):
                    raise ValueError
                self._connection.executemany(
                    "INSERT INTO attempts(attempt_id) VALUES (?)",
                    [(attempt_id,) for attempt_id in additions],
                )
                self._connection.execute(
                    "UPDATE ledger_meta SET allowed_attempt_ids=? WHERE singleton=1",
                    (json.dumps(updated, separators=(",", ":")),),
                )
                self._connection.execute("COMMIT")
                return updated
            except Exception:
                try:
                    self._connection.execute("ROLLBACK")
                except Exception:
                    pass
                raise R5AttemptLedgerError("R5 attempt ledger: extension rejected") from None

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "SQLiteR5AttemptLedger":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _transition(
        self,
        attempt_id: str,
        *,
        state: str,
        result_digest: str | None,
        outcome: str | None,
        reason_code: str,
    ) -> None:
        with self._lock:
            self._ensure_open()
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                last = self._connection.execute(
                    "SELECT state,input_digest FROM attempt_events "
                    "WHERE attempt_id=? ORDER BY event_id DESC LIMIT 1",
                    (attempt_id,),
                ).fetchone()
                if last is None or last[0] != "CLAIMED":
                    self._connection.execute("ROLLBACK")
                    raise R5AttemptLedgerError("R5 attempt ledger: transition unavailable")
                self._connection.execute(
                    "INSERT INTO attempt_events(attempt_id,state,input_digest,result_digest,outcome,reason_code) "
                    "VALUES (?,?,?,?,?,?)",
                    (attempt_id, state, last[1], result_digest, outcome, reason_code),
                )
                self._connection.execute("COMMIT")
            except R5AttemptLedgerError:
                raise
            except Exception:
                try:
                    self._connection.execute("ROLLBACK")
                except Exception:
                    pass
                raise R5AttemptLedgerError("R5 attempt ledger: transition failed") from None

    def _ensure_open(self) -> None:
        if self._closed:
            raise R5AttemptLedgerError("R5 attempt ledger: ledger is closed")


def _validate_attempt_ids(values: object) -> tuple[str, ...]:
    if type(values) is not tuple or not values or len(values) > 100:
        raise R5AttemptLedgerError("R5 attempt ledger: attempt list rejected")
    if any(type(value) is not str or _ATTEMPT_ID.fullmatch(value) is None for value in values):
        raise R5AttemptLedgerError("R5 attempt ledger: attempt list rejected")
    if len(set(values)) != len(values):
        raise R5AttemptLedgerError("R5 attempt ledger: attempt list rejected")
    if values != tuple(sorted(values, key=lambda value: int(value[3:]))):
        raise R5AttemptLedgerError("R5 attempt ledger: attempt list rejected")
    return values


def _validate_digest(value: object) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise R5AttemptLedgerError("R5 attempt ledger: digest rejected")


def _validate_new_path(value: object) -> Path:
    if type(value) is str:
        path = Path(value)
    elif isinstance(value, Path):
        path = value
    else:
        raise R5AttemptLedgerError("R5 attempt ledger: destination unavailable")
    if (
        not path.is_absolute()
        or path.name in {"", ".", ".."}
        or not path.parent.is_dir()
        or path.parent.is_symlink()
        or path.exists()
        or path.is_symlink()
        or Path(str(path) + "-wal").exists()
        or Path(str(path) + "-shm").exists()
    ):
        raise R5AttemptLedgerError("R5 attempt ledger: destination unavailable")
    return path


def _validate_existing_path(value: object) -> Path:
    if type(value) is str:
        path = Path(value)
    elif isinstance(value, Path):
        path = value
    else:
        raise R5AttemptLedgerError("R5 attempt ledger: existing ledger rejected")
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise R5AttemptLedgerError("R5 attempt ledger: existing ledger rejected")
    return path


def _set_connection_profile(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA busy_timeout=5000")


def _read_record(connection: sqlite3.Connection, attempt_id: str) -> R5AttemptRecord:
    exists = connection.execute(
        "SELECT 1 FROM attempts WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    if exists is None:
        raise ValueError
    event = connection.execute(
        "SELECT state,input_digest,result_digest,outcome,reason_code "
        "FROM attempt_events WHERE attempt_id=? ORDER BY event_id DESC LIMIT 1",
        (attempt_id,),
    ).fetchone()
    if event is None:
        return R5AttemptRecord(attempt_id, "PENDING", None, None, None, None)
    state, input_digest, result_digest, outcome, reason_code = event
    _validate_digest(input_digest)
    if state == "CLAIMED":
        if result_digest is not None or outcome is not None or reason_code is not None:
            raise ValueError
    elif state == "COMPLETED":
        _validate_digest(result_digest)
        if outcome not in _OUTCOMES or reason_code not in _REASONS:
            raise ValueError
    elif state == "UNKNOWN":
        if result_digest is not None:
            _validate_digest(result_digest)
        if outcome is not None or reason_code not in _UNKNOWN_REASONS:
            raise ValueError
    else:
        raise ValueError
    return R5AttemptRecord(
        attempt_id, state, input_digest, result_digest, outcome, reason_code
    )


def _validate_existing_schema(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA user_version").fetchone() != (_SCHEMA_VERSION,):
        raise ValueError
    meta = connection.execute(
        "SELECT schema_version, allowed_attempt_ids FROM ledger_meta WHERE singleton=1"
    ).fetchone()
    if type(meta) is not tuple or meta[0] != _SCHEMA_VERSION:
        raise ValueError
    allowed = json.loads(meta[1])
    validated = _validate_attempt_ids(tuple(allowed))
    actual = tuple(
        row[0]
        for row in connection.execute(
            "SELECT attempt_id FROM attempts ORDER BY attempt_id"
        ).fetchall()
    )
    if set(actual) != set(validated) or len(actual) != len(validated):
        raise ValueError
    for attempt_id in validated:
        events = connection.execute(
            "SELECT state,input_digest,result_digest,outcome,reason_code "
            "FROM attempt_events WHERE attempt_id=? ORDER BY event_id",
            (attempt_id,),
        ).fetchall()
        if len(events) > 2:
            raise ValueError
        if events:
            if events[0][0] != "CLAIMED":
                raise ValueError
            _validate_digest(events[0][1])
            if any(value is not None for value in events[0][2:]):
                raise ValueError
        if len(events) == 2:
            state, input_digest, result_digest, outcome, reason_code = events[1]
            if events[0][1] != input_digest or state not in {"COMPLETED", "UNKNOWN"}:
                raise ValueError
            _read_record(connection, attempt_id)
        if events and events[-1][0] == "CLAIMED":
            _read_record(connection, attempt_id)
