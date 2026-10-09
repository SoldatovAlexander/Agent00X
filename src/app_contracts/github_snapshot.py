"""Bounded records for GitHub snapshot API claims.

These records fix the structure of a future API claim for one exact commit
or tree snapshot. They never attest authorship, remote provenance, or trust:
network retrieval and its credibility are out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
import hashlib
import json
import posixpath
import re
from typing import Any, Literal

from .digests import sha256_bytes, sha256_digest
from .secret_scan import CredentialLeakDetected, assert_no_credential_pattern_content
from .pinned_snapshot import (
    MAX_SNAPSHOT_FILE_BYTES,
    MAX_SNAPSHOT_FILES,
    MAX_SNAPSHOT_PATH_BYTES,
    MAX_SNAPSHOT_TOTAL_BYTES,
    MAX_SNAPSHOT_TREE_LIST_BYTES,
    SNAPSHOT_DIGEST_CANONICALIZATION,
)


class GitHubSnapshotError(ValueError):
    """A GitHub snapshot record field is malformed."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        if http_status is not None and (
            type(http_status) is not int or not 100 <= http_status <= 599
        ):
            raise ValueError("github snapshot: HTTP status is invalid")
        super().__init__(message)
        self.http_status = http_status


_OWNER_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_OID_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")

_BLOB_MODES = frozenset({"100644", "100755"})
_REMOTE_SNAPSHOT_EVIDENCE_ORIGINS = frozenset(
    {"github_rest_api_claim", "github_codeload_archive"}
)
_TREE_MODE = "040000"
_BLOB_ENCODING = "base64"
_MAX_BLOB_WIRE_BYTES = MAX_SNAPSHOT_FILE_BYTES * 2

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_API_VERSION = "2026-03-10"
_GITHUB_ACCEPT_HEADER = "application/vnd.github+json"
_MAX_COMMIT_RESPONSE_BYTES = 1_000_000
MAX_GIT_COMMIT_OBJECT_BYTES = 1_000_000
_MAX_GIT_COMMIT_HEADER_BYTES = 65_536
_MAX_TREE_RESPONSE_BYTES = MAX_SNAPSHOT_TREE_LIST_BYTES
_MAX_BLOB_RESPONSE_BYTES = _MAX_BLOB_WIRE_BYTES


@dataclass(frozen=True)
class GitHubSnapshotRequest:
    """Immutable request for one exact commit snapshot claim."""

    owner: str
    repository: str
    commit_oid: str
    include_paths: tuple[str, ...] | None = None
    evidence_origin: Literal["github_rest_api_claim"] = "github_rest_api_claim"

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        _validate_repository(self.repository)
        _validate_oid(self.commit_oid, "github snapshot: commit OID is invalid")
        _validate_selected_paths(self.include_paths)
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


@dataclass(frozen=True)
class GitCommitObject:
    """Content-address-checked commit/tree IDs; not authorship provenance."""

    commit_oid: str
    tree_oid: str

    def __post_init__(self) -> None:
        _validate_oid(self.commit_oid, "github snapshot: commit object is invalid")
        _validate_oid(self.tree_oid, "github snapshot: commit object is invalid")


