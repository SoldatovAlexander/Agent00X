from __future__ import annotations

import io
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import probe_isolated_buildx_version_exp1615 as probe


class ProbeIsolatedBuildxVersionExp1615Tests(unittest.TestCase):
    def test_parser_accepts_documented_optional_revision(self):
        self.assertEqual(
            probe._version(b"github.com/docker/buildx v0.11.2 9872040b6626fb7d87ef7296fd5b832e8cc2ad17\n"),
            "0.11.2",
        )
        self.assertEqual(probe._version(b"v0.27.0-desktop.1\n"), "0.27.0-desktop.1")

    def test_parser_rejects_unbounded_or_untrusted_output(self):
        for raw in (b"private/path v1.2.3\n", b"v1.2.3 invalid-revision\n", b"v1.2.3\nsecret\n"):
            with self.subTest(raw=raw):
                self.assertIsNone(probe._version(raw))

    def test_exact_version_command_uses_only_prepared_environment(self):
        calls = []

        def runner(command, *, max_bytes, timeout, env):
            calls.append((command, max_bytes, timeout, env))
            return subprocess.CompletedProcess(
                command, 0,
                b"github.com/docker/buildx v0.27.0-desktop.1 " + b"a" * 40 + b"\n",
                None,
            )

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "BUILDX_VERSION|version=v0.27.0-desktop.1\n")
        command, max_bytes, timeout, env = calls[0]
        self.assertEqual(command, (probe.DOCKER, "buildx", "version"))
        self.assertEqual(max_bytes, probe.MAX_OUTPUT_BYTES)
        self.assertEqual(timeout, probe.TIMEOUT_SECONDS)
        self.assertEqual(env["DOCKER_HOST"], "unix:///var/run/docker.sock")
        self.assertIn("DOCKER_CONFIG", env)

    def test_nonzero_exit_is_fixed_and_suppresses_stderr(self):
        def failed(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b"", b"secret")

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
