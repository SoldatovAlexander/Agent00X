"""Durable, idempotent publication recovery for the MVP mock actuator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .mock_github import MockGitHubEndpoint, MockPullRequest


class PublicationRecoveryRequired(RuntimeError):
    """The external effect cannot be established and must not be retried blindly."""


class SimulatedCrash(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicationRecord:
    process_id: str
    idempotency_key: str
    request_digest: str
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
                    status TEXT NOT NULL CHECK(status IN ('prepared', 'attempting', 'completed', 'reconciliation_required')),
                    pull_request_id INTEGER
                )"""
            )

    def prepare(self, process_id: str, *, idempotency_key: str, request_digest: str) -> PublicationRecord:
        try:
            existing = self.get(process_id)
        except KeyError:
            existing = None
        if existing is not None:
            if (
                existing.idempotency_key == idempotency_key
                and existing.request_digest == request_digest
            ):
                return existing
            raise ValueError(f"publication payload conflict for {process_id}")
        try:
            with self._connection:
                self._connection.execute(
                    """INSERT INTO publication_attempts(process_id, idempotency_key, request_digest, status)
                       VALUES (?, ?, ?, 'prepared')""",
                    (process_id, idempotency_key, request_digest),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"publication payload conflict for {process_id}") from exc
        return self.get(process_id)

    def get(self, process_id: str) -> PublicationRecord:
        row = self._connection.execute(
            """SELECT process_id, idempotency_key, request_digest, status, pull_request_id
               FROM publication_attempts WHERE process_id = ?""",
            (process_id,),
        ).fetchone()
        if row is None:
            raise KeyError(process_id)
        return PublicationRecord(**dict(row))

    def mark_attempting(self, process_id: str) -> None:
        self._set_status(process_id, "prepared", "attempting")

    def mark_completed(self, process_id: str, pull_request: MockPullRequest) -> None:
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
    record = journal.get(request["process_id"])
    if record.status != "prepared":
        raise ValueError("publication is not prepared")
    journal.mark_attempting(record.process_id)
    boundary_fields = {
        "operation", "repository_id", "branch", "staged_change_digest",
        "idempotency_key", "policy_effect", "approval_valid",
    }
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
