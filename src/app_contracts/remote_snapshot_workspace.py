"""Lease-owned local materialization for bounded GitHub snapshot claims.

Materialization does not authenticate the GitHub REST claim or attest the
source repository. The temporary tree exists only to hand those exact bytes to
the local executor.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

from .github_snapshot import (
    GitHubBlobClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
)
from .pinned_snapshot import compute_snapshot_tree_digest


class RemoteSnapshotWorkspaceError(ValueError):
    """A bounded snapshot could not be materialized or its lease is invalid."""


_OWNER_TOKEN = object()


class MaterializedGitHubSnapshot:
    """Explicit lease for one read-only tree materialized from a REST claim."""

    def __init__(
        self,
        snapshot: GitHubSnapshotContents,
        temporary_directory: tempfile.TemporaryDirectory,
        *,
        _owner_token: object,
    ) -> None:
        if _owner_token is not _OWNER_TOKEN:
            raise RemoteSnapshotWorkspaceError("remote snapshot workspace: lease is invalid")
        self._snapshot = snapshot
        self._temporary_directory = temporary_directory
        self._closed = False

    @property
    def snapshot(self) -> GitHubSnapshotContents:
        self._require_open()
        return self._snapshot

    @property
    def path(self) -> Path:
        self._require_open()
        return Path(self._temporary_directory.name)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._temporary_directory.cleanup()
        except Exception:
            raise RemoteSnapshotWorkspaceError(
                "remote snapshot workspace: cleanup failed"
            ) from None
        self._closed = True

    def __enter__(self) -> "MaterializedGitHubSnapshot":
        self._require_open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            "MaterializedGitHubSnapshot(evidence_origin='github_rest_api_claim', "
            f"closed={self._closed})"
        )

    def _require_open(self) -> None:
        if self._closed:
            raise RemoteSnapshotWorkspaceError("remote snapshot workspace: lease is closed")


def materialize_github_snapshot(
    snapshot: object,
) -> MaterializedGitHubSnapshot:
    """Write exact bounded claim bytes into a private, read-only temp tree."""

    if type(snapshot) is not GitHubSnapshotContents:
        raise RemoteSnapshotWorkspaceError("remote snapshot workspace: input is invalid")
    snapshot = _copy_and_validate_snapshot(snapshot)
    temporary_directory = tempfile.TemporaryDirectory(prefix="agent00x-remote-snapshot-")
    root = Path(temporary_directory.name)
    try:
        expected_files = tuple(
            (blob.path, blob.mode, blob.content) for blob in snapshot.files
        )
        for relative_path, mode, content in expected_files:
            destination = root.joinpath(*relative_path.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise ValueError("duplicate path")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(destination, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
            os.chmod(
                destination,
                0o555 if mode == "100755" else 0o444,
                follow_symlinks=False,
            )

        _verify_materialized_tree(root, expected_files, snapshot.claim.content_digest)
        directories = [path for path in root.rglob("*") if path.is_dir()]
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            if directory.is_symlink():
                raise ValueError("symlink directory")
            directory.chmod(0o555)
        root.chmod(0o555)
        return MaterializedGitHubSnapshot(
            snapshot, temporary_directory, _owner_token=_OWNER_TOKEN
        )
    except Exception:
        try:
            temporary_directory.cleanup()
        except Exception:
            pass
        raise RemoteSnapshotWorkspaceError(
            "remote snapshot workspace: materialization failed"
        ) from None


def _copy_and_validate_snapshot(snapshot: GitHubSnapshotContents) -> GitHubSnapshotContents:
    try:
        source_claim = snapshot.claim
        claim = GitHubSnapshotClaim(
            owner=source_claim.owner,
            repository=source_claim.repository,
            commit_oid=source_claim.commit_oid,
            tree_oid=source_claim.tree_oid,
            content_digest=source_claim.content_digest,
            selected_paths=source_claim.selected_paths,
            evidence_origin=source_claim.evidence_origin,
        )
        if type(snapshot.files) is not tuple:
            raise ValueError()
        files = tuple(
            GitHubBlobClaim(
                path=blob.path,
                mode=blob.mode,
                sha=blob.sha,
                size=blob.size,
                content=blob.content,
                content_digest=blob.content_digest,
                evidence_origin=blob.evidence_origin,
            )
            for blob in snapshot.files
            if type(blob) is GitHubBlobClaim
        )
        if len(files) != len(snapshot.files):
            raise ValueError()
        return GitHubSnapshotContents(claim=claim, files=files)
    except Exception:
        raise RemoteSnapshotWorkspaceError(
            "remote snapshot workspace: input is invalid"
        ) from None


def _verify_materialized_tree(
    root: Path,
    expected_files: tuple[tuple[str, str, bytes], ...],
    expected_digest: str,
) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("root invalid")
    actual_files: list[tuple[str, str, bytes]] = []
    for path in root.rglob("*"):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("symlink invalid")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("file type invalid")
        relative_path = path.relative_to(root).as_posix()
        mode = "100755" if metadata.st_mode & 0o111 else "100644"
        content = path.read_bytes()
        if len(content) != metadata.st_size:
            raise ValueError("file changed")
        actual_files.append((relative_path, mode, content))
    actual = tuple(sorted(actual_files, key=lambda entry: entry[0]))
    if actual != expected_files:
        raise ValueError("file contents mismatch")
    if compute_snapshot_tree_digest(root) != expected_digest:
        raise ValueError("tree digest mismatch")
