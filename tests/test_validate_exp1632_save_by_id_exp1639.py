from __future__ import annotations

import io
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import validate_exp1632_save_by_id_exp1639 as probe


class ValidateExp1632SaveByIdExp1639Tests(unittest.TestCase):
    def test_opt_in_guard_stops_before_runner(self):
        output = io.StringIO()
        runner = unittest.mock.Mock()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(probe.run_once(runner=runner, output=output), 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        runner.assert_not_called()

    def test_one_exact_bounded_save_and_full_parser_binding(self):
        calls = []
        output = io.StringIO()
        archive = b"archive"
        facts = SimpleNamespace(
            config_digest=probe.REMOTE_CONFIG_IMAGE_ID,
            os_name="linux",
            architecture="amd64",
            diff_ids=probe.DIFF_IDS,
            repo_tags=(),
            archive_format="docker-legacy",
            portable_manifest_digest=None,
        )

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, archive, b"")

        with (
            patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True),
            patch.object(probe, "STREAM_SIZE", len(archive)),
            patch.object(probe, "parse_portable_archive", return_value=facts) as parse,
        ):
            self.assertEqual(probe.run_once(runner=runner, output=output), 0)
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertEqual(
            command,
            (probe.DOCKER, "--host=" + probe.DOCKER_HOST, "image", "save", probe.IMAGE_ID),
        )
        self.assertEqual(kwargs["max_bytes"], probe.MAX_ARCHIVE_BYTES)
        self.assertEqual(kwargs["timeout"], probe.TIMEOUT_SECONDS)
        self.assertEqual(kwargs["env"]["DOCKER_HOST"], probe.DOCKER_HOST)
        parse.assert_called_once_with(
            archive,
            expected_config_digest=probe.REMOTE_CONFIG_IMAGE_ID,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=probe.DIFF_IDS,
            expected_repo_tag=None,
            max_archive_bytes=probe.MAX_ARCHIVE_BYTES,
        )
        self.assertEqual(
            output.getvalue(),
            "IMAGE_SAVE_CHAIN_CONFIRMED|format=docker-legacy|manifest=absent|"
            f"config=verified|size={probe.IMAGE_SIZE}|archive_bytes=7|"
            f"layers={len(probe.DIFF_IDS)}|repo_tags=tagless|tag={probe.IMAGE_TAG}\n",
        )

    def test_parser_failure_emits_only_safe_stage_and_never_retries(self):
        output = io.StringIO()
        runner = unittest.mock.Mock(
            return_value=subprocess.CompletedProcess((), 0, b"archive", b"")
        )
        with (
            patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True),
            patch.object(probe, "STREAM_SIZE", 7),
            patch.object(probe, "parse_portable_archive", side_effect=probe.InvalidChain("docker-manifest")),
        ):
            self.assertEqual(probe.run_once(runner=runner, output=output), 15)
        self.assertEqual(output.getvalue(), "ARCHIVE_INVALID|stage=docker-manifest\n")
        runner.assert_called_once()

    def test_size_or_runtime_mismatch_fails_closed_without_extra_calls(self):
        output = io.StringIO()
        runner = unittest.mock.Mock(
            return_value=subprocess.CompletedProcess((), 0, b"short", b"")
        )
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True):
            self.assertEqual(probe.run_once(runner=runner, output=output), 14)
        self.assertEqual(output.getvalue(), "IMAGE_SAVE_SIZE_MISMATCH\n")
        runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
