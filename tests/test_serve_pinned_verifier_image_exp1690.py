from __future__ import annotations

import io
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from scripts import serve_pinned_verifier_image_exp1653 as delivery
from scripts import serve_pinned_verifier_image_exp1690 as profile
from scripts import stream_pinned_verifier_image as pinned


class _TTYInput(io.StringIO):
    def isatty(self):
        return True


class ServePinnedVerifierImageExp1690Tests(unittest.TestCase):
    def test_cli_help_is_inert(self):
        result = subprocess.run(
            (sys.executable, str(Path(profile.__file__)), "--help"),
            cwd=Path(profile.__file__).resolve().parents[1],
            capture_output=True,
            check=False,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn(b"--bind-address", result.stdout)

    def test_exact_tty_gate_expiry_and_bind_fail_closed(self):
        runner = mock.Mock(side_effect=AssertionError("no image operation expected"))
        output = io.StringIO()
        result = profile.run_once(
            bind_address="192.168.88.5", port=0,
            stdin=io.StringIO(profile.CONFIRMATION_PHRASE + "\n"),
            stdout=output, runner=runner,
        )
        self.assertEqual((result, output.getvalue()), (10, "RUN_NOT_CONFIRMED\n"))
        runner.assert_not_called()

        output = io.StringIO()
        result = profile.run_once(
            bind_address="192.168.88.5", port=0,
            stdin=_TTYInput("RUN EXP-1676 ONCE\n"), stdout=output, runner=runner,
        )
        self.assertEqual((result, output.getvalue()), (10, "RUN_NOT_CONFIRMED\n"))

        for address, now, marker, code in (
            ("0.0.0.0", datetime(2026, 10, 21, tzinfo=timezone.utc), "BIND_ADDRESS_INVALID", 11),
            ("192.168.88.5", profile.AUTHORIZATION_EXPIRES_AT, "AUTHORIZATION_EXPIRED", 20),
        ):
            output = io.StringIO()
            result = profile.run_once(
                bind_address=address, port=0,
                stdin=_TTYInput(profile.CONFIRMATION_PHRASE + "\n"),
                stdout=output, runner=runner, now=now,
            )
            self.assertEqual((result, output.getvalue()), (code, marker + "\n"))
        runner.assert_not_called()

    def test_current_pin_listener_and_generated_import_command(self):
        archive = b"synthetic-current-image-archive"
        server = mock.Mock()
        server.server_address = ("192.168.88.5", 49231)
        server.request_consumed = True
        server.archive_served = True
        server.__enter__ = mock.Mock(return_value=server)
        server.__exit__ = mock.Mock(return_value=False)
        factory = mock.Mock(return_value=server)
        output = io.StringIO()
        now = datetime(2026, 10, 20, 22, tzinfo=timezone.utc)
        with (
            mock.patch.object(profile.delivery, "prepare_archive", return_value=archive) as prepare,
            mock.patch.object(pinned, "STREAM_SIZE", len(archive)),
        ):
            result = profile.run_once(
                bind_address="192.168.88.5", port=0,
                stdin=_TTYInput(profile.CONFIRMATION_PHRASE + "\n"),
                stdout=output, server_factory=factory, now=now,
            )
        self.assertEqual(result, 0)
        prepare.assert_called_once()
        factory.assert_called_once_with(("192.168.88.5", 0), archive, profile.REQUEST_PATH)
        self.assertIn("/exp-1692/verifier-image.tar", output.getvalue())
        self.assertIn("agent00x-exp1692.XXXXXX", output.getvalue())
        self.assertIn(pinned.REMOTE_CONFIG_IMAGE_ID, output.getvalue())
        self.assertIn(pinned._EXPECTED_REMOTE_INSPECT, output.getvalue())
        self.assertTrue(output.getvalue().endswith("ARCHIVE_SERVED\n"))

        command = delivery.remote_import_command(
            "192.168.88.5", 49231, "a" * 64,
            request_path=profile.REQUEST_PATH, task_prefix=profile.TASK_PREFIX,
        )
        self.assertLess(command.index("ARCHIVE_DIGEST_MISMATCH"), command.index("docker image load"))
        syntax = subprocess.run(("/bin/bash", "-n", "-c", command), capture_output=True, check=False)
        self.assertEqual(syntax.returncode, 0, syntax.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
