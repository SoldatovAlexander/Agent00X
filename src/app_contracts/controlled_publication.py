"""Controlled-publication gates: approval, policy, gateway, broker.

The approval gate admits only a caller-provided fresh approval bound to the
exact seed-bound intent. The policy gate evaluates that exact approval
through the existing deterministic Policy Engine itself and never accepts a
caller-supplied decision. The gateway gate invokes the injected gateway with
an envelope bound to the same intent and admits only a matching slow-allow.
The broker gate opens one single-use channel for the same verified request
through the injected broker after verifying grant bindings, without touching
the provider endpoint. No gate calls gateway, broker or provider code beyond
its own narrow collaborator: each downstream step runs only via an injected
``proceed`` callable after every check passes.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from .authority import DeterministicPolicy, check_decision_usable, check_intent_approved
from .digests import sha256_digest
from .gateway import GatewayDecision, GatewayPath
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


def run_gateway_gate(
    intent: PublicationIntent,
    approval: Any,
    decision: Any,
    gateway: Any,
    envelope: Any,
    *,
    now: datetime,
    proceed: Callable[[PublicationIntent, Any, dict, GatewayDecision], T],
) -> T:
    """Pass the approved intent to broker only on a matching gateway slow-allow.

    The envelope must be bound to the same seed-bound intent before the
    gateway is invoked — operation, destination repository, source principal,
    staged digest and correlation key must equal the intent, so the gateway
    verdict cannot belong to a foreign request. The gateway itself is invoked
    here — a caller-supplied verdict is never accepted. Only a genuine
    slow-allow reaches the downstream step, so no broker action is reachable
    without an exact gateway allow for this publication request. A deny,
    degraded, malformed or mismatched envelope or output stops the path with
    zero broker calls. Failures carry stable messages without envelope,
    decision, approval, intent or digest values.
    """

    if not callable(proceed):
        raise ControlledPublicationError("controlled publication: downstream step is invalid")
    if not isinstance(intent, PublicationIntent):
        raise ControlledPublicationError("controlled publication: intent is invalid")
    if not isinstance(approval, dict):
        raise ControlledPublicationError("controlled publication: approval is missing")
    if not isinstance(decision, dict):
        raise ControlledPublicationError("controlled publication: decision is missing")
    if not callable(gateway):
        raise ControlledPublicationError("controlled publication: gateway is invalid")
    moment = _require_clock(now)
    check_decision_usable(decision, now=moment)
    if not isinstance(envelope, dict):
        raise ControlledPublicationError("controlled publication: gateway envelope mismatch")
    if not isinstance(envelope.get("intent"), dict) or envelope["intent"].get(
        "operation"
    ) != "publish_pull_request":
        raise ControlledPublicationError("controlled publication: gateway envelope mismatch")
    if not isinstance(envelope.get("destination"), dict) or envelope[
        "destination"
    ].get("repository_id") != intent.repository_id:
        raise ControlledPublicationError("controlled publication: gateway envelope mismatch")
    if not isinstance(envelope.get("source"), dict) or envelope["source"].get(
        "principal_id"
    ) != intent.process_id:
        raise ControlledPublicationError("controlled publication: gateway envelope mismatch")
    if not isinstance(envelope.get("payload"), dict) or envelope["payload"].get(
        "content_digest"
    ) != intent.staged_change_digest:
        raise ControlledPublicationError("controlled publication: gateway envelope mismatch")
    if envelope.get("correlation_id") != intent.idempotency_key:
        raise ControlledPublicationError("controlled publication: gateway envelope mismatch")
    try:
        gateway_decision = gateway(envelope, now=moment)
    except Exception:
        raise ControlledPublicationError(
            "controlled publication: gateway invocation failed"
        ) from None
    if (
        not isinstance(gateway_decision, GatewayDecision)
        or gateway_decision.allowed is not True
        or gateway_decision.path is not GatewayPath.SLOW
        or not isinstance(gateway_decision.reason_codes, tuple)
    ):
        raise ControlledPublicationError(
            "controlled publication: gateway has not authorized slow path"
        )
    return proceed(intent, approval, decision, gateway_decision)


def run_broker_gate(
    intent: PublicationIntent,
    approval: Any,
    decision: Any,
    gateway_decision: Any,
    broker: Any,
    credential_grant: Any,
    *,
    actuator_id: Any,
    now: datetime,
    proceed: Callable[[PublicationIntent, Any, dict, GatewayDecision, Any], T],
) -> T:
    """Open one single-use channel for the same verified request.

    Grant bindings — repository, operation, actuator, staged digest,
    credential class, single-use flag and expiry — are verified against the
    same seed-bound intent before the broker is touched, the policy decision
    itself is bound back to the same intent by operation, repository and
    staged digest, and the slow-allow is re-verified for direct entry. The
    channel itself is opened through the injected broker and handed
    downstream; this gate never calls the provider endpoint, so a refusal
    leaves zero endpoint side effects. A reused grant, a grant for another
    repository, operation or digest, or a decision bound elsewhere stops the
    path. Failures carry stable messages without grant, decision, approval,
    intent or digest values.
    """

    if not callable(proceed):
        raise ControlledPublicationError("controlled publication: downstream step is invalid")
    if not isinstance(intent, PublicationIntent):
        raise ControlledPublicationError("controlled publication: intent is invalid")
    if not isinstance(approval, dict):
        raise ControlledPublicationError("controlled publication: approval is missing")
    if not isinstance(decision, dict):
        raise ControlledPublicationError("controlled publication: decision is missing")
    if (
        not isinstance(gateway_decision, GatewayDecision)
        or gateway_decision.allowed is not True
        or gateway_decision.path is not GatewayPath.SLOW
        or not isinstance(gateway_decision.reason_codes, tuple)
    ):
        raise ControlledPublicationError(
            "controlled publication: gateway has not authorized slow path"
        )
    if not callable(getattr(broker, "open_github_publication_channel", None)):
        raise ControlledPublicationError("controlled publication: broker is invalid")
    if not isinstance(credential_grant, dict):
        raise ControlledPublicationError("controlled publication: credential grant is invalid")
    if not isinstance(actuator_id, str) or not actuator_id:
        raise ControlledPublicationError("controlled publication: actuator id is invalid")
    moment = _require_clock(now)
    check_decision_usable(decision, now=moment)
    if decision.get("operation") != "publish_pull_request":
        raise ControlledPublicationError("controlled publication: decision operation mismatch")
    if decision.get("repository_id") != intent.repository_id:
        raise ControlledPublicationError("controlled publication: decision repository mismatch")
    if decision.get("staged_change_digest") != intent.staged_change_digest:
        raise ControlledPublicationError("controlled publication: decision digest mismatch")
    if not isinstance(credential_grant.get("credential_grant_id"), str) or not credential_grant[
        "credential_grant_id"
    ]:
        raise ControlledPublicationError("controlled publication: credential grant is invalid")
    if credential_grant.get("repository_id") != intent.repository_id:
        raise ControlledPublicationError("controlled publication: credential grant binding mismatch")
    if credential_grant.get("operation") != "publish_pull_request":
        raise ControlledPublicationError("controlled publication: credential grant binding mismatch")
    if credential_grant.get("actuator_id") != actuator_id:
        raise ControlledPublicationError("controlled publication: credential grant binding mismatch")
    if credential_grant.get("credential_class") != "github-app-installation":
        raise ControlledPublicationError("controlled publication: credential grant binding mismatch")
    if credential_grant.get("single_use") is not True:
        raise ControlledPublicationError("controlled publication: credential grant must be single-use")
    if _require_grant_expiry(credential_grant) <= moment:
        raise ControlledPublicationError("controlled publication: credential grant expired")
    actuator_request = {
        "operation": "publish_pull_request",
        "repository_id": intent.repository_id,
        "actuator_id": actuator_id,
        "staged_change_digest": intent.staged_change_digest,
        "branch_namespace": intent.branch.split("/", 1)[0],
        "idempotency_key": intent.idempotency_key,
    }
    if credential_grant.get("request_digest") != sha256_digest(actuator_request):
        raise ControlledPublicationError("controlled publication: credential grant binding mismatch")
    try:
        channel = broker.open_github_publication_channel(
            credential_grant, actuator_request, now=moment
        )
    except Exception:
        raise ControlledPublicationError(
            "controlled publication: broker invocation failed"
        ) from None
    return proceed(intent, approval, decision, gateway_decision, channel)


def _require_grant_expiry(credential_grant: dict) -> datetime:
    raw = credential_grant.get("expires_at")
    if not isinstance(raw, str):
        raise ControlledPublicationError("controlled publication: credential grant expiry is invalid")
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ControlledPublicationError(
            "controlled publication: credential grant expiry is invalid"
        ) from None
    if moment.tzinfo is None:
        raise ControlledPublicationError("controlled publication: credential grant expiry is invalid")
    return moment


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
