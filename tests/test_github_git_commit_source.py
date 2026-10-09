from __future__ import annotations

from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.brainbooster_target_profile import (
    PINNED_COMMIT,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
)
from app_contracts.github_snapshot import GitHubCommitClaim, GitCommitObject
from app_contracts.github_git_commit_source import (
    GitCommitObjectSourceError,
    GitHubRawCommitObjectSource,
)
import app_contracts.github_git_commit_source as source_module


class GitHubRawCommitObjectSourceTests(unittest.TestCase):
    def setUp(self):
        self.claim = GitHubCommitClaim(
            owner=PINNED_OWNER,
            repository=PINNED_REPOSITORY,
            commit_oid=PINNED_COMMIT,
            tree_oid=PINNED_TREE,
        )
        self.source = GitHubRawCommitObjectSource("/usr/bin/git")

    def test_source_requires_absolute_executable_and_bounded_timeout(self):
        for executable, timeout in (("git", 15), ("/usr/bin/git", 30.1)):
            with self.subTest(executable=executable, timeout=timeout):
                with self.assertRaisesRegex(
                    GitCommitObjectSourceError,
                    "^github commit source: configuration is invalid$",
                ):
                    GitHubRawCommitObjectSource(
                        executable, timeout_seconds=timeout
                    )

    def test_unpinned_claim_fails_before_subprocess(self):
        claim = GitHubCommitClaim(
            owner=PINNED_OWNER,
            repository=PINNED_REPOSITORY,
            commit_oid="a" * 40,
            tree_oid=PINNED_TREE,
        )
        with patch.object(source_module.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(
                GitCommitObjectSourceError,
                "^github commit source: claim is invalid$",
            ):
                self.source(claim)
        popen.assert_not_called()

    def test_fetch_uses_only_pinned_depth_limited_anonymous_command(self):
        raw_commit = b"synthetic commit bytes"
        expected = GitCommitObject(PINNED_COMMIT, PINNED_TREE)
        run_calls = []

        def fake_run(*args, **kwargs):
            arguments = args[-1]
            run_calls.append((arguments, kwargs))
            if "fetch" in arguments:
                return b""
            if "count-objects" in arguments:
                return b"count: 0\nin-pack: 1\npacks: 1\n"
            if "-s" in arguments:
                return f"{len(raw_commit)}\n".encode("ascii")
            if "cat-file" in arguments:
                return raw_commit
            return b""

        with (
            patch.object(
                GitHubRawCommitObjectSource, "_run_git", side_effect=fake_run
            ),
            patch.object(GitHubRawCommitObjectSource, "_validate_pack_sizes"),
            patch.object(
                source_module, "parse_git_commit_object", return_value=expected
            ) as parser,
        ):
            result = self.source(self.claim)

        self.assertEqual(result, raw_commit)
        parser.assert_called_once_with(self.claim, raw_commit)
        fetch_arguments = next(
            arguments for arguments, _kwargs in run_calls if "fetch" in arguments
        )
        self.assertEqual(
            fetch_arguments[fetch_arguments.index("fetch") + 1 :],
            [
                "--no-tags",
                "--no-recurse-submodules",
                "--depth=1",
                source_module._REMOTE_URL,
                PINNED_COMMIT,
            ],
        )
        self.assertFalse(
            any(argument.startswith("--filter=") for argument in fetch_arguments)
        )
        self.assertIn("credential.helper=", fetch_arguments)
        self.assertIn("http.followRedirects=false", fetch_arguments)
        self.assertIn("protocol.allow=never", fetch_arguments)
        self.assertIn("protocol.https.allow=always", fetch_arguments)
        self.assertIn("protocol.version=2", fetch_arguments)
        self.assertNotIn("credential", repr(self.source).lower())
        self.assertFalse(run_calls[0][1]["cwd"].exists())

    def test_init_failure_is_sanitized_and_does_not_expose_child_output(self):
        details = "PRIVATE-STderr-CANARY"
        with (
            patch.object(
                GitHubRawCommitObjectSource,
                "_run_git",
                side_effect=source_module._GitProcessFailure(23),
            ),
            patch.object(GitHubRawCommitObjectSource, "_validate_pack_sizes"),
        ):
            with self.assertRaisesRegex(
                GitCommitObjectSourceError,
                r"^github commit source: init failed \(exit 23\)$",
            ) as raised:
                self.source(self.claim)
        self.assertNotIn(details, str(raised.exception))
        self.assertEqual(raised.exception.exit_code, 23)

    def test_only_one_commit_pack_and_object_are_accepted(self):
        self.source._validate_object_count(b"count: 0\nin-pack: 4\npacks: 1\n")
        with self.assertRaises(ValueError):
            self.source._validate_object_count(b"count: 0\nin-pack: 129\npacks: 1\n")
        with self.assertRaises(ValueError):
            self.source._validate_object_count(b"in-pack: 1\npacks: 2\n")
        self.source._validate_object_count(b"count: 0\nin-pack: 1\npacks: 1\n")

    def test_pack_and_commit_object_limits_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="git-pack-bound-test-") as root:
            repository = Path(root) / "objects.git"
            pack_directory = repository / "objects" / "pack"
            pack_directory.mkdir(parents=True)
            (pack_directory / ("a" * 40 + ".pack")).write_bytes(
                b"x" * (source_module._MAX_FETCH_PACK_BYTES + 1)
            )
            with self.assertRaises(ValueError):
                self.source._validate_pack_sizes(repository)

        for invalid in (b"0\n", b"1000001\n", b"01\n", b"size\n"):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    self.source._parse_object_size(invalid)

    def test_git_process_timeout_is_killed_and_waited(self):
        class HangingProcess:
            returncode = None

            def __init__(self):
                self.killed = False
                self.waited = False

            def communicate(self, timeout):
                raise subprocess.TimeoutExpired("git", timeout)

            def kill(self):
                self.killed = True
                self.returncode = -9

            def wait(self):
                self.waited = True
                return self.returncode

            def poll(self):
                return self.returncode

        process = HangingProcess()
        with tempfile.TemporaryDirectory(prefix="git-timeout-test-") as root:
            with patch.object(
                source_module.subprocess, "Popen", return_value=process
            ) as popen:
                with self.assertRaises(TimeoutError):
                    self.source._run_git(
                        ["status"],
                        cwd=Path(root),
                        environment={"HOME": root},
                        resource_module=type(
                            "Resource", (),
                            {
                                "RLIMIT_FSIZE": 1,
                                "setrlimit": staticmethod(lambda *_args: None),
                            },
                        ),
                        deadline=source_module.time.monotonic() + 1,
                        capture_stdout=False,
                    )
        self.assertTrue(process.killed)
        self.assertTrue(process.waited)
        self.assertIs(popen.call_args.kwargs["shell"], False)
        self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
