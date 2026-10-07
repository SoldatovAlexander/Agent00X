"""Platform-neutral, least-authority source for one opaque credential.

Implementations may later bridge to an operating-system vault. The core
contract deliberately knows nothing about a particular OS, environment
variables, files, or credential storage. A source instance is scoped to one
credential so a consumer does not receive a general-purpose vault capability.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol, runtime_checkable


_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")


class CredentialSourceError(ValueError):
    """A process-injected credential is unavailable or malformed."""


@runtime_checkable
class CredentialSource(Protocol):
    """Callable that supplies one credential only when its consumer needs it."""

    def __call__(self) -> str:
        """Return the credential value without logging or persisting it."""
        ...


class ProcessEnvironmentCredentialSource:
    """Lazily read exactly one value from an explicitly supplied mapping.

    The mapping must be provided by a trusted outer runtime (for example,
    after an approved secret manager injects a short-lived process variable).
    This adapter does not read the ambient environment, parse files, or provide
    encrypted storage or process isolation.
    """

    __slots__ = ("_environment", "_name")

    def __init__(self, environment: Mapping[str, str], name: str) -> None:
        if (
            not isinstance(environment, Mapping)
            or type(name) is not str
            or _ENVIRONMENT_NAME.fullmatch(name) is None
        ):
            raise CredentialSourceError("credential source: configuration is invalid")
        self._environment = environment
        self._name = name

    def __repr__(self) -> str:
        return "ProcessEnvironmentCredentialSource(value='opaque')"

    __str__ = __repr__

    def __call__(self) -> str:
        try:
            value = self._environment[self._name]
        except Exception:
            raise CredentialSourceError("credential source: value is unavailable") from None
        if type(value) is not str or not value or value != value.strip():
            raise CredentialSourceError("credential source: value is invalid")
        return value


class TerminalPromptCredentialSource:
    """Lazily request one credential using hidden standard-library terminal input.

    The default reader rejects ``getpass``'s insecure echo fallback. Tests can
    patch the standard-library reader to return synthetic values. This source
    does not persist or erase the returned Python string and does not provide
    process-memory isolation.
    """

    __slots__ = ()

    _PROMPT = "API credential (input hidden): "

    def __repr__(self) -> str:
        return "TerminalPromptCredentialSource(value='opaque')"

    __str__ = __repr__

    def __call__(self) -> str:
        try:
            import getpass
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = getpass.getpass(self._PROMPT)
        except Exception:
            raise CredentialSourceError(
                "credential source: secure input unavailable"
            ) from None
        if type(value) is not str or not value or value != value.strip():
            raise CredentialSourceError("credential source: value is invalid")
        return value
