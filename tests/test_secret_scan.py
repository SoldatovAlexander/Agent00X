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

    def test_nested_canary_reports_location_without_value(self):
        surfaces = dict(self.clean_surfaces)
        surfaces["agent-context"] = {
            "task": "prepare patch",
            "history": [{"tool": "workspace.read", "output": {"note": self.canary}}],
        }
        self.assertEqual(find_canary_surfaces(self.canary, surfaces), ["agent-context"])
        with self.assertRaises(CredentialLeakDetected) as raised:
            assert_canary_absent(self.canary, surfaces)
        self.assertIn("agent-context", str(raised.exception))
        self.assertNotIn(self.canary, str(raised.exception))

    def test_redacted_artifact_reference_is_not_a_finding(self):
        surfaces = dict(self.clean_surfaces)
        surfaces["agent-context"] = {
            "task": "prepare patch",
            "inputs": ["artifact://snapshots/observer-demo", "artifact://evidence/observer-demo-001"],
        }
        self.assertEqual(find_canary_surfaces(self.canary, surfaces), [])
        assert_canary_absent(self.canary, surfaces)

    def test_scanner_reads_no_credential_files(self):
        source = (ROOT / "src" / "app_contracts" / "secret_scan.py").read_text(encoding="utf-8")
        self.assertNotIn("open(", source)
        self.assertNotIn(".env", source)

    def test_cyclic_surface_is_reported_without_recursion_or_leak(self):
        cyclic_mapping: dict = {}
        cyclic_mapping["self"] = cyclic_mapping
        cyclic_list: list = []
        cyclic_list.append(cyclic_list)
        surfaces = {"agent-context": cyclic_mapping, "stdout": cyclic_list}
        self.assertEqual(
            find_canary_surfaces(self.canary, surfaces), ["agent-context", "stdout"]
        )
        with self.assertRaises(CredentialLeakDetected) as raised:
            assert_canary_absent(self.canary, surfaces)
        self.assertIn("agent-context", str(raised.exception))
        self.assertNotIn(self.canary, str(raised.exception))

    def test_canary_in_reachable_cyclic_surface_is_not_printed(self):
        holder: dict = {"note": self.canary}
        holder["self"] = holder
        surfaces = dict(self.clean_surfaces)
        surfaces["evidence"] = holder
        self.assertEqual(find_canary_surfaces(self.canary, surfaces), ["evidence"])
        with self.assertRaises(CredentialLeakDetected) as raised:
            assert_canary_absent(self.canary, surfaces)
        self.assertIn("evidence", str(raised.exception))
        self.assertNotIn(self.canary, str(raised.exception))

    def test_repeated_sentinel_yields_one_stable_finding_without_value(self):
        surfaces = {
            "agent-context": {
                "history": [
                    {"output": self.canary},
                    {"nested": {"deep": [self.canary, self.canary]}},
                ],
            },
            "stdout": f"first {self.canary} then {self.canary} again",
        }
        first = find_canary_surfaces(self.canary, surfaces)
        second = find_canary_surfaces(self.canary, surfaces)
        self.assertEqual(first, ["agent-context", "stdout"])
        self.assertEqual(second, first)
        with self.assertRaises(CredentialLeakDetected) as raised:
            assert_canary_absent(self.canary, surfaces)
        self.assertEqual(
            str(raised.exception),
            "credential canary found in surfaces: agent-context, stdout",
        )
        self.assertNotIn(self.canary, str(raised.exception))

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
