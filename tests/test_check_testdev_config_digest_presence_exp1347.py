from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import check_testdev_config_digest_presence_exp1347 as probe


class TestdevConfigDigestPresenceTests(unittest.TestCase):
    def test_exact_gate_is_required_before_ssh(self):
        runner = mock.Mock()
        output = io.StringIO()
        result = probe.main(io.StringIO("RUN EXP-1346 ONCE\n"), output, runner)

        self.assertEqual(result, 19)
        self.assertEqual(
            output.getvalue(), "Type RUN EXP-1347 ONCE to continue: RUN_NOT_CONFIRMED\n"
        )
        runner.assert_not_called()

    def test_exact_id_present_emits_only_fixed_marker_once(self):
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(
                (), 0, b"REMOTE_CONFIG_IMAGE_ID_PRESENT\n", b"sensitive"
            )
        )
        output = io.StringIO()
        result = probe.main(io.StringIO("RUN EXP-1347 ONCE\n"), output, runner)

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue(), "Type RUN EXP-1347 ONCE to continue: "
            "REMOTE_CONFIG_IMAGE_ID_PRESENT\n"
        )
        self.assertNotIn(probe.CONFIG_IMAGE_ID, output.getvalue())
        runner.assert_called_once()
        command = runner.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/ssh")
        self.assertEqual(command[-2], "alex@192.168.88.101")
        self.assertIn(probe.CONFIG_IMAGE_ID, command[-1])

    def test_absence_and_all_failures_are_redacted(self):
        cases = (
            (subprocess.CompletedProcess((), 0, b"REMOTE_CONFIG_IMAGE_ID_ABSENT\n", b""),
             "REMOTE_CONFIG_IMAGE_ID_ABSENT\n", 10),
            (subprocess.CompletedProcess((), 42, b"REMOTE_IMAGE_LIST_FAILED\n", b"secret"),
             "REMOTE_IMAGE_LIST_FAILED\n", 11),
            (subprocess.CompletedProcess((), 255, b"secret", b"secret"),
             "SSH_CLIENT_EXIT_255\n", 13),
            (subprocess.CompletedProcess((), 0, b"secret\n", b"secret"),
             "REMOTE_PROBE_UNEXPECTED\n", 14),
        )
        for completed, expected, code in cases:
            with self.subTest(expected=expected):
                runner = mock.Mock(return_value=completed)
                output = io.StringIO()
                self.assertEqual(probe.check_once(runner, output), code)
                self.assertEqual(output.getvalue(), expected)
                self.assertNotIn("secret", output.getvalue())
                runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
