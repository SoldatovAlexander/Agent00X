from __future__ import annotations

import io
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import check_buildx_version_exp1612 as probe


class CheckBuildxVersionExp1612Tests(unittest.TestCase):
    def test_version_parser_accepts_fixed_version_forms(self):
        self.assertEqual(probe._version(b"github.com/docker/buildx v0.27.0-desktop.1\n"), "0.27.0-desktop.1")
        self.assertEqual(probe._version(b"v0.18.2\n"), "0.18.2")

    def test_version_parser_rejects_extra_or_unsafe_output(self):
        for raw in (b"secret/path v0.27.0\n", b"v0.27.0\nprivate detail\n", b"not-a-version\n"):
            with self.subTest(raw=raw):
                self.assertIsNone(probe._version(raw))

    def test_exact_version_command_uses_isolated_minimal_environment(self):
        calls = []

        def runner(command, *, max_bytes, timeout, env):
            calls.append((command, max_bytes, timeout, env))
            return subprocess.CompletedProcess(command, 0, b"github.com/docker/buildx v0.27.0-desktop.1\n", None)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "BUILDX_VERSION|version=v0.27.0-desktop.1\n")
        command, max_bytes, timeout, env = calls[0]
        self.assertEqual(command, (probe.DOCKER, "buildx", "version"))
        self.assertEqual(max_bytes, probe.MAX_OUTPUT_BYTES)
        self.assertEqual(timeout, probe.TIMEOUT_SECONDS)
        self.assertIn("DOCKER_CONFIG", env)
        self.assertNotIn("DOCKER_HOST", env)

    def test_nonzero_exit_emits_no_stderr(self):
        def failed(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b"", b"private path")

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=failed, output=output)
        self.assertEqual(code, 14)
        self.assertEqual(output.getvalue(), "BUILDX_VERSION_FAILED\n")

    def test_opt_in_refusal_prevents_process(self):
        calls = []

        def runner(*args, **kwargs):
            calls.append(args)
            raise AssertionError("must not invoke Docker")

        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
