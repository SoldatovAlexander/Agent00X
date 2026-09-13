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
        self.assertEqual(str(raised.exception), "credential canary found")
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
        self.assertEqual(str(raised.exception), "credential canary found")
        self.assertNotIn(self.canary, str(raised.exception))

    def test_canary_in_reachable_cyclic_surface_is_not_printed(self):
        holder: dict = {"note": self.canary}
        holder["self"] = holder
        surfaces = dict(self.clean_surfaces)
        surfaces["evidence"] = holder
        self.assertEqual(find_canary_surfaces(self.canary, surfaces), ["evidence"])
        with self.assertRaises(CredentialLeakDetected) as raised:
            assert_canary_absent(self.canary, surfaces)
        self.assertEqual(str(raised.exception), "credential canary found")
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
        self.assertEqual(str(raised.exception), "credential canary found")
        self.assertNotIn(self.canary, str(raised.exception))

    def test_unsupported_value_yields_finding_without_repr_or_value(self):
        class Unprintable:
            def __str__(self):
                raise RuntimeError("synthetic-serialization-failure-001")

            def __repr__(self):
                return "Unprintable(synthetic-repr-002)"

        surfaces = {"agent-context": {"opaque": Unprintable()}, "stdout": "clean"}
        self.assertEqual(find_canary_surfaces(self.canary, surfaces), ["agent-context"])
        with self.assertRaises(CredentialLeakDetected) as raised:
            assert_canary_absent(self.canary, surfaces)
        message = str(raised.exception)
        self.assertEqual(message, "credential canary found")
        self.assertNotIn("synthetic-serialization-failure-001", message)
        self.assertNotIn("synthetic-repr-002", message)
        self.assertNotIn(self.canary, message)

    def test_non_string_surface_key_is_rejected_without_repr(self):
        for hostile in (123, ("agent", "context"), frozenset({"agent-context"})):
            with self.subTest(key=type(hostile).__name__):
                with self.assertRaises(ValueError) as raised:
                    find_canary_surfaces(self.canary, {hostile: self.canary})
                message = str(raised.exception)
                self.assertEqual(message, "surface name must be a string")
                self.assertNotIn(self.canary, message)
        with self.assertRaises(ValueError):
            assert_canary_absent(self.canary, {123: "clean"})

    def test_deeply_nested_canary_detected_without_value_leak(self):
        surfaces = {
            "agent-context": {
                "turns": [
                    {"role": "tool", "output": {"files": [{"note": "clean"}]}},
                    {"role": "tool", "output": {"files": [{"note": self.canary}]}},
                ]
            },
            "stdout": {"lines": ["ok", {"nested": ["ok", {"deep": "ok"}]}]},
        }
        self.assertEqual(find_canary_surfaces(self.canary, surfaces), ["agent-context"])
        with self.assertRaises(CredentialLeakDetected) as raised:
            assert_canary_absent(self.canary, surfaces)
        self.assertEqual(str(raised.exception), "credential canary found")
        self.assertNotIn(self.canary, str(raised.exception))
        clean = {"stdout": {"lines": ["ok", {"nested": ["ok", {"deep": "ok"}]}]}}
        self.assertEqual(find_canary_surfaces(self.canary, clean), [])
        assert_canary_absent(self.canary, clean)

    def test_malformed_surface_root_rejected_without_representation(self):
        for bad in (None, ["agent-context"], "surfaces", 42, {("k", "v")}):
            with self.subTest(surfaces=type(bad).__name__):
                with self.assertRaises(ValueError) as raised:
                    find_canary_surfaces(self.canary, bad)
                self.assertNotIsInstance(raised.exception, (TypeError, AttributeError))
                self.assertNotIn(self.canary, str(raised.exception))
                with self.assertRaises(ValueError):
                    assert_canary_absent(self.canary, bad)
        self.assertEqual(find_canary_surfaces(self.canary, self.clean_surfaces), [])

    def test_invalid_canary_rejected_deterministically(self):
        for bad in ("", None, 123, ["canary"]):
            with self.subTest(canary=type(bad).__name__):
                with self.assertRaises(ValueError) as raised:
                    find_canary_surfaces(bad, self.clean_surfaces)
                self.assertNotIsInstance(raised.exception, TypeError)
                with self.assertRaises(ValueError):
                    assert_canary_absent(bad, self.clean_surfaces)

    def test_raised_finding_contains_no_surface_names(self):
        hostile_name = "surface-caller-secret-001"
        surfaces = {hostile_name: {"note": self.canary}, "stdout": "clean"}
        self.assertEqual(find_canary_surfaces(self.canary, surfaces), [hostile_name])
        with self.assertRaises(CredentialLeakDetected) as raised:
            assert_canary_absent(self.canary, surfaces)
        message = str(raised.exception)
        self.assertEqual(message, "credential canary found")
        self.assertNotIn(hostile_name, message)
        self.assertNotIn(self.canary, message)

    def test_canary_leak_in_audit_is_detected(self):
        surfaces = dict(self.clean_surfaces)
        surfaces["audit"] = {"note": self.canary}
        with self.assertRaises(CredentialLeakDetected):
            assert_canary_absent(self.canary, surfaces)

    def test_canary_leak_in_evidence_is_detected(self):
        surfaces = dict(self.clean_surfaces)
        surfaces["evidence"] = {"report": f"failure output: {self.canary}"}
        with self.assertRaises(CredentialLeakDetected):
            assert_canary_absent(self.canary, surfaces)


if __name__ == "__main__":
    unittest.main()
