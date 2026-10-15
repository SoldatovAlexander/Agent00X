from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import inspect_testdev_verifier_config_digest_exp1346 as inspect


class TestdevVerifierConfigDigestInspectTests(unittest.TestCase):
    def test_exact_gate_required_before_one_ssh_call(self):
        runner = mock.Mock()
        output = io.StringIO()
        self.assertEqual(inspect.main(io.StringIO("RUN EXP-1345 ONCE\n"), output, runner), 19)
        self.assertEqual(output.getvalue(), "Type RUN EXP-1346 ONCE to continue: RUN_NOT_CONFIRMED\n")
        runner.assert_not_called()

    def test_exact_tuple_confirms_only_fixed_marker(self):
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(
                (), 0, (inspect._EXPECTED + "\n").encode(), b"PRIVATE"
            )
        )
        output = io.StringIO()
        self.assertEqual(inspect.main(io.StringIO("RUN EXP-1346 ONCE\n"), output, runner), 0)
        self.assertEqual(
            output.getvalue(),
            "Type RUN EXP-1346 ONCE to continue: REMOTE_CONFIG_IMAGE_CONFIRMED\n",
        )
        self.assertNotIn(inspect.CONFIG_IMAGE_ID, output.getvalue())
        self.assertEqual(runner.call_count, 1)
        command = runner.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/ssh")
        self.assertEqual(command[-2], "alex@192.168.88.101")
        self.assertIn(inspect.CONFIG_IMAGE_ID, command[-1])

    def test_remote_failures_and_tuple_mismatch_are_redacted(self):
        cases = (
            (
                subprocess.CompletedProcess((), 42, b"REMOTE_INSPECT_FAILED\n", b"SECRET"),
                "REMOTE_INSPECT_FAILED\n",
                10,
            ),
            (
                subprocess.CompletedProcess((), 0, b"sha256:SECRET\n", b""),
                "REMOTE_IMAGE_IDENTITY_MISMATCH\n",
                11,
            ),
            (
                subprocess.CompletedProcess((), 255, b"SECRET", b"SECRET"),
                "SSH_CLIENT_EXIT_255\n",
                13,
            ),
        )
        for result, expected, code in cases:
            with self.subTest(expected=expected):
                runner = mock.Mock(return_value=result)
                output = io.StringIO()
                inspect.inspect_once(runner, output)
                self.assertEqual(output.getvalue(), expected)
                self.assertNotIn("SECRET", output.getvalue())
                runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
