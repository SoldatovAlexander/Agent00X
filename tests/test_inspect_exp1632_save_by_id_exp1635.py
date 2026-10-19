from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
import unittest
from unittest.mock import patch

from scripts import inspect_exp1632_save_by_id_exp1635 as probe


def _archive(tags=None):
    manifest = [{
        "Config": "config.json",
        "RepoTags": tags,
        "Layers": [f"layer/{index}.tar" for index in range(9)],
    }]
    raw = json.dumps(manifest, separators=(",", ":")).encode("ascii")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo("manifest.json")
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))
    return buffer.getvalue()


class InspectExp1632SaveByIdExp1635Tests(unittest.TestCase):
    def test_classifies_tagless_manifest(self):
        self.assertEqual(probe._classify_archive(_archive()), ("tagless", 9))

    def test_classifies_exact_task_tag(self):
        self.assertEqual(probe._classify_archive(_archive([probe.IMAGE_TAG])), ("exact-tag", 9))

    def test_classifies_unexpected_tag_without_echoing_it(self):
        self.assertEqual(probe._classify_archive(_archive(["private/example:latest"])), ("unexpected", 9))

    def test_one_exact_immutable_id_save_and_bounded_output(self):
        calls = []
        output = io.StringIO()

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, _archive(), b"")

        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True):
            result = probe.run_once(runner=runner, output=output)
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertEqual(
            command,
            (probe.DOCKER, "--host=" + probe.DOCKER_HOST, "image", "save", probe.IMAGE_ID),
        )
        self.assertEqual(kwargs["max_bytes"], probe.MAX_ARCHIVE_BYTES)
        self.assertEqual(kwargs["timeout"], probe.TIMEOUT_SECONDS)
        self.assertEqual(kwargs["env"]["DOCKER_HOST"], probe.DOCKER_HOST)
        self.assertTrue(output.getvalue().startswith("SAVE_ARCHIVE_FACTS|archive_bytes="))
        self.assertIn("|repo_tags=tagless|layers=9", output.getvalue())

    def test_opt_in_guard_and_failed_command_are_redacted(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(probe.run_once(output=output), 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")

        output = io.StringIO()

        def fail(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b"raw archive", b"private diagnostic")

        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True):
            self.assertEqual(probe.run_once(runner=fail, output=output), 11)
        self.assertEqual(output.getvalue(), "IMAGE_SAVE_UNAVAILABLE\n")
        self.assertNotIn("private", output.getvalue())


if __name__ == "__main__":
    unittest.main()
