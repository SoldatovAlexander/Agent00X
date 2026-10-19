from __future__ import annotations

import io
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import list_buildx_builders_exp1611 as probe


class ListBuildxBuildersExp1611Tests(unittest.TestCase):
    def test_facts_expose_only_default_row_and_bounded_other_count(self):
        raw = (
            b"secret-builder|running|linux/arm64\n"
            b"default*|running|linux/amd64, linux/arm64/v8*\n"
        )
        self.assertEqual(
            probe._facts(raw),
            "BUILDX_LS|default=present|other_rows=1|statuses=running|platforms=linux/amd64,linux/arm64/v8",
        )
        self.assertNotIn("secret-builder", probe._facts(raw))

    def test_facts_report_default_absent_without_other_names(self):
        self.assertEqual(
            probe._facts(b"private-builder|running|linux/amd64\n"),
            "BUILDX_LS|default=absent|other_rows=1",
        )

    def test_malformed_or_untrusted_rows_are_rejected(self):
        for raw in (
            b"default|running|/private/path\n",
            b"default|running|linux/amd64|secret\n",
            b"default|status leak|linux/amd64\n",
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(probe._facts(raw))

    def test_exact_read_only_command_uses_isolated_config_and_suppresses_stderr(self):
        calls = []

        def runner(command, *, max_bytes, timeout, env):
            calls.append((command, max_bytes, timeout, env))
            return subprocess.CompletedProcess(command, 0, b"default|running|linux/amd64\n", None)

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "BUILDX_LS|default=present|other_rows=0|statuses=running|platforms=linux/amd64\n")
        command, max_bytes, timeout, env = calls[0]
        self.assertEqual(command, (
            probe.DOCKER, "--host=" + probe.DOCKER_HOST, "buildx", "ls", "--format",
            "{{.Name}}|{{.Status}}|{{.Platforms}}",
        ))
        self.assertEqual(max_bytes, probe.MAX_OUTPUT_BYTES)
        self.assertEqual(timeout, probe.TIMEOUT_SECONDS)
        self.assertEqual(env["DOCKER_HOST"], probe.DOCKER_HOST)
        self.assertTrue(env["DOCKER_CONFIG"])

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