def parse_git_commit_object(
    claim: GitHubCommitClaim, raw_commit: object
) -> GitCommitObject:
    """Verify exact Git SHA-1 framing and the claimed unique root-tree header.

    A successful result proves that these bytes hash to the requested commit
    OID and name the API-claimed root tree. It does not verify a commit
    signature, author identity, GitHub identity or the transport that supplied
    the bytes.
    """

    if type(claim) is not GitHubCommitClaim:
        raise GitHubSnapshotError("github snapshot: commit object claim is invalid")
    if (
        type(raw_commit) is not bytes
        or not raw_commit
        or len(raw_commit) > MAX_GIT_COMMIT_OBJECT_BYTES
    ):
        raise GitHubSnapshotError("github snapshot: commit object is invalid")
    try:
        object_header = b"commit " + str(len(raw_commit)).encode("ascii") + b"\0"
        calculated_oid = hashlib.sha1(object_header + raw_commit).hexdigest()
        header_end = raw_commit.find(b"\n\n")
        if header_end <= 0 or header_end > _MAX_GIT_COMMIT_HEADER_BYTES:
            raise ValueError
        header_bytes = raw_commit[:header_end]
        if b"\0" in header_bytes or b"\r" in header_bytes:
            raise ValueError
        header_lines = header_bytes.split(b"\n")
        if any(not line for line in header_lines):
            raise ValueError
        tree_lines = [line for line in header_lines if line.startswith(b"tree ")]
        if len(tree_lines) != 1 or not header_lines[0].startswith(b"tree "):
            raise ValueError
        tree_oid_bytes = header_lines[0][5:]
        if re.fullmatch(rb"[0-9a-f]{40}", tree_oid_bytes) is None:
            raise ValueError
        previous_header = False
        for line in header_lines:
            if line.startswith(b" "):
                if not previous_header:
                    raise ValueError
                continue
            key, separator, value = line.partition(b" ")
            if (
                not separator
                or re.fullmatch(rb"[a-z][a-z0-9-]*", key) is None
                or not value
            ):
                raise ValueError
            previous_header = True
        tree_oid = tree_oid_bytes.decode("ascii")
        if calculated_oid != claim.commit_oid or tree_oid != claim.tree_oid:
            raise ValueError
        return GitCommitObject(commit_oid=calculated_oid, tree_oid=tree_oid)
    except GitHubSnapshotError:
        raise
    except Exception:
        raise GitHubSnapshotError(
            "github snapshot: commit object is invalid"
        ) from None


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
    size: int | None = None


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
    entries with unique safe POSIX paths are accepted. Reported sizes are
    retained as metadata; content limits apply when blob bytes are requested
    and decoded.
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
    _verify_git_tree_entries(claim.tree_oid, tuple(entries))
    return GitHubTreeClaim(
        owner=claim.owner,
        repository=claim.repository,
        tree_oid=claim.tree_oid,
        entries=tuple(entries),
    )


def _verify_git_tree_entries(root_oid: str, entries: tuple[GitHubTreeEntry, ...]) -> None:
    """Rebuild every Git tree object represented by a complete recursive listing."""
    by_path = {entry.path: entry for entry in entries}
    required_directories: set[str] = set()
    for entry in entries:
        parts = entry.path.split("/")
        for index in range(1, len(parts)):
            required_directories.add("/".join(parts[:index]))
    declared_directories = {
        path for path, entry in by_path.items() if entry.entry_type == "tree"
    }
    if declared_directories != required_directories:
        raise GitHubSnapshotError("github snapshot: tree structure mismatch")

    children_by_directory: dict[str, list[GitHubTreeEntry]] = {}
    for entry in entries:
        parent = entry.path.rpartition("/")[0]
        children_by_directory.setdefault(parent, []).append(entry)
    computed: dict[str, str] = {}
    directories = sorted(required_directories, key=lambda path: path.count("/"), reverse=True)
    directories.append("")
    for directory in directories:
        children: list[tuple[bytes, bytes, str]] = []
        for entry in children_by_directory.get(directory, ()):
            path = entry.path
            name = path.rpartition("/")[2]
            object_oid = computed[path] if entry.entry_type == "tree" else entry.sha
            serialized_mode = "40000" if entry.entry_type == "tree" else entry.mode
            name_bytes = name.encode("utf-8")
            sort_name = name_bytes + (b"/" if entry.entry_type == "tree" else b"")
            object_entry = (
                serialized_mode.encode("ascii") + b" " + name_bytes + b"\0"
                + bytes.fromhex(object_oid)
            )
            children.append((sort_name, object_entry, path))
        if not children:
            if directory:
                raise GitHubSnapshotError("github snapshot: tree structure mismatch")
            tree_payload = b""
        else:
            children.sort(key=lambda item: item[0])
            tree_payload = b"".join(item[1] for item in children)
        tree_oid = hashlib.sha1(
            b"tree " + str(len(tree_payload)).encode("ascii") + b"\0" + tree_payload
        ).hexdigest()
        if directory:
            claimed = by_path[directory].sha
            if tree_oid != claimed:
                raise GitHubSnapshotError("github snapshot: subtree OID mismatch")
            computed[directory] = tree_oid
        elif tree_oid != root_oid:
            raise GitHubSnapshotError("github snapshot: tree OID mismatch")


