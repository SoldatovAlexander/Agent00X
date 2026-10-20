"""Capture bounded logical-state and intent metadata for observer checkpoints.

This adapter stores pre-dispatch metadata only. It does not snapshot or restore
process, model, or workspace state; checkpoints therefore remain partial.
"""

from __future__ import annotations

import re
from typing import Any

from .digests import canonical_json, sha256_bytes
from .observer_artifact_store import ArtifactResolution, MAX_ARTIFACT_BYTES
from .observation_store import ObservationStoreError


_OPERATION = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_CHECKPOINT_FIELDS = (
    "schema_version",
    "checkpoint_id",
    "kind",
    "process_id",
    "run_id",
    "branch_id",
    "agent_id",
    "trigger_event_id",
    "event_cursor",
    "completeness",
    "restore_mode",
    "created_at",
)
_INTENT_FIELDS = ("event_id", "event_type", "sequence", "decision_or_tool")
_UNAVAILABLE_STATE_COMPONENTS = (
    "process_memory",
    "model_internal_state",
)
_OPTIONAL_STATE_REFERENCES = (
    ("context_manifest_ref", "context_manifest"),
    ("workspace_manifest_ref", "workspace_manifest"),
    ("configuration_refs", "configuration_refs"),
    ("authority_refs", "authority_refs"),
    ("in_flight_invocation_ids", "in_flight_invocation_state"),
    ("external_effect_refs", "external_effect_state"),
)


class ArtifactCapturingObservationStore:
    """Decorate a journal store with immutable, redacted pending-action refs."""

    __slots__ = ("_journal", "artifact_store")

    def __init__(self, journal: object, artifact_store: object) -> None:
        if (
            not callable(getattr(journal, "append", None))
            or not callable(getattr(journal, "events", None))
            or not callable(getattr(journal, "record_checkpoint", None))
            or not callable(getattr(artifact_store, "put_json", None))
            or not callable(getattr(artifact_store, "resolve", None))
        ):
            raise ObservationStoreError(
                "observation journal: artifact capture configuration unavailable"
            )
        self._journal = journal
        self.artifact_store = artifact_store

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._journal, name)

    def _store_artifact(self, payload: dict) -> str:
        encoded = canonical_json(payload)
        if len(encoded) > MAX_ARTIFACT_BYTES:
            raise ValueError
        digest = sha256_bytes(encoded)
        expected_ref = f"artifact://sha256/{digest.removeprefix('sha256:')}"
        stored = self.artifact_store.put_json(
            encoded,
            classification="internal",
            redaction_status="complete",
        )
        expected = ArtifactResolution(expected_ref, digest, len(encoded))
        if type(stored) is not ArtifactResolution or stored != expected:
            raise ValueError
        resolved = self.artifact_store.resolve(expected_ref)
        if type(resolved) is not ArtifactResolution or resolved != expected:
            raise ValueError
        return expected_ref

    @staticmethod
    def _metadata(checkpoint: object, intent_event: object) -> tuple[dict, dict]:
        if type(checkpoint) is not dict or type(intent_event) is not dict:
            raise ObservationStoreError(
                "observation journal: pending-action metadata unavailable"
            )
        operation = intent_event.get("decision_or_tool")
        if (
            type(operation) is not str
            or _OPERATION.fullmatch(operation) is None
            or intent_event.get("event_type") not in {"tool_requested", "decision_proposed"}
            or type(intent_event.get("event_id")) is not str
            or type(intent_event.get("sequence")) is not int
            or intent_event["sequence"] < 0
            or type(checkpoint.get("checkpoint_id")) is not str
            or type(checkpoint.get("event_cursor")) is not int
            or checkpoint["event_cursor"] < 0
            or "pending_action_ref" in checkpoint
        ):
            raise ObservationStoreError(
                "observation journal: pending-action metadata unavailable"
            )
        checkpoint_metadata = {
            key: checkpoint[key]
            for key in _CHECKPOINT_FIELDS
            if key in checkpoint
        }
        intent_metadata = {
            key: intent_event[key]
            for key in _INTENT_FIELDS
            if key in intent_event
        }
        if (
            len(checkpoint_metadata) != len(_CHECKPOINT_FIELDS)
            or len(intent_metadata) != len(_INTENT_FIELDS)
        ):
            raise ObservationStoreError(
                "observation journal: pending-action metadata unavailable"
            )
        return checkpoint_metadata, intent_metadata

    def _capture(self, checkpoint: object, intent_event: object) -> dict:
        checkpoint_metadata, intent_metadata = self._metadata(checkpoint, intent_event)
        payload = {
            "schema": "observer-pending-action/v1",
            "scope": "checkpoint-metadata-and-intent-only",
            "checkpoint": checkpoint_metadata,
            "intent": intent_metadata,
        }
        try:
            artifact_ref = self._store_artifact(payload)
            unavailable_components = list(_UNAVAILABLE_STATE_COMPONENTS)
            unavailable_components.extend(
                component
                for field, component in _OPTIONAL_STATE_REFERENCES
                if field not in checkpoint
            )
            state_payload = {
                "schema": "observer-logical-state/v1",
                "scope": "checkpoint-metadata-only",
                "capture_mode": "metadata_only",
                "restorable": False,
                "checkpoint": checkpoint_metadata,
                "pending_action_ref": artifact_ref,
                "unavailable_components": unavailable_components,
            }
            state_ref = self._store_artifact(state_payload)
            enriched = dict(checkpoint)
            enriched["state_ref"] = state_ref
            enriched["pending_action_ref"] = artifact_ref
            return enriched
        except ObservationStoreError:
            raise
        except Exception:
            raise ObservationStoreError(
                "observation journal: checkpoint artifact unavailable"
            ) from None

    def record_checkpoint_and_intent(
        self, checkpoint: dict[str, Any], intent_event: dict[str, Any]
    ) -> int:
        enriched = self._capture(checkpoint, intent_event)
        persist_pair = getattr(self._journal, "record_checkpoint_and_intent", None)
        if callable(persist_pair):
            return persist_pair(enriched, intent_event)
        self._journal.record_checkpoint(enriched)
        return self._journal.append(intent_event)

    def record_checkpoint_and_intent_once(
        self, checkpoint: dict[str, Any], intent_event: dict[str, Any]
    ) -> int:
        persist_once = getattr(self._journal, "record_checkpoint_and_intent_once", None)
        if not callable(persist_once):
            raise ObservationStoreError(
                "observation journal: one-shot artifact write unavailable"
            )
        enriched = self._capture(checkpoint, intent_event)
        return persist_once(enriched, intent_event)
