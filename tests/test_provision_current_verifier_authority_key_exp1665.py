from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "provision_current_verifier_authority_key_exp1665.swift"


@unittest.skipUnless(shutil.which("swift"), "Swift is required for the macOS signer self-test")
class CurrentVerifierAuthorityKeyProvisionerTests(unittest.TestCase):
    def test_synthetic_self_test_does_not_use_keychain(self):
        result = subprocess.run(
            ["swift", str(SCRIPT), "--self-test"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "EXP1665_SELF_TEST_OK\n")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