@dataclass(frozen=True)
class GitHubBlobClaim:
    """Immutable remote-source claim binding one blob OID to verified bytes.

    Raw bytes never appear in the record representation; only the digest
    does. The ``size`` always equals the content length.
    """

    path: str
    mode: Literal["100644", "100755"]
    sha: str
    size: int
    content: bytes = field(repr=False)
    content_digest: str = field(repr=False)
    evidence_origin: Literal[
        "github_rest_api_claim", "github_codeload_archive"
    ] = "github_rest_api_claim"

    def __post_init__(self) -> None:
        if not _is_safe_tree_path(self.path):
            raise GitHubSnapshotError("github snapshot: blob entry is invalid")
        if type(self.mode) is not str or self.mode not in _BLOB_MODES:
            raise GitHubSnapshotError("github snapshot: blob entry is invalid")
        _validate_oid(self.sha, "github snapshot: blob OID is invalid")
        if (
            type(self.content) is not bytes
            or type(self.size) is not int
            or self.size != len(self.content)
            or self.size > MAX_SNAPSHOT_FILE_BYTES
        ):
            raise GitHubSnapshotError("github snapshot: blob size is invalid")
        if (
            type(self.content_digest) is not str
            or _DIGEST_PATTERN.fullmatch(self.content_digest) is None
            or sha256_bytes(self.content) != self.content_digest
        ):
            raise GitHubSnapshotError("github snapshot: blob digest is invalid")
        expected_git_oid = hashlib.sha1(
            b"blob " + str(self.size).encode("ascii") + b"\0" + self.content
        ).hexdigest()
        if self.sha != expected_git_oid:
            raise GitHubSnapshotError("github snapshot: blob OID mismatch")
        if self.evidence_origin not in _REMOTE_SNAPSHOT_EVIDENCE_ORIGINS:
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
    if entry.size is not None:
        if type(entry.size) is not int or entry.size < 0:
            raise GitHubSnapshotError("github snapshot: blob entry is invalid")
        if entry.size > MAX_SNAPSHOT_FILE_BYTES:
            raise GitHubSnapshotError("github snapshot: blob size exceeds limit")
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
    wire_bytes = wire_bytes.replace(b"\r\n", b"\n")
    if b"\r" in wire_bytes:
        raise GitHubSnapshotError("github snapshot: blob response is invalid")
    if b"\n" in wire_bytes:
        lines = wire_bytes.split(b"\n")
        if lines[-1] == b"":
            lines = lines[:-1]
        if any(not line for line in lines):
            raise GitHubSnapshotError("github snapshot: blob response is invalid")
        wire_bytes = b"".join(lines)
    try:
        content = base64.b64decode(wire_bytes, validate=True)
    except Exception:
        raise GitHubSnapshotError("github snapshot: blob response is invalid") from None
    size = response.get("size")
    if type(size) is not int or size != len(content):
        raise GitHubSnapshotError("github snapshot: blob size mismatch")
    if entry.size is not None and size != entry.size:
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
        mode=entry.mode,
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
    size = None
    if "size" in raw_entry:
        size = raw_entry["size"]
        if type(size) is not int or size < 0:
            raise GitHubSnapshotError("github snapshot: tree entry is invalid")
    return GitHubTreeEntry(
        path=normalized, mode=mode, entry_type=entry_type, sha=sha, size=size
    )


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
    if (
        not isinstance(value, str)
        or value in (".", "..")
        or _REPOSITORY_PATTERN.fullmatch(value) is None
    ):
        raise GitHubSnapshotError("github snapshot: repository identity is invalid")


