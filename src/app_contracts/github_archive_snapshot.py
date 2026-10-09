"""Bounded anonymous codeload archive intake with explicit provenance.

This reader does not treat an archive as a REST API response. It accepts only
one fixed-host TLS response, validates every Git blob and reconstructs the
root tree before returning typed ``github_codeload_archive`` evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import http.client
import io
import math
from pathlib import PurePosixPath
import tarfile
import threading
from typing import Callable

from .digests import sha256_bytes
from .github_http_transport import _create_verified_ssl_context
from .github_snapshot import (
    GitHubBlobClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
    GitHubSnapshotError,
    _is_safe_tree_path,
    _snapshot_content_digest,
    _validate_oid,
    _validate_owner,
    _validate_repository,
)
from .pinned_snapshot import (
    MAX_SNAPSHOT_FILE_BYTES,
    MAX_SNAPSHOT_FILES,
    MAX_SNAPSHOT_PATH_BYTES,
    MAX_SNAPSHOT_TOTAL_BYTES,
)

_HOST = "codeload.github.com"
_MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 1024
_ARCHIVE_EVIDENCE_ORIGIN = "github_codeload_archive"
_SHA256_DIGEST_PREFIX = "sha256:"


class GitHubArchiveSnapshotError(ValueError):
    """A fixed-host codeload archive could not be safely validated."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        if http_status is not None and (
            type(http_status) is not int or not 100 <= http_status <= 599
        ):
            raise ValueError("github archive: HTTP status is invalid")
        super().__init__(message)
        self.http_status = http_status


@dataclass(frozen=True)
class GitHubArchiveSnapshotRequest:
    """Control-plane pins required to bind one archive to known Git objects."""

    owner: str
    repository: str
    commit_oid: str
    tree_oid: str
    content_digest: str
    file_count: int

    def __post_init__(self) -> None:
        try:
            _validate_owner(self.owner)
            _validate_repository(self.repository)
            _validate_oid(self.commit_oid, "github archive: commit OID is invalid")
            _validate_oid(self.tree_oid, "github archive: tree OID is invalid")
        except GitHubSnapshotError:
            raise GitHubArchiveSnapshotError(
                "github archive: request is invalid"
            ) from None
        if (
            type(self.content_digest) is not str
            or len(self.content_digest) != len(_SHA256_DIGEST_PREFIX) + 64
            or not self.content_digest.startswith(_SHA256_DIGEST_PREFIX)
            or any(character not in "0123456789abcdef" for character in self.content_digest[7:])
            or type(self.file_count) is not int
            or not 1 <= self.file_count <= MAX_SNAPSHOT_FILES
        ):
            raise GitHubArchiveSnapshotError("github archive: request is invalid")


