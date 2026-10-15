from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import inspect_testdev_config_image_tuple_exp1348 as inspect


class TestdevConfigImageTupleTests(unittest.TestCase):
    def test_exact_gate_required_before_ssh(self):
        runner = mock.Mock()
        output = io.StringIO()
        result = inspect.main(io.StringIO("RUN EXP-1347 ONCE\n"), output, runner)

        self.assertEqual(result, 19)
        self.assertEqual(
            output.getvalue(), "Type RUN EXP-1348 ONCE to continue: RUN_NOT_CONFIRMED\n"
        )
        runner.assert_not_called()

    def test_exact_tuple_emits_only_confirmation_marker(self):
        tuple_output = (
            f"{inspect.CONFIG_IMAGE_ID}|{inspect.source_pin.OS}|"
            f"{inspect.source_pin.ARCH}|{inspect.source_pin.IMAGE_SIZE}|"
            f"{inspect._EXPECTED_LAYERS}\n"
        ).encode("ascii")
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess((), 0, tuple_output, b"secret")
        )
        output = io.StringIO()
        result = inspect.main(io.StringIO("RUN EXP-1348 ONCE\n"), output, runner)

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue(),
            "Type RUN EXP-1348 ONCE to continue: "
            "REMOTE_CONFIG_IMAGE_TUPLE_CONFIRMED\n",
        )
        self.assertNotIn(inspect.CONFIG_IMAGE_ID, output.getvalue())
        self.assertEqual(runner.call_count, 1)
        command = runner.call_args.args[0]
        self.assertEqual(command[-2], "alex@192.168.88.101")
        self.assertIn(inspect.CONFIG_IMAGE_ID, command[-1])

    def test_mismatch_and_failures_are_redacted(self):
        tuple_output = (
            f"{inspect.CONFIG_IMAGE_ID}|{inspect.source_pin.OS}|"
            f"{inspect.source_pin.ARCH}|0|{inspect._EXPECTED_LAYERS}\n"
        ).encode("ascii")
        cases = (
            (subprocess.CompletedProcess((), 0, tuple_output, b"secret"),
             "REMOTE_CONFIG_IMAGE_TUPLE_MISMATCH\n", 11),
            (subprocess.CompletedProcess((), 42, b"REMOTE_INSPECT_FAILED\n", b"secret"),
             "REMOTE_INSPECT_FAILED\n", 10),
            (subprocess.CompletedProcess((), 255, b"secret", b"secret"),
             "SSH_CLIENT_EXIT_255\n", 13),
            (subprocess.CompletedProcess((), 0, b"secret\n", b"secret"),
             "REMOTE_CONFIG_IMAGE_TUPLE_UNEXPECTED\n", 14),
        )
        for completed, expected, code in cases:
            with self.subTest(expected=expected):
                runner = mock.Mock(return_value=completed)
                output = io.StringIO()
                self.assertEqual(inspect.inspect_once(runner, output), code)
                self.assertEqual(output.getvalue(), expected)
                self.assertNotIn("secret", output.getvalue())
                runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
