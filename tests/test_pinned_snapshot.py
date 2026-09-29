from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.pinned_snapshot import PinnedSnapshot


class PinnedSnapshotRecordTests(unittest.TestCase):
    def test_record_carries_local_commit_tree_and_origin(self):
        snapshot = PinnedSnapshot(
            repository_id="repo-demo-001",
            commit_oid="a" * 40,
            tree_digest="sha256:" + "b" * 64,
            snapshot_path=Path("/private/tmp/snapshot-demo-001"),
        )

        self.assertEqual(snapshot.repository_id, "repo-demo-001")
        self.assertEqual(snapshot.commit_oid, "a" * 40)
        self.assertEqual(snapshot.tree_digest, "sha256:" + "b" * 64)
        self.assertEqual(snapshot.snapshot_path, Path("/private/tmp/snapshot-demo-001"))
        self.assertEqual(snapshot.evidence_origin, "local_git_commit")

    def test_record_is_immutable(self):
        snapshot = PinnedSnapshot(
            repository_id="repo-demo-001",
            commit_oid="a" * 40,
            tree_digest="sha256:" + "b" * 64,
            snapshot_path=Path("/private/tmp/snapshot-demo-001"),
        )

        with self.assertRaises(FrozenInstanceError):
            snapshot.commit_oid = "c" * 40

    def test_repr_hides_host_path_and_record_has_no_secret_capability_fields(self):
        host_path = "/private/tmp/snapshot-secret-host-path"
        snapshot = PinnedSnapshot(
            repository_id="repo-demo-001",
            commit_oid="a" * 40,
            tree_digest="sha256:" + "b" * 64,
            snapshot_path=Path(host_path),
        )

        self.assertNotIn(host_path, repr(snapshot))
        self.assertIn("repo-demo-001", repr(snapshot))
        self.assertEqual(
            {item.name for item in fields(PinnedSnapshot)},
            {"repository_id", "commit_oid", "tree_digest", "snapshot_path", "evidence_origin"},
        )

    def test_identity_validation_accepts_full_sha1_and_sha256_oids(self):
        for oid in ("a" * 40, "b" * 64):
            with self.subTest(oid_length=len(oid)):
                snapshot = PinnedSnapshot(
                    repository_id="org/repository-1",
                    commit_oid=oid,
                    tree_digest="sha256:" + "c" * 64,
                    snapshot_path=Path("/private/tmp/snapshot-valid"),
                )
                self.assertEqual(snapshot.commit_oid, oid)

    def test_identity_validation_rejects_malformed_values_without_echoing_them(self):
        valid = {
            "repository_id": "repo-demo-001",
            "commit_oid": "a" * 40,
            "tree_digest": "sha256:" + "b" * 64,
            "snapshot_path": Path("/private/tmp/snapshot-invalid"),
        }
        invalid_cases = (
            ("repository_id", "ssh://user:secret@host/repository"),
            ("repository_id", "../outside"),
            ("repository_id", "repo with spaces"),
            ("commit_oid", "HEAD"),
            ("commit_oid", "a" * 39),
            ("commit_oid", "A" * 40),
            ("commit_oid", 123),
            ("tree_digest", "sha256:" + "B" * 64),
            ("tree_digest", "sha256:short"),
            ("evidence_origin", "remote_git_commit"),
        )

        for field_name, invalid_value in invalid_cases:
            with self.subTest(field=field_name, value_type=type(invalid_value).__name__):
                arguments = dict(valid)
                arguments[field_name] = invalid_value
                with self.assertRaises(ValueError) as raised:
                    PinnedSnapshot(**arguments)
                self.assertNotIn(str(invalid_value), str(raised.exception))

    def test_identity_validation_rejects_boolean_and_non_path_values(self):
        with self.assertRaisesRegex(ValueError, "^pinned snapshot repository identity is invalid$"):
            PinnedSnapshot(
                repository_id=True,
                commit_oid="a" * 40,
                tree_digest="sha256:" + "b" * 64,
                snapshot_path=Path("/private/tmp/snapshot-invalid"),
            )
        with self.assertRaisesRegex(ValueError, "^pinned snapshot local path is invalid$"):
            PinnedSnapshot(
                repository_id="repo-demo-001",
                commit_oid="a" * 40,
                tree_digest="sha256:" + "b" * 64,
                snapshot_path="/private/tmp/snapshot-invalid",
            )


if __name__ == "__main__":
    unittest.main()
