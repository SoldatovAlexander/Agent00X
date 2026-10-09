from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from app_contracts.github_commit_signature import (
    GitCommitSignatureError,
    primary_fingerprint_from_armored_public_key,
    verify_git_commit_signature,
)
from app_contracts.github_snapshot import GitHubCommitClaim


def _run(command, *, env, input_bytes=None):
    return subprocess.run(
        command,
        input=input_bytes,
        cwd=env["TEST_TMP"],
        env={key: value for key, value in env.items() if key != "TEST_TMP"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=True,
        shell=False,
    ).stdout


class GitCommitSignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gpg = shutil.which("gpg")
        git = shutil.which("git")
        if not gpg or not git:
            raise unittest.SkipTest("GPG and Git executables are required")
        cls.gpg = str(Path(gpg).resolve())
        cls.git = str(Path(git).resolve())
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="agent00x-synthetic-commit-signature-test-"
        )
        cls.root = Path(cls.temporary.name)
        cls.signing_temporary = tempfile.TemporaryDirectory(
            prefix="a0g-", dir="/tmp" if Path("/tmp").is_dir() else None
        )
        cls.signing_home = Path(cls.signing_temporary.name)
        cls.repository = cls.root / "signed-fixture.git"
        base_environment = {
            "HOME": str(cls.root),
            "GNUPGHOME": str(cls.signing_home),
            "PATH": os.pathsep.join(
                (str(Path(cls.gpg).parent), str(Path(cls.git).parent), os.defpath)
            ),
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
        cls._test_environment = {**base_environment, "TEST_TMP": str(cls.root)}
        generated = subprocess.run(
            [
                cls.gpg,
                "--batch",
                "--no-tty",
                "--no-options",
                "--homedir",
                str(cls.signing_home),
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                "Agent00X Synthetic Test <synthetic@example.invalid>",
                "ed25519",
                "sign",
                "0",
            ],
            cwd=cls.root,
            env=base_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
            shell=False,
        )
        if generated.returncode != 0:
            raise RuntimeError(generated.stderr.decode("utf-8", errors="replace"))
        key_listing = subprocess.run(
            [
                cls.gpg,
                "--batch",
                "--no-tty",
                "--no-options",
                "--homedir",
                str(cls.signing_home),
                "--with-colons",
                "--fingerprint",
                "--list-keys",
            ],
            cwd=cls.root,
            env=base_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
            shell=False,
        ).stdout
        cls.fingerprint = next(
            line.split(b":")[9].decode("ascii")
            for line in key_listing.splitlines()
            if line.startswith(b"fpr:")
        )
        cls.public_key = subprocess.run(
            [
                cls.gpg,
                "--batch",
                "--no-tty",
                "--no-options",
                "--homedir",
                str(cls.signing_home),
                "--armor",
                "--export",
                cls.fingerprint,
            ],
            cwd=cls.root,
            env=base_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
            shell=False,
        ).stdout
        subprocess.run(
            [cls.git, "init", "--bare", "--quiet", "--template=", str(cls.repository)],
            cwd=cls.root,
            env=base_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
            shell=False,
        )
        cls.tree_oid = _run(
            [cls.git, "-C", str(cls.repository), "mktree"],
            env=cls._test_environment,
            input_bytes=b"",
        ).strip().decode("ascii")
        cls.commit_oid = _run(
            [
                cls.git,
                "-C",
                str(cls.repository),
                "-c",
                "user.name=Agent00X Synthetic Test",
                "-c",
                "user.email=synthetic@example.invalid",
                "-c",
                f"user.signingkey={cls.fingerprint}",
                "-c",
                f"gpg.program={cls.gpg}",
                "-c",
                "gpg.format=openpgp",
                "commit-tree",
                "--gpg-sign",
                cls.tree_oid,
                "-m",
                "synthetic test commit",
            ],
            env=cls._test_environment,
        ).strip().decode("ascii")
        cls.raw_commit = _run(
            [cls.git, "-C", str(cls.repository), "cat-file", "commit", cls.commit_oid],
            env=cls._test_environment,
        )
        cls.claim = GitHubCommitClaim(
            owner="fixture-owner",
            repository="fixture-repository",
            commit_oid=cls.commit_oid,
            tree_oid=cls.tree_oid,
        )

    @classmethod
    def tearDownClass(cls):
        cls.signing_temporary.cleanup()
        cls.temporary.cleanup()

    def verify(self, **overrides):
        parameters = {
            "claim": self.claim,
            "raw_commit": self.raw_commit,
            "armored_public_key": self.public_key,
            "expected_primary_fingerprint": self.fingerprint,
            "git_executable": self.git,
            "gpg_executable": self.gpg,
        }
        parameters.update(overrides)
        return verify_git_commit_signature(**parameters)

    def test_valid_signature_is_bound_to_exact_commit_tree_and_pinned_key(self):
        proof = self.verify()

        self.assertEqual(proof.commit_oid, self.claim.commit_oid)
        self.assertEqual(proof.tree_oid, self.claim.tree_oid)
        self.assertEqual(proof.primary_fingerprint, self.fingerprint)
        self.assertTrue(proof.signature_valid)
        self.assertFalse(proof.identity_authenticated)
        self.assertFalse(proof.independent_transport_trust_established)

    def test_public_fingerprint_read_does_not_require_key_import(self):
        self.assertEqual(
            primary_fingerprint_from_armored_public_key(
                self.public_key, gpg_executable=self.gpg
            ),
            self.fingerprint,
        )

    def test_wrong_pinned_fingerprint_is_rejected_without_detail_leak(self):
        wrong_fingerprint = "0" * 40
        if wrong_fingerprint == self.fingerprint:
            wrong_fingerprint = "1" * 40
        with self.assertRaises(GitCommitSignatureError) as raised:
            self.verify(expected_primary_fingerprint=wrong_fingerprint)
        self.assertEqual(str(raised.exception), "github commit signature: verification failed")
        self.assertNotIn(self.fingerprint, str(raised.exception))

    def test_wrong_public_key_is_rejected(self):
        other_temporary = tempfile.TemporaryDirectory(
            prefix="a0o-", dir="/tmp" if Path("/tmp").is_dir() else None
        )
        self.addCleanup(other_temporary.cleanup)
        other_home = Path(other_temporary.name)
        environment = {
            "HOME": str(self.root),
            "GNUPGHOME": str(other_home),
            "PATH": os.pathsep.join((str(Path(self.gpg).parent), os.defpath)),
            "LANG": "C",
            "LC_ALL": "C",
        }
        subprocess.run(
            [
                self.gpg,
                "--batch",
                "--no-tty",
                "--no-options",
                "--homedir",
                str(other_home),
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                "Agent00X Other Synthetic Test <other@example.invalid>",
                "ed25519",
                "sign",
                "0",
            ],
            cwd=self.root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=True,
            shell=False,
        )
        other_key = subprocess.run(
            [
                self.gpg,
                "--batch",
                "--no-tty",
                "--no-options",
                "--homedir",
                str(other_home),
                "--armor",
                "--export",
            ],
            cwd=self.root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
            shell=False,
        ).stdout
        other_listing = subprocess.run(
            [
                self.gpg,
                "--batch",
                "--no-tty",
                "--no-options",
                "--homedir",
                str(other_home),
                "--with-colons",
                "--fingerprint",
                "--list-keys",
            ],
            cwd=self.root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
            shell=False,
        ).stdout
        other_fingerprint = next(
            line.split(b":")[9].decode("ascii")
            for line in other_listing.splitlines()
            if line.startswith(b"fpr:")
        )
        with self.assertRaises(GitCommitSignatureError):
            self.verify(
                armored_public_key=other_key,
                expected_primary_fingerprint=other_fingerprint,
            )

    def test_altered_object_and_unsigned_object_are_rejected(self):
        with self.assertRaises(GitCommitSignatureError):
            self.verify(raw_commit=self.raw_commit + b"altered")

        unsigned_oid = _run(
            [
                self.git,
                "-C",
                str(self.repository),
                "-c",
                "user.name=Agent00X Synthetic Test",
                "-c",
                "user.email=synthetic@example.invalid",
                "commit-tree",
                self.tree_oid,
                "-m",
                "synthetic unsigned commit",
            ],
            env=self._test_environment,
        ).strip().decode("ascii")
        unsigned_raw = _run(
            [self.git, "-C", str(self.repository), "cat-file", "commit", unsigned_oid],
            env=self._test_environment,
        )
        unsigned_claim = GitHubCommitClaim(
            owner="fixture-owner",
            repository="fixture-repository",
            commit_oid=unsigned_oid,
            tree_oid=self.tree_oid,
        )
        with self.assertRaises(GitCommitSignatureError):
            self.verify(claim=unsigned_claim, raw_commit=unsigned_raw)

    def test_operation_deadline_is_enforced(self):
        with self.assertRaises(GitCommitSignatureError):
            self.verify(timeout_seconds=0.0001)


if __name__ == "__main__":
    unittest.main()
