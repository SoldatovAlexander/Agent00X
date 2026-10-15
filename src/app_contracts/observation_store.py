"""Minimal in-memory append-only store for validated ObservationEvent records.

The store is a local R0 step toward the append-only observation journal from
document 28. It is not a durable audit journal: contents live only in memory.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any

from .digests import sha256_digest
from .validator import ContractValidationError, validate


def _load_schema(name: str) -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / name
    with schema_path.open(encoding="utf-8") as handle:
        return json.load(handle)


EVENT_SCHEMA = _load_schema("observation-event.schema.json")
CHECKPOINT_SCHEMA = _load_schema("checkpoint.schema.json")

_INTENT_EVENT_TYPES = frozenset({
    "decision_proposed",
    "tool_requested",
})


class EventConflictError(ValueError):
    """A second record reuses an event_id with different content."""


class PreDispatchError(RuntimeError):
    """The pre-dispatch gate refused; no side effect was started."""


class ObservationStoreError(RuntimeError):
    """The local observation journal could not be opened safely."""


def _create_private_database_file(path: str) -> None:
    """Create a missing on-disk SQLite file without exposing a broad mode."""

    if path == ":memory:":
        return
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        return
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def run_gated_dispatch(
    store: ObservationStore,
    *,
    checkpoint: dict[str, Any],
    intent_event: dict[str, Any],
    dispatch,
    once: bool = False,
    on_intent_recorded=None,
):
    """Record the checkpoint and the intent event before dispatch.

    The ``dispatch`` callable runs only after both writes succeed. Any store
    failure raises PreDispatchError without starting the side effect.
    A malformed store collaborator or a non-callable dispatch target is
    refused before any record call or dispatch execution.
    """

    if (
        not callable(getattr(store, "record_checkpoint", None))
        or not callable(getattr(store, "append", None))
    ):
        raise PreDispatchError("pre-dispatch gate refused: store is invalid")
    if not callable(dispatch):
        raise PreDispatchError("pre-dispatch gate refused: dispatch is not callable")
    if on_intent_recorded is not None and not callable(on_intent_recorded):
        raise PreDispatchError("pre-dispatch gate refused: intent callback is invalid")
    try:
        if once:
            persist_once = getattr(store, "record_checkpoint_and_intent_once", None)
            if not callable(persist_once):
                raise ObservationStoreError("one-shot journal insertion unavailable")
            cursor = persist_once(checkpoint, intent_event)
            if on_intent_recorded is not None:
                on_intent_recorded(cursor)
            return cursor, dispatch()
        persist_pair = getattr(store, "record_checkpoint_and_intent", None)
        if callable(persist_pair):
            cursor = persist_pair(checkpoint, intent_event)
        else:
            store.record_checkpoint(checkpoint)
            cursor = store.append(intent_event)
        if on_intent_recorded is not None:
            on_intent_recorded(cursor)
    except (ContractValidationError, EventConflictError, ObservationStoreError) as exc:
        raise PreDispatchError(f"pre-dispatch gate refused: {exc}") from exc
    return cursor, dispatch()


class ObservationStore:
    """Append-only insertion-ordered store of schema-valid observation events."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._digests: dict[str, str] = {}
        self._checkpoints: list[dict[str, Any]] = []
        self._checkpoint_digests: dict[str, str] = {}
        self._claim_lock = Lock()

    def append(self, event: dict[str, Any]) -> int:
        """Validate and append an event, returning its insertion cursor.

        Re-appending the same ``event_id`` with identical content is idempotent
        and returns the original cursor without creating a second record.
        Reusing an ``event_id`` with different content raises EventConflictError.
        """

        validate(event, EVENT_SCHEMA)
        digest = sha256_digest(event)
        event_id = event["event_id"]
        known = self._digests.get(event_id)
        if known is not None:
            if known == digest:
                return self._position(event_id)
            raise EventConflictError("event id conflict")
        self._events.append(copy.deepcopy(event))
        self._digests[event_id] = digest
        return len(self._events) - 1

    def check_checkpoint(self, checkpoint: dict[str, Any]) -> int:
        """Validate a checkpoint reference against recorded history.

        Returns the checkpoint cursor when the trigger event exists and the
        cursor is inside the journal. Never returns event payloads; use the
        explicit read API to fetch events.
        """

        if not isinstance(checkpoint, dict):
            raise ContractValidationError("checkpoint is malformed")
        validate(checkpoint, CHECKPOINT_SCHEMA)
        trigger = checkpoint["trigger_event_id"]
        trigger_position: int | None = None
        for position, stored in enumerate(self._events):
            if stored["event_id"] == trigger:
                trigger_event = stored
                trigger_position = position
                break
        else:
            trigger_event = None
        if trigger_event is None or trigger_position is None:
            raise ContractValidationError("unknown trigger event")
        for field in ("process_id", "run_id", "branch_id"):
            if trigger_event[field] != checkpoint[field]:
                raise ContractValidationError(f"checkpoint trigger {field} mismatch")
        cursor = checkpoint["event_cursor"]
        if cursor >= len(self._events):
            raise ContractValidationError("checkpoint cursor is beyond journal end")
        if cursor != trigger_position:
            raise ContractValidationError("checkpoint cursor does not match trigger position")
        return cursor

    def record_checkpoint(self, checkpoint: dict[str, Any]) -> int:
        """Validate and persist a checkpoint, returning its insertion index.

        Re-recording the same ``checkpoint_id`` with identical content is
        idempotent and returns the original index without creating a second
        record. Reusing a ``checkpoint_id`` with different content raises
        EventConflictError.
        """

        self.check_checkpoint(checkpoint)
        digest = sha256_digest(checkpoint)
        checkpoint_id = checkpoint["checkpoint_id"]
        known = self._checkpoint_digests.get(checkpoint_id)
        if known is not None:
            if known == digest:
                return self._checkpoint_position(checkpoint_id)
            raise EventConflictError("checkpoint id conflict")
        self._checkpoints.append(copy.deepcopy(checkpoint))
        self._checkpoint_digests[checkpoint_id] = digest
        return len(self._checkpoints) - 1

    def record_checkpoint_and_intent_once(
        self, checkpoint: dict[str, Any], intent_event: dict[str, Any]
    ) -> int:
        """Atomically append one intent ID only once within this store instance."""
        validate(intent_event, EVENT_SCHEMA)
        with self._claim_lock:
            if intent_event["event_id"] in self._digests:
                raise EventConflictError("one-shot intent already recorded")
            self.record_checkpoint(checkpoint)
            return self.append(intent_event)

    def checkpoints(self) -> tuple[dict[str, Any], ...]:
        """Return stored checkpoints in insertion order as detached copies."""

        return tuple(copy.deepcopy(item) for item in self._checkpoints)

    def check_result_causality(self, result_event: dict[str, Any]) -> int:
        """Validate that a result event references a recorded intent invocation.

        Returns the intent cursor when another recorded event carries the same
        ``invocation_id``. A missing or foreign reference is rejected without
        returning any stored payload.
        """

        validate(result_event, EVENT_SCHEMA)
        invocation_id = result_event.get("invocation_id")
        if not invocation_id:
            raise ContractValidationError("result has no invocation reference")
        own_position: int | None = None
        for position, stored in enumerate(self._events):
            if stored["event_id"] == result_event["event_id"]:
                own_position = position
                break
        preceding: list[int] = []
        saw_non_intent = False
        saw_later_intent = False
        for position, stored in enumerate(self._events):
            if stored.get("invocation_id") != invocation_id or stored["event_id"] == result_event["event_id"]:
                continue
            if stored.get("event_type") not in _INTENT_EVENT_TYPES:
                saw_non_intent = True
                continue
            if own_position is not None and position >= own_position:
                saw_later_intent = True
                continue
            preceding.append(position)
        if len(preceding) > 1:
            raise ContractValidationError("ambiguous invocation reference")
        if len(preceding) == 1:
            return preceding[0]
        if saw_later_intent:
            raise ContractValidationError("invocation reference is not preceding")
        if saw_non_intent:
            raise ContractValidationError("invocation reference is not an intent")
        raise ContractValidationError("unknown invocation reference")

    def events(self) -> tuple[dict[str, Any], ...]:
        """Return stored events in insertion order as detached copies."""

        return tuple(copy.deepcopy(event) for event in self._events)

    def __len__(self) -> int:
        return len(self._events)

    def _position(self, event_id: str) -> int:
        for position, stored in enumerate(self._events):
            if stored["event_id"] == event_id:
                return position
        raise KeyError(event_id)  # pragma: no cover - index always consistent

    def _checkpoint_position(self, checkpoint_id: str) -> int:
        for position, stored in enumerate(self._checkpoints):
            if stored["checkpoint_id"] == checkpoint_id:
                return position
        raise KeyError(checkpoint_id)  # pragma: no cover - index always consistent


