from __future__ import annotations

import io
import os
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

from scripts import serve_pinned_verifier_host_bundle_exp1679 as profile
from scripts import stream_pinned_verifier_host_bundle as pinned


class _TTYInput(io.StringIO):
    def isatty(self):
        return True


class ServePinnedVerifierHostBundleExp1679Tests(unittest.TestCase):
    def _run(self, phrase: str, *, now=None, bind_address="192.168.88.5", builder=None):
        output = io.StringIO()
        errors = io.StringIO()
        factory = mock.Mock(side_effect=AssertionError("must not listen"))
        build = mock.Mock(side_effect=AssertionError("must not build")) if builder is None else builder
        result = profile.run_once(
            bind_address=bind_address,
            port=0,
            stdin=_TTYInput(phrase),
            stdout=output,
            stderr=errors,
            bundle_builder=build,
            server_factory=factory,
            now=now,
        )
        return result, output.getvalue(), errors.getvalue(), build, factory

    def _run_receiver(self, bundle, *, home, digest=None, count=None, source_bytes=None):
        raw, actual_digest, actual_count, actual_source_bytes = bundle
        args = [
            "remote-receiver",
            actual_digest if digest is None else digest,
            str(actual_count if count is None else count),
            str(actual_source_bytes if source_bytes is None else source_bytes),
            str(len(raw)),
            str(home / ".local/share/agent00x/verifier-host/exp-1679"),
        ]
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="ascii")
        stdout = io.StringIO()
        namespace = {"__name__": "__main__"}
        with (
            mock.patch.object(sys, "argv", args),
            mock.patch.object(sys, "stdin", stdin),
            mock.patch.object(sys, "stdout", stdout),
            mock.patch.object(pwd, "getpwuid", return_value=SimpleNamespace(pw_dir=str(home))),
        ):
            try:
                exec(compile(profile._REMOTE_RECEIVER, "exp1679-receiver", "exec"), namespace)
            except SystemExit as exc:
                return exc.code, stdout.getvalue()
        return 0, stdout.getvalue()

    def test_cli_help_imports_without_opening_gate(self):
        result = subprocess.run(
            (sys.executable, str(ROOT / "scripts/serve_pinned_verifier_host_bundle_exp1679.py"), "--help"),
            cwd=ROOT,
            capture_output=True,
            check=False,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn(b"--bind-address", result.stdout)

    def test_requires_tty_and_new_exact_gate_before_bundle_build_or_listener(self):
        builder = mock.Mock(side_effect=AssertionError("must not build"))
        output = io.StringIO()
        result = profile.run_once(
            bind_address="192.168.88.5",
            port=0,
            stdin=io.StringIO(profile.CONFIRMATION_PHRASE + "\n"),
            stdout=output,
            bundle_builder=builder,
        )
        self.assertEqual(result, 10)
        self.assertEqual(output.getvalue(), "RUN_NOT_CONFIRMED\n")
        builder.assert_not_called()

        result, output, prompt, builder, factory = self._run("RUN EXP-1676 ONCE\n")
        self.assertEqual(result, 10)
        self.assertEqual(output, "RUN_NOT_CONFIRMED\n")
        self.assertEqual(prompt, "Type RUN EXP-1679 ONCE to continue: ")
        builder.assert_not_called()
        factory.assert_not_called()

    def test_expiry_and_invalid_address_refuse_before_build(self):
        expired = datetime(2026, 10, 20, 21, 0, 0, tzinfo=timezone.utc)
        result, output, _prompt, builder, factory = self._run(
            "RUN EXP-1679 ONCE\n", now=expired
        )
        self.assertEqual(result, 16)
        self.assertEqual(output, "AUTHORIZATION_EXPIRED\n")
        builder.assert_not_called()
        factory.assert_not_called()

        result, output, _prompt, builder, factory = self._run(
            "RUN EXP-1679 ONCE\n", bind_address="0.0.0.0"
        )
        self.assertEqual(result, 11)
        self.assertEqual(output, "BIND_ADDRESS_INVALID\n")
        builder.assert_not_called()
        factory.assert_not_called()

    def test_bundle_pin_mismatch_fails_before_listener(self):
        builder = mock.Mock(return_value=(b"bad", pinned.BUNDLE_SHA256, 34, 573896))
        result, output, _prompt, builder, factory = self._run(
            "RUN EXP-1679 ONCE\n",
            now=datetime(2026, 10, 20, 20, 0, 0, tzinfo=timezone.utc),
            builder=builder,
        )
        self.assertEqual(result, 12)
        self.assertEqual(output, "BUNDLE_PIN_MISMATCH\n")
        builder.assert_called_once_with()
        factory.assert_not_called()

    def test_remote_command_is_digest_first_pinned_and_shell_syntax_valid(self):
        command = profile.remote_bundle_command(
            "192.168.88.5", 49231, pinned.BUNDLE_SHA256
        )
        self.assertIn(profile.REQUEST_PATH, command)
        self.assertIn("agent00x-exp1679.XXXXXX", command)
        self.assertIn(pinned.BUNDLE_SHA256, command)
        self.assertIn("verifier-host/exp-1679", command)
        self.assertIn("HOST_BUNDLE_IMPORT_SMOKE_CONFIRMED", command)
        self.assertIn("--help", command)
        self.assertNotIn("exp-1491", command)
        self.assertLess(command.index("BUNDLE_DIGEST_MISMATCH"), command.index("python3 -c"))
        result = subprocess.run(
            ("/bin/bash", "-n", "-c", command), capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

        with self.assertRaises(ValueError):
            profile.remote_bundle_command("0.0.0.0", 49231, pinned.BUNDLE_SHA256)
        with self.assertRaises(ValueError):
            profile.remote_bundle_command("192.168.88.5", 49231, "0" * 64)

    def test_real_bundle_receiver_extracts_fresh_private_target_and_help_smoke(self):
        from scripts.build_verifier_host_bundle import build_bundle

        bundle = build_bundle()
        self.assertEqual(bundle[1], pinned.BUNDLE_SHA256)
        self.assertEqual(bundle[2:], (pinned.BUNDLE_MEMBER_COUNT, pinned.BUNDLE_SOURCE_BYTES))
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result, output = self._run_receiver(bundle, home=home)
            target = home / ".local/share/agent00x/verifier-host/exp-1679"
            self.assertEqual(result, 0)
            self.assertEqual(
                output,
                f"HOST_BUNDLE_IMPORTED|sha256={bundle[1]}|members={bundle[2]}\n",
            )
            self.assertEqual(
                (target / "scripts/serve_ephemeral_signed_verifier_https.py").stat().st_mode & 0o777,
                0o600,
            )
            help_result = subprocess.run(
                (sys.executable, str(target / "scripts/serve_ephemeral_signed_verifier_https.py"), "--help"),
                cwd=target,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                check=False,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr.decode("utf-8", "replace"))
            self.assertIn(b"--help", help_result.stdout)

    def test_receiver_rejects_digest_mismatch_and_preexisting_target(self):
        from scripts.build_verifier_host_bundle import build_bundle

        bundle = build_bundle()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result, output = self._run_receiver(bundle, home=home, digest="0" * 64)
            self.assertEqual(result, 41)
            self.assertEqual(output, "HOST_BUNDLE_REJECTED\n")
            self.assertFalse((home / ".local/share/agent00x/verifier-host/exp-1679").exists())

        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            target = home / ".local/share/agent00x/verifier-host/exp-1679"
            target.mkdir(parents=True)
            sentinel = target / "existing"
            sentinel.write_text("preserve", encoding="ascii")
            result, output = self._run_receiver(bundle, home=home)
            self.assertEqual(result, 41)
            self.assertEqual(output, "HOST_BUNDLE_REJECTED\n")
            self.assertEqual(sentinel.read_text(encoding="ascii"), "preserve")

    def test_one_shot_listener_uses_only_exact_private_peer_and_path(self):
        self.assertEqual(profile.delivery.TARGET_ADDRESS, profile.TARGET_ADDRESS)
        archive = b""  # fake server prevents opening a socket
        fake_server = mock.Mock()
        fake_server.server_address = ("192.168.88.5", 49231)
        fake_server.request_consumed = True
        fake_server.archive_served = True
        fake_server.__enter__ = mock.Mock(return_value=fake_server)
        fake_server.__exit__ = mock.Mock(return_value=False)
        fake_server.handle_request = mock.Mock()
        factory = mock.Mock(return_value=fake_server)
        output = io.StringIO()
        # The real archive pin is validated by run_once; this assertion tests only
        # the listener wrapper's request path and output using an internal stub.
        with mock.patch.object(profile, "BUNDLE_ARCHIVE_BYTES", len(archive)), mock.patch.object(
            profile, "BUNDLE_SHA256", profile.hashlib_sha256(archive)
        ):
            result = profile.serve_once(
                archive,
                bind_address="192.168.88.5",
                port=0,
                output=output,
                server_factory=factory,
            )
        self.assertEqual(result, 0)
        factory.assert_called_once_with(("192.168.88.5", 0), archive, profile.REQUEST_PATH)
        self.assertIn("/exp-1679/verifier-host-bundle.tar", output.getvalue())
        self.assertIn("HOST_BUNDLE_IMPORT_SMOKE_CONFIRMED", output.getvalue())
        self.assertTrue(output.getvalue().endswith("BUNDLE_SERVED\n"))


if __name__ == "__main__":
    unittest.main()
