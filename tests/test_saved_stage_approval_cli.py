"""Opt-in fail-closed check for the retained codeload-origin stage."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_STAGE_DIGEST = (
    "sha256:e66f65b6be74cc70dc6aa3a8cec658bc65c30051bddd9adb3d74536d4c347f51"
)
EXPECTED_DATABASE_SHA256 = (
    "991d4ffa21145432ba7f926c390c7d9f8d262b2604e31c70623d01424a66e46d"
)
EXPECTED_SOURCE_REPOSITORY = "SoldatovAlexander/brainbooster_full_v11"


@unittest.skipUnless(
    os.environ.get("AGENT00X_EXP789_STAGE_DB")
    and os.environ.get("AGENT00X_EXP789_STAGE_DIGEST"),
    "set the exact retained-stage inputs to run this opt-in harness",
)
class SavedStageApprovalCliTests(unittest.TestCase):
    def test_unproven_codeload_stage_cannot_emit_approval_request(self):
        stage_path = Path(os.environ["AGENT00X_EXP789_STAGE_DB"])
        self.assertEqual(
            os.environ["AGENT00X_EXP789_STAGE_DIGEST"], EXPECTED_STAGE_DIGEST
        )
        self.assertTrue(stage_path.is_absolute())
        self.assertFalse(stage_path.is_symlink())
        self.assertTrue(stage_path.is_file())
        stage_bytes_before = stage_path.read_bytes()
        self.assertEqual(
            hashlib.sha256(stage_bytes_before).hexdigest(),
            EXPECTED_DATABASE_SHA256,
        )

        environment = dict(os.environ)
        environment.update(
            {
                "AGENT_GITHUB_TEST_REPOSITORY": EXPECTED_SOURCE_REPOSITORY,
                "AGENT_GITHUB_INSTALLATION_ID": "900001",
                "AGENT_GITHUB_REPOSITORY_ID": "900002",
                "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT / "tests"))),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        command = [
            sys.executable,
            str(ROOT / "scripts" / "create_approval_request.py"),
            str(stage_path),
            EXPECTED_STAGE_DIGEST,
            "agent/exp-790-unproven-codeload",
            "master",
            "approval-exp-790-unproven-codeload",
            "user-alice",
            "synthetic-test-policy-v1",
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr.strip(),
            "approval request: verifier provenance trust is unavailable",
        )
        self.assertEqual(stage_path.read_bytes(), stage_bytes_before)
        self.assertEqual(
            hashlib.sha256(stage_path.read_bytes()).hexdigest(),
            EXPECTED_DATABASE_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
