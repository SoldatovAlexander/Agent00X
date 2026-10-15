from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import inspect_testdev_config_image_facts_exp1349 as inspect


class TestdevConfigImageFactsTests(unittest.TestCase):
    def setUp(self):
        self.tuple_line = (
            f"{inspect.CONFIG_IMAGE_ID}|{inspect.source_pin.OS}|"
            f"{inspect.source_pin.ARCH}|{inspect.source_pin.IMAGE_SIZE}|"
            f"{inspect.source_pin._DIFF_ID_LIST}\n"
        ).encode("ascii")

    def test_exact_gate_required_before_ssh(self):
        runner = mock.Mock()
        output = io.StringIO()
        result = inspect.main(io.StringIO("RUN EXP-1348 ONCE\n"), output, runner)
        self.assertEqual(result, 19)
        self.assertEqual(output.getvalue(),
                         "Type RUN EXP-1349 ONCE to continue: RUN_NOT_CONFIRMED\n")
        runner.assert_not_called()

    def test_exact_tuple_emits_only_boolean_facts(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess((), 0, self.tuple_line, b"secret"))
        output = io.StringIO()
        result = inspect.main(io.StringIO("RUN EXP-1349 ONCE\n"), output, runner)
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(),
                         "Type RUN EXP-1349 ONCE to continue: "
                         "REMOTE_CONFIG_IMAGE_FACTS|id=match|platform=match|size=match|layers=match\n")
        self.assertNotIn(inspect.CONFIG_IMAGE_ID, output.getvalue())
        runner.assert_called_once()

    def test_mismatch_and_failures_are_redacted(self):
        mismatch = self.tuple_line.replace(b"|48854834|", b"|0|")
        cases = (
            (subprocess.CompletedProcess((), 0, mismatch, b"secret"),
             "REMOTE_CONFIG_IMAGE_FACTS|id=match|platform=match|size=mismatch|layers=match\n", 11),
            (subprocess.CompletedProcess((), 42, b"REMOTE_INSPECT_FAILED\n", b"secret"),
             "REMOTE_INSPECT_FAILED\n", 10),
            (subprocess.CompletedProcess((), 255, b"secret", b"secret"),
             "SSH_CLIENT_EXIT_255\n", 14),
            (subprocess.CompletedProcess((), 0, b"secret\n", b"secret"),
             "REMOTE_CONFIG_IMAGE_FACTS_UNEXPECTED\n", 12),
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
