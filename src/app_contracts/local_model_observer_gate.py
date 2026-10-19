"""Worker-only journal gate for local model metadata preflight.

This module is intentionally outside the verifier runtime import closure. It
uses the existing journal adapter's private run context only at the Worker CLI
boundary; verifier host code must not import it.
"""

from __future__ import annotations

import hashlib
from typing import Callable

from .observation_store import PreDispatchError, run_gated_dispatch


_STEP = "LocalOllamaMetadataPreflight.inspect"
_AGENT_ID = "service-model-channel"


class LocalModelObserverGateError(RuntimeError):
    """The journal refused the local model preflight or its terminal record."""


class LocalModelObserverOutcomeUnknownError(LocalModelObserverGateError):
    """The metadata request may have run, but its result was not recorded."""


def _stable_id(kind: str, process_id: str, run_id: str) -> str:
    material = f"{process_id}\0{run_id}\0{_STEP}\0{kind}".encode("utf-8")
    return f"{kind}-{hashlib.sha256(material).hexdigest()[:32]}"


def journal_local_model_preflight(
    journal: object,
    dispatch: Callable[[], object],
    *,
    process_id: str,
) -> object:
    """Record one redacted intent/terminal pair around a metadata call.

    A deterministic intent ID plus the store's atomic one-shot insertion makes
    repeats fail closed even if multiple adapters race or the process resumes.
    Only fixed event labels/status/error codes are persisted.
    """

    if not callable(dispatch) or getattr(journal, "_process_id", None) != process_id:
        raise LocalModelObserverGateError("local model observer gate unavailable")
    store = getattr(journal, "_store", None)
    run_id = getattr(journal, "_run_id", None)
    branch_id = getattr(journal, "_branch_id", None)
    previous_event_id = getattr(journal, "_last_event_id", None)
    previous_cursor = getattr(journal, "_last_event_cursor", None)
    sequence = getattr(journal, "_sequence", None)
    base_event = getattr(journal, "_base_event", None)
    timestamp = getattr(journal, "_timestamp", None)
    if (
        type(run_id) is not str
        or type(branch_id) is not str
        or type(previous_event_id) is not str
        or type(previous_cursor) is not int
        or type(sequence) is not int
        or not callable(base_event)
        or not callable(timestamp)
        or not callable(getattr(store, "events", None))
    ):
        raise LocalModelObserverGateError("local model observer gate unavailable")

    try:
        if any(
            event.get("run_id") == run_id
            and event.get("decision_or_tool") == _STEP
            for event in store.events()
        ):
            raise LocalModelObserverGateError("local model preflight already claimed")
        created_at = timestamp()
        checkpoint_id = _stable_id("checkpoint", process_id, run_id)
        invocation_id = _stable_id("invocation", process_id, run_id)
        intent_id = _stable_id("event", process_id, run_id)
        checkpoint = {
            "schema_version": 1,
            "checkpoint_id": checkpoint_id,
            "kind": "tool_call",
            "process_id": process_id,
            "run_id": run_id,
            "branch_id": branch_id,
            "agent_id": _AGENT_ID,
            "trigger_event_id": previous_event_id,
            "event_cursor": previous_cursor,
            "state_ref": f"artifact://observer-state/{run_id}/local-model-preflight",
            "completeness": "partial",
            "restore_mode": "none",
            "created_at": created_at,
        }
        intent = base_event(
            event_type="tool_requested",
            sequence=sequence,
            event_id=intent_id,
            agent_id=_AGENT_ID,
        )
        intent.update(
            {
                "checkpoint_id": checkpoint_id,
                "invocation_id": invocation_id,
                "causal_event_ids": [previous_event_id],
                "decision_or_tool": _STEP,
                "expected_result": "bounded local model identity result",
                "status": "pending",
            }
        )
        result = object()

        def guarded_dispatch():
            try:
                return dispatch()
            except Exception:
                return result

        try:
            cursor, value = run_gated_dispatch(
                store,
                checkpoint=checkpoint,
                intent_event=intent,
                dispatch=guarded_dispatch,
                once=True,
            )
        except PreDispatchError:
            raise LocalModelObserverGateError(
                "local model observer pre-dispatch refused"
            ) from None

        journal._last_event_id = intent_id
        journal._last_event_cursor = cursor
        journal._sequence = sequence + 1
        failed = value is result
        terminal = base_event(
            event_type="tool_failed" if failed else "tool_completed",
            sequence=journal._sequence,
            event_id=_stable_id("event-terminal", process_id, run_id),
            agent_id=_AGENT_ID,
        )
        terminal.update(
            {
                "invocation_id": invocation_id,
                "causal_event_ids": [intent_id],
                "decision_or_tool": _STEP,
                "status": "failed" if failed else "ok",
            }
        )
        if failed:
            terminal["error_code"] = "local-model-preflight-failed"
        try:
            terminal_cursor = store.append(terminal)
        except Exception:
            raise LocalModelObserverOutcomeUnknownError(
                "local model observer outcome unknown"
            ) from None
        journal._last_event_id = terminal["event_id"]
        journal._last_event_cursor = terminal_cursor
        journal._sequence += 1
        if failed:
            raise LocalModelObserverGateError("local model preflight failed") from None
        return value
    except LocalModelObserverGateError:
        raise
    except Exception:
        raise LocalModelObserverGateError("local model observer gate unavailable") from None
