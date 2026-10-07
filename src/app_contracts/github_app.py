"""GitHub App preflight and trusted installation-token minting boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from .broker import _register_github_app_types, validate_credential_use_grant
from .digests import sha256_bytes, sha256_digest
from .publication_seed import publication_idempotency_key, validate_publication_base_branch
from .repository_binding import RepositoryTargetBinding, provider_repository_id
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

    @property
    def repository_target_binding(self) -> RepositoryTargetBinding:
        return RepositoryTargetBinding(
            source_repository_id=self.repository,
            provider_repository_id=provider_repository_id(
                self.installation_id, self.repository_id
            ),
        )

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "GitHubAppBrokerConfig":
        source = os.environ if environ is None else environ
        if not isinstance(source, Mapping):
            raise GitHubAppConfigurationError("configuration source is invalid")
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
        if not isinstance(api_url, str):
            raise GitHubAppConfigurationError("AGENT_GITHUB_API_URL must be an absolute https URL")
        parsed = urlparse(api_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise GitHubAppConfigurationError("AGENT_GITHUB_API_URL must be an absolute https URL")
        return cls(app_id, installation_id, repository_id, repository, key_path, api_url.rstrip("/"))


def _required(source: Mapping[str, str], name: str) -> str:
    value = source.get(name, "")
    if not isinstance(value, str) or not value.strip():
        raise GitHubAppConfigurationError(f"{name} is required")
    return value.strip()


def _positive_integer(source: Mapping[str, str], name: str) -> int:
    value = _required(source, name)
    try:
        parsed = int(value)
    except ValueError as error:
        raise GitHubAppConfigurationError(f"{name} must be a positive integer") from error
    if parsed < 1:
        raise GitHubAppConfigurationError(f"{name} must be a positive integer")
    return parsed


def _git_blob_sha(content: str) -> str:
    """Return GitHub's SHA-1 blob identity for UTF-8 text content."""
    encoded = content.encode("utf-8")
    header = f"blob {len(encoded)}\0".encode("ascii")
    return hashlib.sha1(header + encoded).hexdigest()


@dataclass(frozen=True)
class _InstallationToken:
    """Broker-private credential material; never serialize or return to an agent."""

    value: str
    expires_at: str


class GitHubAppInstallationTokenMinter:
    """Trusted-only GitHub App token exchange using a private-key file reference."""

    def __init__(self, config: GitHubAppBrokerConfig, *, post_json=None, now=None) -> None:
        self._config = config
        if post_json is not None and not callable(post_json):
            raise GitHubAppBrokerError("GitHub App post transport is invalid")
        if now is not None and not callable(now):
            raise GitHubAppBrokerError("GitHub App clock is invalid")
        self._post_json = post_json or _post_json
        self._now = now or (lambda: datetime.now(timezone.utc))

    def mint(self, credential_grant: Mapping[str, object]) -> _InstallationToken:
        if not isinstance(credential_grant, dict):
            raise GitHubAppBrokerError("GitHub App credential grant is malformed")
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
                "repositories": [self._config.repository.split("/", 1)[1]],
                "permissions": _github_permissions(credential_grant.get("permissions")),
            },
        )
        if not isinstance(token_response, dict):
            raise GitHubAppBrokerError("GitHub App token response must be an object")
        token = token_response.get("token")
        expires_at = token_response.get("expires_at")
        if not isinstance(token, str) or not token or not isinstance(expires_at, str) or not expires_at:
            raise GitHubAppBrokerError("GitHub App token response is missing required fields")
        try:
            parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise GitHubAppBrokerError("GitHub App token expiry is invalid") from exc
        if parsed_expiry.tzinfo is None:
            raise GitHubAppBrokerError("GitHub App token expiry is invalid")
        now = self._now()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise GitHubAppBrokerError("GitHub App clock is invalid")
        if parsed_expiry <= now.astimezone(timezone.utc):
            raise GitHubAppBrokerError("GitHub App token is expired")
        return _InstallationToken(token, expires_at)

    def _app_jwt(self) -> str:
        if shutil.which("openssl") is None:
            raise GitHubAppBrokerError("GitHub App Broker requires openssl for RS256 signing")
        now = self._now()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise GitHubAppBrokerError("GitHub App clock is invalid")
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
        if not isinstance(permission, str) or permission not in {
            "contents:read", "pull_requests:read",
            "contents:write", "pull_requests:write",
        }:
            raise GitHubAppBrokerError("credential grant contains an unsupported GitHub permission")
        scope, level = permission.split(":", 1)
        permissions[scope] = level
    if len(permissions) != len(raw_permissions):
        raise GitHubAppBrokerError("credential grant contains duplicate GitHub permissions")
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
    except HTTPError as error:
        if error.code == 404:
            # A confirmed 404 is the only production signal for an absent
            # resource. It maps to FileNotFoundError so read-only
            # reconciliation can distinguish absent from unknown.
            raise FileNotFoundError(f"GitHub resource not found: {url}") from error
        raise GitHubAppBrokerError("GitHub pull-request reconciliation failed") from error
    except Exception as error:
        raise GitHubAppBrokerError("GitHub pull-request reconciliation failed") from error


