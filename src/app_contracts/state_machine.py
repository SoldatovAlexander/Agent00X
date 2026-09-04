"""Deterministic state transitions for the repository-change MVP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProcessState(StrEnum):
    RECEIVED = "received"
    SPECIFIED = "specified"
    AUTHORIZED = "authorized"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    STAGED = "staged"
    WAITING_APPROVAL = "waiting_approval"
    APPLYING = "applying"
    COMPLETED = "completed"
    WAITING_INPUT = "waiting_input"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    CANCELLED = "cancelled"


class InvalidTransition(ValueError):
    """Raised when a caller attempts a transition outside the workflow graph."""


_NORMAL = {
    ProcessState.RECEIVED: {ProcessState.SPECIFIED, ProcessState.WAITING_INPUT, ProcessState.REJECTED, ProcessState.CANCELLED},
    ProcessState.SPECIFIED: {ProcessState.AUTHORIZED, ProcessState.WAITING_INPUT, ProcessState.REJECTED, ProcessState.CANCELLED},
    ProcessState.AUTHORIZED: {ProcessState.EXECUTING, ProcessState.REJECTED, ProcessState.CANCELLED},
    ProcessState.EXECUTING: {ProcessState.VERIFYING, ProcessState.QUARANTINED, ProcessState.FAILED, ProcessState.CANCELLED},
    ProcessState.VERIFYING: {ProcessState.EXECUTING, ProcessState.STAGED, ProcessState.QUARANTINED, ProcessState.REJECTED, ProcessState.FAILED},
    ProcessState.STAGED: {ProcessState.WAITING_APPROVAL, ProcessState.EXECUTING, ProcessState.CANCELLED},
    ProcessState.WAITING_APPROVAL: {ProcessState.APPLYING, ProcessState.EXECUTING, ProcessState.REJECTED, ProcessState.CANCELLED},
    ProcessState.APPLYING: {ProcessState.COMPLETED, ProcessState.FAILED, ProcessState.RECONCILIATION_REQUIRED},
    ProcessState.WAITING_INPUT: {ProcessState.SPECIFIED, ProcessState.CANCELLED},
    ProcessState.QUARANTINED: {ProcessState.EXECUTING, ProcessState.REJECTED, ProcessState.CANCELLED},
    ProcessState.RECONCILIATION_REQUIRED: {ProcessState.COMPLETED, ProcessState.FAILED},
}

_TERMINAL = {
    ProcessState.COMPLETED,
    ProcessState.REJECTED,
    ProcessState.FAILED,
    ProcessState.CANCELLED,
}


@dataclass(frozen=True)
class TransitionEvidence:
    contract_complete: bool = False
    policy_allowed: bool = False
    artifact_digest: bool = False
    verification_passed: bool = False
    staged_digest: bool = False
    approval_valid: bool = False
    receipt_present: bool = False
    postcondition_verified: bool = False


def transition(current: ProcessState, target: ProcessState, evidence: TransitionEvidence) -> ProcessState:
    if current in _TERMINAL:
        raise InvalidTransition(f"terminal state {current} cannot transition")
    if target not in _NORMAL.get(current, set()):
        raise InvalidTransition(f"transition {current} -> {target} is not allowed")

    requirements = {
        (ProcessState.RECEIVED, ProcessState.SPECIFIED): evidence.contract_complete,
        (ProcessState.SPECIFIED, ProcessState.AUTHORIZED): evidence.policy_allowed,
        (ProcessState.EXECUTING, ProcessState.VERIFYING): evidence.artifact_digest,
        (ProcessState.VERIFYING, ProcessState.STAGED): evidence.verification_passed and evidence.staged_digest,
        (ProcessState.STAGED, ProcessState.WAITING_APPROVAL): evidence.staged_digest,
        (ProcessState.WAITING_APPROVAL, ProcessState.APPLYING): evidence.approval_valid and evidence.staged_digest,
        (ProcessState.APPLYING, ProcessState.COMPLETED): evidence.receipt_present and evidence.postcondition_verified,
        (ProcessState.RECONCILIATION_REQUIRED, ProcessState.COMPLETED): evidence.receipt_present and evidence.postcondition_verified,
    }
    required = requirements.get((current, target), True)
    if not required:
        raise InvalidTransition(f"transition {current} -> {target} lacks required evidence")
    return target

