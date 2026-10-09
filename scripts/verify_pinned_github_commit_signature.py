"""One bounded anonymous read-only signature probe for the fixed commit pin."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.brainbooster_target_profile import (  # noqa: E402
    PINNED_COMMIT,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
)
from app_contracts.github_commit_signature import (  # noqa: E402
    GitCommitSignatureError,
    primary_fingerprint_from_armored_public_key,
    verify_git_commit_signature,
)
from app_contracts.github_git_commit_source import (  # noqa: E402
    GitHubRawCommitObjectSource,
)
from app_contracts.github_http_transport import (  # noqa: E402
    GitHubAnonymousSnapshotTransport,
)
from app_contracts.github_snapshot import (  # noqa: E402
    GitHubCommitClaim,
    GitHubSnapshotRequest,
    parse_github_commit,
)


_API = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2026-03-10"
_MAX_COMMIT_RESPONSE_BYTES = 1_000_000
_MAX_KEY_RESPONSE_BYTES = 1_000_000
_MAX_KEY_COUNT = 8
_OVERALL_TIMEOUT_SECONDS = 120.0
_ALLOWED_SIGNERS = frozenset({PINNED_OWNER, "web-flow"})


class ProbeStopped(ValueError):
    def __init__(self, reason: str) -> None:
        if reason not in {
            "rate-limit-unavailable",
            "commit-response-rejected",
            "signer-not-allowlisted",
            "public-key-response-rejected",
            "raw-commit-unavailable",
            "signature-not-verified",
            "tool-unavailable",
        }:
            reason = "probe-failed"
        self.reason = reason
        super().__init__(reason)


def run_probe(*, now: object = time.monotonic) -> dict[str, object]:
    """Read only the fixed pin, its signer public keys, and its raw object."""

    if not callable(now):
        raise ProbeStopped("probe-failed")
    started = now()
    deadline = started + _OVERALL_TIMEOUT_SECONDS
    git_executable = shutil.which("git")
    gpg_executable = shutil.which("gpg")
    if not git_executable or not gpg_executable:
        raise ProbeStopped("tool-unavailable")

    transport = GitHubAnonymousSnapshotTransport(timeout_seconds=20.0)
    try:
        readiness = transport.read_rate_limit()
    except Exception:
        raise ProbeStopped("rate-limit-unavailable") from None
    if (
        readiness.status != 200
        or readiness.remaining is None
        or readiness.remaining < 2
    ):
        raise ProbeStopped("rate-limit-unavailable")
    _require_time(now, deadline)

    commit_url = (
        f"{_API}/repos/{PINNED_OWNER}/{PINNED_REPOSITORY}/commits/{PINNED_COMMIT}"
    )
    try:
        commit_result = transport(
            "GET",
            commit_url,
            {"Accept": _ACCEPT, "X-GitHub-Api-Version": _API_VERSION},
            _MAX_COMMIT_RESPONSE_BYTES,
            allow_redirects=False,
        )
        commit_response = _parse_json_response(
            commit_result, _MAX_COMMIT_RESPONSE_BYTES
        )
        request = GitHubSnapshotRequest(
            owner=PINNED_OWNER,
            repository=PINNED_REPOSITORY,
            commit_oid=PINNED_COMMIT,
        )
        claim = parse_github_commit(request, commit_response)
        signer = commit_response.get("committer")
        signer_login = signer.get("login") if type(signer) is dict else None
        if (
            claim.tree_oid != PINNED_TREE
            or type(signer_login) is not str
            or signer_login not in _ALLOWED_SIGNERS
        ):
            raise ProbeStopped("signer-not-allowlisted")
    except ProbeStopped:
        raise
    except Exception:
        raise ProbeStopped("commit-response-rejected") from None
    _require_time(now, deadline)

    key_url = f"{_API}/users/{signer_login}/gpg_keys"
    try:
        key_result = transport(
            "GET",
            key_url,
            {"Accept": _ACCEPT, "X-GitHub-Api-Version": _API_VERSION},
            _MAX_KEY_RESPONSE_BYTES,
            allow_redirects=False,
        )
        key_records = _parse_public_key_records(key_result)
    except Exception:
        raise ProbeStopped("public-key-response-rejected") from None
    _require_time(now, deadline)

    try:
        raw_commit_source = GitHubRawCommitObjectSource(
            git_executable,
            timeout_seconds=min(30.0, _remaining_time(now, deadline)),
        )
        raw_commit = raw_commit_source(claim)
    except Exception:
        raise ProbeStopped("raw-commit-unavailable") from None
    _require_time(now, deadline)

    matches = []
    for armored_key in key_records:
        _require_time(now, deadline)
        try:
            fingerprint = primary_fingerprint_from_armored_public_key(
                armored_key,
                gpg_executable=gpg_executable,
                timeout_seconds=min(5.0, _remaining_time(now, deadline)),
            )
            proof = verify_git_commit_signature(
                claim,
                raw_commit,
                armored_key,
                expected_primary_fingerprint=fingerprint,
                git_executable=git_executable,
                gpg_executable=gpg_executable,
                timeout_seconds=min(10.0, _remaining_time(now, deadline)),
            )
            matches.append(proof)
        except ProbeStopped:
            raise
        except GitCommitSignatureError:
            continue
        except Exception:
            continue
    if len(matches) != 1:
        raise ProbeStopped("signature-not-verified")
    proof = matches[0]
    return {
        "status": "signature-valid",
        "commit_oid": proof.commit_oid,
        "tree_oid": proof.tree_oid,
        "primary_fingerprint": proof.primary_fingerprint,
        "identity_authenticated": False,
        "independent_transport_trust_established": False,
    }


def _parse_json_response(result: object, max_bytes: int) -> dict[str, object]:
    if (
        type(result) is not dict
        or result.get("status") != 200
        or type(result.get("body")) is not bytes
        or not result["body"]
        or len(result["body"]) > max_bytes
    ):
        raise ProbeStopped("commit-response-rejected")
    value = json.loads(result["body"])
    if type(value) is not dict:
        raise ProbeStopped("commit-response-rejected")
    return value


def _parse_public_key_records(result: object) -> tuple[bytes, ...]:
    if (
        type(result) is not dict
        or result.get("status") != 200
        or type(result.get("body")) is not bytes
        or not result["body"]
        or len(result["body"]) > _MAX_KEY_RESPONSE_BYTES
    ):
        raise ProbeStopped("public-key-response-rejected")
    value = json.loads(result["body"])
    if type(value) is not list or not 1 <= len(value) <= _MAX_KEY_COUNT:
        raise ProbeStopped("public-key-response-rejected")
    keys = []
    for record in value:
        key = record.get("public_key") if type(record) is dict else None
        if (
            type(key) is not str
            or not key.isascii()
            or len(key.encode("ascii")) > 64 * 1024
        ):
            raise ProbeStopped("public-key-response-rejected")
        keys.append(key.encode("ascii"))
    return tuple(keys)


def _require_time(now, deadline: float) -> None:
    _remaining_time(now, deadline)


def _remaining_time(now, deadline: float) -> float:
    try:
        remaining = deadline - now()
        if remaining <= 0:
            raise ProbeStopped("probe-failed")
        return remaining
    except ProbeStopped:
        raise
    except Exception:
        raise ProbeStopped("probe-failed") from None


def main(argv: list[str] | None = None) -> int:
    if argv:
        print('{"status":"stopped","reason":"invalid-invocation"}')
        return 2
    try:
        result = run_probe()
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except ProbeStopped as error:
        print(
            json.dumps(
                {"status": "stopped", "reason": error.reason},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 3
    except Exception:
        print('{"status":"stopped","reason":"probe-failed"}')
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
