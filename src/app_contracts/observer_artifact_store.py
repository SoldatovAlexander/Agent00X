"""Local immutable content-addressed artifacts for the observer prototype.

This store resolves only canonical JSON metadata. It is not a secret vault,
complete redaction proof, workspace snapshotter, or replay engine.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from .digests import canonical_json, sha256_bytes
from .secret_scan import (
    CredentialLeakDetected,
    assert_no_credential_pattern_content,
)


MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_DATABASE_BYTES = 256 * 1024 * 1024
_ARTIFACT_REF = re.compile(r"artifact://sha256/([0-9a-f]{64})\Z")
_JSON_CREDENTIAL_ASSIGNMENT = re.compile(
    rb'(?i)"(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd)"'
    rb'\s*:\s*"[^"\r\n]{8,}"'
)
_TABLES = {"observer_artifacts"}
_COLUMNS = {
    "artifact_ref",
    "content_digest",
    "content_json",
    "content_bytes",
    "classification",
    "redaction_status",
}


class ObserverArtifactStoreError(ValueError):
    """A local observer artifact was invalid or unavailable."""


@dataclass(frozen=True)
class ArtifactResolution:
    """Payload-free evidence for one successfully resolved artifact."""

    artifact_ref: str
    content_digest: str
    content_bytes: int

    def __repr__(self) -> str:
        return (
            "ArtifactResolution(artifact_ref='opaque', "
            f"content_digest={self.content_digest!r}, "
            f"content_bytes={self.content_bytes})"
        )


def _canonical_payload(payload: object) -> tuple[bytes, str]:
    try:
        if type(payload) is not bytes or not 0 < len(payload) <= MAX_ARTIFACT_BYTES:
            raise ValueError
        decoded = json.loads(payload.decode("utf-8", errors="strict"))
        if type(decoded) is not dict or canonical_json(decoded) != payload:
            raise ValueError
        _assert_safe_payload(payload)
        return payload, sha256_bytes(payload)
    except Exception:
        raise ObserverArtifactStoreError(
            "observer artifact store: content rejected"
        ) from None


def _assert_safe_payload(payload: bytes) -> None:
    assert_no_credential_pattern_content((("artifact.json", payload),))
    if _JSON_CREDENTIAL_ASSIGNMENT.search(payload):
        raise CredentialLeakDetected("credential-shaped content detected")


class SQLiteObserverArtifactStore:
    """Append-only SQLite store for redaction-complete canonical JSON objects.

    References are derived from the content digest and cannot be rebound to a
    different payload. Reads re-check the reference, digest, canonical form,
    size and known credential-shaped content before returning metadata or
    bytes. The heuristic scanner is not proof that unknown secrets are absent.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self._connection: sqlite3.Connection | None = None
        self._read_only = read_only
        try:
            if type(read_only) is not bool:
                raise ValueError
            source = Path(path)
            if source.is_symlink():
                raise ValueError
            if read_only:
                source = source.resolve(strict=True)
                if (
                    not source.is_file()
                    or source.stat().st_size > MAX_DATABASE_BYTES
                    or Path(f"{source}-wal").exists()
                    or Path(f"{source}-shm").exists()
                ):
                    raise ValueError
                uri = f"{source.as_uri()}?mode=ro&immutable=1"
                self._connection = sqlite3.connect(uri, uri=True, timeout=1)
                self._connection.execute("PRAGMA query_only = ON")
            else:
                if source.exists() and (
                    not source.is_file()
                    or source.stat().st_size > MAX_DATABASE_BYTES
                ):
                    raise ValueError
                self._connection = sqlite3.connect(source, timeout=1)
            self._connection.row_factory = sqlite3.Row
            self._initialize_schema()
            self._validate_persisted_rows()
        except Exception:
            self.close()
            raise ObserverArtifactStoreError(
                "observer artifact store: database unavailable"
            ) from None

    def __repr__(self) -> str:
        return "SQLiteObserverArtifactStore(content='opaque')"

    @property
    def read_only(self) -> bool:
        """Whether this instance was opened with SQLite query-only access."""

        return self._read_only and self._connection is not None

    def _initialize_schema(self) -> None:
        assert self._connection is not None
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
        if version == 0 and not tables and not self._read_only:
            with self._connection:
                self._connection.execute(
                    """CREATE TABLE observer_artifacts (
                        artifact_ref TEXT PRIMARY KEY,
                        content_digest TEXT NOT NULL,
                        content_json BLOB NOT NULL,
                        content_bytes INTEGER NOT NULL,
                        classification TEXT NOT NULL,
                        redaction_status TEXT NOT NULL
                    )"""
                )
                self._connection.execute(
                    "CREATE TRIGGER observer_artifacts_no_update "
                    "BEFORE UPDATE ON observer_artifacts "
                    "BEGIN SELECT RAISE(ABORT, 'immutable artifact'); END"
                )
                self._connection.execute(
                    "CREATE TRIGGER observer_artifacts_no_delete "
                    "BEFORE DELETE ON observer_artifacts "
                    "BEGIN SELECT RAISE(ABORT, 'immutable artifact'); END"
                )
                self._connection.execute(
                    f"PRAGMA user_version = {self.SCHEMA_VERSION}"
                )
            return
        if version != self.SCHEMA_VERSION or tables != _TABLES:
            raise ValueError
        columns = {
            row[1]
            for row in self._connection.execute(
                "PRAGMA table_info(observer_artifacts)"
            )
        }
        if columns != _COLUMNS:
            raise ValueError
        triggers = {
            row[0]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        if triggers != {"observer_artifacts_no_update", "observer_artifacts_no_delete"}:
            raise ValueError

    def _validate_record(
        self, artifact_ref: object, content_digest: object, content: object,
        content_bytes: object, classification: object, redaction_status: object,
    ) -> ArtifactResolution:
        match = _ARTIFACT_REF.fullmatch(artifact_ref) if type(artifact_ref) is str else None
        if (
            match is None
            or type(content_digest) is not str
            or content_digest != f"sha256:{match.group(1)}"
            or type(content) is not bytes
            or type(content_bytes) is not int
            or content_bytes != len(content)
            or not 0 < content_bytes <= MAX_ARTIFACT_BYTES
            or type(classification) is not str
            or classification not in {"public", "internal"}
            or type(redaction_status) is not str
            or redaction_status != "complete"
            or sha256_bytes(content) != content_digest
        ):
            raise ValueError
        payload = json.loads(content.decode("utf-8", errors="strict"))
        if type(payload) is not dict or canonical_json(payload) != content:
            raise ValueError
        _assert_safe_payload(content)
        return ArtifactResolution(artifact_ref, content_digest, content_bytes)

    def _validate_persisted_rows(self) -> None:
        assert self._connection is not None
        try:
            for row in self._connection.execute(
                "SELECT artifact_ref, content_digest, content_json, content_bytes, "
                "classification, redaction_status "
                "FROM observer_artifacts ORDER BY artifact_ref"
            ):
                self._validate_record(
                    row["artifact_ref"], row["content_digest"],
                    row["content_json"], row["content_bytes"],
                    row["classification"], row["redaction_status"],
                )
        except Exception:
            raise ValueError from None

    def put_json(
        self,
        payload: object,
        *,
        classification: object,
        redaction_status: object,
    ) -> ArtifactResolution:
        """Store one redaction-complete public/internal object exactly once."""

        if (
            self._read_only
            or type(classification) is not str
            or classification not in {"public", "internal"}
            or type(redaction_status) is not str
            or redaction_status != "complete"
        ):
            raise ObserverArtifactStoreError(
                "observer artifact store: write policy refused"
            )
        encoded, digest = _canonical_payload(payload)
        reference = f"artifact://sha256/{digest.removeprefix('sha256:')}"
        try:
            assert self._connection is not None
            with self._connection:
                existing = self._connection.execute(
                    "SELECT artifact_ref, content_digest, content_json, content_bytes, "
                    "classification, redaction_status "
                    "FROM observer_artifacts WHERE artifact_ref = ?",
                    (reference,),
                ).fetchone()
                if existing is None:
                    self._connection.execute(
                        "INSERT INTO observer_artifacts "
                        "(artifact_ref, content_digest, content_json, content_bytes, "
                        "classification, redaction_status) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            reference,
                            digest,
                            encoded,
                            len(encoded),
                            classification,
                            redaction_status,
                        ),
                    )
                else:
                    self._validate_record(
                        existing["artifact_ref"], existing["content_digest"],
                        existing["content_json"], existing["content_bytes"],
                        existing["classification"], existing["redaction_status"],
                    )
                    if (
                        existing["classification"] != classification
                        or existing["redaction_status"] != redaction_status
                    ):
                        raise ObserverArtifactStoreError(
                            "observer artifact store: write policy refused"
                        )
            return ArtifactResolution(reference, digest, len(encoded))
        except ObserverArtifactStoreError:
            raise
        except Exception:
            raise ObserverArtifactStoreError(
                "observer artifact store: write failed"
            ) from None

    def read_json(self, artifact_ref: object) -> bytes:
        """Read one exact artifact after rechecking all content bindings."""

        if type(artifact_ref) is not str or _ARTIFACT_REF.fullmatch(artifact_ref) is None:
            raise ObserverArtifactStoreError(
                "observer artifact store: reference unavailable"
            )
        try:
            assert self._connection is not None
            row = self._connection.execute(
                "SELECT artifact_ref, content_digest, content_json, content_bytes, "
                "classification, redaction_status "
                "FROM observer_artifacts WHERE artifact_ref = ?",
                (artifact_ref,),
            ).fetchone()
            if row is None:
                raise ValueError
            self._validate_record(
                row["artifact_ref"], row["content_digest"],
                row["content_json"], row["content_bytes"],
                row["classification"], row["redaction_status"],
            )
            return bytes(row["content_json"])
        except Exception:
            raise ObserverArtifactStoreError(
                "observer artifact store: reference unavailable"
            ) from None

    def resolve(self, artifact_ref: object) -> ArtifactResolution:
        """Resolve without returning or rendering the artifact payload."""

        content = self.read_json(artifact_ref)
        match = _ARTIFACT_REF.fullmatch(artifact_ref)
        assert match is not None
        return ArtifactResolution(
            artifact_ref=artifact_ref,
            content_digest=f"sha256:{match.group(1)}",
            content_bytes=len(content),
        )

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()

    def __enter__(self) -> SQLiteObserverArtifactStore:
        if self._connection is None:
            raise ObserverArtifactStoreError(
                "observer artifact store: database unavailable"
            )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
