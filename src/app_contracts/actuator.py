"""Typed adapter from a policy-authorized request to the mock GitHub boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .authority import check_decision_usable, check_intent_approved
from .mock_github import MockGitHubEndpoint, MockPullRequest
from .gateway import GatewayDecision, GatewayPath
from .validator import ContractValidationError


def publish_authorized_request(
    endpoint: MockGitHubEndpoint,
    actuator_request: dict[str, Any],
    policy_decision: dict[str, Any],
    *,
    approval_valid: bool,
    gateway_decision: GatewayDecision,
    intent: dict[str, Any],
    now: datetime,
    approval: dict[str, Any] | None = None,
) -> MockPullRequest:
    """Publish only a typed request matched to an allow decision and approval.

    The allow decision must still be usable at the explicit timezone-aware
    ``now``: an expired (or non-allow) decision is refused before any other
    check and never reaches the mock boundary. The ``approval`` is mandatory:
    a call without it is refused before any other check and never reaches the
    mock boundary. The presented intent must equal the full canonical approved
    intent by digest, so a coordinated post-approval swap of request, intent,
    or grant is rejected here instead of reaching the mock boundary. The
    request must then match the decision on operation, repository and staged
    digest, and its idempotency key must be consistent with its own branch
    and digest. The approval-bound ``intent`` is required: the request branch
    and idempotency key must equal the approved values. This also covers the
    brokered path, which forwards its approval, intent, and use time.
    """

    if approval is None:
        raise ContractValidationError("actuator: approval is required")
    check_decision_usable(policy_decision, now=now)
    check_intent_approved(intent, approval)
    if not gateway_decision.allowed or gateway_decision.path is not GatewayPath.SLOW:
        raise ContractValidationError("actuator: gateway has not authorized slow path")
    if policy_decision["effect"] != "allow":
        raise ContractValidationError("actuator: policy decision is not allow")
    for field in ("operation", "repository_id", "staged_change_digest"):
        if policy_decision[field] != actuator_request[field]:
            raise ContractValidationError(f"actuator: policy decision {field} mismatch")
    for field in ("branch_namespace", "idempotency_key"):
        if intent[field] != actuator_request[field]:
            raise ContractValidationError(f"actuator: approved intent {field} mismatch")
    branch = actuator_request["branch_namespace"]
    expected_key = f"publish/{branch.removeprefix('agent/')}/{actuator_request['staged_change_digest']}"
    if actuator_request["idempotency_key"] != expected_key:
        raise ContractValidationError("actuator: idempotency key does not match request branch and digest")

    return endpoint.publish_pull_request({
        "operation": actuator_request["operation"],
        "repository_id": actuator_request["repository_id"],
        "branch": actuator_request["branch_namespace"],
        "staged_change_digest": actuator_request["staged_change_digest"],
        "idempotency_key": actuator_request["idempotency_key"],
        "policy_effect": policy_decision["effect"],
        "approval_valid": approval_valid,
    })
