"""GitHub App preflight and trusted installation-token minting boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Mapping
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class GitHubAppConfigurationError(ValueError):
    """A broker-required setting is absent or violates the security profile."""


_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubAppBrokerError(RuntimeError):
    """The trusted Broker could not mint a short-lived installation token."""


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


@dataclass(frozen=True)
class _InstallationToken:
    """Broker-private credential material; never serialize or return to an agent."""

    value: str
    expires_at: str


class GitHubAppInstallationTokenMinter:
    """Trusted-only GitHub App token exchange using a private-key file reference."""

    def __init__(self, config: GitHubAppBrokerConfig, *, post_json=None, now=None) -> None:
        self._config = config
        self._post_json = post_json or _post_json
        self._now = now or (lambda: datetime.now(timezone.utc))

    def mint(self, credential_grant: Mapping[str, object]) -> _InstallationToken:
        if credential_grant.get("credential_class") != "github-app-installation":
            raise GitHubAppBrokerError("GitHub App token requires a github-app installation grant")
        if credential_grant.get("installation_id") != self._config.installation_id:
            raise GitHubAppBrokerError("GitHub App installation does not match the credential grant")
        token_response = self._post_json(
            urljoin(self._config.api_url + "/", f"app/installations/{self._config.installation_id}/access_tokens"),
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._app_jwt()}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            {
                "repositories": [self._config.repository],
                "permissions": _github_permissions(credential_grant.get("permissions")),
            },
        )
        token = token_response.get("token")
        expires_at = token_response.get("expires_at")
        if not isinstance(token, str) or not token or not isinstance(expires_at, str) or not expires_at:
            raise GitHubAppBrokerError("GitHub App token response is missing required fields")
        return _InstallationToken(token, expires_at)

    def _app_jwt(self) -> str:
        if shutil.which("openssl") is None:
            raise GitHubAppBrokerError("GitHub App Broker requires openssl for RS256 signing")
        now = self._now()
        header = _base64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = _base64url(json.dumps({
            "iat": int((now - timedelta(seconds=60)).timestamp()),
            "exp": int((now + timedelta(minutes=9)).timestamp()),
            "iss": str(self._config.app_id),
        }, separators=(",", ":")).encode())
        signing_input = f"{header}.{payload}".encode("ascii")
        completed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(self._config.private_key_path)],
            input=signing_input, capture_output=True, timeout=10, check=False,
        )
        if completed.returncode != 0 or not completed.stdout:
            raise GitHubAppBrokerError("GitHub App private-key signing failed")
        return f"{signing_input.decode('ascii')}.{_base64url(completed.stdout)}"


def _github_permissions(raw_permissions: object) -> dict[str, str]:
    if not isinstance(raw_permissions, list) or not raw_permissions:
        raise GitHubAppBrokerError("credential grant must include GitHub permissions")
    permissions: dict[str, str] = {}
    for permission in raw_permissions:
        if not isinstance(permission, str) or permission not in {"contents:write", "pull_requests:write"}:
            raise GitHubAppBrokerError("credential grant contains an unsupported GitHub permission")
        scope, level = permission.split(":", 1)
        permissions[scope] = level
    return permissions


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _post_json(url: str, headers: Mapping[str, str], payload: Mapping[str, object]) -> Mapping[str, object]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={**headers, "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 -- endpoint is validated in config.
            decoded = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise GitHubAppBrokerError("GitHub App token exchange failed") from error
    if not isinstance(decoded, dict):
        raise GitHubAppBrokerError("GitHub App token response must be an object")
    return decoded
