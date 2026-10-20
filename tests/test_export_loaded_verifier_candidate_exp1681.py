from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import export_loaded_verifier_candidate_exp1580 as candidate
from scripts import export_loaded_verifier_candidate_exp1681 as exp1681


class ExportLoadedVerifierCandidateExp1681Tests(unittest.TestCase):
    def test_wrapper_uses_only_fresh_tag_and_full_portable_archive_audit(self):
        self.assertEqual(
            candidate.EXP1681_IMAGE_TAG,
            "agent00x-verifier:exp-1681",
        )
        self.assertIn(candidate.EXP1681_IMAGE_TAG, candidate._ALLOWED_IMAGE_TAGS)

        with mock.patch.object(candidate, "run_once", return_value=0) as run_once:
            self.assertEqual(exp1681.main(), 0)

        run_once.assert_called_once_with(
            image_tag=candidate.EXP1681_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )


if __name__ == "__main__":
    unittest.main()
