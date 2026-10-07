"""Durable local records of exact-digest confirmation for mock-only actions.

These records are not authenticated approvals and must never authorize a real
provider write. They only make the local interactive mock flow inspectable
across process restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3


SCHEMA_VERSION = 1
CONFIRMATION_MODE = "typed-digest-local-mock"
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ID_PATTERN = re.compile(r"operator-confirmation-[0-9a-f]{32}\Z")
_BRANCH_PATTERN = re.compile(r"agent/[A-Za-z0-9][A-Za-z0-9._/-]{0,126}\Z")


class OperatorConfirmationStoreError(ValueError):
    """A durable local operator confirmation record is invalid or unavailable."""


@dataclass(frozen=True)
class OperatorConfirmationRecord:
    confirmation_id: str
    staged_change_digest: str
    intent_digest: str
    repository_id: str
    branch: str
    operation: str
    confirmed_at: str
    expires_at: str
    status: str
    mock_receipt_id: int | None = None
    confirmation_mode: str = CONFIRMATION_MODE
    authenticated: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.confirmation_id) is not str
            or _ID_PATTERN.fullmatch(self.confirmation_id) is None
        ):
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )
        if (
            type(self.staged_change_digest) is not str
            or _DIGEST_PATTERN.fullmatch(self.staged_change_digest) is None
            or type(self.intent_digest) is not str
            or _DIGEST_PATTERN.fullmatch(self.intent_digest) is None
        ):
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )
        if (
            type(self.repository_id) is not str
            or not self.repository_id
            or type(self.branch) is not str
            or _BRANCH_PATTERN.fullmatch(self.branch) is None
            or self.operation != "publish_pull_request"
            or self.confirmation_mode != CONFIRMATION_MODE
            or self.authenticated is not False
            or self.status not in {"confirmed", "mock_completed"}
        ):
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )
        confirmed = _parse_utc(self.confirmed_at)
        expires = _parse_utc(self.expires_at)
        if expires <= confirmed:
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )
        if self.status == "confirmed" and self.mock_receipt_id is not None:
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )
        if self.status == "mock_completed" and (
            type(self.mock_receipt_id) is not int or self.mock_receipt_id < 1
        ):
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )


class SQLiteOperatorConfirmationStore:
    """Persist and read back local typed-digest confirmation records."""

    def __init__(self, path: Path | str) -> None:
        if not isinstance(path, (Path, str)) or not str(path).strip():
            raise OperatorConfirmationStoreError(
                "operator confirmation: database path is invalid"
            )
        self._connection: sqlite3.Connection | None = None
        try:
            self._connection = sqlite3.connect(path, timeout=5.0)
            self._connection.row_factory = sqlite3.Row
            with self._connection:
                version = self._connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, SCHEMA_VERSION):
                    raise OperatorConfirmationStoreError(
                        "operator confirmation: schema version is unsupported"
                    )
                existing_table = self._connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'operator_confirmations'"
                ).fetchone()
                if (version == 0 and existing_table is not None) or (
                    version == SCHEMA_VERSION and existing_table is None
                ):
                    raise OperatorConfirmationStoreError(
                        "operator confirmation: schema is malformed"
                    )
                self._connection.execute(
                    """CREATE TABLE IF NOT EXISTS operator_confirmations (
                        confirmation_id TEXT PRIMARY KEY,
                        staged_change_digest TEXT NOT NULL,
                        intent_digest TEXT NOT NULL,
                        repository_id TEXT NOT NULL,
                        branch TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        confirmed_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('confirmed', 'mock_completed')),
                        mock_receipt_id INTEGER,
                        confirmation_mode TEXT NOT NULL,
                        authenticated INTEGER NOT NULL CHECK(authenticated = 0)
                    )"""
                )
                if version == 0:
                    self._connection.execute(
                        f"PRAGMA user_version = {SCHEMA_VERSION}"
                    )
                self._validate_schema()
        except OperatorConfirmationStoreError:
            self.close()
            raise
        except Exception:
            self.close()
            raise OperatorConfirmationStoreError(
                "operator confirmation: database is unavailable"
            ) from None

    def __enter__(self) -> "SQLiteOperatorConfirmationStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def save_confirmed(self, record: OperatorConfirmationRecord) -> None:
        if type(record) is not OperatorConfirmationRecord or record.status != "confirmed":
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )
        connection = self._require_connection()
        try:
            with connection:
                connection.execute(
                    """INSERT INTO operator_confirmations (
                        confirmation_id, staged_change_digest, intent_digest,
                        repository_id, branch, operation, confirmed_at,
                        expires_at, status, mock_receipt_id, confirmation_mode,
                        authenticated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (
                        record.confirmation_id,
                        record.staged_change_digest,
                        record.intent_digest,
                        record.repository_id,
                        record.branch,
                        record.operation,
                        record.confirmed_at,
                        record.expires_at,
                        record.status,
                        record.mock_receipt_id,
                        record.confirmation_mode,
                    ),
                )
        except OperatorConfirmationStoreError:
            raise
        except Exception:
            raise OperatorConfirmationStoreError(
                "operator confirmation: record could not be saved"
            ) from None
        persisted = self.load(record.confirmation_id)
        if persisted != record:
            raise OperatorConfirmationStoreError(
                "operator confirmation: exact readback failed"
            )

    def complete_mock(self, confirmation_id: str, mock_receipt_id: int) -> OperatorConfirmationRecord:
        if (
            type(confirmation_id) is not str
            or _ID_PATTERN.fullmatch(confirmation_id) is None
            or type(mock_receipt_id) is not int
            or mock_receipt_id < 1
        ):
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )
        connection = self._require_connection()
        try:
            with connection:
                cursor = connection.execute(
                    """UPDATE operator_confirmations
                       SET status = 'mock_completed', mock_receipt_id = ?
                       WHERE confirmation_id = ? AND status = 'confirmed'
                         AND mock_receipt_id IS NULL""",
                    (mock_receipt_id, confirmation_id),
                )
            if cursor.rowcount != 1:
                raise OperatorConfirmationStoreError(
                    "operator confirmation: record transition is invalid"
                )
            return self.load(confirmation_id)
        except OperatorConfirmationStoreError:
            raise
        except Exception:
            raise OperatorConfirmationStoreError(
                "operator confirmation: record transition failed"
            ) from None

    def load(self, confirmation_id: str) -> OperatorConfirmationRecord:
        if (
            type(confirmation_id) is not str
            or _ID_PATTERN.fullmatch(confirmation_id) is None
        ):
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is invalid"
            )
        connection = self._require_connection()
        try:
            row = connection.execute(
                """SELECT confirmation_id, staged_change_digest, intent_digest,
                          repository_id, branch, operation, confirmed_at,
                          expires_at, status, mock_receipt_id, confirmation_mode,
                          authenticated
                   FROM operator_confirmations WHERE confirmation_id = ?""",
                (confirmation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(confirmation_id)
            values = dict(row)
            values["authenticated"] = values["authenticated"] == 1
            return OperatorConfirmationRecord(**values)
        except OperatorConfirmationStoreError:
            raise
        except KeyError:
            raise
        except Exception:
            raise OperatorConfirmationStoreError(
                "operator confirmation: record is malformed"
            ) from None

    def _validate_schema(self) -> None:
        rows = self._require_connection().execute(
            "PRAGMA table_info(operator_confirmations)"
        ).fetchall()
        expected = (
            "confirmation_id",
            "staged_change_digest",
            "intent_digest",
            "repository_id",
            "branch",
            "operation",
            "confirmed_at",
            "expires_at",
            "status",
            "mock_receipt_id",
            "confirmation_mode",
            "authenticated",
        )
        if tuple(row[1] for row in rows) != expected:
            raise OperatorConfirmationStoreError(
                "operator confirmation: schema is malformed"
            )

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise OperatorConfirmationStoreError(
                "operator confirmation: database is unavailable"
            )
        return self._connection


def _parse_utc(value: object) -> datetime:
    if type(value) is not str:
        raise OperatorConfirmationStoreError(
            "operator confirmation: record is invalid"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise OperatorConfirmationStoreError(
            "operator confirmation: record is invalid"
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise OperatorConfirmationStoreError(
            "operator confirmation: record is invalid"
        )
    return parsed.astimezone(timezone.utc)
