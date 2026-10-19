from __future__ import annotations

import io
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import probe_buildx_default_exp1575 as probe


class ProbeBuildxDefaultExp1575Tests(unittest.TestCase):
    def test_parses_only_buildx_and_builder_capability_fields(self):
        self.assertEqual(
            probe.parse_version(b"github.com/docker/buildx v0.21.2-desktop.1\n"),
            "v0.21.2-desktop.1",
        )
        self.assertEqual(
            probe.parse_builder(
                b"Name: default\nDriver: docker\nNodes:\nName: default\n"
                b"BuildKit version: v0.20.2\nEndpoint: secret-looking\n"
            ),
            ("docker", "v0.20.2"),
        )

    def test_rejects_unbounded_or_unclassified_output(self):
        self.assertIsNone(probe.parse_version(b"unrelated output\n"))
        self.assertIsNone(probe.parse_builder(b"Driver: docker-container\n"))
        self.assertIsNone(
            probe.parse_builder(b"Driver: docker\xff\nBuildKit version: v1\n")
        )

    def test_gate_prevents_every_command(self):
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

    def test_emits_only_parsed_version_driver_and_buildkit(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            if "version" in command:
                return subprocess.CompletedProcess(
                    command, 0, b"github.com/docker/buildx v0.21.2\n", None
                )
            return subprocess.CompletedProcess(
                command,
                0,
                b"Name: default\nDriver: docker\nBuildKit version: v0.20.2\n"
                b"Endpoint: must-not-leak\n",
                None,
            )

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(
            output.getvalue(),
            "BUILDX_PROBE|version=v0.21.2|builder=docker,v0.20.2\n",
        )
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call[1]["env"]["DOCKER_CONFIG"] for call in calls))
        self.assertTrue(all(call[1]["max_bytes"] == probe.MAX_OUTPUT_BYTES for call in calls))
        self.assertNotIn("Endpoint", output.getvalue())

    def test_inspect_failure_preserves_the_successful_version_fact(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if "version" in command:
                return subprocess.CompletedProcess(
                    command, 0, b"github.com/docker/buildx v0.21.2\n", None
                )
            return subprocess.CompletedProcess(command, 1, b"", None)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 12)
        self.assertEqual(
            output.getvalue(),
            "BUILDX_PROBE|version=v0.21.2|builder=unclassified\n",
        )
        self.assertEqual(len(calls), 2)

    def test_version_failure_preserves_the_builder_fact(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if "version" in command:
                return subprocess.CompletedProcess(command, 1, b"", None)
            return subprocess.CompletedProcess(
                command,
                0,
                b"Driver: docker-container\nBuildKit version: v0.20.2\n",
                None,
            )

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 12)
        self.assertEqual(
            output.getvalue(),
            "BUILDX_PROBE|version=unclassified|builder=docker-container,v0.20.2\n",
        )
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
