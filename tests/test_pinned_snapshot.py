from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import app_contracts.pinned_snapshot as pinned_snapshot_module
from app_contracts.pinned_snapshot import (
    PinnedSnapshot,
    export_local_commit_tree,
    open_local_repository,
    resolve_local_commit,
)


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


class _LocalGitRepositoryTestSupport:
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


class LocalGitRepositoryPreflightTests(_LocalGitRepositoryTestSupport, unittest.TestCase):

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


class LocalCommitResolutionTests(_LocalGitRepositoryTestSupport, unittest.TestCase):
    def test_resolves_an_exact_full_commit_oid_from_local_objects(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_path = self._create_repository(Path(temporary_directory))
            repository = open_local_repository(repository_path)
            commit_oid = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(resolve_local_commit(repository, commit_oid), commit_oid)

    def test_rejects_symbolic_abbreviated_missing_and_non_commit_objects(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_path = self._create_repository(Path(temporary_directory))
            repository = open_local_repository(repository_path)
            tree_oid = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD^{tree}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            commit_oid = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            for invalid in ("HEAD", commit_oid[:12], "f" * 40, tree_oid):
                with self.subTest(input_kind="symbolic" if invalid == "HEAD" else "object"):
                    with self.assertRaises(ValueError) as raised:
                        resolve_local_commit(repository, invalid)
                    self.assertNotIn(invalid, str(raised.exception))

    def test_resolver_uses_only_exact_commit_object_query(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_path = self._create_repository(Path(temporary_directory))
            local_repository = open_local_repository(repository_path)
            commit_oid = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            with patch(
                "app_contracts.pinned_snapshot.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, commit_oid + "\n", ""),
            ) as run:
                resolved = resolve_local_commit(local_repository, commit_oid)

        self.assertEqual(resolved, commit_oid)
        command = run.call_args.args[0]
        self.assertEqual(
            command[3:],
            ["rev-parse", "--verify", "--end-of-options", f"{commit_oid}^{{commit}}"],
        )


class LocalCommitExportTests(_LocalGitRepositoryTestSupport, unittest.TestCase):
    def test_export_uses_exact_commit_blobs_and_ignores_worktree_changes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository_path = self._create_repository(root)
            attributes = repository_path / ".gitattributes"
            version_file = repository_path / "version.txt"
            attributes.write_text("version.txt export-subst\n", encoding="utf-8")
            version_file.write_text("$Format:%H$\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repository_path), "add", ".gitattributes", "version.txt"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(repository_path), "-c", "user.name=Snapshot Test",
                    "-c", "user.email=snapshot@example.invalid", "commit", "--quiet", "-m",
                    "add snapshot fixture",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            repository = open_local_repository(repository_path)
            commit_oid = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            version_file.write_text("dirty worktree content\n", encoding="utf-8")
            untracked_file = repository_path / "untracked.txt"
            untracked_file.write_text("untracked content\n", encoding="utf-8")
            status_before = subprocess.run(
                ["git", "-C", str(repository_path), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            head_before = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            destination_parent = root / "exports"
            destination_parent.mkdir()

            exported = export_local_commit_tree(repository, commit_oid, destination_parent)

            self.assertEqual(
                (exported / "version.txt").read_text(encoding="utf-8"), "$Format:%H$\n"
            )
            self.assertFalse((exported / "untracked.txt").exists())
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(repository_path), "status", "--porcelain"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout,
                status_before,
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout,
                head_before,
            )

    def test_export_rejects_invalid_destination_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository_path = self._create_repository(root)
            repository = open_local_repository(repository_path)
            commit_oid = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            missing_parent = root / "missing-parent"

            with self.assertRaisesRegex(ValueError, "^pinned snapshot destination is invalid$"):
                export_local_commit_tree(repository, commit_oid, missing_parent)
            self.assertFalse(missing_parent.exists())


class PinnedTreeSafetyTests(_LocalGitRepositoryTestSupport, unittest.TestCase):
    def test_export_rejects_symlink_entries_without_following_them(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository_path = self._create_repository(root)
            (repository_path / "link.txt").symlink_to(root / "outside.txt")
            subprocess.run(
                ["git", "-C", str(repository_path), "add", "link.txt"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(repository_path), "-c", "user.name=Snapshot Test",
                    "-c", "user.email=snapshot@example.invalid", "commit", "--quiet", "-m",
                    "add symlink",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            repository = open_local_repository(repository_path)
            commit_oid = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            destination_parent = root / "exports"
            destination_parent.mkdir()

            with self.assertRaisesRegex(ValueError, "^pinned snapshot export failed$"):
                export_local_commit_tree(repository, commit_oid, destination_parent)

            self.assertFalse((root / "outside.txt").exists())
            self.assertEqual(list(destination_parent.iterdir()), [])

    def test_export_rejects_gitlink_without_initializing_submodule(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            module_path = self._create_repository(root / "module-parent")
            outer_path = self._create_repository(root / "outer-parent")
            module_oid = subprocess.run(
                ["git", "-C", str(module_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(outer_path), "update-index", "--add", "--cacheinfo", f"160000,{module_oid},module"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(outer_path), "-c", "user.name=Snapshot Test",
                    "-c", "user.email=snapshot@example.invalid", "commit", "--quiet", "-m",
                    "add gitlink",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            repository = open_local_repository(outer_path)
            commit_oid = subprocess.run(
                ["git", "-C", str(outer_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            destination_parent = root / "exports"
            destination_parent.mkdir()

            with self.assertRaisesRegex(ValueError, "^pinned snapshot export failed$"):
                export_local_commit_tree(repository, commit_oid, destination_parent)

            self.assertEqual(list(destination_parent.iterdir()), [])

    def test_export_rejects_traversal_path_before_outside_write(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository_path = self._create_repository(root)
            repository = open_local_repository(repository_path)
            commit_oid = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            destination_parent = root / "exports"
            destination_parent.mkdir()
            malicious_listing = f"100644 blob {'a' * 40}\t../../outside.txt\0".encode()
            original = pinned_snapshot_module._run_local_git_bytes

            def with_malicious_listing(path, arguments):
                if arguments[0] == "ls-tree":
                    return malicious_listing
                return original(path, arguments)

            with patch(
                "app_contracts.pinned_snapshot._run_local_git_bytes",
                side_effect=with_malicious_listing,
            ):
                with self.assertRaisesRegex(ValueError, "^pinned snapshot export failed$"):
                    export_local_commit_tree(repository, commit_oid, destination_parent)

            self.assertFalse((root / "outside.txt").exists())
            self.assertEqual(list(destination_parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