def _put_json(url: str, headers: Mapping[str, str], payload: Mapping[str, object]) -> Mapping[str, object]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={**headers, "Content-Type": "application/json"}, method="PUT")
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 -- endpoint is validated in config.
            decoded = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise GitHubAppBrokerError("GitHub verified-file publication failed") from error
    if not isinstance(decoded, dict):
        raise GitHubAppBrokerError("GitHub verified-file response must be an object")
    return decoded


@dataclass(frozen=True)
class GitHubPullRequest:
    pull_request_id: int
    pull_request_url: str
    repository_id: str
    branch: str
    staged_change_digest: str
    idempotency_key: str
    base_branch: str = ""


class GitHubAppPublicationChannel:
    """Actuator-only channel for one typed GitHub pull-request operation."""

    def __init__(self, config: GitHubAppBrokerConfig, token: _InstallationToken, *, post_json=None, get_json=None, put_json=None) -> None:
        if not isinstance(config, GitHubAppBrokerConfig):
            raise ContractValidationError("GitHub actuator: channel config is invalid")
        if not isinstance(token, _InstallationToken):
            raise ContractValidationError("GitHub actuator: channel token is invalid")
        for name, transport in (("post_json", post_json), ("get_json", get_json), ("put_json", put_json)):
            if transport is not None and not callable(transport):
                raise ContractValidationError("GitHub actuator: injected transport is not callable")
        self._config = config
        self._token = token
        self._post_json = post_json or _post_json
        self._get_json = get_json or _get_json
        self._put_json = put_json or _put_json
        self._file_reconciliation_required: set[str] = set()

    def reconcile_branch(self, branch: str) -> bool | None:
        """Read-only check whether the scoped branch already exists.

        Returns True when the branch exists, False only on a confirmed
        absent signal (HTTP 404 surfaced as FileNotFoundError), and None
        when the outcome is unknown (transport failure, ``None`` payload,
        or any malformed shape). A None result must be resolved before any
        retry; it never implies permission to repeat a side effect blindly.
        """

        state, _commit_sha = self._read_branch_reference(branch)
        return state

    def _read_branch_reference(self, branch: str) -> tuple[bool | None, str | None]:
        if not isinstance(branch, str) or not branch.startswith("agent/process-") or len(branch) <= len("agent/process-"):
            raise ContractValidationError("GitHub actuator: branch is outside the agent namespace")
        url = urljoin(self._config.api_url + "/", f"repos/{self._config.repository}/git/ref/heads/{quote(branch, safe='')}")
        try:
            response = self._get_json(url, self._headers())
        except FileNotFoundError:
            return False, None
        except HTTPError as error:
            if error.code == 404:
                return False, None
            return None, None
        except Exception:
            return None, None
        reference = response.get("object") if isinstance(response, dict) else None
        commit_sha = reference.get("sha") if isinstance(reference, dict) else None
        if (
            isinstance(response, dict)
            and response.get("ref") == f"refs/heads/{branch}"
            and isinstance(reference, dict)
            and reference.get("type") == "commit"
            and isinstance(commit_sha, str)
            and re.fullmatch(r"[0-9a-f]{40}", commit_sha)
        ):
            return True, commit_sha
        return None, None

    def reconcile_pull_request(
        self, *, branch: str, base_branch: str, idempotency_key: str,
        staged_change_digest: str = "",
    ) -> GitHubPullRequest | None:
        """Read-only lookup of an existing pull request by idempotency marker.

        Returns the existing receipt, or None when no matching pull request
        is known. None is an explicit unknown outcome, not a missing receipt.
        """

        if not isinstance(branch, str) or not branch.startswith("agent/process-") or len(branch) <= len("agent/process-"):
            raise ContractValidationError("GitHub actuator: branch is outside the agent namespace")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ContractValidationError("GitHub actuator: idempotency key is invalid")
        try:
            validate_publication_base_branch(base_branch)
        except Exception:
            raise ContractValidationError("GitHub actuator: base branch is invalid") from None
        if not isinstance(staged_change_digest, str):
            raise ContractValidationError("GitHub actuator: staged change digest is invalid")
        if (
            re.fullmatch(r"sha256:[0-9a-f]{64}", staged_change_digest) is None
            or idempotency_key
            != publication_idempotency_key(branch, base_branch, staged_change_digest)
        ):
            raise ContractValidationError("GitHub actuator: idempotency key does not match publication intent")
        repository_id = f"github-installation/{self._config.installation_id}/repository/{self._config.repository_id}"
        marker = f"<!-- agent-process-idempotency: {idempotency_key} -->"
        try:
            found = self._find_existing_pull_request(branch, base_branch, marker)
        except Exception:
            return None
        if found is None:
            return None
        number, html_url = found
        return GitHubPullRequest(number, html_url, repository_id, branch, staged_change_digest, idempotency_key, base_branch)

    def find_by_idempotency_key(
        self, idempotency_key: str, *, repository_id: str | None = None,
        base_branch: str | None = None,
    ) -> GitHubPullRequest | None:
        """Read-only journal recovery lookup for the canonical PR key."""
        expected_base_branch = base_branch
        if not isinstance(idempotency_key, str):
            raise ContractValidationError("GitHub actuator: idempotency key is invalid")
        parts = idempotency_key.split("/")
        if (
            len(parts) != 4
            or parts[0] != "publish"
            or not re.fullmatch(r"[A-Za-z0-9._%~-]+", parts[1])
            or not re.fullmatch(r"[A-Za-z0-9._%~-]+", parts[2])
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", parts[3])
        ):
            raise ContractValidationError("GitHub actuator: idempotency key is not canonical")
        branch_suffix = unquote(parts[1])
        parsed_base_branch = unquote(parts[2])
        if quote(branch_suffix, safe="") != parts[1] or quote(parsed_base_branch, safe="") != parts[2]:
            raise ContractValidationError("GitHub actuator: idempotency key is not canonical")
        branch = f"agent/{branch_suffix}"
        try:
            validate_publication_base_branch(parsed_base_branch)
        except Exception:
            raise ContractValidationError("GitHub actuator: idempotency key is not canonical") from None
        if expected_base_branch is not None and expected_base_branch != parsed_base_branch:
            raise ContractValidationError("GitHub actuator: lookup base branch conflicts with idempotency key")
        expected_repository_id = f"github-installation/{self._config.installation_id}/repository/{self._config.repository_id}"
        if repository_id is not None and repository_id != expected_repository_id:
            raise ContractValidationError("GitHub actuator: lookup repository is not allowlisted")
        return self.reconcile_pull_request(
            branch=branch,
            idempotency_key=idempotency_key,
            base_branch=parsed_base_branch,
            staged_change_digest=parts[3],
        )

    def publish_verified_files(self, *, branch: str, staged_change: Mapping[str, object], files: Sequence[object]) -> str:
        """Create a scoped branch and publish only files exported from a verified manifest."""

        if not isinstance(staged_change, dict):
            raise ContractValidationError("GitHub actuator: staged change is invalid")
        if not isinstance(files, (list, tuple)) or not files:
            raise ContractValidationError("GitHub actuator: verified publish manifest is empty")
        repository_id = f"github-installation/{self._config.installation_id}/repository/{self._config.repository_id}"
        if staged_change.get("repository_id") != repository_id:
            raise ContractValidationError("GitHub actuator: staged change repository is not allowlisted")
        base_commit = staged_change.get("base_commit")
        patch_digest = staged_change.get("patch_digest")
        if not isinstance(base_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", base_commit):
            raise ContractValidationError("GitHub actuator: staged change base commit is invalid")
        if not isinstance(patch_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", patch_digest):
            raise ContractValidationError("GitHub actuator: staged change patch digest is invalid")
        if not isinstance(branch, str) or not branch.startswith("agent/process-") or len(branch) <= len("agent/process-"):
            raise ContractValidationError("GitHub actuator: branch is outside the agent namespace")
        if branch in self._file_reconciliation_required:
            raise GitHubAppBrokerError("GitHub verified-file reconciliation required before retry")
        validated: list[tuple[str, str]] = []
        for file in files:
            path, content, content_digest = getattr(file, "path", None), getattr(file, "content", None), getattr(file, "content_digest", None)
            if not isinstance(path, str) or not path or path != path.strip() or path.startswith("/") or ".." in path.split("/"):
                raise ContractValidationError("GitHub actuator: manifest path is unsafe")
            if not isinstance(content, str) or not isinstance(content_digest, str) or sha256_bytes(content.encode("utf-8")) != content_digest:
                raise ContractValidationError("GitHub actuator: manifest content digest mismatch")
            validated.append((path, content))
        seen_paths: set[str] = set()
        for manifest_path, _manifest_content in validated:
            if manifest_path in seen_paths:
                raise ContractValidationError("GitHub actuator: manifest contains duplicate path")
            seen_paths.add(manifest_path)

        # The Contents API requires the current blob SHA when replacing an
        # existing file. Read that identity from the exact approved base commit,
        # never from a mutable default branch or the candidate branch.
        base_blob_shas: dict[str, str] = {}
        for path, _content in validated:
            url = urljoin(
                self._config.api_url + "/",
                f"repos/{self._config.repository}/contents/{quote(path)}?ref={quote(base_commit, safe='')}",
            )
            try:
                metadata = self._get_json(url, self._headers())
            except Exception:
                raise GitHubAppBrokerError("GitHub base-file reconciliation failed") from None
            blob_sha = metadata.get("sha") if isinstance(metadata, dict) else None
            if (
                not isinstance(metadata, dict)
                or metadata.get("type") != "file"
                or not isinstance(blob_sha, str)
                or not re.fullmatch(r"[0-9a-f]{40}", blob_sha)
            ):
                raise GitHubAppBrokerError("GitHub base-file metadata is invalid")
            base_blob_shas[path] = blob_sha

        branch_state, branch_commit_sha = self._read_branch_reference(branch)
        if branch_state is None:
            raise GitHubAppBrokerError("GitHub branch outcome unknown; reconcile before retry")
        if branch_state is False:
            self._post_json(urljoin(self._config.api_url + "/", f"repos/{self._config.repository}/git/refs"), self._headers(), {"ref": f"refs/heads/{branch}", "sha": base_commit})
            branch_commit_sha = base_commit

        files_to_update: list[tuple[str, str]] = []
        if branch_state is True:
            for path, content in validated:
                url = urljoin(
                    self._config.api_url + "/",
                    f"repos/{self._config.repository}/contents/{quote(path)}?ref={quote(branch, safe='')}",
                )
                try:
                    current = self._get_json(url, self._headers())
                except Exception:
                    raise GitHubAppBrokerError("GitHub branch-file reconciliation failed") from None
                current_sha = current.get("sha") if isinstance(current, dict) else None
                if (
                    not isinstance(current, dict)
                    or current.get("type") != "file"
                    or not isinstance(current_sha, str)
                    or not re.fullmatch(r"[0-9a-f]{40}", current_sha)
                ):
                    raise GitHubAppBrokerError("GitHub branch-file metadata is invalid")
                if current_sha == _git_blob_sha(content):
                    continue
                if current_sha != base_blob_shas[path]:
                    raise GitHubAppBrokerError("GitHub branch-file state conflicts with staged base")
                files_to_update.append((path, content))
        else:
            files_to_update = list(validated)

        commit_sha = branch_commit_sha
        for path, content in files_to_update:
            try:
                response = self._put_json(urljoin(self._config.api_url + "/", f"repos/{self._config.repository}/contents/{quote(path)}"), self._headers(), {"message": f"Apply verified staged change {patch_digest}", "content": base64.b64encode(content.encode("utf-8")).decode("ascii"), "branch": branch, "sha": base_blob_shas[path]})
                commit = response.get("commit")
                if not isinstance(commit, dict) or not isinstance(commit.get("sha"), str):
                    raise GitHubAppBrokerError("GitHub verified-file response is missing commit SHA")
            except Exception as error:
                self._file_reconciliation_required.add(branch)
                if isinstance(error, GitHubAppBrokerError):
                    raise
                raise GitHubAppBrokerError("GitHub verified-file publication failed") from error
            commit_sha = commit["sha"]
        return commit_sha

    def reconcile_verified_files(
        self, *, branch: str, files: Sequence[object],
    ) -> str | None:
        """Confirm an exact manifest on an existing branch using GETs only.

        A commit SHA is returned only when every path is a regular file whose
        Git blob SHA matches the supplied verified content. Missing, partial,
        malformed, conflicting, or transport-unknown state returns None.
        """
        if (
            not isinstance(branch, str)
            or not branch.startswith("agent/process-")
            or len(branch) <= len("agent/process-")
            or not isinstance(files, (list, tuple))
            or not files
        ):
            raise ContractValidationError("GitHub actuator: verified-file reconciliation input is invalid")
        validated: list[tuple[str, str]] = []
        seen_paths: set[str] = set()
        for file in files:
            path = getattr(file, "path", None)
            content = getattr(file, "content", None)
            content_digest = getattr(file, "content_digest", None)
            if (
                not isinstance(path, str)
                or not path
                or path != path.strip()
                or path.startswith("/")
                or ".." in path.split("/")
                or path in seen_paths
                or not isinstance(content, str)
                or not isinstance(content_digest, str)
                or sha256_bytes(content.encode("utf-8")) != content_digest
            ):
                raise ContractValidationError("GitHub actuator: verified-file reconciliation input is invalid")
            seen_paths.add(path)
            validated.append((path, content))
        if [path for path, _content in validated] != sorted(seen_paths):
            raise ContractValidationError("GitHub actuator: verified-file reconciliation input is invalid")

        branch_state, commit_sha = self._read_branch_reference(branch)
        if (
            branch_state is not True
            or not isinstance(commit_sha, str)
            or re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None
        ):
            return None
        for path, content in validated:
            url = urljoin(
                self._config.api_url + "/",
                f"repos/{self._config.repository}/contents/{quote(path)}?ref={quote(branch, safe='')}",
            )
            try:
                metadata = self._get_json(url, self._headers())
            except Exception:
                return None
            blob_sha = metadata.get("sha") if isinstance(metadata, dict) else None
            if (
                not isinstance(metadata, dict)
                or metadata.get("type") != "file"
                or not isinstance(blob_sha, str)
                or re.fullmatch(r"[0-9a-f]{40}", blob_sha) is None
                or blob_sha != _git_blob_sha(content)
            ):
                return None
        return commit_sha

    def publish_pull_request(self, request: dict[str, Any]) -> GitHubPullRequest:
        expected = {"operation", "repository_id", "branch", "base_branch", "staged_change_digest", "idempotency_key", "policy_effect", "approval_valid"}
        if not isinstance(request, dict) or set(request) != expected or request["operation"] != "publish_pull_request":
            raise ContractValidationError("GitHub actuator: request shape or operation is invalid")
        for field in ("repository_id", "branch", "base_branch", "staged_change_digest", "idempotency_key"):
            value = request[field]
            if not isinstance(value, str) or not value:
                raise ContractValidationError("GitHub actuator: request field is invalid")
        repository_id = f"github-installation/{self._config.installation_id}/repository/{self._config.repository_id}"
        if request["repository_id"] != repository_id:
            raise ContractValidationError("GitHub actuator: request repository is not allowlisted")
        if request["policy_effect"] != "allow" or request["approval_valid"] is not True:
            raise ContractValidationError("GitHub actuator: authority proof is invalid")
        try:
            validate_publication_base_branch(request["base_branch"])
        except Exception:
            raise ContractValidationError("GitHub actuator: base branch is invalid") from None
        branch = request["branch"]
        if not isinstance(branch, str) or not branch.startswith("agent/process-") or len(branch) <= len("agent/process-"):
            raise ContractValidationError("GitHub actuator: branch is outside the agent namespace")
        expected_key = publication_idempotency_key(
            branch, request["base_branch"], request["staged_change_digest"]
        )
        if request["idempotency_key"] != expected_key:
            raise ContractValidationError("GitHub actuator: idempotency key does not match publication intent")
        marker = f"<!-- agent-process-idempotency: {request['idempotency_key']} -->"
        existing = self._find_existing_pull_request(
            branch, request["base_branch"], marker
        )
        if existing is not None:
            return GitHubPullRequest(existing[0], existing[1], repository_id, branch, request["staged_change_digest"], request["idempotency_key"], request["base_branch"])
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
                "base": request["base_branch"],
                "body": f"Automated publication for staged change `{request['staged_change_digest']}`.\n\n{marker}",
            },
        )
        number, html_url = response.get("number"), response.get("html_url")
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or number < 1
            or not isinstance(html_url, str)
            or not html_url.startswith("https://")
            or not isinstance(response.get("base"), dict)
            or response["base"].get("ref") != request["base_branch"]
        ):
            raise GitHubAppBrokerError("GitHub pull-request response is missing required fields")
        return GitHubPullRequest(number, html_url, repository_id, branch, request["staged_change_digest"], request["idempotency_key"], request["base_branch"])

    def _find_existing_pull_request(
        self, branch: str, base_branch: str, marker: str
    ) -> tuple[int, str] | None:
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
            head = item.get("head")
            if head is not None and (
                not isinstance(head, dict) or head.get("ref") != branch
            ):
                raise GitHubAppBrokerError("GitHub pull-request entry conflicts with requested branch")
            base = item.get("base")
            if not isinstance(base, dict) or base.get("ref") != base_branch:
                raise GitHubAppBrokerError("GitHub pull-request entry conflicts with requested base branch")
            number, html_url = item.get("number"), item.get("html_url")
            if not (
                isinstance(number, int)
                and not isinstance(number, bool)
                and number > 0
                and isinstance(html_url, str)
                and html_url.startswith("https://")
            ):
                raise GitHubAppBrokerError("GitHub pull-request entry is malformed")
            return number, html_url
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token.value}",
            "X-GitHub-Api-Version": "2022-11-28",
        }


