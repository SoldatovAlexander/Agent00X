from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import check_pinned_verifier_image_presence as probe
from scripts import stream_pinned_verifier_image as pinned


def completed(stdout=b"", returncode=0, stderr=b""):
    return subprocess.CompletedProcess(args=(), returncode=returncode, stdout=stdout, stderr=stderr)


class PinnedVerifierImagePresenceTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()

    def test_command_is_one_read_only_id_query_and_never_returns_inventory(self):
        result = subprocess.run(("/bin/sh", "-n", "-c", probe._REMOTE_SCRIPT), capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("docker image ls --all --no-trunc", probe._REMOTE_SCRIPT)
        self.assertIn(pinned.IMAGE_ID, probe._REMOTE_SCRIPT)
        self.assertIn("REMOTE_IMAGE_ID_PRESENT", probe._REMOTE_SCRIPT)
        self.assertNotIn("docker image load", probe._REMOTE_SCRIPT)
        self.assertNotIn("docker image inspect", probe._REMOTE_SCRIPT)
        self.assertNotIn("docker image tag", probe._REMOTE_SCRIPT)
        self.assertNotIn("docker run", probe._REMOTE_SCRIPT)

    def test_exact_markers_are_forwarded_once_without_raw_output(self):
        for marker, code in (
            ("REMOTE_IMAGE_ID_PRESENT", 0),
            ("REMOTE_IMAGE_ID_ABSENT", 10),
            ("REMOTE_DOCKER_CLI_UNAVAILABLE", 11),
            ("REMOTE_IMAGE_LIST_FAILED", 12),
        ):
            with self.subTest(marker=marker):
                self.output = io.StringIO()
                runner = mock.Mock(return_value=completed((marker + "\n").encode()))
                self.assertEqual(probe.check_remote_image_presence(runner, self.output), code)
                self.assertEqual(self.output.getvalue(), marker + "\n")
                runner.assert_called_once()
                self.assertEqual(runner.call_args.kwargs["timeout"], 20)
                self.assertTrue(runner.call_args.kwargs["capture_output"])
                self.assertEqual(runner.call_args.args[0][-2], "alex@192.168.88.101")

    def test_transport_and_unexpected_output_are_redacted(self):
        scenarios = (
            (mock.Mock(return_value=completed(b"SECRET", 255, b"SECRET_ERR")), 13, "SSH_CLIENT_EXIT_255"),
            (mock.Mock(return_value=completed(b"SECRET", 2, b"SECRET_ERR")), 15, "REMOTE_COMMAND_FAILED"),
            (mock.Mock(side_effect=subprocess.TimeoutExpired("ssh", 20)), 17, "SSH_CLIENT_TIMEOUT"),
            (mock.Mock(side_effect=OSError("SECRET_EXCEPTION")), 14, "SSH_CLIENT_LAUNCH_FAILED"),
            (mock.Mock(return_value=completed(b"SECRET_RAW_OUTPUT\n")), 16, "REMOTE_PROBE_UNEXPECTED"),
        )
        for runner, expected_code, marker in scenarios:
            with self.subTest(marker=marker):
                self.output = io.StringIO()
                self.assertEqual(probe.check_remote_image_presence(runner, self.output), expected_code)
                self.assertEqual(self.output.getvalue(), marker + "\n")
                self.assertNotIn("SECRET", self.output.getvalue())

    def test_gate_is_exact_and_fresh_gate_dispatches_once(self):
        for value in ("RUN EXP-1315 ONCE", "RUN EXP-1318 ONCE", ""):
            with self.subTest(value=value):
                stdout, stderr = io.StringIO(), io.StringIO()
                dispatch = mock.Mock(return_value=0)
                with (
                    mock.patch.object(probe.sys, "stdin", io.StringIO(value + "\n")),
                    mock.patch.object(probe.sys, "stdout", stdout),
                    mock.patch.object(probe.sys, "stderr", stderr),
                    mock.patch.object(probe, "check_remote_image_presence", dispatch),
                ):
                    self.assertEqual(probe.main(), 19)
                self.assertEqual(stdout.getvalue(), "RUN_NOT_CONFIRMED\n")
                self.assertEqual(stderr.getvalue(), "Type RUN EXP-1320 ONCE to continue: ")
                dispatch.assert_not_called()

        stdout, stderr = io.StringIO(), io.StringIO()
        dispatch = mock.Mock(return_value=0)
        with (
            mock.patch.object(probe.sys, "stdin", io.StringIO("RUN EXP-1320 ONCE\n")),
            mock.patch.object(probe.sys, "stdout", stdout),
            mock.patch.object(probe.sys, "stderr", stderr),
            mock.patch.object(probe, "check_remote_image_presence", dispatch),
        ):
            self.assertEqual(probe.main(), 0)
        self.assertEqual(stderr.getvalue(), "Type RUN EXP-1320 ONCE to continue: ")
        dispatch.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
