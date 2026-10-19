from __future__ import annotations

import io
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import locate_buildx_plugin_exp1613 as probe


class LocateBuildxPluginExp1613Tests(unittest.TestCase):
    def test_candidate_paths_are_exact_and_standard(self):
        self.assertEqual(len(probe.CANDIDATES), 5)
        self.assertIn("/Users/aleksandrsoldatov/.docker/cli-plugins/docker-buildx", probe.CANDIDATES)

    def test_zero_or_multiple_candidates_stop_without_execution(self):
        for count in (0, 2):
            output = io.StringIO()
            calls = []
            with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
                code = probe.run_once(
                    is_executable=lambda _path: len(calls) < count and not calls.append(_path),
                    runner=lambda *args, **kwargs: self.fail("must not execute ambiguous candidate"),
                    output=output,
                )
            self.assertEqual(code, 11)
            self.assertEqual(output.getvalue(), f"BUILDX_PLUGIN_CANDIDATES|executable_count={count}\n")

    def test_unique_candidate_invokes_only_its_version_subcommand(self):
        selected = probe.CANDIDATES[0]
        observed = []

        def executable(path):
            return path == selected

        def runner(command, *, max_bytes, timeout, env):
            observed.append((command, max_bytes, timeout, env))
            return subprocess.CompletedProcess(command, 0, b"github.com/docker/buildx v0.27.0-desktop.1\n", None)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, is_executable=executable, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "BUILDX_PLUGIN|location=one-standard-path|version=v0.27.0-desktop.1\n")
        command, max_bytes, timeout, env = observed[0]
        self.assertEqual(command, (selected, "version"))
        self.assertEqual(max_bytes, probe.MAX_OUTPUT_BYTES)
        self.assertEqual(timeout, probe.TIMEOUT_SECONDS)
        self.assertIn("DOCKER_CONFIG", env)
        self.assertNotIn("DOCKER_HOST", env)

    def test_untrusted_version_output_is_not_emitted(self):
        selected = probe.CANDIDATES[0]

        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, b"secret-path v1.2.3\n", None)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, is_executable=lambda p: p == selected, output=output)
        self.assertEqual(code, 16)
        self.assertEqual(output.getvalue(), "BUILDX_PLUGIN_VERSION_UNCLASSIFIED\n")

    def test_opt_in_refusal_prevents_path_checks(self):
        calls = []
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            code = probe.run_once(is_executable=lambda p: calls.append(p) or True, output=output)
        self.assertEqual(code, 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