class GitHubAppReadOnlyReconciliationChannel:
    """Read-only provider capability for reconciling one existing journal row.

    The object deliberately has no POST/PUT transport and exposes no publication
    method. Shared implementation is routed only through the existing adapter's
    read methods; write orchestration does not register this class as a channel.
    """

    def __init__(self, config: GitHubAppBrokerConfig, token: _InstallationToken, *, get_json=None) -> None:
        if not isinstance(config, GitHubAppBrokerConfig):
            raise ContractValidationError("GitHub actuator: read-only config is invalid")
        if not isinstance(token, _InstallationToken):
            raise ContractValidationError("GitHub actuator: read-only token is invalid")
        if get_json is not None and not callable(get_json):
            raise ContractValidationError("GitHub actuator: read transport is invalid")
        self._config = config
        self._token = token
        self._get_json = get_json or _get_json

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token.value}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _read_branch_reference(self, branch: str) -> tuple[bool | None, str | None]:
        return GitHubAppPublicationChannel._read_branch_reference(self, branch)

    def _find_existing_pull_request(
        self, branch: str, base_branch: str, marker: str
    ) -> tuple[int, str] | None:
        return GitHubAppPublicationChannel._find_existing_pull_request(
            self, branch, base_branch, marker
        )

    def reconcile_pull_request(
        self, *, branch: str, base_branch: str, idempotency_key: str,
        staged_change_digest: str = "",
    ) -> GitHubPullRequest | None:
        receipt = GitHubAppPublicationChannel.reconcile_pull_request(
            self,
            branch=branch,
            base_branch=base_branch,
            idempotency_key=idempotency_key,
            staged_change_digest=staged_change_digest,
        )
        if receipt is not None and receipt.pull_request_url != (
            f"https://github.com/{self._config.repository}/pull/{receipt.pull_request_id}"
        ):
            return None
        return receipt

    def find_by_idempotency_key(
        self,
        idempotency_key: str,
        *,
        repository_id: str | None = None,
        base_branch: str | None = None,
    ) -> GitHubPullRequest | None:
        return GitHubAppPublicationChannel.find_by_idempotency_key(
            self,
            idempotency_key,
            repository_id=repository_id,
            base_branch=base_branch,
        )

    def reconcile_verified_files(
        self, *, branch: str, files: Sequence[object]
    ) -> str | None:
        return GitHubAppPublicationChannel.reconcile_verified_files(
            self, branch=branch, files=files
        )


