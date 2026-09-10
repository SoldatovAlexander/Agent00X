"""Actuator that can publish only through a broker-owned private channel."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .actuator import publish_authorized_request
from .authority import check_decision_usable
from .broker import CredentialBroker
from .gateway import GatewayDecision
from .mock_github import MockPullRequest


class BrokeredGitHubActuator:
    def __init__(self, broker: CredentialBroker) -> None:
        self._broker = broker

    def publish_pull_request(
        self,
        *,
        actuator_request: dict[str, Any],
        credential_grant: dict[str, Any],
        policy_decision: dict[str, Any],
        approval_valid: bool,
        gateway_decision: GatewayDecision,
        intent: dict[str, Any],
        now: datetime,
    ) -> MockPullRequest:
        # The allow decision must still be usable at the explicit use time.
        # This gate runs before the broker opens its provider channel, so an
        # expired decision never reaches the broker/provider boundary.
        check_decision_usable(policy_decision, now=now)
        # The broker validates grant/request binding before any provider call.
        channel = self._broker.open_github_publication_channel(credential_grant, actuator_request)
        # The channel is intentionally opaque. It alone performs the provider operation.
        # The approved intent and use time are forwarded so a post-allow
        # branch/key swap or a stale decision is rejected at the actuator
        # boundary instead of reaching the provider.
        return publish_authorized_request(
            channel, actuator_request, policy_decision,
            approval_valid=approval_valid, gateway_decision=gateway_decision,
            intent=intent, now=now,
        )
