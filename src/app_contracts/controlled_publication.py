"""Controlled-publication gates: approval, then policy decision.

Only a caller-provided fresh approval bound to the exact seed-bound intent
passes the first gate, verified through the existing authority contract, and
only a fresh allow decision bound to the same intent passes the second gate,
verified field-by-field with the existing decision-use contract. The Policy
Engine stays the sole decision source: this module never synthesizes,
relaxes, caches or re-timestamps decisions. Neither gate calls policy,
gateway, broker or provider code: each downstream step runs only via an
injected ``proceed`` callable after every check passes.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from .authority import check_decision_usable, check_intent_approved
from .publication_seed import PublicationIntent


class ControlledPublicationError(ValueError):
    """A controlled-publication input or gate precondition is invalid."""


T = TypeVar("T")


def run_approval_gate(
    intent: PublicationIntent,
    approval: Any,
    *,
    now: datetime,
    proceed: Callable[[PublicationIntent], T],
) -> T:
    """Pass a seed-bound intent downstream only with a fresh matching approval.

    A missing, expired or mismatched approval stops the path before the
    downstream step runs. Failures carry stable messages without approval,
    intent or digest values.
    """

    if not callable(proceed):
        raise ControlledPublicationError("controlled publication: downstream step is invalid")
    if not isinstance(intent, PublicationIntent):
        raise ControlledPublicationError("controlled publication: intent is invalid")
    if not isinstance(approval, dict):
        raise ControlledPublicationError("controlled publication: approval is missing")
    moment = _require_clock(now)
    check_intent_approved(asdict(intent), approval)
    if _require_approval_expiry(approval) <= moment:
        raise ControlledPublicationError("controlled publication: approval expired")
    return proceed(intent)


def run_policy_gate(
    intent: PublicationIntent,
    approval: Any,
    decision: Any,
    *,
    now: datetime,
    proceed: Callable[[PublicationIntent, Any, dict], T],
) -> T:
    """Pass the approved intent downstream only with a fresh matching decision.

    The approval itself is re-verified here — it must be fresh and its
    process, repository and staged-digest bindings must equal the same
    seed-bound intent — so entering this gate directly can never smuggle a
    stale or foreign approval past the approval boundary. The decision
    effect, operation, repository and staged digest are then verified against
    the same intent, and its allow lifetime is verified through the existing
    decision-use contract, all before the downstream step runs. A stale,
    mismatched or deny approval or decision stops the path with zero
    downstream calls. Failures carry stable messages without decision,
    approval, intent or digest values.
    """

    if not callable(proceed):
        raise ControlledPublicationError("controlled publication: downstream step is invalid")
    if not isinstance(intent, PublicationIntent):
        raise ControlledPublicationError("controlled publication: intent is invalid")
    if not isinstance(approval, dict):
        raise ControlledPublicationError("controlled publication: approval is missing")
    if not isinstance(decision, dict):
        raise ControlledPublicationError("controlled publication: decision is missing")
    moment = _require_clock(now)
    if _require_approval_expiry(approval) <= moment:
        raise ControlledPublicationError("controlled publication: approval expired")
    for field in ("process_id", "repository_id", "staged_change_digest"):
        if approval.get(field) != getattr(intent, field):
            raise ControlledPublicationError("controlled publication: approval binding mismatch")
    if decision.get("operation") != "publish_pull_request":
        raise ControlledPublicationError("controlled publication: decision operation mismatch")
    if decision.get("repository_id") != intent.repository_id:
        raise ControlledPublicationError("controlled publication: decision repository mismatch")
    if decision.get("staged_change_digest") != intent.staged_change_digest:
        raise ControlledPublicationError("controlled publication: decision digest mismatch")
    check_decision_usable(decision, now=moment)
    return proceed(intent, approval, decision)


def _require_clock(now: Any) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ControlledPublicationError("controlled publication: clock is invalid")
    return now.astimezone(timezone.utc)


def _require_approval_expiry(approval: dict) -> datetime:
    raw = approval.get("expires_at")
    if not isinstance(raw, str):
        raise ControlledPublicationError("controlled publication: approval expiry is invalid")
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ControlledPublicationError(
            "controlled publication: approval expiry is invalid"
        ) from None
    if moment.tzinfo is None:
        raise ControlledPublicationError("controlled publication: approval expiry is invalid")
    return moment
