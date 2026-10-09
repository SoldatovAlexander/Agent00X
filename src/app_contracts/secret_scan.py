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


MAX_CANARY_SURFACES = 64
MAX_CANARY_SURFACE_BYTES = 1_000_000
MAX_CANARY_SURFACE_NODES = 100_000
MAX_CANARY_NESTING_DEPTH = 64


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

    A surface that cannot be fully inspected within the fixed byte/node/depth
    limits (cyclic or unsupported data included) is reported as a finding:
    absence can never be proven there. Only surface names are returned, never
    scanned values.
    """

    if type(canary) is not str or not canary:
        raise ValueError("canary must not be empty")
    try:
        canary_bytes = canary.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ValueError("canary must not be empty") from None
    if len(canary_bytes) > MAX_CANARY_SURFACE_BYTES:
        raise ValueError("canary must not be empty")
    if type(surfaces) is not dict:
        raise ValueError("surfaces must be a mapping")
    if len(surfaces) > MAX_CANARY_SURFACES:
        raise ValueError("surface count exceeds limit")
    for name in surfaces:
        if type(name) is not str or not name:
            raise ValueError("surface name must be a non-empty string")
    found: list[str] = []
    for name, value in surfaces.items():
        try:
            contains_canary = _contains_canary_bounded(value, canary, canary_bytes)
        except Exception:
            found.append(name)
            continue
        if contains_canary:
            found.append(name)
    return found


def assert_canary_absent(canary: str, surfaces: Mapping[str, Any]) -> None:
    leaked = find_canary_surfaces(canary, surfaces)
    if leaked:
        raise CredentialLeakDetected("credential canary found")


def _contains_canary_bounded(value: Any, canary: str, canary_bytes: bytes) -> bool:
    """Search JSON-like data without constructing an unbounded serialized copy."""
    stack: list[tuple[Any, int, bool]] = [(value, 0, False)]
    active_containers: set[int] = set()
    visited_nodes = 0
    scanned_bytes = 0

    while stack:
        current, depth, exiting = stack.pop()
        if exiting:
            active_containers.remove(id(current))
            continue
        visited_nodes += 1
        if visited_nodes > MAX_CANARY_SURFACE_NODES or depth > MAX_CANARY_NESTING_DEPTH:
            raise ValueError("surface cannot be scanned within bounds")

        if type(current) is str:
            if len(current) > MAX_CANARY_SURFACE_BYTES - scanned_bytes:
                raise ValueError("surface cannot be scanned within bounds")
            encoded = current.encode("utf-8", errors="strict")
            scanned_bytes += len(encoded)
            if scanned_bytes > MAX_CANARY_SURFACE_BYTES:
                raise ValueError("surface cannot be scanned within bounds")
            if canary in current:
                return True
            continue

        if type(current) is bytes:
            if len(current) > MAX_CANARY_SURFACE_BYTES - scanned_bytes:
                raise ValueError("surface cannot be scanned within bounds")
            scanned_bytes += len(current)
            if canary_bytes in current:
                return True
            continue

        if current is None or type(current) in (bool, int, float):
            encoded = json.dumps(current, allow_nan=False, separators=(",", ":"))
            encoded_size = len(encoded.encode("ascii"))
            if encoded_size > MAX_CANARY_SURFACE_BYTES - scanned_bytes:
                raise ValueError("surface cannot be scanned within bounds")
            scanned_bytes += encoded_size
            if canary in encoded:
                return True
            continue

        if type(current) in (dict, list, tuple):
            child_count = len(current) * (2 if type(current) is dict else 1)
            if child_count > MAX_CANARY_SURFACE_NODES - visited_nodes:
                raise ValueError("surface cannot be scanned within bounds")
            identity = id(current)
            if identity in active_containers:
                raise ValueError("surface cannot be scanned within bounds")
            active_containers.add(identity)
            stack.append((current, depth, True))
            if type(current) is dict:
                children: list[Any] = []
                for key, item in current.items():
                    if type(key) is not str:
                        raise ValueError("surface cannot be scanned within bounds")
                    children.extend((key, item))
                stack.extend((child, depth + 1, False) for child in reversed(children))
            else:
                stack.extend(
                    (child, depth + 1, False) for child in reversed(current)
                )
            continue

        raise ValueError("surface cannot be scanned within bounds")

    return False
