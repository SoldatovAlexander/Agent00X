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


def validate_approval(
    approval: dict[str, Any],
    staged_change: dict[str, Any],
    intent: dict[str, Any],
    *,
    policy_version: str,
    now: datetime,
) -> None:
    """Reject any approval no longer bound to this exact publication intent."""

    moment = _utc(now)
    staged_digest = sha256_digest(staged_change)
    required_matches = ("process_id", "repository_id", "operation")
    for field in required_matches:
        if approval[field] != intent[field]:
            raise ContractValidationError(f"approval: {field} mismatch")
    if approval["staged_change_digest"] != staged_digest:
        raise ContractValidationError("approval: staged change digest mismatch")
    if intent["staged_change_digest"] != staged_digest:
        raise ContractValidationError("approval: intent staged change digest mismatch")
    if intent["approval_id"] != approval["approval_id"]:
        raise ContractValidationError("approval: approval_id mismatch")
    if approval["policy_version"] != policy_version:
        raise ContractValidationError("approval: policy version mismatch")
    if _parse_time(approval["expires_at"]) <= moment:
        raise ContractValidationError("approval: expired")
    if _parse_time(intent["expires_at"]) <= moment:
        raise ContractValidationError("approval: intent expired")


class DeterministicPolicy:
    """Narrow allowlist policy for the one MVP side effect."""

    def __init__(self, config: PolicyConfig, *, available: bool = True) -> None:
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

        reasons: list[str] = []
        effect = "allow"
        if actuator_request["operation"] != "publish_pull_request":
            effect, reasons = "deny", ["operation-not-registered"]
        elif actuator_request["repository_id"] not in self._config.allowed_repositories:
            effect, reasons = "deny", ["repository-not-allowlisted"]
        elif actuator_request["actuator_id"] not in self._config.allowed_actuators:
            effect, reasons = "deny", ["actuator-not-allowlisted"]
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

        moment = _utc(now)
        expires_at = moment + timedelta(seconds=self._config.decision_ttl_seconds)
        return {
            "schema_version": 1,
            "decision_id": decision_id,
            "effect": effect,
            "reason_codes": reasons,
            "principal_id": actuator_request["actuator_id"],
            "operation": actuator_request["operation"],
            "repository_id": actuator_request["repository_id"],
            "staged_change_digest": actuator_request["staged_change_digest"],
            "policy_version": self._config.version,
            "evaluated_at": _format_time(moment),
            "expires_at": _format_time(expires_at),
        }


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
