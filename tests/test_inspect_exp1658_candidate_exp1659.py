from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import inspect_exp1658_candidate_exp1659 as inspect


class InspectExp1658CandidateExp1659Tests(unittest.TestCase):
    @staticmethod
    def _stdout(*, image_id=None, tags=None):
        values = (
            image_id or inspect.EXPECTED_ID,
            "linux",
            "amd64",
            str(inspect.EXPECTED_SIZE),
            json.dumps([f"sha256:{number:064x}" for number in range(1, 10)]),
            json.dumps(tags if tags is not None else [inspect.IMAGE_TAG]),
        )
        return ("|".join(values) + "\n").encode("ascii")

    def test_opt_in_refusal_precedes_runner(self):
        runner = unittest.mock.Mock()
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(inspect.inspect_once(runner=runner, output=output), 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        runner.assert_not_called()

    def test_one_exact_inspect_emits_only_validated_tuple(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, self._stdout(), b"")

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True):
            self.assertEqual(inspect.inspect_once(runner=runner, output=output), 0)
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertEqual(command[-2:], ("{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|{{json .RootFS.Layers}}|{{json .RepoTags}}", inspect.IMAGE_TAG))
        self.assertEqual(kwargs["timeout"], inspect.TIMEOUT_SECONDS)
        self.assertEqual(kwargs["env"]["DOCKER_HOST"], inspect.DOCKER_HOST)
        self.assertNotIn("DOCKER_AUTH_CONFIG", kwargs["env"])
        self.assertEqual(output.getvalue().split("|tag=")[-1].strip(), inspect.IMAGE_TAG)
        self.assertIn("|platform=linux/amd64|size=48857457|diff_ids=", output.getvalue())

    def test_wrong_identity_or_invalid_diffids_fails_without_echoing_tuple(self):
        for raw in (
            self._stdout(image_id="sha256:" + "0" * 64),
            ("|".join((inspect.EXPECTED_ID, "linux", "amd64", str(inspect.EXPECTED_SIZE), "[]", json.dumps([inspect.IMAGE_TAG]))) + "\n").encode("ascii"),
        ):
            output = io.StringIO()

            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 0, raw, b"")

            with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}, clear=True):
                self.assertEqual(inspect.inspect_once(runner=runner, output=output), 12)
            self.assertEqual(output.getvalue(), "IMAGE_TUPLE_MISMATCH\n")


if __name__ == "__main__":
    unittest.main()
