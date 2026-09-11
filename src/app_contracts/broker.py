"""Credential Broker boundary: agents receive no credential values or handles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from .digests import sha256_digest
from .validator import ContractValidationError


class GitHubPublicationChannel(Protocol):
    """Private actuator-to-provider channel; its credential is never exposed."""

    def publish_pull_request(self, request: dict[str, Any]) -> Any: ...


class CredentialBroker(Protocol):
    def open_github_publication_channel(
        self,
        credential_grant: dict[str, Any],
        actuator_request: dict[str, Any],
        *,
        now: datetime,
    ) -> GitHubPublicationChannel: ...


_REQUIRED_GRANT_FIELDS = (
    "credential_grant_id",
    "actuator_id",
    "repository_id",
    "operation",
    "request_digest",
    "single_use",
)


_REQUIRED_REQUEST_FIELDS = ("actuator_id", "repository_id", "operation")


def validate_credential_use_grant(
    credential_grant: dict[str, Any],
    actuator_request: dict[str, Any],
    *,
    now: datetime,
) -> None:
    """Ensure a single-use broker channel is scoped to exactly one request.

    The explicit timezone-aware ``now`` is mandatory: grant lifetime is
    always enforced, so no channel opens for a malformed or expired grant.
    """

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ContractValidationError("broker: grant expiry check requires aware time")
    if not isinstance(credential_grant, dict) or any(
        field not in credential_grant for field in _REQUIRED_GRANT_FIELDS
    ):
        raise ContractValidationError("broker: credential grant is malformed")
    if not isinstance(actuator_request, dict) or any(
        field not in actuator_request for field in _REQUIRED_REQUEST_FIELDS
    ):
        raise ContractValidationError("broker: actuator request is malformed")
    for field in ("actuator_id", "repository_id", "operation"):
        for mapping in (credential_grant, actuator_request):
            value = mapping[field]
            if not isinstance(value, str) or not value:
                raise ContractValidationError("broker: binding value is invalid")
    grant_id = credential_grant["credential_grant_id"]
    if not isinstance(grant_id, str) or not grant_id:
        raise ContractValidationError("broker: binding value is invalid")
    if credential_grant.get("credential_class") != "github-app-installation":
        raise ContractValidationError("broker: credential class mismatch")
    if credential_grant["actuator_id"] != actuator_request["actuator_id"]:
        raise ContractValidationError("broker: actuator identity mismatch")
    if credential_grant["repository_id"] != actuator_request["repository_id"]:
        raise ContractValidationError("broker: repository mismatch")
    if credential_grant["operation"] != actuator_request["operation"]:
        raise ContractValidationError("broker: operation mismatch")
    if credential_grant["request_digest"] != sha256_digest(actuator_request):
        raise ContractValidationError("broker: request digest mismatch")
    if credential_grant["single_use"] is not True:
        raise ContractValidationError("broker: credential grant must be single-use")
    raw_expiry = credential_grant.get("expires_at")
    if not isinstance(raw_expiry, str):
        raise ContractValidationError("broker: credential grant expiry is invalid")
    try:
        expires_at = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError("broker: credential grant expiry is invalid") from exc
    if expires_at.tzinfo is None:
        raise ContractValidationError("broker: credential grant expiry is invalid")
    if expires_at <= now.astimezone(timezone.utc):
        raise ContractValidationError("broker: credential grant expired")


@dataclass
class InMemoryCredentialBroker:
    """Test-only broker which mints an opaque, single-use provider channel."""

    _channel_factory: Any
    opened_grants: list[str]

    def __init__(self, channel_factory: Any) -> None:
        self._channel_factory = channel_factory
        self.opened_grants = []
        self._used_grants: set[str] = set()

    def open_github_publication_channel(
        self,
        credential_grant: dict[str, Any],
        actuator_request: dict[str, Any],
        *,
        now: datetime,
    ) -> GitHubPublicationChannel:
        validate_credential_use_grant(credential_grant, actuator_request, now=now)
        grant_id = credential_grant["credential_grant_id"]
        if grant_id in self._used_grants:
            raise ContractValidationError("broker: credential grant already used")
        self._used_grants.add(grant_id)
        self.opened_grants.append(grant_id)
        channel = self._channel_factory()
        if not callable(getattr(channel, "publish_pull_request", None)):
            raise ContractValidationError("broker: channel factory result is invalid")
        return channel
