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


def _load_event_schema() -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "observation-event.schema.json"
    with schema_path.open(encoding="utf-8") as handle:
        return json.load(handle)


EVENT_SCHEMA = _load_event_schema()


class EventConflictError(ValueError):
    """A second record reuses an event_id with different content."""


class ObservationStore:
    """Append-only insertion-ordered store of schema-valid observation events."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._digests: dict[str, str] = {}

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
