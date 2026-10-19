from __future__ import annotations

import io
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import inspect_buildx_default_exp1609 as probe
from scripts import inspect_buildx_current_exp1610 as current_probe


class InspectBuildxDefaultExp1609Tests(unittest.TestCase):
    def test_facts_emit_only_builder_driver_status_and_platforms(self):
        raw = (
            b"Name:          default\n"
            b"Driver:        docker\n"
            b"Last Activity: 2026-10-19 12:00:00\n\n"
            b"Nodes:\n"
            b"Name:           default\n"
            b"Endpoint:       unix:///secret/path\n"
            b"Driver Options: secret=value\n"
            b"Status:         running\n"
            b"Platforms:      linux/amd64, linux/arm64/v8\n"
        )
        self.assertEqual(
            probe._facts(raw),
            "BUILDX_INSPECT|name=default|driver=docker|nodes=1|statuses=running|platforms=linux/amd64,linux/arm64/v8",
        )

    def test_facts_fail_closed_on_unknown_name_status_or_platform(self):
        for raw in (
            b"Name: hostile\nDriver: docker\nNodes:\nStatus: running\nPlatforms: linux/amd64\n",
            b"Name: default\nDriver: docker\nNodes:\nStatus: active canary\nPlatforms: linux/amd64\n",
            b"Name: default\nDriver: docker\nNodes:\nStatus: running\nPlatforms: /private/path\n",
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(probe._facts(raw))

    def test_one_exact_non_bootstrapping_local_inspect(self):
        calls = []

        def runner(command, *, max_bytes, timeout, env):
            calls.append((command, max_bytes, timeout, env))
            return subprocess.CompletedProcess(
                command,
                0,
                b"Name: default\nDriver: docker\nNodes:\nName: default\nStatus: running\nPlatforms: linux/amd64\n",
                None,
            )

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "BUILDX_INSPECT|name=default|driver=docker|nodes=1|statuses=running|platforms=linux/amd64\n")
        command, max_bytes, timeout, env = calls[0]
        self.assertEqual(command, (probe.DOCKER, "--host=" + probe.DOCKER_HOST, "buildx", "inspect", "default"))
        self.assertNotIn("--bootstrap", command)
        self.assertEqual(max_bytes, probe.MAX_OUTPUT_BYTES)
        self.assertEqual(timeout, probe.TIMEOUT_SECONDS)
        self.assertEqual(env["DOCKER_HOST"], probe.DOCKER_HOST)
        self.assertNotIn("DOCKER_CONTEXT", env)

    def test_opt_in_blocks_process(self):
        calls = []

        def runner(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("must not invoke Docker")

        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        self.assertEqual(calls, [])

    def test_failures_are_fixed_and_do_not_expose_raw_diagnostics(self):
        raw = b"credentials at /private/path must never appear"

        def failed(command, **kwargs):
            return subprocess.CompletedProcess(command, 125, b"", raw)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=failed, output=output)
        self.assertEqual(code, 14)
        self.assertEqual(output.getvalue(), "BUILDX_INSPECT_FAILED|exit=125\n")
        self.assertNotIn("private", output.getvalue())

    def test_exp1610_inspects_selected_builder_without_name(self):
        with patch.object(current_probe, "run_once", return_value=7) as run:
            self.assertEqual(current_probe.main(), 7)
        run.assert_called_once_with(builder_name=None)


if __name__ == "__main__":
    unittest.main()