class GitHubCodeloadArchiveTransport:
    """One-shot HTTPS GET to codeload with the project's verified CA context."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        connection_factory: Callable[..., object] | None = None,
    ) -> None:
        try:
            valid_timeout = (
                not isinstance(timeout_seconds, bool)
                and isinstance(timeout_seconds, (int, float))
                and math.isfinite(float(timeout_seconds))
                and 0 < float(timeout_seconds) <= 15
            )
        except (OverflowError, TypeError, ValueError):
            valid_timeout = False
        if not valid_timeout or (
            connection_factory is not None and not callable(connection_factory)
        ):
            raise GitHubArchiveSnapshotError("github archive: transport config is invalid")
        self._timeout_seconds = float(timeout_seconds)
        self._connection_factory = connection_factory
        self._lock = threading.Lock()
        self._used = False

    def __repr__(self) -> str:
        return "GitHubCodeloadArchiveTransport(authentication='none', used=" + str(self._used) + ")"

    def __call__(
        self, owner: str, repository: str, commit_oid: str
    ) -> bytes:
        try:
            _validate_owner(owner)
            _validate_repository(repository)
            _validate_oid(commit_oid, "github archive: commit OID is invalid")
        except GitHubSnapshotError:
            raise GitHubArchiveSnapshotError("github archive: request is invalid") from None
        with self._lock:
            if self._used:
                raise GitHubArchiveSnapshotError("github archive: one-shot transport already used")
            self._used = True

        connection = None
        response = None
        try:
            factory = self._connection_factory or http.client.HTTPSConnection
            connection = factory(
                _HOST,
                timeout=self._timeout_seconds,
                context=_create_verified_ssl_context(),
            )
            path = f"/{owner}/{repository}/legacy.tar.gz/{commit_oid}"
            connection.request(
                "GET",
                path,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Agent00X-read-only-snapshot",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            status = getattr(response, "status", None)
            if type(status) is not int or not 100 <= status <= 599:
                raise GitHubArchiveSnapshotError("github archive: response is invalid")
            if status != 200:
                raise GitHubArchiveSnapshotError(
                    "github archive: response failed", http_status=status
                )
            body = response.read(_MAX_ARCHIVE_BYTES + 1)
            if type(body) is not bytes or len(body) > _MAX_ARCHIVE_BYTES:
                raise GitHubArchiveSnapshotError("github archive: response exceeds limit")
            return body
        except GitHubArchiveSnapshotError:
            raise
        except Exception:
            raise GitHubArchiveSnapshotError("github archive: request failed") from None
        finally:
            close_response = getattr(response, "close", None)
            if callable(close_response):
                try:
                    close_response()
                except Exception:
                    pass
            close_connection = getattr(connection, "close", None)
            if callable(close_connection):
                try:
                    close_connection()
                except Exception:
                    pass


def read_github_archive_snapshot_contents(
    request: GitHubArchiveSnapshotRequest,
    transport: object | None = None,
) -> GitHubSnapshotContents:
    """Fetch and validate one archive against exact commit/tree/content pins."""

    if type(request) is not GitHubArchiveSnapshotRequest:
        raise GitHubArchiveSnapshotError("github archive: request is invalid")
    source = GitHubCodeloadArchiveTransport() if transport is None else transport
    if not callable(source):
        raise GitHubArchiveSnapshotError("github archive: transport is invalid")
    try:
        archive_bytes = source(request.owner, request.repository, request.commit_oid)
    except GitHubArchiveSnapshotError:
        raise
    except Exception:
        raise GitHubArchiveSnapshotError("github archive: request failed") from None
    return parse_github_archive_snapshot(request, archive_bytes)


def parse_github_archive_snapshot(
    request: GitHubArchiveSnapshotRequest, archive_bytes: bytes
) -> GitHubSnapshotContents:
    """Parse an already bounded archive without extracting filesystem paths."""

    if (
        type(request) is not GitHubArchiveSnapshotRequest
        or type(archive_bytes) is not bytes
        or not archive_bytes
        or len(archive_bytes) > _MAX_ARCHIVE_BYTES
    ):
        raise GitHubArchiveSnapshotError("github archive: archive input is invalid")
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            members = archive.getmembers()
            if not members or len(members) > _MAX_ARCHIVE_MEMBERS:
                raise GitHubArchiveSnapshotError("github archive: member limit exceeded")
            roots: set[str] = set()
            seen: dict[str, bool] = {}
            file_records: list[tuple[str, str, str, bytes]] = []
            total_bytes = 0
            for member in members:
                name = member.name
                normalized_name = name.rstrip("/") if member.isdir() and type(name) is str else name
                if (
                    type(name) is not str
                    or not name
                    or not normalized_name
                    or normalized_name.startswith("/")
                    or "\\" in normalized_name
                    or any(part in ("", ".", "..") for part in normalized_name.split("/"))
                ):
                    raise GitHubArchiveSnapshotError("github archive: member path is invalid")
                parts = tuple(PurePosixPath(normalized_name).parts)
                if not parts:
                    raise GitHubArchiveSnapshotError("github archive: member path is invalid")
                roots.add(parts[0])
                if len(parts) == 1:
                    if not member.isdir() or parts[0] in seen:
                        raise GitHubArchiveSnapshotError("github archive: root is invalid")
                    seen[parts[0]] = True
                    continue
                relative = "/".join(parts[1:])
                if len(relative.encode("utf-8")) > MAX_SNAPSHOT_PATH_BYTES or not _is_safe_tree_path(relative):
                    raise GitHubArchiveSnapshotError("github archive: member path is invalid")
                if relative in seen:
                    raise GitHubArchiveSnapshotError("github archive: duplicate member")
                if member.isdir():
                    seen[relative] = True
                    continue
                if not member.isfile():
                    raise GitHubArchiveSnapshotError("github archive: member type is invalid")
                if (
                    type(member.size) is not int
                    or member.size < 0
                    or member.size > MAX_SNAPSHOT_FILE_BYTES
                    or len(file_records) >= request.file_count
                ):
                    raise GitHubArchiveSnapshotError("github archive: file limit exceeded")
                stream = archive.extractfile(member)
                if stream is None:
                    raise GitHubArchiveSnapshotError("github archive: file content is invalid")
                content = stream.read(member.size + 1)
                if type(content) is not bytes or len(content) != member.size:
                    raise GitHubArchiveSnapshotError("github archive: file content is invalid")
                total_bytes += len(content)
                if total_bytes > MAX_SNAPSHOT_TOTAL_BYTES:
                    raise GitHubArchiveSnapshotError("github archive: total size exceeded")
                if (
                    type(member.mode) is not int
                    or member.mode < 0
                    or member.mode & ~0o777
                ):
                    raise GitHubArchiveSnapshotError("github archive: file mode is invalid")
                mode = "100755" if member.mode & 0o111 else "100644"
                blob_oid = hashlib.sha1(
                    b"blob " + str(len(content)).encode("ascii") + b"\0" + content
                ).hexdigest()
                seen[relative] = False
                file_records.append((relative, mode, blob_oid, content))
    except GitHubArchiveSnapshotError:
        raise
    except Exception:
        raise GitHubArchiveSnapshotError("github archive: archive is invalid") from None

    if len(roots) != 1 or len(file_records) != request.file_count:
        raise GitHubArchiveSnapshotError("github archive: snapshot shape mismatch")
    required_directories = {
        "/".join(parts[:index])
        for path, _, _, _ in file_records
        for parts in [path.split("/")]
        for index in range(1, len(parts))
    }
    declared_directories = {
        path
        for path, is_directory in seen.items()
        if is_directory and path not in roots
    }
    if declared_directories != required_directories:
        raise GitHubArchiveSnapshotError("github archive: directory structure mismatch")
    try:
        blobs = tuple(
            GitHubBlobClaim(
                path=path,
                mode=mode,
                sha=blob_oid,
                size=len(content),
                content=content,
                content_digest=sha256_bytes(content),
                evidence_origin=_ARCHIVE_EVIDENCE_ORIGIN,
            )
            for path, mode, blob_oid, content in sorted(file_records)
        )
        content_digest = _snapshot_content_digest(
            [(blob.path, blob.mode, blob.content) for blob in blobs]
        )
        if content_digest != request.content_digest:
            raise GitHubArchiveSnapshotError("github archive: content digest mismatch")
        tree_oid = _git_tree_oid(
            [(blob.path, blob.mode, blob.sha) for blob in blobs]
        )
        if tree_oid != request.tree_oid:
            raise GitHubArchiveSnapshotError("github archive: tree OID mismatch")
        claim = GitHubSnapshotClaim(
            owner=request.owner,
            repository=request.repository,
            commit_oid=request.commit_oid,
            tree_oid=tree_oid,
            content_digest=content_digest,
            evidence_origin=_ARCHIVE_EVIDENCE_ORIGIN,
        )
        return GitHubSnapshotContents(claim=claim, files=blobs)
    except GitHubArchiveSnapshotError:
        raise
    except Exception:
        raise GitHubArchiveSnapshotError("github archive: snapshot claim is invalid") from None


def _git_tree_oid(files: list[tuple[str, str, str]]) -> str:
    root: dict[str, object] = {}
    for path, mode, blob_oid in files:
        parts = path.split("/")
        current = root
        for part in parts[:-1]:
            existing = current.get(part)
            if existing is None:
                existing = {}
                current[part] = existing
            if type(existing) is not dict:
                raise GitHubArchiveSnapshotError("github archive: tree path conflict")
            current = existing
        if parts[-1] in current:
            raise GitHubArchiveSnapshotError("github archive: duplicate tree path")
        current[parts[-1]] = (mode, blob_oid)

    def hash_tree(node: dict[str, object]) -> str:
        children: list[tuple[bytes, bytes]] = []
        for name, value in node.items():
            name_bytes = name.encode("utf-8")
            if type(value) is dict:
                mode = "40000"
                oid = hash_tree(value)
                sort_name = name_bytes + b"/"
            else:
                mode, oid = value
                sort_name = name_bytes
            entry = (
                mode.encode("ascii") + b" " + name_bytes + b"\0" + bytes.fromhex(oid)
            )
            children.append((sort_name, entry))
        children.sort(key=lambda item: item[0])
        payload = b"".join(entry for _, entry in children)
        return hashlib.sha1(
            b"tree " + str(len(payload)).encode("ascii") + b"\0" + payload
        ).hexdigest()

    return hash_tree(root)
