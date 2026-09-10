"""Canary credential scanning for agent-visible and persisted surfaces."""

from __future__ import annotations

import json
from typing import Any, Mapping


class CredentialLeakDetected(RuntimeError):
    pass


def find_canary_surfaces(canary: str, surfaces: Mapping[str, Any]) -> list[str]:
    """Return the names of surfaces containing an exact canary value.

    A surface that cannot be serialized (cyclic, unbounded, or otherwise
    unsupported) is reported as a finding: absence can never be proven
    there, so fail-closed suspicion replaces silent traversal or a raw
    exception. Only surface names are reported, never scanned values.
    """

    if not canary:
        raise ValueError("canary must not be empty")
    for name in surfaces:
        if not isinstance(name, str):
            raise ValueError("surface name must be a string")
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
        raise CredentialLeakDetected(f"credential canary found in surfaces: {', '.join(leaked)}")


def _serialize(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
