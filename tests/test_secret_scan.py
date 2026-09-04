from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.secret_scan import CredentialLeakDetected, assert_canary_absent, find_canary_surfaces


class CanaryCredentialTests(unittest.TestCase):
    def setUp(self):
        self.canary = "canary-credential-for-test-only-001"
        self.chain = json.loads((ROOT / "fixtures" / "valid" / "mvp-chain.json").read_text())
        self.clean_surfaces = {
            "agent-context": {"task": "prepare patch", "capabilities": ["workspace.read"]},
            "environment": {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            "stdout": "tests passed",
            "stderr": "",
            "evidence": self.chain["evidence_bundle"],
            "audit": {"input_digest": "sha256:" + "a" * 64, "result": "allowed"},
            "credential-grant": self.chain["credential_use_grant"],
        }

    def test_canary_is_absent_from_agent_and_persisted_surfaces(self):
        self.assertEqual(find_canary_surfaces(self.canary, self.clean_surfaces), [])
        assert_canary_absent(self.canary, self.clean_surfaces)

    def test_canary_leak_in_audit_is_detected(self):
        surfaces = dict(self.clean_surfaces)
        surfaces["audit"] = {"note": self.canary}
        with self.assertRaisesRegex(CredentialLeakDetected, "audit"):
            assert_canary_absent(self.canary, surfaces)

    def test_canary_leak_in_evidence_is_detected(self):
        surfaces = dict(self.clean_surfaces)
        surfaces["evidence"] = {"report": f"failure output: {self.canary}"}
        with self.assertRaisesRegex(CredentialLeakDetected, "evidence"):
            assert_canary_absent(self.canary, surfaces)


if __name__ == "__main__":
    unittest.main()
