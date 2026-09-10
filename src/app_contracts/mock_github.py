"""In-memory GitHub boundary double for M0 contract and idempotency tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .validator import ContractValidationError


@dataclass(frozen=True)
class MockPullRequest:
    pull_request_id: int
    repository_id: str
    branch: str
    staged_change_digest: str
    idempotency_key: str


class MockGitHubEndpoint:
    """Records a typed publication once and returns it on an identical retry."""

    def __init__(self) -> None:
        self._by_idempotency_key: dict[str, MockPullRequest] = {}

    def publish_pull_request(self, request: dict[str, Any]) -> MockPullRequest:
        required = {
            "operation", "repository_id", "branch", "staged_change_digest",
            "idempotency_key", "policy_effect", "approval_valid",
        }
        if set(request) != required:
            raise ContractValidationError("mock github: request shape mismatch")
        if request["operation"] != "publish_pull_request":
            raise ContractValidationError("mock github: operation is not registered")
        if request["policy_effect"] != "allow" or request["approval_valid"] is not True:
            raise ContractValidationError("mock github: authority proof is invalid")

        for field in ("repository_id", "branch", "staged_change_digest", "idempotency_key"):
            if not isinstance(request[field], str) or not request[field]:
                raise ContractValidationError("mock github: boundary field is invalid")

        expected_key = (
            f"publish/{request['branch'].removeprefix('agent/')}/"
            f"{request['staged_change_digest']}"
        )
        if request["idempotency_key"] != expected_key:
            raise ContractValidationError("mock github: idempotency key mismatch")

        existing = self._by_idempotency_key.get(request["idempotency_key"])
        if existing is not None:
            if (
                existing.repository_id != request["repository_id"]
                or existing.branch != request["branch"]
                or existing.staged_change_digest != request["staged_change_digest"]
            ):
                raise ContractValidationError("mock github: idempotency conflict")
            return existing

        result = MockPullRequest(
            pull_request_id=len(self._by_idempotency_key) + 1,
            repository_id=request["repository_id"],
            branch=request["branch"],
            staged_change_digest=request["staged_change_digest"],
            idempotency_key=request["idempotency_key"],
        )
        self._by_idempotency_key[result.idempotency_key] = result
        return result

    def find_by_idempotency_key(
        self, idempotency_key: str, *, repository_id: str | None = None,
    ) -> MockPullRequest | None:
        """Reconciliation query; it has no side effect.

        When ``repository_id`` is given, a receipt bound to another
        repository is never returned.
        """

        found = self._by_idempotency_key.get(idempotency_key)
        if found is not None and repository_id is not None and found.repository_id != repository_id:
            return None
        return found
