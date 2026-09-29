"""Controlled-publication gates: fresh approval, then local policy evaluation.

The second gate invokes the existing deterministic Policy Engine itself with
the exact caller-provided approval, staged change and seed-bound intent. It
does not accept cached/caller-supplied decisions or call gateway, broker or
provider code; downstream work is exposed only through an injected
``proceed`` callable after the fresh engine result passes validation.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from .authority import DeterministicPolicy, check_decision_usable, check_intent_approved
from .digests import sha256_digest
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
    policy: Any,
    engine_intent: Any,
    staged_change: Any,
    *,
    decision_id: Any,
    actuator_id: Any,
    now: datetime,
    proceed: Callable[[PublicationIntent, Any, dict], T],
) -> T:
    """Evaluate the exact approval through Policy Engine before proceeding.

    A decision is created inside this gate by the existing deterministic
    Policy Engine; a precomputed decision cannot be supplied by a caller.
    Approval and engine-intent bindings are checked before evaluation, and
    the fresh result is checked again before the downstream step. Failures
    carry stable messages without approval, intent, decision or digest values.
    """

    if not callable(proceed):
        raise ControlledPublicationError("controlled publication: downstream step is invalid")
    if not isinstance(intent, PublicationIntent):
        raise ControlledPublicationError("controlled publication: intent is invalid")
    if not isinstance(approval, dict):
        raise ControlledPublicationError("controlled publication: approval is missing")
    if type(policy) is not DeterministicPolicy:
        raise ControlledPublicationError("controlled publication: policy engine is invalid")
    if not isinstance(engine_intent, dict):
        raise ControlledPublicationError("controlled publication: engine intent is missing")
    if not isinstance(staged_change, dict):
        raise ControlledPublicationError("controlled publication: staged change is invalid")
    if not isinstance(decision_id, str) or not decision_id:
        raise ControlledPublicationError("controlled publication: decision id is invalid")
    if not isinstance(actuator_id, str) or not actuator_id:
        raise ControlledPublicationError("controlled publication: actuator id is invalid")
    moment = _require_clock(now)
    if _require_approval_expiry(approval) <= moment:
        raise ControlledPublicationError("controlled publication: approval expired")
    for field in (
        "process_id", "repository_id", "base_commit", "staged_change_digest",
        "idempotency_key",
    ):
        if engine_intent.get(field) != getattr(intent, field):
            raise ControlledPublicationError("controlled publication: engine intent binding mismatch")
    if engine_intent.get("operation") != "publish_pull_request":
        raise ControlledPublicationError("controlled publication: engine intent binding mismatch")
    if engine_intent.get("branch_namespace") != intent.branch.split("/", 1)[0]:
        raise ControlledPublicationError("controlled publication: engine intent binding mismatch")
    try:
        check_intent_approved(engine_intent, approval)
        staged_digest = sha256_digest(staged_change)
    except Exception:
        raise ControlledPublicationError("controlled publication: approval binding is invalid") from None
    if staged_digest != intent.staged_change_digest:
        raise ControlledPublicationError("controlled publication: staged change digest mismatch")
    if not isinstance(approval.get("approval_id"), str) or not approval["approval_id"]:
        raise ControlledPublicationError("controlled publication: approval binding is invalid")
    if not isinstance(approval.get("policy_version"), str) or not approval["policy_version"]:
        raise ControlledPublicationError("controlled publication: approval binding is invalid")
    if not isinstance(engine_intent.get("expires_at"), str):
        raise ControlledPublicationError("controlled publication: engine intent binding is invalid")
    if _require_approval_expiry({"expires_at": engine_intent["expires_at"]}) <= moment:
        raise ControlledPublicationError("controlled publication: engine intent expired")

    decision = policy.decide(
        decision_id=decision_id,
        actuator_request={
            "operation": "publish_pull_request",
            "repository_id": intent.repository_id,
            "actuator_id": actuator_id,
            "staged_change_digest": intent.staged_change_digest,
            "branch_namespace": engine_intent["branch_namespace"],
            "idempotency_key": intent.idempotency_key,
        },
        approval=approval,
        staged_change=staged_change,
        intent=engine_intent,
        now=moment,
    )
    if not isinstance(decision, dict):
        raise ControlledPublicationError("controlled publication: policy decision is invalid")
    if decision.get("operation") != "publish_pull_request":
        raise ControlledPublicationError("controlled publication: decision operation mismatch")
    if decision.get("repository_id") != intent.repository_id:
        raise ControlledPublicationError("controlled publication: decision repository mismatch")
    if decision.get("staged_change_digest") != intent.staged_change_digest:
        raise ControlledPublicationError("controlled publication: decision digest mismatch")
    if decision.get("policy_version") != approval["policy_version"]:
        raise ControlledPublicationError("controlled publication: decision policy version mismatch")
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
