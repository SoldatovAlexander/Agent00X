"""Bounded records for GitHub snapshot API claims.

These records fix the structure of a future API claim for one exact commit
or tree snapshot. They never attest authorship, remote provenance, or trust:
network retrieval and its credibility are out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


class GitHubSnapshotError(ValueError):
    """A GitHub snapshot record field is malformed."""


_OWNER_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_OID_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class GitHubSnapshotRequest:
    """Immutable request for one exact commit snapshot claim."""

    owner: str
    repository: str
    commit_oid: str
    evidence_origin: Literal["github_rest_api_claim"] = "github_rest_api_claim"

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        _validate_repository(self.repository)
        _validate_oid(self.commit_oid, "github snapshot: commit OID is invalid")
        if self.evidence_origin != "github_rest_api_claim":
            raise GitHubSnapshotError("github snapshot: evidence origin is invalid")


@dataclass(frozen=True)
class GitHubCommitClaim:
    """Immutable API claim binding one commit OID to its tree OID."""

    owner: str
    repository: str
    commit_oid: str
    tree_oid: str
    evidence_origin: Literal["github_rest_api_claim"] = "github_rest_api_claim"

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        _validate_repository(self.repository)
        _validate_oid(self.commit_oid, "github snapshot: commit OID is invalid")
        _validate_oid(self.tree_oid, "github snapshot: tree OID is invalid")
        if self.evidence_origin != "github_rest_api_claim":
            raise GitHubSnapshotError("github snapshot: evidence origin is invalid")


def parse_github_commit(request: GitHubSnapshotRequest, response: object) -> GitHubCommitClaim:
    """Bind one commit API response to the requested commit OID.

    Only an object whose ``sha`` exactly matches the requested full commit
    OID and whose ``commit.tree.sha`` is a well-formed tree OID is accepted.
    Author, committer and verification metadata are never read and never
    elevate the claim: the result stays a plain API claim.
    """

    if type(request) is not GitHubSnapshotRequest:
        raise GitHubSnapshotError("github snapshot: request shape is invalid")
    if type(response) is not dict:
        raise GitHubSnapshotError("github snapshot: commit response is invalid")
    sha = response.get("sha")
    if not isinstance(sha, str) or _OID_PATTERN.fullmatch(sha) is None:
        raise GitHubSnapshotError("github snapshot: commit response is invalid")
    if sha != request.commit_oid:
        raise GitHubSnapshotError("github snapshot: commit OID mismatch")
    commit_section = response.get("commit")
    if type(commit_section) is not dict:
        raise GitHubSnapshotError("github snapshot: commit response is invalid")
    tree_section = commit_section.get("tree")
    if type(tree_section) is not dict:
        raise GitHubSnapshotError("github snapshot: commit response is invalid")
    tree_sha = tree_section.get("sha")
    if not isinstance(tree_sha, str) or _OID_PATTERN.fullmatch(tree_sha) is None:
        raise GitHubSnapshotError("github snapshot: commit response is invalid")
    return GitHubCommitClaim(
        owner=request.owner,
        repository=request.repository,
        commit_oid=request.commit_oid,
        tree_oid=tree_sha,
    )


def _validate_owner(value: object) -> None:
    if not isinstance(value, str) or _OWNER_PATTERN.fullmatch(value) is None:
        raise GitHubSnapshotError("github snapshot: repository identity is invalid")


def _validate_repository(value: object) -> None:
    if not isinstance(value, str) or _REPOSITORY_PATTERN.fullmatch(value) is None:
        raise GitHubSnapshotError("github snapshot: repository identity is invalid")


def _validate_oid(value: object, message: str) -> None:
    if not isinstance(value, str) or _OID_PATTERN.fullmatch(value) is None:
        raise GitHubSnapshotError(message)
