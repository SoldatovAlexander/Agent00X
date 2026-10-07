from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
)
from app_contracts.pinned_snapshot import SNAPSHOT_DIGEST_CANONICALIZATION
from app_contracts.remote_snapshot_workspace import (
    MaterializedGitHubSnapshot,
    RemoteSnapshotWorkspaceError,
    materialize_github_snapshot,
)
import app_contracts.remote_snapshot_workspace as workspace_module


class RemoteSnapshotWorkspaceTests(unittest.TestCase):
    @staticmethod
    def make_snapshot() -> GitHubSnapshotContents:
        raw_files = (
            ("README.md", "100644", b"WORKSPACE-CANARY-SOURCE\n"),
            ("scripts/run.sh", "100755", b"#!/bin/sh\nexit 0\n"),
        )
        blobs = tuple(
            GitHubBlobClaim(
                path=path,
                mode=mode,
                sha=hashlib.sha1(
                    b"blob " + str(len(content)).encode("ascii") + b"\0" + content
                ).hexdigest(),
                size=len(content),
                content=content,
                content_digest=sha256_bytes(content),
            )
            for path, mode, content in raw_files
        )
        aggregate_digest = sha256_digest(
            {
                "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
                "files": [
                    {
                        "path": path,
                        "content_digest": sha256_bytes(content),
                        "mode": mode,
                    }
                    for path, mode, content in raw_files
                ],
            }
        )
        claim = GitHubSnapshotClaim(
            owner="fixture-owner",
            repository="fixture-repository",
            commit_oid="a" * 40,
            tree_oid="b" * 40,
            content_digest=aggregate_digest,
        )
        return GitHubSnapshotContents(claim=claim, files=blobs)

    def test_materializes_exact_nested_bytes_and_git_modes_read_only(self):
        snapshot = self.make_snapshot()
        with materialize_github_snapshot(snapshot) as workspace:
            self.assertIsInstance(workspace, MaterializedGitHubSnapshot)
            self.assertEqual(workspace.snapshot, snapshot)
            root = workspace.path
            files = tuple(sorted(path for path in root.rglob("*") if path.is_file()))
            self.assertEqual(
                tuple(path.relative_to(root).as_posix() for path in files),
                ("README.md", "scripts/run.sh"),
            )
            self.assertEqual(files[0].read_bytes(), snapshot.files[0].content)
            self.assertEqual(files[1].read_bytes(), snapshot.files[1].content)
            self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(files[1].stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE((root / "scripts").stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o555)
            for path in (root, root / "scripts", *files):
                self.assertFalse(path.is_symlink())
            serialized = repr(workspace)
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("WORKSPACE-CANARY-SOURCE", serialized)
        self.assertTrue(workspace.closed)
        self.assertFalse(root.exists())

    def test_materializes_selected_snapshot_without_losing_partial_scope(self):
        complete = self.make_snapshot()
        selected_files = (complete.files[0],)
        selected_claim = GitHubSnapshotClaim(
            owner=complete.claim.owner,
            repository=complete.claim.repository,
            commit_oid=complete.claim.commit_oid,
            tree_oid=complete.claim.tree_oid,
            content_digest=sha256_digest(
                {
                    "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
                    "files": [
                        {
                            "path": selected_files[0].path,
                            "content_digest": selected_files[0].content_digest,
                            "mode": selected_files[0].mode,
                        }
                    ],
                }
            ),
            selected_paths=(selected_files[0].path,),
        )
        selected = GitHubSnapshotContents(selected_claim, selected_files)

        with materialize_github_snapshot(selected) as workspace:
            self.assertEqual(workspace.snapshot.claim.selected_paths, ("README.md",))
            self.assertEqual(tuple(blob.path for blob in workspace.snapshot.files), ("README.md",))

    def test_close_is_idempotent_and_closed_handle_rejects_access(self):
        workspace = materialize_github_snapshot(self.make_snapshot())
        root = workspace.path
        workspace.close()
        workspace.close()
        self.assertTrue(workspace.closed)
        self.assertFalse(root.exists())
        with self.assertRaisesRegex(
            RemoteSnapshotWorkspaceError,
            "^remote snapshot workspace: lease is closed$",
        ):
            _ = workspace.path
        with self.assertRaisesRegex(
            RemoteSnapshotWorkspaceError,
            "^remote snapshot workspace: lease is closed$",
        ):
            _ = workspace.snapshot

    def test_rejects_wrong_type_without_creating_a_workspace(self):
        with patch.object(
            workspace_module.tempfile,
            "TemporaryDirectory",
            side_effect=AssertionError("no temporary directory expected"),
        ):
            with self.assertRaisesRegex(
                RemoteSnapshotWorkspaceError,
                "^remote snapshot workspace: input is invalid$",
            ):
                materialize_github_snapshot(object())

    def test_tampered_or_duplicate_content_is_rejected_before_temp_creation(self):
        actual_temporary_directory = tempfile.TemporaryDirectory
        created: list[Path] = []

        def tracking_temporary_directory(*args, **kwargs):
            directory = actual_temporary_directory(*args, **kwargs)
            created.append(Path(directory.name))
            return directory

        snapshot = self.make_snapshot()
        object.__setattr__(snapshot.files[0], "content", b"tampered\n")
        with patch.object(
            workspace_module.tempfile,
            "TemporaryDirectory",
            side_effect=tracking_temporary_directory,
        ):
            with self.assertRaisesRegex(
                RemoteSnapshotWorkspaceError,
                "^remote snapshot workspace: input is invalid$",
            ):
                materialize_github_snapshot(snapshot)
        self.assertEqual(created, [])

        duplicate = self.make_snapshot()
        object.__setattr__(duplicate, "files", (duplicate.files[0], duplicate.files[0]))
        with patch.object(
            workspace_module.tempfile,
            "TemporaryDirectory",
            side_effect=tracking_temporary_directory,
        ):
            with self.assertRaisesRegex(
                RemoteSnapshotWorkspaceError,
                "^remote snapshot workspace: input is invalid$",
            ):
                materialize_github_snapshot(duplicate)
        self.assertEqual(created, [])

    def test_unsafe_mutated_path_is_rejected_before_any_filesystem_write(self):
        snapshot = self.make_snapshot()
        object.__setattr__(snapshot.files[0], "path", "../WORKSPACE-ESCAPE-CANARY")
        with tempfile.TemporaryDirectory() as parent:
            outside_path = Path(parent) / "WORKSPACE-ESCAPE-CANARY"
            with self.assertRaisesRegex(
                RemoteSnapshotWorkspaceError,
                "^remote snapshot workspace: input is invalid$",
            ):
                materialize_github_snapshot(snapshot)
            self.assertFalse(outside_path.exists())

    def test_credential_shaped_tampering_is_rejected_before_temp_creation(self):
        snapshot = self.make_snapshot()
        suspicious = b'password = "synthetic-password-value"\n'
        first = snapshot.files[0]
        object.__setattr__(first, "content", suspicious)
        object.__setattr__(first, "size", len(suspicious))
        object.__setattr__(
            first,
            "sha",
            hashlib.sha1(
                b"blob " + str(len(suspicious)).encode("ascii") + b"\0" + suspicious
            ).hexdigest(),
        )
        object.__setattr__(first, "content_digest", sha256_bytes(suspicious))
        object.__setattr__(
            snapshot.claim,
            "content_digest",
            sha256_digest(
                {
                    "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
                    "files": [
                        {
                            "path": blob.path,
                            "content_digest": blob.content_digest,
                            "mode": blob.mode,
                        }
                        for blob in snapshot.files
                    ],
                }
            ),
        )
        actual_temporary_directory = tempfile.TemporaryDirectory
        created: list[Path] = []

        def tracking_temporary_directory(*args, **kwargs):
            directory = actual_temporary_directory(*args, **kwargs)
            created.append(Path(directory.name))
            return directory

        with patch.object(
            workspace_module.tempfile,
            "TemporaryDirectory",
            side_effect=tracking_temporary_directory,
        ):
            with self.assertRaisesRegex(
                RemoteSnapshotWorkspaceError,
                "^remote snapshot workspace: input is invalid$",
            ) as raised:
                materialize_github_snapshot(snapshot)
        self.assertNotIn(suspicious.decode().strip(), str(raised.exception))
        self.assertEqual(created, [])

    def test_materialization_failure_cleans_partial_root(self):
        actual_temporary_directory = tempfile.TemporaryDirectory
        created: list[Path] = []

        def tracking_temporary_directory(*args, **kwargs):
            directory = actual_temporary_directory(*args, **kwargs)
            created.append(Path(directory.name))
            return directory

        with (
            patch.object(
                workspace_module.tempfile,
                "TemporaryDirectory",
                side_effect=tracking_temporary_directory,
            ),
            patch.object(
                workspace_module,
                "_verify_materialized_tree",
                side_effect=OSError("synthetic verification failure"),
            ),
        ):
            with self.assertRaisesRegex(
                RemoteSnapshotWorkspaceError,
                "^remote snapshot workspace: materialization failed$",
            ) as raised:
                materialize_github_snapshot(self.make_snapshot())
        self.assertNotIn("synthetic verification failure", str(raised.exception))
        self.assertNotIn("WORKSPACE-CANARY-SOURCE", str(raised.exception))
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].exists())


if __name__ == "__main__":
    unittest.main()