def _validate_oid(value: object, message: str) -> None:
    if not isinstance(value, str) or _OID_PATTERN.fullmatch(value) is None:
        raise GitHubSnapshotError(message)


@dataclass(frozen=True)
class GitHubSnapshotClaim:
    """Immutable read-only claim over one exact remote snapshot."""

    owner: str
    repository: str
    commit_oid: str
    tree_oid: str
    content_digest: str
    selected_paths: tuple[str, ...] | None = None
    evidence_origin: Literal[
        "github_rest_api_claim", "github_codeload_archive"
    ] = "github_rest_api_claim"

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        _validate_repository(self.repository)
        _validate_oid(self.commit_oid, "github snapshot: commit OID is invalid")
        _validate_oid(self.tree_oid, "github snapshot: tree OID is invalid")
        if type(self.content_digest) is not str or _DIGEST_PATTERN.fullmatch(
            self.content_digest
        ) is None:
            raise GitHubSnapshotError("github snapshot: content digest is invalid")
        _validate_selected_paths(self.selected_paths, allow_none=True)
        if self.evidence_origin not in _REMOTE_SNAPSHOT_EVIDENCE_ORIGINS:
            raise GitHubSnapshotError("github snapshot: evidence origin is invalid")

    @property
    def full_snapshot(self) -> bool:
        return self.selected_paths is None


