"""Read and validate the exact public snapshot required by the R5 study."""

from __future__ import annotations

from app_contracts.brainbooster_target_profile import (
    PINNED_COMMIT,
    PINNED_CONTENT_DIGEST,
    PINNED_FILE_COUNT,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
)
from app_contracts.github_snapshot import (
    GitHubCommitClaim,
    GitCommitObject,
    GitHubSnapshotContents,
    parse_git_commit_object,
)
from app_contracts.github_archive_snapshot import (
    GitHubArchiveSnapshotRequest,
    read_github_archive_snapshot_contents,
)


_ROUTE_SHA256 = "sha256:32847307337ab9e9f02bec60c69ed1b581206f453f6d6f59ef6ea15938de1cf7"
_ROUTE_PATH = "backend/routes.py"


class R5SnapshotError(ValueError):
    """A fixed, redacted R5 pinned-snapshot error."""


def read_pinned_r5_snapshot(*, transport: object, commit_object_source: object) -> GitHubSnapshotContents:
    """Read one pinned codeload archive and independently verify its commit object."""

    try:
        if not callable(transport) or not callable(commit_object_source):
            raise ValueError
        request = GitHubArchiveSnapshotRequest(
            owner=PINNED_OWNER,
            repository=PINNED_REPOSITORY,
            commit_oid=PINNED_COMMIT,
            tree_oid=PINNED_TREE,
            content_digest=PINNED_CONTENT_DIGEST,
            file_count=PINNED_FILE_COUNT,
        )
        archive_snapshot = read_github_archive_snapshot_contents(request, transport)
        commit_claim = GitHubCommitClaim(
            owner=PINNED_OWNER,
            repository=PINNED_REPOSITORY,
            commit_oid=PINNED_COMMIT,
            tree_oid=PINNED_TREE,
        )
        verified_commit_object = parse_git_commit_object(
            commit_claim, commit_object_source(commit_claim)
        )
        snapshot = GitHubSnapshotContents(
            claim=archive_snapshot.claim,
            files=archive_snapshot.files,
            verified_commit_object=verified_commit_object,
        )
        if type(snapshot) is not GitHubSnapshotContents:
            raise ValueError
        claim = snapshot.claim
        if (
            claim.owner != PINNED_OWNER
            or claim.repository != PINNED_REPOSITORY
            or claim.commit_oid != PINNED_COMMIT
            or claim.tree_oid != PINNED_TREE
            or claim.content_digest != PINNED_CONTENT_DIGEST
            or claim.evidence_origin != "github_codeload_archive"
            or not claim.full_snapshot
            or len(snapshot.files) != PINNED_FILE_COUNT
            or type(snapshot.verified_commit_object) is not GitCommitObject
            or snapshot.verified_commit_object.commit_oid != PINNED_COMMIT
            or snapshot.verified_commit_object.tree_oid != PINNED_TREE
        ):
            raise ValueError
        route = next(blob for blob in snapshot.files if blob.path == _ROUTE_PATH)
        if route.content_digest != _ROUTE_SHA256:
            raise ValueError
        return snapshot
    except Exception:
        raise R5SnapshotError("R5 snapshot: pinned source rejected") from None
