"""Canary credential scanning for agent-visible and persisted surfaces."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .pinned_snapshot import (
    MAX_SNAPSHOT_FILE_BYTES,
    MAX_SNAPSHOT_FILES,
    MAX_SNAPSHOT_PATH_BYTES,
    MAX_SNAPSHOT_TOTAL_BYTES,
)


class CredentialLeakDetected(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CredentialPatternFinding:
    """Redacted heuristic finding; never stores or exposes the matched bytes."""

    path: str
    rule_id: str


_CONTENT_RULES: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    (
        "github-token",
        re.compile(rb"(?:gh[pousr]_[A-Za-z0-9_]{20,255}|github_pat_[A-Za-z0-9_]{20,255})"),
    ),
    ("aws-access-key", re.compile(rb"AKIA[0-9A-Z]{16}")),
    (
        "private-key-pem",
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "credential-assignment",
        re.compile(
            rb"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd)"
            rb"\s*[:=]\s*['\"][^'\"\r\n]{8,}['\"]"
        ),
    ),
)


def find_credential_pattern_content(
    files: object,
) -> tuple[CredentialPatternFinding, ...]:
    """Find common credential-shaped source bytes without returning values.

    This bounded heuristic catches selected known formats only. An empty result
    is not proof that source content contains no credentials or secrets.
    """

    if type(files) is not tuple or len(files) > MAX_SNAPSHOT_FILES:
        raise ValueError("credential content input is invalid")
    findings: list[CredentialPatternFinding] = []
    previous_path: str | None = None
    total_bytes = 0
    for record in files:
        if (
            type(record) is not tuple
            or len(record) != 2
            or type(record[0]) is not str
            or type(record[1]) is not bytes
        ):
            raise ValueError("credential content input is invalid")
        path, content = record
        try:
            path_bytes = path.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise ValueError("credential content input is invalid") from None
        parts = path.split("/")
        if (
            not path
            or path != path.strip()
            or len(path_bytes) > MAX_SNAPSHOT_PATH_BYTES
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in parts)
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
            or (previous_path is not None and path <= previous_path)
            or len(content) > MAX_SNAPSHOT_FILE_BYTES
        ):
            raise ValueError("credential content input is invalid")
        previous_path = path
        total_bytes += len(content)
        if total_bytes > MAX_SNAPSHOT_TOTAL_BYTES:
            raise ValueError("credential content input is invalid")
        for rule_id, pattern in _CONTENT_RULES:
            if pattern.search(content):
                findings.append(CredentialPatternFinding(path, rule_id))
    return tuple(findings)


def assert_no_credential_pattern_content(files: object) -> None:
    """Fail closed on known credential-shaped content without exposing it."""

    if find_credential_pattern_content(files):
        raise CredentialLeakDetected("credential-shaped content detected")


def find_canary_surfaces(canary: str, surfaces: Mapping[str, Any]) -> list[str]:
    """Return the names of surfaces containing an exact canary value.

    A surface that cannot be serialized (cyclic, unbounded, or otherwise
    unsupported) is reported as a finding: absence can never be proven
    there, so fail-closed suspicion replaces silent traversal or a raw
    exception. Only surface names are reported, never scanned values.
    """

    if not isinstance(canary, str) or not canary:
        raise ValueError("canary must not be empty")
    if not isinstance(surfaces, dict):
        raise ValueError("surfaces must be a mapping")
    for name in surfaces:
        if not isinstance(name, str) or not name:
            raise ValueError("surface name must be a non-empty string")
    found: list[str] = []
    for name, value in surfaces.items():
        try:
            serialized = _serialize(value)
        except Exception:
            found.append(name)
            continue
        if canary in serialized:
            found.append(name)
    return found


def assert_canary_absent(canary: str, surfaces: Mapping[str, Any]) -> None:
    leaked = find_canary_surfaces(canary, surfaces)
    if leaked:
        raise CredentialLeakDetected("credential canary found")


def _serialize(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
