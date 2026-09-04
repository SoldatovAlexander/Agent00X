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
from typing import Any, Mapping
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from .broker import validate_credential_use_grant
from .validator import ContractValidationError


class GitHubAppConfigurationError(ValueError):
    """A broker-required setting is absent or violates the security profile."""


_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubAppBrokerError(RuntimeError):
    """The trusted Broker could not mint a short-lived installation token."""


@dataclass(frozen=True)
class GitHubAppBrokerConfig:
    app_id: int
    installation_id: int
    repository_id: int
    repository: str
    private_key_path: Path
    api_url: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "GitHubAppBrokerConfig":
        source = os.environ if environ is None else environ
        app_id = _positive_integer(source, "AGENT_GITHUB_APP_ID")
        installation_id = _positive_integer(source, "AGENT_GITHUB_INSTALLATION_ID")
        repository_id = _positive_integer(source, "AGENT_GITHUB_REPOSITORY_ID")
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
        return cls(app_id, installation_id, repository_id, repository, key_path, api_url.rstrip("/"))


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


def _get_json(url: str, headers: Mapping[str, str]) -> object:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 -- endpoint is validated in config.
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise GitHubAppBrokerError("GitHub pull-request reconciliation failed") from error


@dataclass(frozen=True)
class GitHubPullRequest:
    pull_request_id: int
    pull_request_url: str
    repository_id: str
    branch: str
    staged_change_digest: str
    idempotency_key: str


class GitHubAppPublicationChannel:
    """Actuator-only channel for one typed GitHub pull-request operation."""

    def __init__(self, config: GitHubAppBrokerConfig, token: _InstallationToken, *, post_json=None, get_json=None) -> None:
        self._config = config
        self._token = token
        self._post_json = post_json or _post_json
        self._get_json = get_json or _get_json

    def publish_pull_request(self, request: dict[str, Any]) -> GitHubPullRequest:
        expected = {"operation", "repository_id", "branch", "staged_change_digest", "idempotency_key", "policy_effect", "approval_valid"}
        if set(request) != expected or request["operation"] != "publish_pull_request":
            raise ContractValidationError("GitHub actuator: request shape or operation is invalid")
        repository_id = f"github-installation/{self._config.installation_id}/repository/{self._config.repository_id}"
        if request["repository_id"] != repository_id:
            raise ContractValidationError("GitHub actuator: request repository is not allowlisted")
        if request["policy_effect"] != "allow" or request["approval_valid"] is not True:
            raise ContractValidationError("GitHub actuator: authority proof is invalid")
        branch = request["branch"]
        if not isinstance(branch, str) or not branch.startswith("agent/process-"):
            raise ContractValidationError("GitHub actuator: branch is outside the agent namespace")
        marker = f"<!-- agent-process-idempotency: {request['idempotency_key']} -->"
        existing = self._find_existing_pull_request(branch, marker)
        if existing is not None:
            return GitHubPullRequest(existing[0], existing[1], repository_id, branch, request["staged_change_digest"], request["idempotency_key"])
        response = self._post_json(
            urljoin(self._config.api_url + "/", f"repos/{self._config.repository}/pulls"),
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token.value}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            {
                "title": f"Agent publication: {branch}",
                "head": branch,
                "base": "main",
                "body": f"Automated publication for staged change `{request['staged_change_digest']}`.\n\n{marker}",
            },
        )
        number, html_url = response.get("number"), response.get("html_url")
        if not isinstance(number, int) or number < 1 or not isinstance(html_url, str) or not html_url.startswith("https://"):
            raise GitHubAppBrokerError("GitHub pull-request response is missing required fields")
        return GitHubPullRequest(number, html_url, repository_id, branch, request["staged_change_digest"], request["idempotency_key"])

    def _find_existing_pull_request(self, branch: str, marker: str) -> tuple[int, str] | None:
        owner = self._config.repository.split("/", 1)[0]
        url = urljoin(
            self._config.api_url + "/",
            f"repos/{self._config.repository}/pulls?state=all&head={quote(f'{owner}:{branch}', safe='')}",
        )
        response = self._get_json(url, self._headers())
        if not isinstance(response, list):
            raise GitHubAppBrokerError("GitHub pull-request reconciliation response must be a list")
        for item in response:
            if not isinstance(item, dict) or marker not in item.get("body", ""):
                continue
            number, html_url = item.get("number"), item.get("html_url")
            if isinstance(number, int) and number > 0 and isinstance(html_url, str) and html_url.startswith("https://"):
                return number, html_url
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token.value}",
            "X-GitHub-Api-Version": "2022-11-28",
        }


class GitHubAppCredentialBroker:
    """Single-use Broker that mints a private token and opens one actuator channel."""

    def __init__(self, config: GitHubAppBrokerConfig, token_minter: GitHubAppInstallationTokenMinter, *, post_json=None, get_json=None) -> None:
        self._config = config
        self._token_minter = token_minter
        self._post_json = post_json
        self._get_json = get_json
        self._used_grants: set[str] = set()

    def open_github_publication_channel(self, credential_grant: dict[str, Any], actuator_request: dict[str, Any]) -> GitHubAppPublicationChannel:
        validate_credential_use_grant(credential_grant, actuator_request)
        grant_id = credential_grant["credential_grant_id"]
        if grant_id in self._used_grants:
            raise ContractValidationError("broker: credential grant already used")
        self._used_grants.add(grant_id)
        return GitHubAppPublicationChannel(self._config, self._token_minter.mint(credential_grant), post_json=self._post_json, get_json=self._get_json)