class GitHubAppReadOnlyReconciliationBroker:
    """Single-use broker restricted to exact read-only GitHub permissions."""

    _ACTUATOR_ID = "github-app-readonly-reconciliation"
    _PERMISSIONS = ["contents:read", "pull_requests:read"]

    def __init__(
        self,
        config: GitHubAppBrokerConfig,
        token_minter: GitHubAppInstallationTokenMinter,
        *,
        get_json=None,
    ) -> None:
        if not isinstance(config, GitHubAppBrokerConfig):
            raise ContractValidationError("GitHub actuator: read-only broker config is invalid")
        if not callable(getattr(token_minter, "mint", None)):
            raise ContractValidationError("GitHub actuator: read-only token minter is invalid")
        if get_json is not None and not callable(get_json):
            raise ContractValidationError("GitHub actuator: read transport is invalid")
        self._config = config
        self._token_minter = token_minter
        self._get_json = get_json
        self._used_grants: set[str] = set()

    def open_read_only_reconciliation_channel(
        self,
        credential_grant: dict[str, Any],
        actuator_request: dict[str, Any],
        *,
        now: datetime,
    ) -> GitHubAppReadOnlyReconciliationChannel:
        validate_credential_use_grant(credential_grant, actuator_request, now=now)
        grant_id = credential_grant["credential_grant_id"]
        if (
            credential_grant.get("operation") != "reconcile_publication"
            or actuator_request.get("operation") != "reconcile_publication"
            or credential_grant.get("actuator_id") != self._ACTUATOR_ID
            or actuator_request.get("actuator_id") != self._ACTUATOR_ID
            or credential_grant.get("installation_id") != self._config.installation_id
            or credential_grant.get("permissions") != self._PERMISSIONS
            or credential_grant.get("repository_id")
            != self._config.repository_target_binding.provider_repository_id
            or grant_id in self._used_grants
        ):
            raise ContractValidationError("GitHub actuator: read-only credential grant is invalid")
        token = self._token_minter.mint(credential_grant)
        channel = GitHubAppReadOnlyReconciliationChannel(
            self._config, token, get_json=self._get_json
        )
        self._used_grants.add(grant_id)
        return channel


