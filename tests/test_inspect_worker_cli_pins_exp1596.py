from __future__ import annotations

import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import inspect_worker_cli_pins_exp1596 as inspector


class InspectWorkerCliPinsExp1596Tests(unittest.TestCase):
    def _run(self, *, target=None, verifier=None, target_code=0, verifier_code=0):
        calls = []
        responses = [
            (target or f"{inspector.TARGET_RUNTIME_IMAGE_ID}\n".encode(), target_code),
            (verifier or f"{inspector.VERIFIER_RUNTIME_IMAGE_ID}\n".encode(), verifier_code),
        ]

        def runner(command, *, max_bytes, timeout):
            calls.append((command, max_bytes, timeout))
            data, code = responses[len(calls) - 1]
            return subprocess.CompletedProcess(command, code, data, None)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = inspector.run_once(runner=runner, which=lambda _name: "/resolved/docker", output=output)
        return code, output.getvalue(), calls

    def test_exact_images_match_using_worker_cli_invocation_shape(self):
        code, output, calls = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(output, "EXP1596_IMAGES|TARGET_MATCH|VERIFIER_MATCH\n")
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            calls[0][0],
            ("/resolved/docker", "image", "inspect", "--format={{.Id}}", inspector.TARGET_RUNTIME_IMAGE_ID),
        )
        self.assertEqual(
            calls[1][0],
            ("/resolved/docker", "image", "inspect", "--format={{.Id}}", inspector.VERIFIER_RUNTIME_IMAGE_ID),
        )
        self.assertTrue(all("--host" not in call[0] for call in calls))
        self.assertTrue(all(call[1:] == (inspector.MAX_OUTPUT_BYTES, inspector.TIMEOUT_SECONDS) for call in calls))

    def test_mismatch_is_classified_without_raw_output(self):
        code, output, _ = self._run(target=("sha256:" + "a" * 64 + "\n").encode())
        self.assertEqual(code, 12)
        self.assertEqual(output, "EXP1596_IMAGES|TARGET_MISMATCH|VERIFIER_MATCH\n")

    def test_nonzero_result_is_unavailable(self):
        code, output, _ = self._run(target_code=1)
        self.assertEqual(code, 12)
        self.assertEqual(output, "EXP1596_IMAGES|TARGET_UNAVAILABLE|VERIFIER_MATCH\n")

    def test_unclassified_output_never_escapes(self):
        code, output, _ = self._run(target=b"private docker diagnostic\n")
        self.assertEqual(code, 12)
        self.assertEqual(output, "EXP1596_IMAGES|TARGET_UNCLASSIFIED|VERIFIER_MATCH\n")
        self.assertNotIn("private docker diagnostic", output)

    def test_opt_in_prevents_path_resolution_and_docker(self):
        calls = []
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            code = inspector.run_once(
                runner=lambda *args, **kwargs: calls.append("runner"),
                which=lambda _name: calls.append("which"),
                output=output,
            )
        self.assertEqual(code, 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        self.assertEqual(calls, [])

    def test_missing_cli_is_bounded(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = inspector.run_once(which=lambda _name: None, output=output)
        self.assertEqual(code, 11)
        self.assertEqual(output.getvalue(), "EXP1596_IMAGES|CLI_UNAVAILABLE\n")

    def test_direct_script_without_opt_in_stops_before_docker(self):
        env = {"PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            (sys.executable, str(Path(inspector.__file__))),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=env,
        )
        self.assertEqual(completed.returncode, 10)
        self.assertEqual(completed.stdout, "OPT_IN_REQUIRED\n")
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
