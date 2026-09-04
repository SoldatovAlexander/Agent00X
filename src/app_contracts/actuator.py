"""Typed adapter from a policy-authorized request to the mock GitHub boundary."""

from __future__ import annotations

from typing import Any

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
) -> MockPullRequest:
    """Publish only a typed request matched to an allow decision and approval."""

    if not gateway_decision.allowed or gateway_decision.path is not GatewayPath.SLOW:
        raise ContractValidationError("actuator: gateway has not authorized slow path")
    if policy_decision["effect"] != "allow":
        raise ContractValidationError("actuator: policy decision is not allow")
    for field in ("operation", "repository_id", "staged_change_digest"):
        if policy_decision[field] != actuator_request[field]:
            raise ContractValidationError(f"actuator: policy decision {field} mismatch")

    return endpoint.publish_pull_request({
        "operation": actuator_request["operation"],
        "repository_id": actuator_request["repository_id"],
        "branch": actuator_request["branch_namespace"],
        "staged_change_digest": actuator_request["staged_change_digest"],
        "idempotency_key": actuator_request["idempotency_key"],
        "policy_effect": policy_decision["effect"],
        "approval_valid": approval_valid,
    })
