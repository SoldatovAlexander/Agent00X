"""Durable, idempotent publication journal for mock and typed provider receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import quote, unquote, urlparse

from .github_app import GitHubPullRequest
from .mock_github import MockGitHubEndpoint, MockPullRequest
from .publication_seed import publication_idempotency_key, validate_publication_base_branch
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
    base_branch: str | None
    status: str
    pull_request_id: int | None
    pull_request_url: str | None = None
    verified_files_digest: str | None = None
    verified_files_outcome: str | None = None
    verified_branch_commit_sha: str | None = None
    verified_files_observed_at: str | None = None


class PublicationJournal:
    """SQLite journal with only the states needed around one external effect."""

    def __init__(self, path: Path, *, create_if_missing: bool = True) -> None:
        if type(create_if_missing) is not bool:
            raise ValueError("publication journal mode is invalid")
        if create_if_missing:
            connection = sqlite3.connect(path)
        else:
            journal_path = Path(path)
            if journal_path.is_symlink() or not journal_path.is_file():
                raise ValueError("publication journal is unavailable")
            try:
                uri = journal_path.resolve(strict=True).as_uri() + "?mode=rw"
                connection = sqlite3.connect(uri, timeout=5.0, uri=True)
            except Exception:
                raise ValueError("publication journal is unavailable") from None
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        if not create_if_missing:
            try:
                columns = {
                    row["name"]
                    for row in self._connection.execute(
                        "PRAGMA table_info(publication_attempts)"
                    )
                }
                required = {
                    "process_id", "idempotency_key", "request_digest",
                    "repository_id", "base_branch", "status",
                    "pull_request_id", "pull_request_url",
                    "verified_files_digest", "verified_files_outcome",
                    "verified_branch_commit_sha", "verified_files_observed_at",
                }
                if not required.issubset(columns):
                    raise ValueError
            except Exception:
                self._connection.close()
                raise ValueError("publication journal schema is unavailable") from None
            self._configure_durability(create_if_missing=False)
            return
        self._configure_durability(create_if_missing=True)
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS publication_attempts (
                    process_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_digest TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    base_branch TEXT,
                    status TEXT NOT NULL CHECK(status IN ('prepared', 'attempting', 'completed', 'reconciliation_required')),
                    pull_request_id INTEGER,
                    pull_request_url TEXT,
                    verified_files_digest TEXT,
                    verified_files_outcome TEXT CHECK(verified_files_outcome IS NULL OR verified_files_outcome IN ('verified', 'unverified')),
                    verified_branch_commit_sha TEXT,
                    verified_files_observed_at TEXT
                )"""
            )
            columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(publication_attempts)")
            }
            if "pull_request_url" not in columns:
                self._connection.execute(
                    "ALTER TABLE publication_attempts ADD COLUMN pull_request_url TEXT"
                )
            if "base_branch" not in columns:
                self._connection.execute(
                    "ALTER TABLE publication_attempts ADD COLUMN base_branch TEXT"
                )
            migrations = {
                "verified_files_digest": "TEXT",
                "verified_files_outcome": "TEXT CHECK(verified_files_outcome IS NULL OR verified_files_outcome IN ('verified', 'unverified'))",
                "verified_branch_commit_sha": "TEXT",
                "verified_files_observed_at": "TEXT",
            }
            for name, declaration in migrations.items():
                if name not in columns:
                    self._connection.execute(
                        f"ALTER TABLE publication_attempts ADD COLUMN {name} {declaration}"
                    )

    def _configure_durability(self, *, create_if_missing: bool) -> None:
        try:
            if create_if_missing:
                journal_mode = self._connection.execute(
                    "PRAGMA journal_mode=WAL"
                ).fetchone()
            else:
                journal_mode = self._connection.execute(
                    "PRAGMA journal_mode"
                ).fetchone()
            self._connection.execute("PRAGMA synchronous=FULL")
            synchronous = self._connection.execute(
                "PRAGMA synchronous"
            ).fetchone()
            if (
                not journal_mode
                or type(journal_mode[0]) is not str
                or journal_mode[0].lower() != "wal"
                or not synchronous
                or synchronous[0] != 2
            ):
                raise sqlite3.DatabaseError("required journal durability unavailable")
        except Exception:
            self._connection.close()
            raise ValueError("publication journal durability is unavailable") from None

    def prepare(
        self,
        process_id: str,
        *,
        idempotency_key: str,
        request_digest: str,
        repository_id: str,
        verified_files_digest: str | None = None,
    ) -> PublicationRecord:
        if not isinstance(process_id, str) or not process_id:
            raise ValueError("publication process ID is invalid")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError("publication idempotency key is invalid")
        key_body = idempotency_key[len("publish/"):] if idempotency_key.startswith("publish/") else ""
        key_parts = key_body.split("/")
        if (
            len(key_parts) != 3
            or any(part == "" for part in key_parts)
            or quote(unquote(key_parts[0]), safe="") != key_parts[0]
            or quote(unquote(key_parts[1]), safe="") != key_parts[1]
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", key_parts[2])
        ):
            raise ValueError("publication idempotency key is not canonical")
        base_branch = unquote(key_parts[1])
        try:
            validate_publication_base_branch(base_branch)
        except Exception:
            raise ValueError("publication idempotency key is not canonical") from None
        if not isinstance(request_digest, str) or not request_digest:
            raise ValueError("publication request digest is invalid")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", request_digest) is None:
            raise ValueError("publication request digest is not canonical")
        if not isinstance(repository_id, str) or not repository_id:
            raise ValueError("publication repository is invalid")
        if verified_files_digest is not None and (
            not isinstance(verified_files_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", verified_files_digest) is None
        ):
            raise ValueError("publication verified-files digest is invalid")
        try:
            existing = self.get(process_id)
        except KeyError:
            existing = None
        if existing is not None:
            if (
                existing.idempotency_key == idempotency_key
                and existing.request_digest == request_digest
                and existing.repository_id == repository_id
                and existing.base_branch == base_branch
                and (
                    verified_files_digest is None
                    or existing.verified_files_digest == verified_files_digest
                )
            ):
                return existing
            raise ValueError("publication payload conflict")
        try:
            with self._connection:
                self._connection.execute(
                    """INSERT INTO publication_attempts(
                           process_id, idempotency_key, request_digest, repository_id,
                           base_branch, status, verified_files_digest
                       ) VALUES (?, ?, ?, ?, ?, 'prepared', ?)""",
                    (process_id, idempotency_key, request_digest, repository_id, base_branch, verified_files_digest),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("publication payload conflict") from exc
        return self.get(process_id)

    def get(self, process_id: str) -> PublicationRecord:
        if not isinstance(process_id, str) or not process_id:
            raise ValueError("publication process ID is invalid")
        row = self._connection.execute(
            """SELECT process_id, idempotency_key, request_digest, repository_id,
                      base_branch, status,
                      pull_request_id, pull_request_url, verified_files_digest,
                      verified_files_outcome, verified_branch_commit_sha,
                      verified_files_observed_at
               FROM publication_attempts WHERE process_id = ?""",
            (process_id,),
        ).fetchone()
        if row is None:
            raise KeyError(process_id)
        return PublicationRecord(**dict(row))

    def mark_attempting(self, process_id: str) -> None:
        self._set_status(process_id, "prepared", "attempting")

    def mark_completed(
        self, process_id: str, pull_request: MockPullRequest | GitHubPullRequest,
    ) -> None:
        self._mark_completed(process_id, pull_request, expected_status="attempting")

    def mark_completed_from_reconciliation(
        self, process_id: str, pull_request: MockPullRequest | GitHubPullRequest,
    ) -> None:
        """Complete only from a matching receipt found by read-only lookup."""
        self._mark_completed(
            process_id, pull_request, expected_status="reconciliation_required"
        )

    def _mark_completed(
        self,
        process_id: str,
        pull_request: MockPullRequest | GitHubPullRequest,
        *,
        expected_status: str,
    ) -> None:
        record = self.get(process_id)
        if record.status != expected_status:
            raise ValueError(f"publication is not {expected_status}")
        if type(pull_request) not in (MockPullRequest, GitHubPullRequest):
            raise ValueError("publication receipt is invalid")
        receipt_id = pull_request.pull_request_id
        if isinstance(receipt_id, bool) or not isinstance(receipt_id, int) or receipt_id < 1:
            raise ValueError("publication receipt is invalid")
        branch, digest = pull_request.branch, pull_request.staged_change_digest
        if not isinstance(branch, str) or not branch or not isinstance(digest, str) or not digest:
            raise ValueError("publication receipt is invalid")
        receipt_url = getattr(pull_request, "pull_request_url", None)
        if type(pull_request) is GitHubPullRequest:
            try:
                parsed_url = urlparse(receipt_url) if isinstance(receipt_url, str) else None
            except ValueError:
                parsed_url = None
            if (
                parsed_url is None
                or parsed_url.scheme != "https"
                or not parsed_url.netloc
                or parsed_url.username is not None
                or parsed_url.password is not None
                or parsed_url.fragment
            ):
                raise ValueError("publication receipt is invalid")
        elif receipt_url is not None:
            raise ValueError("publication receipt is invalid")
        expected_key = publication_idempotency_key(
            branch, record.base_branch or "", digest
        )
        if (
            expected_key != record.idempotency_key
            or pull_request.idempotency_key != record.idempotency_key
            or pull_request.repository_id != record.repository_id
            or pull_request.base_branch != record.base_branch
            or record.base_branch is None
        ):
            raise ValueError("publication receipt mismatch")
        with self._connection:
            updated = self._connection.execute(
                """UPDATE publication_attempts SET status = 'completed', pull_request_id = ?, pull_request_url = ?
                   WHERE process_id = ? AND status = ?""",
                (pull_request.pull_request_id, receipt_url, process_id, expected_status),
            )
            if updated.rowcount != 1:
                raise ValueError(f"publication is not {expected_status}")

    def mark_reconciliation_required(self, process_id: str) -> None:
        self._set_status(process_id, "attempting", "reconciliation_required")

    def record_verified_file_reconciliation(
        self,
        process_id: str,
        *,
        manifest_digest: str,
        outcome: str,
        branch_commit_sha: str | None,
        observed_at: datetime,
    ) -> None:
        record = self.get(process_id)
        if record.status != "reconciliation_required":
            raise ValueError("publication is not awaiting reconciliation")
        if (
            not isinstance(manifest_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_digest) is None
            or manifest_digest != record.verified_files_digest
            or type(outcome) is not str
            or outcome not in {"verified", "unverified"}
            or not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
        ):
            raise ValueError("publication reconciliation evidence is invalid")
        if outcome == "verified":
            if (
                not isinstance(branch_commit_sha, str)
                or re.fullmatch(r"[0-9a-f]{40}", branch_commit_sha) is None
            ):
                raise ValueError("publication reconciliation evidence is invalid")
        elif branch_commit_sha is not None:
            raise ValueError("publication reconciliation evidence is invalid")
        observed = observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._connection:
            updated = self._connection.execute(
                """UPDATE publication_attempts
                   SET verified_files_digest = ?, verified_files_outcome = ?,
                       verified_branch_commit_sha = ?, verified_files_observed_at = ?
                   WHERE process_id = ? AND status = 'reconciliation_required'""",
                (manifest_digest, outcome, branch_commit_sha, observed, process_id),
            )
            if updated.rowcount != 1:
                raise ValueError("publication is not awaiting reconciliation")

    def _set_status(self, process_id: str, expected: str, target: str) -> None:
        if not isinstance(process_id, str) or not process_id:
            raise ValueError("publication process ID is invalid")
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
    endpoint: Any,
    request: dict,
    *,
    crash_after_external_effect: bool = False,
    before_publish: Any = None,
) -> MockPullRequest | GitHubPullRequest:
    boundary_fields = {
        "operation", "repository_id", "branch", "base_branch", "staged_change_digest",
        "idempotency_key", "policy_effect", "approval_valid",
    }
    if (
        not callable(getattr(journal, "get", None))
        or not callable(getattr(journal, "mark_attempting", None))
        or not callable(getattr(journal, "mark_completed", None))
        or not callable(getattr(endpoint, "publish_pull_request", None))
        or (before_publish is not None and not callable(before_publish))
    ):
        raise ContractValidationError("publication: collaborator is invalid")
    if (
        not isinstance(request, dict)
        or "process_id" not in request
        or any(field not in request for field in boundary_fields)
    ):
        raise ContractValidationError("publication: request is malformed")
    for field in (
        "operation", "repository_id", "branch",
        "base_branch", "staged_change_digest", "idempotency_key", "policy_effect",
    ):
        value = request[field]
        if not isinstance(value, str) or not value:
            raise ContractValidationError("publication: request value is invalid")
    if not isinstance(request["approval_valid"], bool):
        raise ContractValidationError("publication: request value is invalid")
    process_id = request["process_id"]
    if not isinstance(process_id, str) or not process_id:
        raise ContractValidationError("publication: request value is invalid")
    record = journal.get(request["process_id"])
    if record.status != "prepared":
        raise ValueError("publication is not prepared")
    journal.mark_attempting(record.process_id)
    if before_publish is not None:
        before_publish()
    result = endpoint.publish_pull_request({field: request[field] for field in boundary_fields})
    if crash_after_external_effect:
        raise SimulatedCrash("crash after external effect before local receipt")
    journal.mark_completed(record.process_id, result)
    return result


def recover_publication(
    journal: PublicationJournal,
    endpoint: Any,
    process_id: str,
) -> PublicationRecord:
    """Recover safely; never re-run an uncertain side effect automatically."""

    if not callable(getattr(endpoint, "find_by_idempotency_key", None)):
        raise ContractValidationError("publication: collaborator is invalid")
    for method in ("get", "mark_completed", "mark_reconciliation_required"):
        if not callable(getattr(journal, method, None)):
            raise ContractValidationError("publication: collaborator is invalid")
    record = journal.get(process_id)
    if record.status == "completed":
        return record
    if record.status == "prepared":
        return record  # no external call was started; a caller may retry explicitly
    if record.status == "attempting":
        if not record.base_branch:
            journal.mark_reconciliation_required(process_id)
            raise PublicationRecoveryRequired("publication recovery required")
        external = endpoint.find_by_idempotency_key(
            record.idempotency_key,
            repository_id=record.repository_id,
            base_branch=record.base_branch,
        )
        if external is not None:
            journal.mark_completed(process_id, external)
            return journal.get(process_id)
        journal.mark_reconciliation_required(process_id)
        raise PublicationRecoveryRequired("publication recovery required")
    raise PublicationRecoveryRequired("publication recovery required")