class GitHubAppCredentialBroker:
    """Single-use Broker that mints a private token and opens one actuator channel."""

    def __init__(self, config: GitHubAppBrokerConfig, token_minter: GitHubAppInstallationTokenMinter, *, post_json=None, get_json=None, put_json=None) -> None:
        self._config = config
        self._token_minter = token_minter
        self._post_json = post_json
        self._get_json = get_json
        self._put_json = put_json
        self._used_grants: set[str] = set()

    @property
    def repository_target_binding(self) -> RepositoryTargetBinding:
        """Expose the non-secret, immutable target identity to the Control Plane."""
        return self._config.repository_target_binding

    def open_github_publication_channel(self, credential_grant: dict[str, Any], actuator_request: dict[str, Any], *, now: datetime) -> GitHubAppPublicationChannel:
        validate_credential_use_grant(credential_grant, actuator_request, now=now)
        grant_id = credential_grant["credential_grant_id"]
        if grant_id in self._used_grants:
            raise ContractValidationError("broker: credential grant already used")
        self._used_grants.add(grant_id)
        return GitHubAppPublicationChannel(self._config, self._token_minter.mint(credential_grant), post_json=self._post_json, get_json=self._get_json, put_json=self._put_json)


_register_github_app_types(
    GitHubAppCredentialBroker,
    GitHubAppPublicationChannel,
    GitHubPullRequest,
    GitHubAppReadOnlyReconciliationChannel,
)
