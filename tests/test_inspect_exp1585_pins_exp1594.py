from __future__ import annotations

import io
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import inspect_exp1585_pins_exp1594 as inspector


class InspectExp1585PinsExp1594Tests(unittest.TestCase):
    def _run(self, *, target=None, verifier=None, target_code=0, verifier_code=0):
        calls = []
        responses = [
            (target or f"{inspector.TARGET_IMAGE_ID}|linux|amd64\n".encode(), target_code),
            (verifier or f"{inspector.VERIFIER_IMAGE_ID}|linux|amd64\n".encode(), verifier_code),
        ]

        def runner(command, *, max_bytes, timeout, env):
            calls.append((command, max_bytes, timeout, env))
            data, code = responses[len(calls) - 1]
            return subprocess.CompletedProcess(command, code, data, b"suppressed")

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = inspector.run_once(runner=runner, output=output)
        return code, output.getvalue(), calls

    def test_exact_pins_match_and_only_two_inspects_are_made(self):
        code, output, calls = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(output, "EXP1594_IMAGES|TARGET_MATCH|VERIFIER_MATCH\n")
        self.assertEqual(len(calls), 2)
        self.assertIn(inspector.TARGET_IMAGE_ID, calls[0][0])
        self.assertIn(inspector.VERIFIER_IMAGE_ID, calls[1][0])
        self.assertTrue(all(call[1] == inspector.MAX_OUTPUT_BYTES for call in calls))

    def test_exact_id_or_platform_mismatch_is_bounded(self):
        wrong = ("sha256:" + "a" * 64 + "|linux|arm64\n").encode()
        code, output, _ = self._run(target=wrong)
        self.assertEqual(code, 11)
        self.assertEqual(output, "EXP1594_IMAGES|TARGET_MISMATCH|VERIFIER_MATCH\n")

    def test_nonzero_command_is_unavailable_without_error_text(self):
        code, output, _ = self._run(target_code=1)
        self.assertEqual(code, 11)
        self.assertEqual(output, "EXP1594_IMAGES|TARGET_UNAVAILABLE|VERIFIER_MATCH\n")
        self.assertNotIn("suppressed", output)

    def test_malformed_output_is_unclassified(self):
        code, output, _ = self._run(target=b"private diagnostic\n")
        self.assertEqual(code, 11)
        self.assertEqual(output, "EXP1594_IMAGES|TARGET_UNCLASSIFIED|VERIFIER_MATCH\n")
        self.assertNotIn("private diagnostic", output)

    def test_opt_in_gate_prevents_docker_calls(self):
        calls = []

        def fail_if_called(*args, **kwargs):
            calls.append(args)
            raise AssertionError("Docker must not be called")

        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            code = inspector.run_once(runner=fail_if_called, output=output)
        self.assertEqual(code, 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
