from __future__ import annotations

import io
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import inspect_exp1587_tag_residue as probe


class InspectExp1587TagResidueTests(unittest.TestCase):
    def test_exact_absent_marker_and_filtered_query(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, b"", None)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "EXP1587_TAG_ABSENT\n")
        self.assertEqual(len(calls), 1)
        self.assertIn("reference=" + probe.IMAGE_TAG, calls[0][0])
        self.assertEqual(calls[0][1]["max_bytes"], 256)
        self.assertTrue(calls[0][1]["env"]["DOCKER_CONFIG"])

    def test_exact_present_marker(self):
        def runner(command, **kwargs):
            del kwargs
            return subprocess.CompletedProcess(command, 0, probe.EXPECTED_LINE, None)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "EXP1587_TAG_PRESENT\n")

    def test_command_failure_or_other_output_is_unclassified(self):
        cases = (
            subprocess.CompletedProcess((), 1, b"", None),
            subprocess.CompletedProcess((), 0, b"other:image\n", None),
            subprocess.CompletedProcess((), 0, probe.EXPECTED_LINE + b"extra\n", None),
        )
        for result in cases:
            with self.subTest(result=result):
                output = io.StringIO()
                with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
                    code = probe.run_once(
                        runner=lambda command, **kwargs: result,
                        output=output,
                    )
                self.assertEqual(code, 11)
                self.assertEqual(output.getvalue(), "EXP1587_TAG_UNCLASSIFIED\n")

    def test_opt_in_gate_prevents_command(self):
        calls = []

        def runner(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("must not run")

        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
