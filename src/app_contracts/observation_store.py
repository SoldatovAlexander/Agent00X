"""Minimal in-memory append-only store for validated ObservationEvent records.

The store is a local R0 step toward the append-only observation journal from
document 28. It is not a durable audit journal: contents live only in memory.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .digests import sha256_digest
from .validator import ContractValidationError, validate


def _load_schema(name: str) -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / name
    with schema_path.open(encoding="utf-8") as handle:
        return json.load(handle)


EVENT_SCHEMA = _load_schema("observation-event.schema.json")
CHECKPOINT_SCHEMA = _load_schema("checkpoint.schema.json")


class EventConflictError(ValueError):
    """A second record reuses an event_id with different content."""


class PreDispatchError(RuntimeError):
    """The pre-dispatch gate refused; no side effect was started."""


def run_gated_dispatch(
    store: ObservationStore,
    *,
    checkpoint: dict[str, Any],
    intent_event: dict[str, Any],
    dispatch,
):
    """Record the checkpoint and the intent event before dispatch.

    The ``dispatch`` callable runs only after both writes succeed. Any store
    failure raises PreDispatchError without starting the side effect.
    """

    try:
        store.record_checkpoint(checkpoint)
        cursor = store.append(intent_event)
    except (ContractValidationError, EventConflictError) as exc:
        raise PreDispatchError(f"pre-dispatch gate refused: {exc}") from exc
    return cursor, dispatch()


class ObservationStore:
    """Append-only insertion-ordered store of schema-valid observation events."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._digests: dict[str, str] = {}
        self._checkpoints: list[dict[str, Any]] = []
        self._checkpoint_digests: dict[str, str] = {}

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
            raise EventConflictError(f"event id conflict: {event_id}")
        self._events.append(copy.deepcopy(event))
        self._digests[event_id] = digest
        return len(self._events) - 1

    def check_checkpoint(self, checkpoint: dict[str, Any]) -> int:
        """Validate a checkpoint reference against recorded history.

        Returns the checkpoint cursor when the trigger event exists and the
        cursor is inside the journal. Never returns event payloads; use the
        explicit read API to fetch events.
        """

        validate(checkpoint, CHECKPOINT_SCHEMA)
        trigger = checkpoint["trigger_event_id"]
        trigger_event = next(
            (stored for stored in self._events if stored["event_id"] == trigger), None
        )
        if trigger_event is None:
            raise ContractValidationError(f"unknown trigger event: {trigger}")
        for field in ("process_id", "run_id", "branch_id"):
            if trigger_event[field] != checkpoint[field]:
                raise ContractValidationError(f"checkpoint trigger {field} mismatch")
        cursor = checkpoint["event_cursor"]
        if cursor >= len(self._events):
            raise ContractValidationError("checkpoint cursor is beyond journal end")
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
            raise EventConflictError(f"checkpoint id conflict: {checkpoint_id}")
        self._checkpoints.append(copy.deepcopy(checkpoint))
        self._checkpoint_digests[checkpoint_id] = digest
        return len(self._checkpoints) - 1

    def checkpoints(self) -> tuple[dict[str, Any], ...]:
        """Return stored checkpoints in insertion order as detached copies."""

        return tuple(copy.deepcopy(item) for item in self._checkpoints)

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
