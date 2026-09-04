"""Deterministic risk classifier for the MVP Agent I/O Gateway."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime
from typing import Any, Protocol

class GatewayPath(StrEnum):
    FAST = "fast"
    SLOW = "slow"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class GatewayDecision:
    path: GatewayPath
    allowed: bool
    reason_codes: tuple[str, ...]


class GatewayAuditSink(Protocol):
    def append_audit_event(
        self, process_id: str, *, actor_id: str, event_type: str, input_digest: str,
        result: str, reason_codes: tuple[str, ...], now: datetime | None = None,
    ) -> None: ...


_READ_ONLY_OPERATIONS = frozenset({
    "repository.read", "workspace.read", "artifact.read", "evidence.read",
})
_SLOW_PORTS = frozenset({"tool", "approval", "credential-operation"})
_PRIVILEGE_PREFIXES = ("capability.", "identity.", "delegation.")


def classify(envelope: dict[str, Any], *, policy_available: bool) -> GatewayDecision:
    """Choose the minimum safe path; a missing policy never permits a write."""

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
    """Classify a request and record a minimal, non-payload audit event."""

    decision = classify(envelope, policy_available=policy_available)
    audit_sink.append_audit_event(
        envelope["correlation_id"],
        actor_id=envelope["source"]["principal_id"],
        event_type="gateway.request",
        input_digest=envelope["payload"]["content_digest"],
        result="allowed" if decision.allowed else "denied",
        reason_codes=decision.reason_codes,
        now=now,
    )
    return decision
