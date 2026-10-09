"""Platform-neutral, least-authority source for one opaque credential.

Implementations may later bridge to an operating-system vault. The core
contract deliberately knows nothing about a particular OS, environment
variables, files, or credential storage. A source instance is scoped to one
credential so a consumer does not receive a general-purpose vault capability.
"""

from __future__ import annotations

import importlib
import re
import sys
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


class NativeKeyringCredentialSource:
    """Lazily read one secret from the OS-native credential manager.

    This prototype never provisions, copies, or persists credentials itself.
    It explicitly constructs one allowlisted native backend for the current OS
    instead of accepting keyring's automatic backend selection or fallback.
    The optional ``keyring`` package must be installed by the operator. Only
    the returned secret value is held by the caller, in process memory.
    """

    __slots__ = ()

    SERVICE_NAME = "Agent00X"
    ACCOUNT_NAME = "AI_PROCESS_API"
    _BACKENDS = {
        "darwin": ("keyring.backends.macOS", "Keyring"),
        "win32": ("keyring.backends.Windows", "WinVaultKeyring"),
        "linux": ("keyring.backends.SecretService", "Keyring"),
    }

    def __repr__(self) -> str:
        return "NativeKeyringCredentialSource(value='opaque')"

    __str__ = __repr__

    @classmethod
    def _open_backend(cls):
        backend_spec = cls._BACKENDS.get(sys.platform)
        if backend_spec is None:
            raise CredentialSourceError(
                "credential source: secure manager unavailable"
            )
        try:
            module_name, class_name = backend_spec
            module = importlib.import_module(module_name)
            backend_type = getattr(module, class_name)
            backend = backend_type()
            priority = backend.priority
            if (
                isinstance(priority, bool)
                or not isinstance(priority, (int, float))
                or priority <= 0
            ):
                raise ValueError
            return backend
        except Exception:
            raise CredentialSourceError(
                "credential source: secure manager unavailable"
            ) from None

    def manager_available(self) -> bool:
        """Check native backend readiness without looking up a credential."""
        try:
            self._open_backend()
            return True
        except CredentialSourceError:
            return False

    def __call__(self) -> str:
        backend = self._open_backend()
        try:
            value = backend.get_password(self.SERVICE_NAME, self.ACCOUNT_NAME)
        except Exception:
            raise CredentialSourceError(
                "credential source: value is unavailable"
            ) from None
        if type(value) is not str or not value or value != value.strip():
            raise CredentialSourceError("credential source: value is invalid")
        return value
