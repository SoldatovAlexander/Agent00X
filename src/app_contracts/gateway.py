"""Deterministic risk classifier for the MVP Agent I/O Gateway."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime
from typing import Any, Protocol

from .validator import ContractValidationError

class GatewayPath(StrEnum):
    FAST = "fast"
    SLOW = "slow"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class GatewayDecision:
    path: GatewayPath
    allowed: bool
    reason_codes: tuple[str, ...]


def _require_envelope_shape(envelope: dict[str, Any]) -> None:
    if not isinstance(envelope, dict):
        raise ContractValidationError("gateway: envelope is malformed")
    for section, field in _REQUIRED_ENVELOPE_FIELDS:
        section_value = envelope.get(section)
        if not isinstance(section_value, dict) or field not in section_value:
            raise ContractValidationError("gateway: envelope is malformed")
    for section, field in (("intent", "operation"), ("destination", "port"), ("source", "protocol")):
        value = envelope[section][field]
        if not isinstance(value, str) or not value:
            raise ContractValidationError("gateway: envelope is malformed")
    if not isinstance(envelope["security"]["tainted"], bool):
        raise ContractValidationError("gateway: envelope is malformed")


class GatewayAuditSink(Protocol):
    def append_audit_event(
        self, process_id: str, *, actor_id: str, event_type: str, input_digest: str,
        result: str, reason_codes: tuple[str, ...], now: datetime | None = None,
    ) -> None: ...


_READ_ONLY_OPERATIONS = frozenset({
    "repository.read", "workspace.read", "artifact.read", "evidence.read",
})
_REQUIRED_ENVELOPE_FIELDS = (
    ("intent", "operation"),
    ("destination", "port"),
    ("source", "protocol"),
    ("security", "tainted"),
    ("security", "sensitivity"),
)
_REQUIRED_AUDIT_FIELDS = (
    ("source", "principal_id"),
    ("payload", "content_digest"),
)


def _require_audit_shape(envelope: dict[str, Any]) -> None:
    if not isinstance(envelope.get("correlation_id"), str) or not envelope["correlation_id"]:
        raise ContractValidationError("gateway: envelope is malformed")
    for section, field in _REQUIRED_AUDIT_FIELDS:
        section_value = envelope.get(section)
        if not isinstance(section_value, dict) or field not in section_value:
            raise ContractValidationError("gateway: envelope is malformed")
_SLOW_PORTS = frozenset({"tool", "approval", "credential-operation"})
_PRIVILEGE_PREFIXES = ("capability.", "identity.", "delegation.")


def classify(envelope: dict[str, Any], *, policy_available: bool) -> GatewayDecision:
    """Choose the minimum safe path; a missing policy never permits a write."""

    _require_envelope_shape(envelope)
    operation = envelope["intent"]["operation"]
    port = envelope["destination"]["port"]
    security = envelope["security"]
    is_read_only = operation in _READ_ONLY_OPERATIONS

    if not policy_available:
        if is_read_only:
            return GatewayDecision(GatewayPath.DEGRADED, True, ("policy-unavailable", "read-only-allowlist"))
        return GatewayDecision(GatewayPath.DEGRADED, False, ("policy-unavailable", "write-or-unknown-denied"))

    if security["tainted"] and not is_read_only:
        return GatewayDecision(GatewayPath.SLOW, False, ("tainted-content", "authorization-denied"))

    reasons: list[str] = []
    if security["tainted"]:
        reasons.append("tainted-content")
    if envelope["source"]["protocol"] != "internal":
        reasons.append("protocol-boundary")
    if port in _SLOW_PORTS:
        reasons.append("sensitive-port")
    if operation.startswith(_PRIVILEGE_PREFIXES):
        reasons.append("privilege-transition")
    if operation not in _READ_ONLY_OPERATIONS:
        reasons.append("write-or-unknown-operation")
    if security["sensitivity"] in {"confidential", "restricted"}:
        reasons.append("sensitive-data")

    if reasons:
        return GatewayDecision(GatewayPath.SLOW, True, tuple(reasons))
    return GatewayDecision(GatewayPath.FAST, True, ("internal-read-only",))


def enforce(
    envelope: dict[str, Any],
    *,
    policy_available: bool,
    audit_sink: GatewayAuditSink,
    now: datetime | None = None,
) -> GatewayDecision:
    """Classify a request and record a minimal, non-payload audit event.

    A failing audit sink never leaks envelope content and never upgrades the
    outcome: enforcement falls back to a degraded deny carrying only a
    stable boundary classification. An envelope that cannot even be
    classified is denied the same way without ever reaching the sink.
    """

    try:
        _require_audit_shape(envelope)
        decision = classify(envelope, policy_available=policy_available)
    except (ContractValidationError, KeyError, TypeError, AttributeError):
        return GatewayDecision(GatewayPath.DEGRADED, False, ("malformed-envelope",))
    try:
        audit_sink.append_audit_event(
            envelope["correlation_id"],
            actor_id=envelope["source"]["principal_id"],
            event_type="gateway.request",
            input_digest=envelope["payload"]["content_digest"],
            result="allowed" if decision.allowed else "denied",
            reason_codes=decision.reason_codes,
            now=now,
        )
    except Exception:
        return GatewayDecision(GatewayPath.DEGRADED, False, ("audit-sink-unavailable",))
    return decision
