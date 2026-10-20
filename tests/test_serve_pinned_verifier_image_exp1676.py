from __future__ import annotations

import io
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from scripts import serve_pinned_verifier_image_exp1653 as delivery
from scripts import serve_pinned_verifier_image_exp1676 as profile
from scripts import stream_pinned_verifier_image as pinned


class _TTYInput(io.StringIO):
    def isatty(self):
        return True


class ServePinnedVerifierImageExp1676Tests(unittest.TestCase):
    def _run(self, text: str, *, now=None, bind_address="192.168.88.5"):
        output = io.StringIO()
        errors = io.StringIO()
        runner = mock.Mock(side_effect=AssertionError("must not inspect/save"))
        factory = mock.Mock(side_effect=AssertionError("must not listen"))
        code = profile.run_once(
            bind_address=bind_address,
            port=0,
            stdin=_TTYInput(text),
            stdout=output,
            stderr=errors,
            runner=runner,
            server_factory=factory,
            now=now,
        )
        return code, output.getvalue(), errors.getvalue(), runner, factory

    def test_script_help_imports_from_repository_without_opening_gate(self):
        result = subprocess.run(
            (sys.executable, str(Path(profile.__file__)), "--help"),
            cwd=Path(profile.__file__).resolve().parents[1],
            capture_output=True,
            check=False,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn(b"--bind-address", result.stdout)

    def test_requires_tty_and_new_exact_phrase_before_side_effects(self):
        runner = mock.Mock(side_effect=AssertionError("must not inspect/save"))
        output = io.StringIO()
        self.assertEqual(
            profile.run_once(
                bind_address="192.168.88.5",
                port=0,
                stdin=io.StringIO(profile.CONFIRMATION_PHRASE + "\n"),
                stdout=output,
                runner=runner,
            ),
            10,
        )
        self.assertEqual(output.getvalue(), "RUN_NOT_CONFIRMED\n")
        runner.assert_not_called()

        code, result, prompt, runner, factory = self._run("RUN EXP-1661 ONCE\n")
        self.assertEqual(code, 10)
        self.assertEqual(result, "RUN_NOT_CONFIRMED\n")
        self.assertEqual(prompt, "Type RUN EXP-1676 ONCE to continue: ")
        runner.assert_not_called()
        factory.assert_not_called()

    def test_expiry_and_invalid_bind_refuse_before_docker_or_listener(self):
        expired = datetime(2026, 10, 20, 21, 0, 0, tzinfo=timezone.utc)
        code, output, _prompt, runner, factory = self._run(
            "RUN EXP-1676 ONCE\n", now=expired
        )
        self.assertEqual(code, 20)
        self.assertEqual(output, "AUTHORIZATION_EXPIRED\n")
        runner.assert_not_called()
        factory.assert_not_called()

        code, output, _prompt, runner, factory = self._run(
            "RUN EXP-1676 ONCE\n", bind_address="0.0.0.0"
        )
        self.assertEqual(code, 11)
        self.assertEqual(output, "BIND_ADDRESS_INVALID\n")
        runner.assert_not_called()
        factory.assert_not_called()

    def test_current_pin_archive_uses_only_new_exp1676_endpoint(self):
        archive = b"synthetic-current-pinned-archive"
        fake_server = mock.Mock()
        fake_server.server_address = ("192.168.88.5", 49231)
        fake_server.request_consumed = True
        fake_server.archive_served = True
        fake_server.__enter__ = mock.Mock(return_value=fake_server)
        fake_server.__exit__ = mock.Mock(return_value=False)
        fake_server.handle_request = mock.Mock()
        factory = mock.Mock(return_value=fake_server)
        now = datetime(2026, 10, 20, 20, 0, 0, tzinfo=timezone.utc)
        output = io.StringIO()
        errors = io.StringIO()

        with (
            mock.patch.object(profile.delivery, "prepare_archive", return_value=archive) as prepare,
            mock.patch.object(pinned, "STREAM_SIZE", len(archive)),
        ):
            result = profile.run_once(
                bind_address="192.168.88.5",
                port=0,
                stdin=_TTYInput("RUN EXP-1676 ONCE\n"),
                stdout=output,
                stderr=errors,
                runner=mock.Mock(),
                server_factory=factory,
                now=now,
            )

        self.assertEqual(result, 0)
        prepare.assert_called_once()
        factory.assert_called_once_with(
            ("192.168.88.5", 0), archive, profile.REQUEST_PATH
        )
        self.assertIn("/exp-1676/verifier-image.tar", output.getvalue())
        self.assertNotIn("/exp-1661/", output.getvalue())
        self.assertNotIn("agent00x-exp1661", output.getvalue())
        self.assertIn(pinned.REMOTE_CONFIG_IMAGE_ID, output.getvalue())
        self.assertIn("IMAGE_IMPORT_CONFIRMED", output.getvalue())
        self.assertTrue(output.getvalue().endswith("ARCHIVE_SERVED\n"))

    def test_generated_command_is_exact_image_bound_and_shell_syntax_valid(self):
        archive_digest = "a" * 64
        command = delivery.remote_import_command(
            "192.168.88.5",
            49231,
            archive_digest,
            request_path=profile.REQUEST_PATH,
            task_prefix=profile.TASK_PREFIX,
        )
        self.assertIn(profile.REQUEST_PATH, command)
        self.assertIn("agent00x-exp1676.XXXXXX", command)
        self.assertIn(pinned.REMOTE_CONFIG_IMAGE_ID, command)
        self.assertIn(pinned._EXPECTED_REMOTE_INSPECT, command)
        self.assertIn(archive_digest, command)
        self.assertLess(command.index("ARCHIVE_DIGEST_MISMATCH"), command.index("docker image load"))
        self.assertIn("trap 'rm -f", command)
        result = subprocess.run(
            ("/bin/bash", "-n", "-c", command), capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
