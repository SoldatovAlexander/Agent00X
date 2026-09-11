"""Deterministic M2 authority checks for staged pull-request publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .digests import sha256_digest
from .validator import ContractValidationError


class PolicyUnavailable(RuntimeError):
    """Policy service cannot make a decision; callers must fail closed."""


@dataclass(frozen=True)
class PolicyConfig:
    version: str
    allowed_repositories: frozenset[str]
    allowed_actuators: frozenset[str]
    decision_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        ttl = self.decision_ttl_seconds
        if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 1:
            raise ValueError("policy: decision TTL must be a positive integer")
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("policy: version must be a non-empty string")
        for name in ("allowed_repositories", "allowed_actuators"):
            members = getattr(self, name)
            if (
                not isinstance(members, (set, frozenset))
                or not members
                or any(not isinstance(member, str) or not member for member in members)
            ):
                raise ValueError(f"policy: {name} must be a non-empty set of strings")


def _require_digest(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(message)
    return value


def check_intent_approved(intent: dict[str, Any], approval: dict[str, Any]) -> None:
    """Fail closed when the presented intent is not the approval-bound intent.

    The approval binds the full canonical approved intent by digest, so any
    coordinated swap of the intent (branch, key, or other fields) after
    approval is rejected here. The message carries no intent, grant, or
    credential contents.
    """

    approved = _require_digest(
        approval.get("approved_intent_digest"), "approval: approved intent digest is invalid"
    )
    if approved != sha256_digest(intent):
        raise ContractValidationError("approval: approved intent digest mismatch")


def validate_approval(
    approval: dict[str, Any],
    staged_change: dict[str, Any],
    intent: dict[str, Any],
    *,
    policy_version: str,
    now: datetime,
) -> None:
    """Reject any approval no longer bound to this exact publication intent."""

    for mapping in (approval, intent, staged_change):
        if not isinstance(mapping, dict):
            raise ContractValidationError("approval: binding root is malformed")
    moment = _require_clock(now)
    staged_digest = sha256_digest(staged_change)
    for field in ("process_id", "repository_id", "operation", "approval_id"):
        if field not in approval or field not in intent:
            raise ContractValidationError(f"approval: {field} is missing")
    for mapping, field in ((approval, "policy_version"), (approval, "expires_at"), (intent, "expires_at")):
        if field not in mapping:
            raise ContractValidationError(f"approval: {field} is missing")
    required_matches = ("process_id", "repository_id", "operation", "approval_id")
    for field in required_matches:
        left, right = approval[field], intent[field]
        if (
            not isinstance(left, str)
            or not isinstance(right, str)
            or not left
            or not right
        ):
            raise ContractValidationError(f"approval: {field} is invalid")
        if left != right:
            raise ContractValidationError(f"approval: {field} mismatch")
    if _require_digest(
        approval.get("staged_change_digest"), "approval: staged change digest is invalid"
    ) != staged_digest:
        raise ContractValidationError("approval: staged change digest mismatch")
    if _require_digest(
        intent.get("staged_change_digest"), "approval: intent staged change digest is invalid"
    ) != staged_digest:
        raise ContractValidationError("approval: intent staged change digest mismatch")
    check_intent_approved(intent, approval)
    if approval["policy_version"] != policy_version:
        raise ContractValidationError("approval: policy version mismatch")
    if _require_expiry(approval, "expiry") <= moment:
        raise ContractValidationError("approval: expired")
    if _require_expiry(intent, "intent expiry") <= moment:
        raise ContractValidationError("approval: intent expired")


class DeterministicPolicy:
    """Narrow allowlist policy for the one MVP side effect."""

    def __init__(self, config: PolicyConfig, *, available: bool = True) -> None:
        if not isinstance(available, bool):
            raise ValueError("policy: availability must be a boolean")
        self._config = config
        self._available = available

    def decide(
        self,
        *,
        decision_id: str,
        actuator_request: dict[str, Any],
        approval: dict[str, Any],
        staged_change: dict[str, Any],
        intent: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        if not self._available:
            raise PolicyUnavailable("policy service is unavailable")
        moment = _require_clock(now)
        if not isinstance(actuator_request, dict):
            raise ContractValidationError("policy: actuator request is malformed")
        for field in ("operation", "repository_id", "actuator_id"):
            value = actuator_request.get(field)
            if not isinstance(value, str) or not value:
                raise ContractValidationError("policy: actuator request is malformed")

        reasons: list[str] = []
        effect = "allow"
        verified_digest = sha256_digest(staged_change)
        if actuator_request["operation"] != "publish_pull_request":
            effect, reasons = "deny", ["operation-not-registered"]
        elif actuator_request["repository_id"] not in self._config.allowed_repositories:
            effect, reasons = "deny", ["repository-not-allowlisted"]
        elif actuator_request["actuator_id"] not in self._config.allowed_actuators:
            effect, reasons = "deny", ["actuator-not-allowlisted"]
        elif actuator_request.get("staged_change_digest") != verified_digest:
            effect, reasons = "deny", ["request-digest-mismatch"]
        elif (
            actuator_request.get("branch_namespace") != intent.get("branch_namespace")
            or actuator_request.get("idempotency_key") != intent.get("idempotency_key")
        ):
            effect, reasons = "deny", ["request-intent-mismatch"]
        else:
            try:
                validate_approval(
                    approval, staged_change, intent,
                    policy_version=self._config.version, now=now,
                )
            except ContractValidationError as exc:
                effect, reasons = "deny", [str(exc).replace("approval: ", "approval-").replace(" ", "-")]
            else:
                reasons = ["repository-allowlisted", "approval-valid", "digest-bound"]

        expires_at = moment + timedelta(seconds=self._config.decision_ttl_seconds)
        return {
            "schema_version": 1,
            "decision_id": decision_id,
            "effect": effect,
            "reason_codes": reasons,
            "principal_id": actuator_request["actuator_id"],
            "operation": actuator_request["operation"],
            "repository_id": actuator_request["repository_id"],
            "staged_change_digest": verified_digest,
            "policy_version": self._config.version,
            "evaluated_at": _format_time(moment),
            "expires_at": _format_time(expires_at),
        }


def check_decision_usable(decision: dict[str, Any], *, now: datetime) -> None:
    """Fail closed when an allow decision is used at or past its expiry.

    Only the decision lifetime is inspected; the message carries no approval,
    digest or payload contents. Actuator boundaries must call this at use
    time because a fresh decision cannot enforce its own TTL.
    """

    moment = _require_clock(now)
    if not isinstance(decision, dict):
        raise ContractValidationError("decision: decision is malformed")
    try:
        expires_at = _parse_time(decision["expires_at"])
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ContractValidationError("decision: expiry is invalid") from exc
    if expires_at.tzinfo is None:
        raise ContractValidationError("decision: expiry is invalid")
    if decision.get("effect") != "allow":
        raise ContractValidationError("decision: not allow")
    if expires_at <= moment:
        raise ContractValidationError("decision: expired")


def _require_expiry(mapping: dict[str, Any], label: str) -> datetime:
    raw = mapping.get("expires_at")
    if not isinstance(raw, str):
        raise ContractValidationError(f"approval: {label} is invalid")
    try:
        moment = _parse_time(raw)
    except ValueError as exc:
        raise ContractValidationError(f"approval: {label} is invalid") from exc
    if moment.tzinfo is None:
        raise ContractValidationError(f"approval: {label} is invalid")
    return moment


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_clock(now: Any) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ContractValidationError("authority: clock is invalid")
    return now.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