class SQLiteObservationStore:
    """Versioned local SQLite journal shell; durability claims stay local-only."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        if isinstance(path, Path):
            path_text: str | None = str(path)
        elif isinstance(path, str):
            path_text = path
        else:
            path_text = None
        if not path_text:
            raise ObservationStoreError("observation journal: database path is invalid")
        try:
            _create_private_database_file(path_text)
            self._connection = sqlite3.connect(path_text)
            self._connection.row_factory = sqlite3.Row
            self._initialize_schema()
            self._validate_persisted_rows()
        except (OSError, sqlite3.Error, ObservationStoreError) as exc:
            connection = getattr(self, "_connection", None)
            if connection is not None:
                connection.close()
            if isinstance(exc, ObservationStoreError):
                raise
            raise ObservationStoreError("observation journal: database could not be opened") from exc

    def _initialize_schema(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if version == 0 and not tables:
            with self._connection:
                self._connection.execute(
                    """CREATE TABLE observation_events (
                        event_id TEXT PRIMARY KEY,
                        cursor INTEGER NOT NULL UNIQUE,
                        event_json TEXT NOT NULL,
                        digest TEXT NOT NULL
                    )"""
                )
                self._connection.execute(
                    """CREATE TABLE observation_checkpoints (
                        checkpoint_id TEXT PRIMARY KEY,
                        cursor INTEGER NOT NULL UNIQUE,
                        checkpoint_json TEXT NOT NULL,
                        digest TEXT NOT NULL
                    )"""
                )
                self._connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            return
        if version != self.SCHEMA_VERSION:
            raise ObservationStoreError("observation journal: unsupported schema version")
        expected = {
            "observation_events": {"event_id", "cursor", "event_json", "digest"},
            "observation_checkpoints": {"checkpoint_id", "cursor", "checkpoint_json", "digest"},
        }
        if not expected.keys() <= tables:
            raise ObservationStoreError("observation journal: schema is malformed")
        for table, columns in expected.items():
            actual = {
                row[1]
                for row in self._connection.execute(f"PRAGMA table_info({table})")
            }
            if actual != columns:
                raise ObservationStoreError("observation journal: schema is malformed")

    def _validate_persisted_rows(self) -> None:
        """Refuse malformed persisted content without attempting a repair."""

        try:
            for expected_cursor, row in enumerate(
                self._connection.execute(
                    "SELECT event_id, cursor, event_json, digest "
                    "FROM observation_events ORDER BY cursor"
                )
            ):
                event = json.loads(row["event_json"])
                validate(event, EVENT_SCHEMA)
                if (
                    row["cursor"] != expected_cursor
                    or event["event_id"] != row["event_id"]
                    or sha256_digest(event) != row["digest"]
                ):
                    raise ValueError("event row mismatch")
            for expected_cursor, row in enumerate(
                self._connection.execute(
                    "SELECT checkpoint_id, cursor, checkpoint_json, digest "
                    "FROM observation_checkpoints ORDER BY cursor"
                )
            ):
                checkpoint = json.loads(row["checkpoint_json"])
                validate(checkpoint, CHECKPOINT_SCHEMA)
                if (
                    row["cursor"] != expected_cursor
                    or checkpoint["checkpoint_id"] != row["checkpoint_id"]
                    or sha256_digest(checkpoint) != row["digest"]
                ):
                    raise ValueError("checkpoint row mismatch")
                self.check_checkpoint(checkpoint)
        except (ContractValidationError, TypeError, ValueError, KeyError, IndexError) as exc:
            raise ObservationStoreError("observation journal: persisted records are malformed") from exc

    def events(self) -> tuple[dict[str, Any], ...]:
        rows = self._connection.execute(
            "SELECT event_json FROM observation_events ORDER BY cursor"
        ).fetchall()
        return tuple(json.loads(row[0]) for row in rows)

    def checkpoints(self) -> tuple[dict[str, Any], ...]:
        rows = self._connection.execute(
            "SELECT checkpoint_json FROM observation_checkpoints ORDER BY cursor"
        ).fetchall()
        return tuple(json.loads(row[0]) for row in rows)

    def __len__(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM observation_events"
        ).fetchone()[0]

    def append(self, event: dict[str, Any]) -> int:
        """Validate and persist an event, returning its stable journal cursor."""

        validate(event, EVENT_SCHEMA)
        digest = sha256_digest(event)
        event_id = event["event_id"]
        try:
            with self._connection:
                known = self._connection.execute(
                    "SELECT cursor, digest FROM observation_events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if known is not None:
                    if known["digest"] == digest:
                        return known["cursor"]
                    raise EventConflictError("event id conflict")
                cursor = self._connection.execute(
                    "SELECT COALESCE(MAX(cursor) + 1, 0) FROM observation_events"
                ).fetchone()[0]
                self._connection.execute(
                    "INSERT INTO observation_events(event_id, cursor, event_json, digest) "
                    "VALUES (?, ?, ?, ?)",
                    (event_id, cursor, json.dumps(event, sort_keys=True, separators=(",", ":")), digest),
                )
                return cursor
        except sqlite3.Error as exc:
            raise ObservationStoreError("observation journal: event could not be stored") from exc

    def check_checkpoint(self, checkpoint: dict[str, Any]) -> int:
        if not isinstance(checkpoint, dict):
            raise ContractValidationError("checkpoint is malformed")
        validate(checkpoint, CHECKPOINT_SCHEMA)
        events = self.events()
        trigger = checkpoint["trigger_event_id"]
        trigger_event: dict[str, Any] | None = None
        trigger_position: int | None = None
        for position, stored in enumerate(events):
            if stored["event_id"] == trigger:
                trigger_event = stored
                trigger_position = position
                break
        if trigger_event is None or trigger_position is None:
            raise ContractValidationError("unknown trigger event")
        for field in ("process_id", "run_id", "branch_id"):
            if trigger_event[field] != checkpoint[field]:
                raise ContractValidationError(f"checkpoint trigger {field} mismatch")
        cursor = checkpoint["event_cursor"]
        if cursor >= len(events):
            raise ContractValidationError("checkpoint cursor is beyond journal end")
        if cursor != trigger_position:
            raise ContractValidationError("checkpoint cursor does not match trigger position")
        return cursor

    def record_checkpoint(self, checkpoint: dict[str, Any]) -> int:
        """Validate and persist a checkpoint against the recorded event history."""

        self.check_checkpoint(checkpoint)
        digest = sha256_digest(checkpoint)
        checkpoint_id = checkpoint["checkpoint_id"]
        try:
            with self._connection:
                known = self._connection.execute(
                    "SELECT cursor, digest FROM observation_checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                ).fetchone()
                if known is not None:
                    if known["digest"] == digest:
                        return known["cursor"]
                    raise EventConflictError("checkpoint id conflict")
                cursor = self._connection.execute(
                    "SELECT COALESCE(MAX(cursor) + 1, 0) FROM observation_checkpoints"
                ).fetchone()[0]
                self._connection.execute(
                    "INSERT INTO observation_checkpoints(checkpoint_id, cursor, checkpoint_json, digest) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        checkpoint_id,
                        cursor,
                        json.dumps(checkpoint, sort_keys=True, separators=(",", ":")),
                        digest,
                    ),
                )
                return cursor
        except sqlite3.Error as exc:
            raise ObservationStoreError("observation journal: checkpoint could not be stored") from exc

    def check_result_causality(self, result_event: dict[str, Any]) -> int:
        """Resolve a result's preceding intent from the persisted event order."""

        validate(result_event, EVENT_SCHEMA)
        invocation_id = result_event.get("invocation_id")
        if not invocation_id:
            raise ContractValidationError("result has no invocation reference")
        events = self.events()
        own_position: int | None = None
        for position, stored in enumerate(events):
            if stored["event_id"] == result_event["event_id"]:
                own_position = position
                break
        preceding: list[int] = []
        saw_non_intent = False
        saw_later_intent = False
        for position, stored in enumerate(events):
            if stored.get("invocation_id") != invocation_id or stored["event_id"] == result_event["event_id"]:
                continue
            if stored.get("event_type") not in _INTENT_EVENT_TYPES:
                saw_non_intent = True
                continue
            if own_position is not None and position >= own_position:
                saw_later_intent = True
                continue
            preceding.append(position)
        if len(preceding) > 1:
            raise ContractValidationError("ambiguous invocation reference")
        if len(preceding) == 1:
            return preceding[0]
        if saw_later_intent:
            raise ContractValidationError("invocation reference is not preceding")
        if saw_non_intent:
            raise ContractValidationError("invocation reference is not an intent")
        raise ContractValidationError("unknown invocation reference")

    def record_checkpoint_and_intent(
        self, checkpoint: dict[str, Any], intent_event: dict[str, Any]
    ) -> int:
        """Commit a validated checkpoint and its intent event in one transaction."""

        validate(intent_event, EVENT_SCHEMA)
        intent_digest = sha256_digest(intent_event)
        intent_id = intent_event["event_id"]
        checkpoint_digest = sha256_digest(checkpoint) if isinstance(checkpoint, dict) else ""
        checkpoint_id = checkpoint.get("checkpoint_id") if isinstance(checkpoint, dict) else None
        try:
            with self._connection:
                self.check_checkpoint(checkpoint)
                known_checkpoint = self._connection.execute(
                    "SELECT digest FROM observation_checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                ).fetchone()
                if known_checkpoint is not None and known_checkpoint["digest"] != checkpoint_digest:
                    raise EventConflictError("checkpoint id conflict")
                known_event = self._connection.execute(
                    "SELECT cursor, digest FROM observation_events WHERE event_id = ?",
                    (intent_id,),
                ).fetchone()
                if known_event is not None and known_event["digest"] != intent_digest:
                    raise EventConflictError("event id conflict")
                if known_checkpoint is None:
                    checkpoint_cursor = self._connection.execute(
                        "SELECT COALESCE(MAX(cursor) + 1, 0) FROM observation_checkpoints"
                    ).fetchone()[0]
                    self._connection.execute(
                        "INSERT INTO observation_checkpoints(checkpoint_id, cursor, checkpoint_json, digest) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            checkpoint_id,
                            checkpoint_cursor,
                            json.dumps(checkpoint, sort_keys=True, separators=(",", ":")),
                            checkpoint_digest,
                        ),
                    )
                if known_event is not None:
                    return known_event["cursor"]
                event_cursor = self._connection.execute(
                    "SELECT COALESCE(MAX(cursor) + 1, 0) FROM observation_events"
                ).fetchone()[0]
                self._connection.execute(
                    "INSERT INTO observation_events(event_id, cursor, event_json, digest) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        intent_id,
                        event_cursor,
                        json.dumps(intent_event, sort_keys=True, separators=(",", ":")),
                        intent_digest,
                    ),
                )
                return event_cursor
        except sqlite3.Error as exc:
            raise ObservationStoreError("observation journal: gated records could not be stored") from exc

    def record_checkpoint_and_intent_once(
        self, checkpoint: dict[str, Any], intent_event: dict[str, Any]
    ) -> int:
        """Commit one checkpoint/intent pair and reject any repeated intent ID.

        `BEGIN IMMEDIATE` serializes competing local processes before checking
        the unique event ID. Only the process that inserts the deterministic
        one-shot intent may dispatch the associated publication callback.
        """
        validate(intent_event, EVENT_SCHEMA)
        intent_digest = sha256_digest(intent_event)
        intent_id = intent_event["event_id"]
        checkpoint_digest = sha256_digest(checkpoint) if isinstance(checkpoint, dict) else ""
        checkpoint_id = checkpoint.get("checkpoint_id") if isinstance(checkpoint, dict) else None
        try:
            with self._connection:
                self._connection.execute("BEGIN IMMEDIATE")
                self.check_checkpoint(checkpoint)
                known_event = self._connection.execute(
                    "SELECT 1 FROM observation_events WHERE event_id = ?",
                    (intent_id,),
                ).fetchone()
                if known_event is not None:
                    raise EventConflictError("one-shot intent already recorded")
                known_checkpoint = self._connection.execute(
                    "SELECT digest FROM observation_checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                ).fetchone()
                if known_checkpoint is not None:
                    if known_checkpoint["digest"] != checkpoint_digest:
                        raise EventConflictError("checkpoint id conflict")
                else:
                    checkpoint_cursor = self._connection.execute(
                        "SELECT COALESCE(MAX(cursor) + 1, 0) FROM observation_checkpoints"
                    ).fetchone()[0]
                    self._connection.execute(
                        "INSERT INTO observation_checkpoints(checkpoint_id, cursor, checkpoint_json, digest) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            checkpoint_id,
                            checkpoint_cursor,
                            json.dumps(checkpoint, sort_keys=True, separators=(",", ":")),
                            checkpoint_digest,
                        ),
                    )
                event_cursor = self._connection.execute(
                    "SELECT COALESCE(MAX(cursor) + 1, 0) FROM observation_events"
                ).fetchone()[0]
                self._connection.execute(
                    "INSERT INTO observation_events(event_id, cursor, event_json, digest) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        intent_id,
                        event_cursor,
                        json.dumps(intent_event, sort_keys=True, separators=(",", ":")),
                        intent_digest,
                    ),
                )
                return event_cursor
        except (ContractValidationError, EventConflictError, ObservationStoreError):
            raise
        except sqlite3.Error as exc:
            raise ObservationStoreError("observation journal: one-shot intent could not be stored") from exc

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteObservationStore:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
