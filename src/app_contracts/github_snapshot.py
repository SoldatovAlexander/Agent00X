"""Bounded records for GitHub snapshot API claims.

These records fix the structure of a future API claim for one exact commit
or tree snapshot. They never attest authorship, remote provenance, or trust:
network retrieval and its credibility are out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
import hashlib
import posixpath
import re
from typing import Literal

from .digests import sha256_bytes
from .pinned_snapshot import (
    MAX_SNAPSHOT_FILE_BYTES,
    MAX_SNAPSHOT_FILES,
    MAX_SNAPSHOT_PATH_BYTES,
    MAX_SNAPSHOT_TOTAL_BYTES,
)


class GitHubSnapshotError(ValueError):
    """A GitHub snapshot record field is malformed."""


_OWNER_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_OID_PATTERN = re.compile(r"[0-9a-f]{40}\Z")

_BLOB_MODES = frozenset({"100644", "100755"})
_TREE_MODE = "040000"
_BLOB_ENCODING = "base64"
_MAX_BLOB_WIRE_BYTES = MAX_SNAPSHOT_FILE_BYTES * 2


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


@dataclass(frozen=True)
class GitHubTreeEntry:
    """One validated entry of a complete GitHub tree response."""

    path: str
    mode: str
    entry_type: str
    sha: str


@dataclass(frozen=True)
class GitHubTreeClaim:
    """Immutable API claim binding one tree OID to its validated entries."""

    owner: str
    repository: str
    tree_oid: str
    entries: tuple[GitHubTreeEntry, ...]
    evidence_origin: Literal["github_rest_api_claim"] = "github_rest_api_claim"

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        _validate_repository(self.repository)
        _validate_oid(self.tree_oid, "github snapshot: tree OID is invalid")
        if type(self.entries) is not tuple or any(
            type(entry) is not GitHubTreeEntry for entry in self.entries
        ):
            raise GitHubSnapshotError("github snapshot: tree entries are invalid")
        if self.evidence_origin != "github_rest_api_claim":
            raise GitHubSnapshotError("github snapshot: evidence origin is invalid")


def parse_github_tree(claim: GitHubCommitClaim, response: object) -> GitHubTreeClaim:
    """Bind one tree API response to the tree of a commit claim.

    The response ``sha`` must equal the claimed tree OID and ``truncated``
    must be an explicit false. Only regular blob modes and structural tree
    entries with unique safe POSIX paths inside existing snapshot limits are
    accepted; anything else fails closed before any blob handling.
    """

    if type(claim) is not GitHubCommitClaim:
        raise GitHubSnapshotError("github snapshot: commit claim is invalid")
    if type(response) is not dict:
        raise GitHubSnapshotError("github snapshot: tree response is invalid")
    sha = response.get("sha")
    if not isinstance(sha, str) or _OID_PATTERN.fullmatch(sha) is None:
        raise GitHubSnapshotError("github snapshot: tree response is invalid")
    if sha != claim.tree_oid:
        raise GitHubSnapshotError("github snapshot: tree OID mismatch")
    raw_entries = response.get("tree")
    if type(raw_entries) is not list or len(raw_entries) > MAX_SNAPSHOT_FILES:
        raise GitHubSnapshotError("github snapshot: tree response is invalid")
    if response.get("truncated") is not False:
        raise GitHubSnapshotError("github snapshot: tree response is incomplete")
    entries: list[GitHubTreeEntry] = []
    seen_paths: set[str] = set()
    for raw_entry in raw_entries:
        entries.append(_parse_tree_entry(raw_entry, seen_paths))
    return GitHubTreeClaim(
        owner=claim.owner,
        repository=claim.repository,
        tree_oid=claim.tree_oid,
        entries=tuple(entries),
    )


@dataclass(frozen=True)
class GitHubBlobClaim:
    """Immutable API claim binding one blob OID to its verified bytes.

    Raw bytes never appear in the record representation; only the digest
    does. The ``size`` always equals the content length.
    """

    path: str
    sha: str
    size: int
    content: bytes = field(repr=False)
    content_digest: str = field(repr=False)
    evidence_origin: Literal["github_rest_api_claim"] = "github_rest_api_claim"

    def __post_init__(self) -> None:
        if not _is_safe_tree_path(self.path):
            raise GitHubSnapshotError("github snapshot: blob entry is invalid")
        _validate_oid(self.sha, "github snapshot: blob OID is invalid")
        if type(self.size) is not int or self.size != len(self.content):
            raise GitHubSnapshotError("github snapshot: blob size is invalid")
        if type(self.content_digest) is not str or not self.content_digest:
            raise GitHubSnapshotError("github snapshot: blob digest is invalid")
        if self.evidence_origin != "github_rest_api_claim":
            raise GitHubSnapshotError("github snapshot: evidence origin is invalid")


def parse_github_blob(
    entry: GitHubTreeEntry,
    response: object,
    *,
    content_bytes_used: int = 0,
) -> GitHubBlobClaim:
    """Decode one blob API response and verify it against a tree entry.

    Only ``base64`` responses are accepted, decoded strictly and bounded
    before use. The response size must match the decoded length, the decoded
    length must fit per-blob and running total snapshot limits, and the Git
    blob identity ``SHA1("blob <size>\\0" + bytes)`` must equal the entry OID.
    Raw bytes never enter errors, representations or diagnostics.
    """

    if type(entry) is not GitHubTreeEntry or entry.entry_type != "blob":
        raise GitHubSnapshotError("github snapshot: blob entry is invalid")
    if type(response) is not dict:
        raise GitHubSnapshotError("github snapshot: blob response is invalid")
    if response.get("encoding") != _BLOB_ENCODING:
        raise GitHubSnapshotError("github snapshot: blob response is invalid")
    if type(content_bytes_used) is not int or content_bytes_used < 0:
        raise GitHubSnapshotError("github snapshot: blob response is invalid")
    encoded = response.get("content")
    if not isinstance(encoded, str):
        raise GitHubSnapshotError("github snapshot: blob response is invalid")
    try:
        wire_bytes = encoded.encode("ascii")
    except UnicodeEncodeError:
        raise GitHubSnapshotError("github snapshot: blob response is invalid") from None
    if len(wire_bytes) > _MAX_BLOB_WIRE_BYTES:
        raise GitHubSnapshotError("github snapshot: blob size exceeds limit")
    try:
        content = base64.b64decode(wire_bytes, validate=True)
    except Exception:
        raise GitHubSnapshotError("github snapshot: blob response is invalid") from None
    size = response.get("size")
    if type(size) is not int or size != len(content):
        raise GitHubSnapshotError("github snapshot: blob size mismatch")
    if len(content) > MAX_SNAPSHOT_FILE_BYTES:
        raise GitHubSnapshotError("github snapshot: blob size exceeds limit")
    if content_bytes_used + len(content) > MAX_SNAPSHOT_TOTAL_BYTES:
        raise GitHubSnapshotError("github snapshot: blob contents exceed limit")
    git_identity = hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()
    if git_identity != entry.sha:
        raise GitHubSnapshotError("github snapshot: blob OID mismatch")
    response_sha = response.get("sha")
    if response_sha != entry.sha:
        raise GitHubSnapshotError("github snapshot: blob OID mismatch")
    return GitHubBlobClaim(
        path=entry.path,
        sha=entry.sha,
        size=len(content),
        content=content,
        content_digest=sha256_bytes(content),
    )


def _parse_tree_entry(raw_entry: object, seen_paths: set[str]) -> GitHubTreeEntry:
    if type(raw_entry) is not dict:
        raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    path = raw_entry.get("path")
    if not _is_safe_tree_path(path):
        raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    normalized = posixpath.normpath(path)
    if normalized in seen_paths:
        raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    seen_paths.add(normalized)
    mode = raw_entry.get("mode")
    entry_type = raw_entry.get("type")
    if not isinstance(mode, str) or not isinstance(entry_type, str):
        raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    if mode in _BLOB_MODES:
        if entry_type != "blob":
            raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    elif mode == _TREE_MODE and entry_type == "tree":
        pass
    else:
        raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    sha = raw_entry.get("sha")
    if not isinstance(sha, str) or _OID_PATTERN.fullmatch(sha) is None:
        raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    if "size" in raw_entry:
        size = raw_entry["size"]
        if (
            type(size) is not int
            or not 0 <= size <= MAX_SNAPSHOT_FILE_BYTES
        ):
            raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    return GitHubTreeEntry(path=normalized, mode=mode, entry_type=entry_type, sha=sha)


def _is_safe_tree_path(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value.startswith("/")
        or "\\" in value
        or "//" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    parts = tuple(value.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        return False
    try:
        path_bytes = value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return len(path_bytes) <= MAX_SNAPSHOT_PATH_BYTES


def _validate_owner(value: object) -> None:
    if not isinstance(value, str) or _OWNER_PATTERN.fullmatch(value) is None:
        raise GitHubSnapshotError("github snapshot: repository identity is invalid")


def _validate_repository(value: object) -> None:
    if not isinstance(value, str) or _REPOSITORY_PATTERN.fullmatch(value) is None:
        raise GitHubSnapshotError("github snapshot: repository identity is invalid")


def _validate_oid(value: object, message: str) -> None:
    if not isinstance(value, str) or _OID_PATTERN.fullmatch(value) is None:
        raise GitHubSnapshotError(message)
