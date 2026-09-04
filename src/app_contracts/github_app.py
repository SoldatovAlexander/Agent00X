"""Fail-closed configuration boundary for the future GitHub App broker.

This module carries metadata only. It neither reads a private key nor mints or
returns a credential, so it is safe to use as a preflight step outside the
trusted broker process.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Mapping
from urllib.parse import urlparse


class GitHubAppConfigurationError(ValueError):
    """A broker-required setting is absent or violates the security profile."""


_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class GitHubAppBrokerConfig:
    app_id: int
    installation_id: int
    repository: str
    private_key_path: Path
    api_url: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "GitHubAppBrokerConfig":
        source = os.environ if environ is None else environ
        app_id = _positive_integer(source, "AGENT_GITHUB_APP_ID")
        installation_id = _positive_integer(source, "AGENT_GITHUB_INSTALLATION_ID")
        repository = _required(source, "AGENT_GITHUB_TEST_REPOSITORY")
        if not _REPOSITORY_PATTERN.fullmatch(repository):
            raise GitHubAppConfigurationError("AGENT_GITHUB_TEST_REPOSITORY must be owner/name")

        key_path = Path(_required(source, "AGENT_GITHUB_PRIVATE_KEY_PATH"))
        if not key_path.is_file():
            raise GitHubAppConfigurationError("AGENT_GITHUB_PRIVATE_KEY_PATH must name an existing regular file")
        if key_path.stat().st_mode & 0o077:
            raise GitHubAppConfigurationError("AGENT_GITHUB_PRIVATE_KEY_PATH must not be readable by group or others")

        api_url = source.get("AGENT_GITHUB_API_URL", "https://api.github.com")
        parsed = urlparse(api_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise GitHubAppConfigurationError("AGENT_GITHUB_API_URL must be an absolute https URL")
        return cls(app_id, installation_id, repository, key_path, api_url.rstrip("/"))


def _required(source: Mapping[str, str], name: str) -> str:
    value = source.get(name, "").strip()
    if not value:
        raise GitHubAppConfigurationError(f"{name} is required")
    return value


def _positive_integer(source: Mapping[str, str], name: str) -> int:
    value = _required(source, name)
    try:
        parsed = int(value)
    except ValueError as error:
        raise GitHubAppConfigurationError(f"{name} must be a positive integer") from error
    if parsed < 1:
        raise GitHubAppConfigurationError(f"{name} must be a positive integer")
    return parsed
