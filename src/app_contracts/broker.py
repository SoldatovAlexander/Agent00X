"""Credential Broker boundary: agents receive no credential values or handles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .digests import sha256_digest
from .validator import ContractValidationError


class GitHubPublicationChannel(Protocol):
    """Private actuator-to-provider channel; its credential is never exposed."""

    def publish_pull_request(self, request: dict[str, Any]) -> Any: ...


class CredentialBroker(Protocol):
    def open_github_publication_channel(
        self, credential_grant: dict[str, Any], actuator_request: dict[str, Any],
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


def validate_credential_use_grant(credential_grant: dict[str, Any], actuator_request: dict[str, Any]) -> None:
    """Ensure a single-use broker channel is scoped to exactly one request."""

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
        self, credential_grant: dict[str, Any], actuator_request: dict[str, Any],
    ) -> GitHubPublicationChannel:
        validate_credential_use_grant(credential_grant, actuator_request)
        grant_id = credential_grant["credential_grant_id"]
        if grant_id in self._used_grants:
            raise ContractValidationError("broker: credential grant already used")
        self._used_grants.add(grant_id)
        self.opened_grants.append(grant_id)
        return self._channel_factory()
