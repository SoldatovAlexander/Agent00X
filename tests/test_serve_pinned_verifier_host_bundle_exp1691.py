from __future__ import annotations

import io
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from scripts import serve_pinned_verifier_host_bundle_exp1691 as profile
from scripts import stream_pinned_verifier_host_bundle as pinned


class _TTYInput(io.StringIO):
    def isatty(self):
        return True


class ServePinnedVerifierHostBundleExp1691Tests(unittest.TestCase):
    def _run_receiver(self, bundle, home, *, digest=None):
        raw, actual_digest, count, source_bytes = bundle
        args = [
            "receiver", actual_digest if digest is None else digest,
            str(count), str(source_bytes), str(len(raw)),
            str(home / ".local/share/agent00x/verifier-host/exp-1693"),
        ]
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="ascii")
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", args),
            mock.patch.object(sys, "stdin", stdin),
            mock.patch.object(sys, "stdout", stdout),
            mock.patch.object(pwd, "getpwuid", return_value=SimpleNamespace(pw_dir=str(home))),
        ):
            try:
                exec(compile(profile._REMOTE_RECEIVER, "exp1691-receiver", "exec"), {"__name__": "__main__"})
            except SystemExit as exc:
                return exc.code, stdout.getvalue()
        return 0, stdout.getvalue()

    def test_exact_gate_expiry_and_wrong_phrase_refuse_before_bundle_or_listener(self):
        builder = mock.Mock(side_effect=AssertionError("no build expected"))
        factory = mock.Mock(side_effect=AssertionError("no listener expected"))
        for phrase, now, expected in (
            ("RUN EXP-1679 ONCE\n", datetime(2026, 10, 21, tzinfo=timezone.utc), "RUN_NOT_CONFIRMED"),
            (profile.CONFIRMATION_PHRASE + "\n", profile.AUTHORIZATION_EXPIRES_AT, "AUTHORIZATION_EXPIRED"),
        ):
            output = io.StringIO()
            result = profile.run_once(
                bind_address="192.168.88.5", port=0, stdin=_TTYInput(phrase),
                stdout=output, bundle_builder=builder, server_factory=factory, now=now,
            )
            self.assertEqual(output.getvalue(), expected + "\n")
            self.assertNotEqual(result, 0)
        builder.assert_not_called()
        factory.assert_not_called()

    def test_digest_pinned_command_syntax_and_listener_path(self):
        command = profile.remote_bundle_command("192.168.88.5", 49231)
        self.assertIn(profile.REQUEST_PATH, command)
        self.assertIn("agent00x-exp1693.XXXXXX", command)
        self.assertIn("verifier-host/exp-1693", command)
        self.assertIn(pinned.BUNDLE_SHA256, command)
        self.assertLess(command.index("BUNDLE_DIGEST_MISMATCH"), command.index("python3 -c"))
        syntax = subprocess.run(("/bin/bash", "-n", "-c", command), capture_output=True, check=False)
        self.assertEqual(syntax.returncode, 0, syntax.stderr.decode("utf-8", "replace"))
        with self.assertRaises(ValueError):
            profile.remote_bundle_command("0.0.0.0", 49231)

        archive = b"synthetic-bundle"
        fake = mock.Mock()
        fake.server_address = ("192.168.88.5", 49231)
        fake.request_consumed = True
        fake.archive_served = True
        fake.__enter__ = mock.Mock(return_value=fake)
        fake.__exit__ = mock.Mock(return_value=False)
        output = io.StringIO()
        with mock.patch.object(profile, "hashlib") as digest, mock.patch.object(profile, "pinned") as current:
            digest.sha256.return_value.hexdigest.return_value = "b" * 64
            current.BUNDLE_SHA256 = "b" * 64
            current.BUNDLE_ARCHIVE_BYTES = len(archive)
            current.BUNDLE_MEMBER_COUNT = 34
            result = profile.serve_once(
                archive, bind_address="192.168.88.5", port=0, output=output,
                server_factory=mock.Mock(return_value=fake),
            )
        self.assertEqual(result, 0)
        self.assertIn("/exp-1693/verifier-host-bundle.tar", output.getvalue())
        self.assertTrue(output.getvalue().endswith("BUNDLE_SERVED\n"))

    def test_real_receiver_extracts_only_to_fresh_profile_path_and_rejects_mismatch(self):
        from scripts.build_verifier_host_bundle import build_bundle

        bundle = build_bundle()
        self.assertEqual(bundle[1], pinned.BUNDLE_SHA256)
        self.assertEqual(bundle[2:], (pinned.BUNDLE_MEMBER_COUNT, pinned.BUNDLE_SOURCE_BYTES))
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            code, output = self._run_receiver(bundle, home, digest="0" * 64)
            self.assertEqual((code, output), (41, "HOST_BUNDLE_REJECTED\n"))
            code, output = self._run_receiver(bundle, home)
            target = home / ".local/share/agent00x/verifier-host/exp-1693"
            self.assertEqual(code, 0)
            self.assertEqual(output, f"HOST_BUNDLE_IMPORTED|sha256={bundle[1]}|members={bundle[2]}\n")
            self.assertEqual((target / "scripts/serve_ephemeral_signed_verifier_https.py").stat().st_mode & 0o777, 0o600)
            self.assertTrue(target.is_dir())


if __name__ == "__main__":
    unittest.main()
