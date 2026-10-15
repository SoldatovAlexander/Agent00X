from __future__ import annotations

import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.github_snapshot import (
    GitCommitObject,
    GitHubBlobClaim,
    GitHubCommitClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
)
from app_contracts.pinned_snapshot import SNAPSHOT_DIGEST_CANONICALIZATION
from scripts import r5_pinned_snapshot
from scripts.r5_pinned_snapshot import R5SnapshotError, read_pinned_r5_snapshot


ROOT = Path(__file__).resolve().parents[1]
ROUTE_BYTES = (ROOT / "fixtures/experiments/r5-pinned-backend-routes.py").read_bytes()
OWNER = "FixtureOwner"
REPOSITORY = "r5-fixture"
COMMIT = "a" * 40
TREE = "b" * 40


def _snapshot(*, commit: str = COMMIT, tree: str = TREE, route: bytes = ROUTE_BYTES):
    blob = GitHubBlobClaim(
        path="backend/routes.py",
        mode="100644",
        sha=hashlib.sha1(
            b"blob " + str(len(route)).encode("ascii") + b"\0" + route
        ).hexdigest(),
        size=len(route),
        content=route,
        content_digest=sha256_bytes(route),
        evidence_origin="github_codeload_archive",
    )
    content_digest = sha256_digest(
        {
            "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
            "files": [
                {
                    "path": blob.path,
                    "content_digest": blob.content_digest,
                    "mode": blob.mode,
                }
            ],
        }
    )
    return GitHubSnapshotContents(
        claim=GitHubSnapshotClaim(
            owner=OWNER,
            repository=REPOSITORY,
            commit_oid=commit,
            tree_oid=tree,
            content_digest=content_digest,
            evidence_origin="github_codeload_archive",
        ),
        files=(blob,),
    )


class R5PinnedSnapshotTests(unittest.TestCase):
    def _pin_patches(self, snapshot):
        return (
            patch.object(r5_pinned_snapshot, "PINNED_OWNER", OWNER),
            patch.object(r5_pinned_snapshot, "PINNED_REPOSITORY", REPOSITORY),
            patch.object(r5_pinned_snapshot, "PINNED_COMMIT", snapshot.claim.commit_oid),
            patch.object(r5_pinned_snapshot, "PINNED_TREE", snapshot.claim.tree_oid),
            patch.object(
                r5_pinned_snapshot,
                "PINNED_CONTENT_DIGEST",
                snapshot.claim.content_digest,
            ),
            patch.object(r5_pinned_snapshot, "PINNED_FILE_COUNT", len(snapshot.files)),
        )

    def test_delegates_to_codeload_and_verifies_raw_commit_object(self) -> None:
        snapshot = _snapshot()
        transport = lambda *_args, **_kwargs: None
        source_claims = []

        def commit_source(claim):
            source_claims.append(claim)
            return b"raw commit object"

        proof = GitCommitObject(COMMIT, TREE)
        patches = self._pin_patches(snapshot)
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
            patch(
                "scripts.r5_pinned_snapshot.read_github_archive_snapshot_contents",
                return_value=snapshot,
            ) as reader,
            patch(
                "scripts.r5_pinned_snapshot.parse_git_commit_object",
                return_value=proof,
            ) as verifier,
        ):
            result = read_pinned_r5_snapshot(
                transport=transport, commit_object_source=commit_source
            )

        self.assertIs(type(result), GitHubSnapshotContents)
        self.assertEqual(result.claim, snapshot.claim)
        self.assertEqual(result.files, snapshot.files)
        self.assertEqual(result.verified_commit_object, proof)
        self.assertEqual(reader.call_count, 1)
        request = reader.call_args.args[0]
        self.assertEqual(request.owner, OWNER)
        self.assertEqual(request.repository, REPOSITORY)
        self.assertEqual(request.commit_oid, COMMIT)
        self.assertIs(reader.call_args.args[1], transport)
        self.assertEqual(request.tree_oid, TREE)
        self.assertEqual(request.content_digest, snapshot.claim.content_digest)
        self.assertEqual(request.file_count, 1)
        self.assertEqual(verifier.call_count, 1)
        self.assertIs(type(verifier.call_args.args[0]), GitHubCommitClaim)
        self.assertEqual(verifier.call_args.args[0].commit_oid, COMMIT)
        self.assertEqual(source_claims, [verifier.call_args.args[0]])
        self.assertEqual(verifier.call_args.args[1], b"raw commit object")

    def test_rejects_wrong_commit_tree_and_route_digest(self) -> None:
        valid = _snapshot()
        mismatches = (
            _snapshot(commit="c" * 40),
            _snapshot(tree="d" * 40),
            _snapshot(route=ROUTE_BYTES + b"# changed\n"),
        )
        for snapshot in mismatches:
            patches = self._pin_patches(valid)
            with (
                patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
                patch(
                    "scripts.r5_pinned_snapshot.read_github_archive_snapshot_contents",
                    return_value=snapshot,
                ),
                patch(
                    "scripts.r5_pinned_snapshot.parse_git_commit_object",
                    return_value=GitCommitObject(snapshot.claim.commit_oid, snapshot.claim.tree_oid),
                ),
            ):
                with self.assertRaises(R5SnapshotError):
                    read_pinned_r5_snapshot(
                        transport=lambda *_args, **_kwargs: None,
                        commit_object_source=lambda _claim: b"raw commit object",
                    )

    def test_rejects_non_callable_transport_before_reader(self) -> None:
        snapshot = _snapshot()
        patches = self._pin_patches(snapshot)
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
            patch("scripts.r5_pinned_snapshot.read_github_archive_snapshot_contents") as reader,
        ):
            with self.assertRaises(R5SnapshotError):
                read_pinned_r5_snapshot(
                    transport=object(),
                    commit_object_source=lambda _claim: b"raw commit object",
                )
            reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