@dataclass(frozen=True)
class GitHubSnapshotContents:
    """Bounded remote bytes paired with the claim that supplied them.

    Bytes are available to an explicit caller but are hidden from repr. The
    record preserves source type and does not establish author or server trust.
    """

    claim: GitHubSnapshotClaim
    files: tuple[GitHubBlobClaim, ...] = field(repr=False)
    verified_commit_object: GitCommitObject | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.claim) is not GitHubSnapshotClaim:
            raise GitHubSnapshotError("github snapshot: content claim is invalid")
        if self.verified_commit_object is not None and (
            type(self.verified_commit_object) is not GitCommitObject
            or self.verified_commit_object.commit_oid != self.claim.commit_oid
            or self.verified_commit_object.tree_oid != self.claim.tree_oid
        ):
            raise GitHubSnapshotError("github snapshot: commit object is invalid")
        if type(self.files) is not tuple or any(
            type(blob) is not GitHubBlobClaim for blob in self.files
        ):
            raise GitHubSnapshotError("github snapshot: content files are invalid")
        if any(blob.evidence_origin != self.claim.evidence_origin for blob in self.files):
            raise GitHubSnapshotError("github snapshot: evidence origin mismatch")
        if len(self.files) > MAX_SNAPSHOT_FILES:
            raise GitHubSnapshotError("github snapshot: content limits exceeded")
        paths = tuple(blob.path for blob in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise GitHubSnapshotError("github snapshot: content files are invalid")
        if self.claim.selected_paths is not None and paths != self.claim.selected_paths:
            raise GitHubSnapshotError("github snapshot: content selection mismatch")
        if sum(blob.size for blob in self.files) > MAX_SNAPSHOT_TOTAL_BYTES:
            raise GitHubSnapshotError("github snapshot: content limits exceeded")
        actual = _snapshot_content_digest(
            [(blob.path, blob.mode, blob.content) for blob in self.files]
        )
        if actual != self.claim.content_digest:
            raise GitHubSnapshotError("github snapshot: content digest mismatch")
        try:
            assert_no_credential_pattern_content(
                tuple((blob.path, blob.content) for blob in self.files)
            )
        except CredentialLeakDetected:
            raise GitHubSnapshotError(
                "github snapshot: credential-shaped content detected"
            ) from None


def read_github_snapshot(
    request: GitHubSnapshotRequest, transport: object
) -> GitHubSnapshotClaim:
    """Read full blob contents and return the corresponding content claim."""

    return read_github_snapshot_contents(request, transport).claim


def read_github_snapshot_metadata(
    request: GitHubSnapshotRequest, transport: object
) -> GitHubTreeClaim:
    """Read only the exact commit and recursive tree metadata (two GETs).

    This deliberately does not request blob objects and therefore cannot
    establish a canonical SHA-256 digest over blob contents.
    """

    if type(request) is not GitHubSnapshotRequest:
        raise GitHubSnapshotError("github snapshot: request shape is invalid")
    try:
        request = GitHubSnapshotRequest(
            owner=request.owner,
            repository=request.repository,
            commit_oid=request.commit_oid,
            include_paths=request.include_paths,
            evidence_origin=request.evidence_origin,
        )
    except Exception:
        raise GitHubSnapshotError("github snapshot: request shape is invalid") from None
    if not callable(transport):
        raise GitHubSnapshotError("github snapshot: transport is invalid")

    commit_payload = _get_json(
        transport,
        f"/repos/{request.owner}/{request.repository}/commits/{request.commit_oid}",
        _MAX_COMMIT_RESPONSE_BYTES,
    )
    commit_claim = parse_github_commit(request, commit_payload)
    tree_payload = _get_json(
        transport,
        f"/repos/{request.owner}/{request.repository}/git/trees/{commit_claim.tree_oid}?recursive=1",
        _MAX_TREE_RESPONSE_BYTES,
    )
    tree_claim = parse_github_tree(commit_claim, tree_payload)
    if request.include_paths is not None:
        blob_paths = {
            entry.path for entry in tree_claim.entries if entry.entry_type == "blob"
        }
        if any(path not in blob_paths for path in request.include_paths):
            raise GitHubSnapshotError("github snapshot: selected path is missing")
    return tree_claim


def read_github_snapshot_contents(
    request: GitHubSnapshotRequest,
    transport: object,
    *,
    commit_object_source: object | None = None,
) -> GitHubSnapshotContents:
    """Read one exact snapshot through an injected bounded GET transport.

    The object chain links the requested commit to its tree SHA and then to
    bounded verified blob contents; the content digest is computed with the
    same canonicalization as local snapshots. Declared oversized blobs stop
    before any blob request. There is no default network
    transport: every byte arrives through the injected collaborator, which is
    only ever called with ``GET``, the fixed API endpoints, explicit headers
    and redirects disabled.
    """

    if type(request) is not GitHubSnapshotRequest:
        raise GitHubSnapshotError("github snapshot: request shape is invalid")
    try:
        request = GitHubSnapshotRequest(
            owner=request.owner,
            repository=request.repository,
            commit_oid=request.commit_oid,
            include_paths=request.include_paths,
            evidence_origin=request.evidence_origin,
        )
    except Exception:
        raise GitHubSnapshotError("github snapshot: request shape is invalid") from None
    if not callable(transport):
        raise GitHubSnapshotError("github snapshot: transport is invalid")
    commit_payload = _get_json(
        transport,
        f"/repos/{request.owner}/{request.repository}/commits/{request.commit_oid}",
        _MAX_COMMIT_RESPONSE_BYTES,
    )
    commit_claim = parse_github_commit(request, commit_payload)
    verified_commit_object = None
    if commit_object_source is not None:
        if not callable(commit_object_source):
            raise GitHubSnapshotError("github snapshot: commit object source is invalid")
        try:
            raw_commit_object = commit_object_source(commit_claim)
            verified_commit_object = parse_git_commit_object(
                commit_claim, raw_commit_object
            )
        except Exception:
            raise GitHubSnapshotError(
                "github snapshot: commit object is invalid"
            ) from None
    tree_payload = _get_json(
        transport,
        f"/repos/{request.owner}/{request.repository}/git/trees/{commit_claim.tree_oid}?recursive=1",
        _MAX_TREE_RESPONSE_BYTES,
    )
    tree_claim = parse_github_tree(commit_claim, tree_payload)
    tree_blob_entries = tuple(
        entry for entry in tree_claim.entries if entry.entry_type == "blob"
    )
    if request.include_paths is None:
        selected_entries = tree_blob_entries
    else:
        entries_by_path = {entry.path: entry for entry in tree_blob_entries}
        if any(path not in entries_by_path for path in request.include_paths):
            raise GitHubSnapshotError("github snapshot: selected path is missing")
        selected_entries = tuple(entries_by_path[path] for path in request.include_paths)
    if any(
        entry.entry_type == "blob"
        and entry.size is not None
        and entry.size > MAX_SNAPSHOT_FILE_BYTES
        for entry in selected_entries
    ):
        raise GitHubSnapshotError("github snapshot: blob size exceeds limit")
    bound_files: list[tuple[str, str, bytes]] = []
    running_total_bytes = 0
    for entry in selected_entries:
        blob_payload = _get_json(
            transport,
            f"/repos/{request.owner}/{request.repository}/git/blobs/{entry.sha}",
            _MAX_BLOB_RESPONSE_BYTES,
        )
        blob = parse_github_blob(
            entry, blob_payload, content_bytes_used=running_total_bytes
        )
        bound_files.append((blob.path, entry.mode, blob.content))
        running_total_bytes += blob.size
    claim = GitHubSnapshotClaim(
        owner=request.owner,
        repository=request.repository,
        commit_oid=request.commit_oid,
        tree_oid=tree_claim.tree_oid,
        content_digest=_snapshot_content_digest(bound_files),
        selected_paths=request.include_paths,
    )
    # `bound_files` carries verified bytes; reconstruct immutable blob records
    # from the already checked tree entries without performing another GET.
    entry_by_path = {
        entry.path: entry
        for entry in tree_claim.entries
        if entry.entry_type == "blob"
    }
    files = tuple(
        GitHubBlobClaim(
            path=path,
            mode=mode,
            sha=entry_by_path[path].sha,
            size=len(content),
            content=content,
            content_digest=sha256_bytes(content),
        )
        for path, mode, content in sorted(bound_files, key=lambda item: item[0])
    )
    return GitHubSnapshotContents(
        claim=claim,
        files=files,
        verified_commit_object=verified_commit_object,
    )


def _snapshot_content_digest(files: list[tuple[str, str, bytes]]) -> str:
    entries = [
        {
            "path": path,
            "content_digest": sha256_bytes(content),
            "mode": mode,
        }
        for path, mode, content in sorted(files, key=lambda item: item[0])
    ]
    return sha256_digest(
        {"canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION, "files": entries}
    )


def _validate_selected_paths(
    paths: object, *, allow_none: bool = True
) -> None:
    if paths is None and allow_none:
        return
    if (
        type(paths) is not tuple
        or not paths
        or len(paths) > MAX_SNAPSHOT_FILES
        or any(not _is_safe_tree_path(path) for path in paths)
    ):
        raise GitHubSnapshotError("github snapshot: selected paths are invalid")
    if (
        paths != tuple(sorted(paths))
        or len(paths) != len(set(paths))
    ):
        raise GitHubSnapshotError("github snapshot: selected paths are invalid")


def _get_json(transport: object, path: str, max_bytes: int) -> object:
    headers = {
        "Accept": _GITHUB_ACCEPT_HEADER,
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }
    try:
        result = transport(
            "GET", _GITHUB_API_BASE + path, headers, max_bytes, allow_redirects=False
        )
    except Exception:
        raise GitHubSnapshotError("github snapshot: snapshot transport failed") from None
    if type(result) is not dict:
        raise GitHubSnapshotError("github snapshot: transport result is invalid")
    status = result.get("status")
    body = result.get("body")
    if (
        type(status) is not int
        or not 100 <= status <= 599
        or type(body) is not bytes
    ):
        raise GitHubSnapshotError("github snapshot: transport result is invalid")
    if len(body) > max_bytes:
        raise GitHubSnapshotError("github snapshot: snapshot response exceeds limit")
    if status != 200:
        raise GitHubSnapshotError(
            f"github snapshot: snapshot response failed (HTTP {status})",
            http_status=status,
        )
    try:
        text = body.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise GitHubSnapshotError("github snapshot: snapshot payload is invalid") from None
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except Exception:
        raise GitHubSnapshotError("github snapshot: snapshot payload is invalid") from None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError("non-standard JSON constant")
