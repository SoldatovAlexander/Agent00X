from __future__ import annotations

import hashlib
import importlib
import io
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import stream_pinned_verifier_host_bundle as transfer


class StreamPinnedVerifierHostBundleTests(unittest.TestCase):
    def _archive(self):
        from build_verifier_host_bundle import build_bundle

        return build_bundle()

    def _run_receiver(self, archive, *, home, digest=None, count=None, source_size=None):
        raw, actual_digest, actual_count, actual_source_size = archive
        args = [
            "remote-receiver",
            actual_digest if digest is None else digest,
            str(actual_count if count is None else count),
            str(actual_source_size if source_size is None else source_size),
            str(len(raw)),
            str(home / ".local/share/agent00x/verifier-host/exp-1491"),
        ]
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="ascii")
        stdout = io.StringIO()
        namespace = {"__name__": "__main__"}
        with (
            patch.object(sys, "argv", args),
            patch.object(sys, "stdin", stdin),
            patch.object(sys, "stdout", stdout),
            patch.object(pwd, "getpwuid", return_value=SimpleNamespace(pw_dir=str(home))),
        ):
            try:
                exec(compile(transfer._REMOTE_RECEIVER, "remote-receiver", "exec"), namespace)
            except SystemExit as exc:
                return exc.code, stdout.getvalue()
        return 0, stdout.getvalue()

    def test_real_bundle_stream_is_one_exact_ssh_call_with_bounded_collection(self):
        archive, digest, count, source_bytes = self._archive()
        process = object()
        output = io.StringIO()
        seen = {}

        def popen(argv, **kwargs):
            seen["argv"] = argv
            seen["kwargs"] = kwargs
            return process

        def collect(child, payload, **kwargs):
            self.assertIs(child, process)
            self.assertEqual(payload, archive)
            self.assertEqual(kwargs, {
                "stdout_cap": 256, "stderr_cap": 4096, "timeout_seconds": 90,
            })
            return transfer._EXPECTED_REMOTE, b"", 0

        with (
            patch.dict(os.environ, {"SSH_AUTH_SOCK": "/tmp/test-agent", "AI_PROCESS_API": "must-not-pass"}, clear=True),
            patch.object(transfer.subprocess, "Popen", side_effect=popen) as popen_mock,
            patch.object(transfer, "_collect_bounded_output", side_effect=collect),
        ):
            result = transfer.run_transfer(output=output)

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "BUNDLE_TRANSFER_CONFIRMED\n")
        self.assertEqual(digest, transfer.BUNDLE_SHA256)
        self.assertEqual(count, transfer.BUNDLE_MEMBER_COUNT)
        self.assertEqual(source_bytes, transfer.BUNDLE_SOURCE_BYTES)
        popen_mock.assert_called_once()
        self.assertEqual(
            seen["argv"],
            [
                "/usr/bin/ssh",
                *transfer._SSH_OPTIONS,
                transfer.TARGET_HOST,
                transfer._REMOTE_COMMAND,
            ],
        )
        self.assertEqual(seen["kwargs"]["executable"], "/usr/bin/ssh")
        self.assertFalse(seen["kwargs"]["shell"])
        self.assertIs(seen["kwargs"]["stdin"], subprocess.PIPE)
        self.assertIs(seen["kwargs"]["stdout"], subprocess.PIPE)
        self.assertIs(seen["kwargs"]["stderr"], subprocess.PIPE)
        self.assertEqual(seen["kwargs"]["env"], {
            "HOME": str(Path.home()),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "SSH_AUTH_SOCK": "/tmp/test-agent",
        })
        self.assertNotIn("AI_PROCESS_API", seen["kwargs"]["env"])

    def test_stale_local_bundle_fails_before_ssh(self):
        archive = self._archive()
        stale = (archive[0], "0" * 64, *archive[2:])
        output = io.StringIO()
        with patch.object(transfer.subprocess, "Popen") as popen:
            result = transfer.run_transfer(
                bundle_builder=lambda: stale,
                output=output,
            )
        self.assertEqual(result, 10)
        self.assertEqual(output.getvalue(), "BUNDLE_PIN_MISMATCH\n")
        popen.assert_not_called()

    def test_remote_receiver_verifies_and_extracts_only_into_fresh_private_target(self):
        archive = self._archive()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result, output = self._run_receiver(archive, home=home)
            target = home / ".local/share/agent00x/verifier-host/exp-1491"
            self.assertEqual(result, 0)
            self.assertEqual(
                output,
                f"HOST_BUNDLE_IMPORTED|sha256={archive[1]}|members={archive[2]}\n",
            )
            self.assertEqual(
                {
                    path.relative_to(target).as_posix()
                    for path in target.rglob("*")
                    if path.is_file()
                },
                set(self._source_names(archive)) | {"MANIFEST.json"},
            )
            self.assertEqual((target / "scripts/serve_ephemeral_signed_verifier_https.py").stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                hashlib.sha256((target / "MANIFEST.json").read_bytes()).hexdigest(),
                hashlib.sha256(self._manifest_bytes(archive)).hexdigest(),
            )

    def test_remote_receiver_rejects_digest_and_existing_target_without_overwrite(self):
        archive = self._archive()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result, output = self._run_receiver(archive, home=home, digest="0" * 64)
            self.assertEqual((result, output), (41, "HOST_BUNDLE_REJECTED\n"))
            self.assertFalse((home / ".local/share").exists())

            target = home / ".local/share/agent00x/verifier-host/exp-1491"
            target.mkdir(parents=True)
            sentinel = target / "preserve.txt"
            sentinel.write_text("keep", encoding="utf-8")
            result, output = self._run_receiver(archive, home=home)
            self.assertEqual((result, output), (41, "HOST_BUNDLE_REJECTED\n"))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_receiver_rejects_manifest_size_mismatch_before_creating_target(self):
        archive = self._archive()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result, output = self._run_receiver(
                archive,
                home=home,
                source_size=archive[3] - 1,
            )
            self.assertEqual((result, output), (41, "HOST_BUNDLE_REJECTED\n"))
            self.assertFalse((home / ".local/share").exists())

    def test_transport_failure_is_redacted_and_not_retried(self):
        output = io.StringIO()
        with (
            patch.object(transfer.subprocess, "Popen", side_effect=OSError("private host path")) as popen,
        ):
            result = transfer.run_transfer(output=output)
        self.assertEqual(result, 11)
        self.assertEqual(output.getvalue(), "SSH_OR_REMOTE_FAILED\n")
        popen.assert_called_once()
        self.assertNotIn("private host path", output.getvalue())

    def test_one_shot_gate_refuses_unconfirmed_input_before_build_or_ssh(self):
        output = io.StringIO()
        prompt = io.StringIO()
        with (
            patch.object(sys, "stdin", io.StringIO("RUN EXP-1493 TWICE\n")),
            patch.object(sys, "stdout", output),
            patch.object(sys, "stderr", prompt),
            patch.object(transfer, "run_transfer") as run,
        ):
            result = transfer.main()
        self.assertEqual(result, 19)
        self.assertEqual(output.getvalue(), "RUN_NOT_CONFIRMED\n")
        self.assertIn("RUN EXP-1493 ONCE", prompt.getvalue())
        run.assert_not_called()

    def test_exact_one_shot_gate_dispatches_once(self):
        with (
            patch.object(sys, "stdin", io.StringIO("RUN EXP-1493 ONCE\n")),
            patch.object(sys, "stdout", io.StringIO()),
            patch.object(sys, "stderr", io.StringIO()),
            patch.object(transfer, "run_transfer", return_value=0) as run,
        ):
            self.assertEqual(transfer.main(), 0)
        run.assert_called_once_with()

    def test_remote_command_is_fixed_to_reviewed_digest_and_target(self):
        self.assertIn(transfer.BUNDLE_SHA256, transfer._REMOTE_COMMAND)
        self.assertIn(str(transfer.BUNDLE_MEMBER_COUNT), transfer._REMOTE_COMMAND)
        self.assertIn(str(transfer.BUNDLE_ARCHIVE_BYTES), transfer._REMOTE_COMMAND)
        self.assertIn(transfer.TARGET_PATH, transfer._REMOTE_COMMAND)
        self.assertIn("HOST_BUNDLE_REJECTED", transfer._REMOTE_RECEIVER)

    def test_import_is_dormant_and_does_not_open_ssh(self):
        with patch.object(transfer.subprocess, "Popen") as popen:
            importlib.reload(transfer)
        popen.assert_not_called()

    def _source_names(self, archive):
        import tarfile

        from build_verifier_host_bundle import _MANIFEST_NAME

        with tarfile.open(fileobj=io.BytesIO(archive[0]), mode="r:") as tar:
            return [item.name for item in tar.getmembers() if item.name != _MANIFEST_NAME]

    def _manifest_bytes(self, archive):
        import tarfile

        with tarfile.open(fileobj=io.BytesIO(archive[0]), mode="r:") as tar:
            member = tar.extractfile("MANIFEST.json")
            return member.read()


if __name__ == "__main__":
    unittest.main()
