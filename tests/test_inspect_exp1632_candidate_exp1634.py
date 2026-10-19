from __future__ import annotations

import io
import json
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import inspect_exp1632_candidate_exp1634 as probe


class InspectExp1632CandidateExp1634Tests(unittest.TestCase):
    def _stdout(self, *, image_id=None, tags=None):
        values = (
            image_id or probe.EXPECTED_ID,
            "linux",
            "amd64",
            str(probe.EXPECTED_SIZE),
            json.dumps([f"sha256:{index:064x}" for index in range(1, 10)]),
            json.dumps(tags if tags is not None else [probe.IMAGE_TAG]),
        )
        return ("|".join(values) + "\n").encode("ascii")

    def test_requires_opt_in_before_docker(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(probe, "_bounded_process_output") as runner:
            self.assertEqual(probe.run_once(output=output), 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        runner.assert_not_called()

    def test_one_exact_read_only_inspect_emits_bounded_tuple(self):
        calls = []
        output = io.StringIO()

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, self._stdout(), b"")

        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True):
            result = probe.run_once(runner=runner, output=output)
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertEqual(
            command,
            (
                probe.DOCKER,
                "--host=" + probe.DOCKER_HOST,
                "image",
                "inspect",
                "--format",
                "{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|{{json .RootFS.Layers}}|{{json .RepoTags}}",
                probe.IMAGE_TAG,
            ),
        )
        self.assertEqual(kwargs["max_bytes"], probe.MAX_OUTPUT_BYTES)
        self.assertEqual(kwargs["timeout"], probe.TIMEOUT_SECONDS)
        self.assertEqual(kwargs["env"]["DOCKER_HOST"], probe.DOCKER_HOST)
        self.assertNotIn("DOCKER_AUTH_CONFIG", kwargs["env"])
        self.assertTrue(output.getvalue().startswith("IMAGE_TUPLE_CONFIRMED|id=" + probe.EXPECTED_ID))
        self.assertIn("|platform=linux/amd64|size=48857362|", output.getvalue())
        self.assertIn("|tag=" + probe.IMAGE_TAG, output.getvalue())

    def test_wrong_identity_or_tag_fails_without_echoing_raw_tuple(self):
        for stdout in (self._stdout(image_id="sha256:" + "0" * 64), self._stdout(tags=[])):
            output = io.StringIO()

            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 0, stdout, b"")

            with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True):
                self.assertEqual(probe.run_once(runner=runner, output=output), 12)
            self.assertEqual(output.getvalue(), "IMAGE_TUPLE_MISMATCH\n")
            self.assertNotIn("sha256:", output.getvalue())

    def test_process_error_is_redacted(self):
        output = io.StringIO()

        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b"private path", b"daemon details")

        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True):
            self.assertEqual(probe.run_once(runner=runner, output=output), 11)
        self.assertEqual(output.getvalue(), "IMAGE_TUPLE_UNAVAILABLE\n")
        self.assertNotIn("private", output.getvalue())


if __name__ == "__main__":
    unittest.main()
