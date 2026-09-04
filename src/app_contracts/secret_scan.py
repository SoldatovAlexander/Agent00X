"""Canary credential scanning for agent-visible and persisted surfaces."""

from __future__ import annotations

import json
from typing import Any, Mapping


class CredentialLeakDetected(RuntimeError):
    pass


def find_canary_surfaces(canary: str, surfaces: Mapping[str, Any]) -> list[str]:
    """Return the names of surfaces containing an exact canary value."""

    if not canary:
        raise ValueError("canary must not be empty")
    return [name for name, value in surfaces.items() if canary in _serialize(value)]


def assert_canary_absent(canary: str, surfaces: Mapping[str, Any]) -> None:
    leaked = find_canary_surfaces(canary, surfaces)
    if leaked:
        raise CredentialLeakDetected(f"credential canary found in surfaces: {', '.join(leaked)}")


def _serialize(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
