from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.pinned_snapshot import PinnedSnapshot, open_local_repository


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


class LocalGitRepositoryPreflightTests(unittest.TestCase):
    def _create_repository(self, root: Path, *, bare: bool = False) -> Path:
        path = root / ("repo.git" if bare else "repo")
        path.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "init", "--quiet"]
        if bare:
            command.append("--bare")
        command.append(str(path))
        subprocess.run(command, check=True, capture_output=True, text=True)
        if not bare:
            subprocess.run(
                [
                    "git", "-C", str(path), "-c", "user.name=Snapshot Test",
                    "-c", "user.email=snapshot@example.invalid", "commit", "--allow-empty",
                    "--quiet", "-m", "initial",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        return path

    def test_preflight_accepts_worktree_and_resolves_repository_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = self._create_repository(root)
            nested = repository / "nested"
            nested.mkdir()

            result = open_local_repository(nested)

            self.assertEqual(result.root_path, repository.resolve())
            self.assertEqual(result.object_format, "sha1")
            self.assertNotIn(str(repository), repr(result))

    def test_preflight_accepts_bare_repository(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = self._create_repository(Path(temporary_directory), bare=True)

            result = open_local_repository(repository)

            self.assertEqual(result.root_path, repository.resolve())
            self.assertEqual(result.object_format, "sha1")

    def test_preflight_uses_only_allowlisted_read_only_local_git_arguments(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            outputs = ("false", "true", str(repository), "sha1")

            with patch("app_contracts.pinned_snapshot.subprocess.run") as run:
                run.side_effect = [
                    subprocess.CompletedProcess([], 0, output, "") for output in outputs
                ]
                open_local_repository(repository)

            invoked = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(invoked), 4)
            allowed = {
                ("rev-parse", "--is-bare-repository"),
                ("rev-parse", "--is-inside-work-tree"),
                ("rev-parse", "--show-toplevel"),
                ("rev-parse", "--show-object-format"),
            }
            for command in invoked:
                self.assertEqual(command[0], "git")
                self.assertEqual(command[1], "-C")
                self.assertIn(tuple(command[3:]), allowed)
                self.assertNotIn("remote", command)
                self.assertNotIn("fetch", command)
                self.assertNotIn("push", command)
                self.assertNotIn("https://", " ".join(command))

    def test_preflight_rejects_missing_and_non_repository_paths_safely(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for path in (root / "missing", root):
                with self.subTest(path_kind="missing" if not path.exists() else "non-repository"):
                    with self.assertRaises(ValueError) as raised:
                        open_local_repository(path)
                    self.assertNotIn(str(path), str(raised.exception))

        with self.assertRaisesRegex(ValueError, "^pinned snapshot repository path is invalid$"):
            open_local_repository("not-a-path")

    def test_preflight_failure_does_not_expose_git_stderr(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            with patch(
                "app_contracts.pinned_snapshot.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    ["git"], 128, "", "secret-token fake remote URL https://private.invalid"
                ),
            ):
                with self.assertRaises(ValueError) as raised:
                    open_local_repository(repository)

        self.assertNotIn("secret-token", str(raised.exception))
        self.assertNotIn("private.invalid", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
