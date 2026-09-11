"""Durable, idempotent publication recovery for the MVP mock actuator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .mock_github import MockGitHubEndpoint, MockPullRequest
from .validator import ContractValidationError


class PublicationRecoveryRequired(RuntimeError):
    """The external effect cannot be established and must not be retried blindly."""


class SimulatedCrash(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicationRecord:
    process_id: str
    idempotency_key: str
    request_digest: str
    repository_id: str
    status: str
    pull_request_id: int | None


class PublicationJournal:
    """SQLite journal with only the states needed around one external effect."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS publication_attempts (
                    process_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_digest TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('prepared', 'attempting', 'completed', 'reconciliation_required')),
                    pull_request_id INTEGER
                )"""
            )

    def prepare(
        self, process_id: str, *, idempotency_key: str, request_digest: str, repository_id: str,
    ) -> PublicationRecord:
        if not isinstance(process_id, str) or not process_id:
            raise ValueError("publication process ID is invalid")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError("publication idempotency key is invalid")
        if not isinstance(repository_id, str) or not repository_id:
            raise ValueError("publication repository is invalid")
        if not isinstance(request_digest, str) or not request_digest:
            raise ValueError("publication request digest is invalid")
        try:
            existing = self.get(process_id)
        except KeyError:
            existing = None
        if existing is not None:
            if (
                existing.idempotency_key == idempotency_key
                and existing.request_digest == request_digest
                and existing.repository_id == repository_id
            ):
                return existing
            raise ValueError("publication payload conflict")
        try:
            with self._connection:
                self._connection.execute(
                    """INSERT INTO publication_attempts(process_id, idempotency_key, request_digest, repository_id, status)
                       VALUES (?, ?, ?, ?, 'prepared')""",
                    (process_id, idempotency_key, request_digest, repository_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("publication payload conflict") from exc
        return self.get(process_id)

    def get(self, process_id: str) -> PublicationRecord:
        row = self._connection.execute(
            """SELECT process_id, idempotency_key, request_digest, repository_id, status, pull_request_id
               FROM publication_attempts WHERE process_id = ?""",
            (process_id,),
        ).fetchone()
        if row is None:
            raise KeyError(process_id)
        return PublicationRecord(**dict(row))

    def mark_attempting(self, process_id: str) -> None:
        self._set_status(process_id, "prepared", "attempting")

    def mark_completed(self, process_id: str, pull_request: MockPullRequest) -> None:
        record = self.get(process_id)
        if record.status != "attempting":
            raise ValueError("publication is not attempting")
        if not isinstance(pull_request, MockPullRequest):
            raise ValueError("publication receipt is invalid")
        receipt_id = pull_request.pull_request_id
        if isinstance(receipt_id, bool) or not isinstance(receipt_id, int) or receipt_id < 1:
            raise ValueError("publication receipt is invalid")
        branch, digest = pull_request.branch, pull_request.staged_change_digest
        expected_key = (
            f"publish/{branch.removeprefix('agent/')}/{digest}"
            if isinstance(branch, str) and isinstance(digest, str)
            else None
        )
        if (
            expected_key != record.idempotency_key
            or pull_request.repository_id != record.repository_id
        ):
            raise ValueError("publication receipt mismatch")
        with self._connection:
            updated = self._connection.execute(
                """UPDATE publication_attempts SET status = 'completed', pull_request_id = ?
                   WHERE process_id = ? AND status = 'attempting'""",
                (pull_request.pull_request_id, process_id),
            )
            if updated.rowcount != 1:
                raise ValueError("publication is not attempting")

    def mark_reconciliation_required(self, process_id: str) -> None:
        self._set_status(process_id, "attempting", "reconciliation_required")

    def _set_status(self, process_id: str, expected: str, target: str) -> None:
        with self._connection:
            updated = self._connection.execute(
                """UPDATE publication_attempts SET status = ?
                   WHERE process_id = ? AND status = ?""",
                (target, process_id, expected),
            )
            if updated.rowcount != 1:
                raise ValueError(f"publication is not {expected}")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PublicationJournal":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def execute_publication(
    journal: PublicationJournal,
    endpoint: MockGitHubEndpoint,
    request: dict,
    *,
    crash_after_external_effect: bool = False,
) -> MockPullRequest:
    boundary_fields = {
        "operation", "repository_id", "branch", "staged_change_digest",
        "idempotency_key", "policy_effect", "approval_valid",
    }
    if (
        not isinstance(request, dict)
        or "process_id" not in request
        or any(field not in request for field in boundary_fields)
    ):
        raise ContractValidationError("publication: request is malformed")
    for field in (
        "operation", "repository_id", "branch",
        "staged_change_digest", "idempotency_key", "policy_effect",
    ):
        value = request[field]
        if not isinstance(value, str) or not value:
            raise ContractValidationError("publication: request value is invalid")
    if not isinstance(request["approval_valid"], bool):
        raise ContractValidationError("publication: request value is invalid")
    record = journal.get(request["process_id"])
    if record.status != "prepared":
        raise ValueError("publication is not prepared")
    journal.mark_attempting(record.process_id)
    result = endpoint.publish_pull_request({field: request[field] for field in boundary_fields})
    if crash_after_external_effect:
        raise SimulatedCrash("crash after external effect before local receipt")
    journal.mark_completed(record.process_id, result)
    return result


def recover_publication(
    journal: PublicationJournal,
    endpoint: MockGitHubEndpoint,
    process_id: str,
) -> PublicationRecord:
    """Recover safely; never re-run an uncertain side effect automatically."""

    record = journal.get(process_id)
    if record.status == "completed":
        return record
    if record.status == "prepared":
        return record  # no external call was started; a caller may retry explicitly
    if record.status == "attempting":
        external = endpoint.find_by_idempotency_key(record.idempotency_key)
        if external is not None:
            journal.mark_completed(process_id, external)
            return journal.get(process_id)
        journal.mark_reconciliation_required(process_id)
        raise PublicationRecoveryRequired(process_id)
    raise PublicationRecoveryRequired(process_id)
