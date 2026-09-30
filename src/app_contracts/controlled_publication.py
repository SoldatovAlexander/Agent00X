"""Controlled-publication gates: approval, policy, gateway, broker.

The approval gate admits only a caller-provided fresh approval bound to the
exact seed-bound intent. The policy gate evaluates that exact approval
through the existing deterministic Policy Engine itself and never accepts a
caller-supplied decision. The gateway gate invokes the injected gateway with
an envelope bound to the same intent and admits only a matching slow-allow.
The broker gate re-evaluates policy for that same intent and staged change,
then checks the live gateway and one single-use broker grant before preparing
a digest-only journal record. The provider endpoint is still reached only
through the injected downstream continuation after those checks pass.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from .authority import DeterministicPolicy, check_decision_usable, check_intent_approved
from .broker import InMemoryCredentialBroker
from .digests import sha256_digest
from .gateway import GatewayDecision, GatewayPath
from .mock_github import MockGitHubEndpoint, MockPullRequest
from .publication import (
    PublicationJournal,
    PublicationRecoveryRequired,
    SimulatedCrash,
    execute_publication,
    recover_publication,
)
from .publication_seed import PublicationIntent, PublicationSeed


class ControlledPublicationError(ValueError):
    """A controlled-publication input or gate precondition is invalid."""


T = TypeVar("T")


def run_approval_gate(
    intent: PublicationIntent,
    approval: Any,
    *,
    engine_intent: Any = None,
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
    if engine_intent is None:
        check_intent_approved(asdict(intent), approval)
    else:
        _require_engine_intent_binding(intent, engine_intent)
        try:
            check_intent_approved(engine_intent, approval)
        except Exception:
            raise ControlledPublicationError(
                "controlled publication: approval binding is invalid"
            ) from None
        if _require_approval_expiry(
            {"expires_at": engine_intent.get("expires_at")}
        ) <= moment:
            raise ControlledPublicationError("controlled publication: engine intent expired")
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
    _require_bound_envelope(intent, envelope)
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


def _require_bound_envelope(intent: PublicationIntent, envelope: Any) -> None:
    """Bind a gateway envelope to the same seed-bound intent.

    Operation, destination repository, source principal, staged digest and
    correlation key must equal the intent, so a gateway verdict cannot belong
    to a foreign request. Shared by every gate that invokes the gateway.
    """

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


def run_broker_gate(
    intent: PublicationIntent,
    approval: Any,
    policy: Any,
    engine_intent: Any,
    staged_change: Any,
    decision_id: Any,
    gateway: Any,
    envelope: Any,
    broker: Any,
    credential_grant: Any,
    *,
    actuator_id: Any,
    now: datetime,
    proceed: Callable[[PublicationIntent, Any, dict, GatewayDecision, Any], T],
    seed: Any,
    journal: Any,
) -> T:
    """Open one single-use channel for the same verified request.

    The existing Policy Engine is run again inside this gate against the
    supplied approved intent and staged change; no caller-supplied decision
    can authorize the broker. The live gateway transition is then verified:
    the envelope bound to the same intent is passed to the injected gateway,
    and only its genuine slow-allow opens the broker path. Grant bindings —
    repository, operation, actuator, staged digest, credential class,
    single-use flag and expiry — are verified before the broker is touched.
    A reused or mismatched grant stops the path. After the channel opens, a
    canonical digest-only journal row is prepared before downstream runs. The
    channel is handed downstream; this gate never calls the provider endpoint,
    so a refusal leaves zero endpoint side effects. Failures carry stable
    messages without grant, decision, approval, intent or digest values.
    """

    if not callable(proceed):
        raise ControlledPublicationError("controlled publication: downstream step is invalid")
    if not isinstance(intent, PublicationIntent):
        raise ControlledPublicationError("controlled publication: intent is invalid")
    if not isinstance(seed, PublicationSeed):
        raise ControlledPublicationError("controlled publication: publication seed is invalid")
    if (
        not callable(getattr(journal, "prepare", None))
        or not callable(getattr(journal, "get", None))
    ):
        raise ControlledPublicationError("controlled publication: journal is invalid")
    if not callable(getattr(broker, "open_github_publication_channel", None)):
        raise ControlledPublicationError("controlled publication: broker is invalid")
    if not isinstance(credential_grant, dict):
        raise ControlledPublicationError("controlled publication: credential grant is invalid")
    if not isinstance(actuator_id, str) or not actuator_id:
        raise ControlledPublicationError("controlled publication: actuator id is invalid")
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
    moment = _require_clock(now)
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

    def open_after_policy(
        policy_intent: PublicationIntent,
        policy_approval: dict,
        decision: dict,
    ) -> T:
        if not callable(gateway):
            raise ControlledPublicationError("controlled publication: gateway is invalid")
        _require_bound_envelope(policy_intent, envelope)
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
        try:
            channel = broker.open_github_publication_channel(
                credential_grant, actuator_request, now=moment
            )
        except Exception:
            raise ControlledPublicationError(
                "controlled publication: broker invocation failed"
            ) from None
        _prepare_publication_journal(
            seed,
            policy_intent,
            policy_approval,
            engine_intent,
            decision,
            gateway_decision,
            journal,
            now=moment,
        )
        return proceed(policy_intent, policy_approval, decision, gateway_decision, channel)

    return run_policy_gate(
        intent,
        approval,
        policy,
        engine_intent,
        staged_change,
        decision_id=decision_id,
        actuator_id=actuator_id,
        now=moment,
        proceed=open_after_policy,
    )


def run_controlled_local_publication(
    seed: Any,
    intent: Any,
    approval: Any,
    policy: Any,
    engine_intent: Any,
    load_staged_change: Any,
    decision_id: Any,
    gateway: Any,
    envelope: Any,
    broker: Any,
    credential_grant: Any,
    journal: Any,
    endpoint: Any,
    *,
    actuator_id: Any,
    now: datetime,
) -> MockPullRequest:
    """Run the narrow local approval-to-mock publication path.

    File contents are supplied only by a bounded injected loader for the
    policy digest check; callers do not pass raw content or a provider channel
    into this coordinator. The only endpoint accepted here is the existing
    in-memory ``MockGitHubEndpoint``, returned as the private channel by the
    test-only in-memory broker. No real provider, credential value, or network
    capability is accepted.
    """

    if type(seed) is not PublicationSeed:
        raise ControlledPublicationError("controlled publication: publication seed is invalid")
    if type(intent) is not PublicationIntent:
        raise ControlledPublicationError("controlled publication: intent is invalid")
    if type(policy) is not DeterministicPolicy:
        raise ControlledPublicationError("controlled publication: policy engine is invalid")
    if not callable(load_staged_change):
        raise ControlledPublicationError("controlled publication: staged change loader is invalid")
    if type(broker) is not InMemoryCredentialBroker:
        raise ControlledPublicationError("controlled publication: in-memory broker is required")
    if type(journal) is not PublicationJournal:
        raise ControlledPublicationError("controlled publication: local journal is required")
    if type(endpoint) is not MockGitHubEndpoint:
        raise ControlledPublicationError("controlled publication: mock endpoint is required")
    _require_seed_intent_binding(seed, intent)

    def after_approval(approved_intent: PublicationIntent) -> MockPullRequest:
        try:
            staged_change = load_staged_change(seed)
        except Exception:
            raise ControlledPublicationError(
                "controlled publication: staged change load failed"
            ) from None
        if not isinstance(staged_change, dict):
            raise ControlledPublicationError("controlled publication: staged change is invalid")

        def publish_after_broker(
            gate_intent: PublicationIntent,
            _gate_approval: dict,
            decision: dict,
            _gateway_decision: GatewayDecision,
            channel: Any,
        ) -> MockPullRequest:
            if type(channel) is not MockGitHubEndpoint or channel is not endpoint:
                raise ControlledPublicationError(
                    "controlled publication: mock broker channel is invalid"
                )
            request = {
                "process_id": gate_intent.process_id,
                "operation": "publish_pull_request",
                "repository_id": gate_intent.repository_id,
                "branch": gate_intent.branch,
                "staged_change_digest": gate_intent.staged_change_digest,
                "idempotency_key": gate_intent.idempotency_key,
                "policy_effect": decision["effect"],
                "approval_valid": True,
            }
            try:
                return execute_publication(journal, channel, request)
            except SimulatedCrash:
                # Keep crash injection observable; the caller owns recovery.
                raise
            except Exception:
                # A failed/invalid receipt is an uncertain external outcome.
                # Reconcile by idempotency lookup only; never repeat publish.
                try:
                    current = journal.get(gate_intent.process_id)
                except Exception:
                    raise
                if current.status != "attempting":
                    raise
                try:
                    recovered = recover_publication(
                        journal, channel, gate_intent.process_id
                    )
                    if recovered.status == "completed":
                        receipt = channel.find_by_idempotency_key(
                            gate_intent.idempotency_key
                        )
                        if isinstance(receipt, MockPullRequest):
                            return receipt
                except Exception:
                    pass
                try:
                    current = journal.get(gate_intent.process_id)
                    if current.status == "attempting":
                        journal.mark_reconciliation_required(gate_intent.process_id)
                except Exception:
                    pass
                raise PublicationRecoveryRequired(
                    "publication recovery required"
                ) from None

        return run_broker_gate(
            approved_intent,
            approval,
            policy,
            engine_intent,
            staged_change,
            decision_id,
            gateway,
            envelope,
            broker,
            credential_grant,
            actuator_id=actuator_id,
            now=now,
            proceed=publish_after_broker,
            seed=seed,
            journal=journal,
        )

    return run_approval_gate(
        intent,
        approval,
        engine_intent=engine_intent,
        now=now,
        proceed=after_approval,
    )


def _require_seed_intent_binding(seed: PublicationSeed, intent: PublicationIntent) -> None:
    if (
        seed.process_id != intent.process_id
        or seed.repository_id != intent.repository_id
        or seed.base_commit != intent.base_commit
        or seed.staged_change_digest != intent.staged_change_digest
    ):
        raise ControlledPublicationError("controlled publication: seed binding mismatch")


def _require_engine_intent_binding(intent: PublicationIntent, engine_intent: Any) -> None:
    if not isinstance(engine_intent, dict):
        raise ControlledPublicationError("controlled publication: engine intent is missing")
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
    if not isinstance(engine_intent.get("expires_at"), str):
        raise ControlledPublicationError("controlled publication: engine intent binding is invalid")


def _prepare_publication_journal(
    seed: Any,
    intent: Any,
    approval: Any,
    engine_intent: Any,
    decision: Any,
    gateway_decision: Any,
    journal: Any,
    *,
    now: datetime,
) -> Any:
    """Prepare one local journal row from the request cleared by all gates.

    This private helper is called by ``run_broker_gate`` only after policy,
    gateway and broker checks have all succeeded. Only bounded seed/intent
    and decision metadata participate in the canonical request digest; the
    journal stores the digest, never the approval object, credential grant or
    channel. Replaying the same request is idempotent at the journal boundary,
    while a conflicting request remains a conflict.
    """

    if not isinstance(seed, PublicationSeed):
        raise ControlledPublicationError("controlled publication: publication seed is invalid")
    if not isinstance(intent, PublicationIntent):
        raise ControlledPublicationError("controlled publication: intent is invalid")
    if not isinstance(approval, dict):
        raise ControlledPublicationError("controlled publication: approval is missing")
    if not isinstance(engine_intent, dict):
        raise ControlledPublicationError("controlled publication: engine intent is missing")
    if not isinstance(decision, dict):
        raise ControlledPublicationError("controlled publication: policy decision is invalid")
    if (
        not callable(getattr(journal, "prepare", None))
        or not callable(getattr(journal, "get", None))
    ):
        raise ControlledPublicationError("controlled publication: journal is invalid")
    moment = _require_clock(now)

    if (
        seed.process_id != intent.process_id
        or seed.repository_id != intent.repository_id
        or seed.base_commit != intent.base_commit
        or seed.staged_change_digest != intent.staged_change_digest
    ):
        raise ControlledPublicationError("controlled publication: seed binding mismatch")
    for field in (
        "process_id", "repository_id", "base_commit", "staged_change_digest",
        "idempotency_key",
    ):
        if engine_intent.get(field) != getattr(intent, field):
            raise ControlledPublicationError("controlled publication: engine intent binding mismatch")
    if engine_intent.get("operation") != "publish_pull_request":
        raise ControlledPublicationError("controlled publication: engine intent binding mismatch")
    try:
        check_intent_approved(engine_intent, approval)
        if _require_approval_expiry(approval) <= moment:
            raise ControlledPublicationError("controlled publication: approval expired")
        check_decision_usable(decision, now=moment)
    except ControlledPublicationError:
        raise
    except Exception:
        raise ControlledPublicationError("controlled publication: approval binding is invalid") from None
    if (
        decision.get("operation") != "publish_pull_request"
        or decision.get("repository_id") != intent.repository_id
        or decision.get("staged_change_digest") != intent.staged_change_digest
        or decision.get("policy_version") != approval.get("policy_version")
    ):
        raise ControlledPublicationError("controlled publication: policy decision binding mismatch")
    if (
        not isinstance(gateway_decision, GatewayDecision)
        or gateway_decision.allowed is not True
        or gateway_decision.path is not GatewayPath.SLOW
        or not isinstance(gateway_decision.reason_codes, tuple)
    ):
        raise ControlledPublicationError("controlled publication: gateway has not authorized slow path")

    approval_fingerprint = sha256_digest({
        "approval_id": approval.get("approval_id"),
        "approved_intent_digest": approval.get("approved_intent_digest"),
        "expires_at": approval.get("expires_at"),
        "policy_version": approval.get("policy_version"),
    })
    decision_metadata = {
        key: decision.get(key)
        for key in (
            "decision_id", "effect", "reason_codes", "operation", "repository_id",
            "staged_change_digest", "policy_version", "evaluated_at", "expires_at",
        )
    }
    request_digest = sha256_digest({
        "schema_version": 1,
        "seed": asdict(seed),
        "intent": asdict(intent),
        "approval_fingerprint": approval_fingerprint,
        "policy_decision": decision_metadata,
        "gateway_decision": {
            "path": gateway_decision.path.value,
            "allowed": gateway_decision.allowed,
            "reason_codes": gateway_decision.reason_codes,
        },
    })
    return journal.prepare(
        intent.process_id,
        idempotency_key=intent.idempotency_key,
        request_digest=request_digest,
        repository_id=intent.repository_id,
    )


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
