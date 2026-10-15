"""Narrow, platform-neutral protocol for one opaque credential source.

This module contains no storage adapter, operating-system integration, prompt,
environment lookup, or file access. Consumers that need only the contract can
depend on it without importing secret-reading implementations.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class CredentialSourceError(ValueError):
    """A process-injected credential is unavailable or malformed."""


@runtime_checkable
class CredentialSource(Protocol):
    """Callable that supplies one credential only when its consumer needs it."""

    def __call__(self) -> str:
        """Return the credential value without logging or persisting it."""
        ...
