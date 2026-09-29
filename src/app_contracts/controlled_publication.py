"""First controlled-publication gate: a fresh approval bound to a seed intent.

Only a caller-provided approval that is fresh and bound to the exact
seed-bound intent passes, verified through the existing authority contract.
This module never creates approvals, recovers expired ones, or calls
policy, gateway, broker or provider code: the single downstream step runs
only via an injected ``proceed`` callable after every check passes.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from .authority import check_intent_approved
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
