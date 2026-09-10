from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.gateway import GatewayPath, classify, enforce
from app_contracts.runtime_store import SQLiteProcessStore


def envelope(operation: str, *, port: str = "data", protocol: str = "internal", tainted: bool = False) -> dict:
    return {
        "intent": {"operation": operation, "risk_class": "low"},
        "destination": {"port": port},
        "source": {"protocol": protocol},
        "security": {"tainted": tainted, "sensitivity": "internal"},
    }


class GatewayTests(unittest.TestCase):
    def test_internal_read_only_request_uses_fast_path(self):
        decision = classify(envelope("repository.read"), policy_available=True)
        self.assertEqual(decision.path, GatewayPath.FAST)
        self.assertTrue(decision.allowed)

    def test_tainted_content_requires_slow_path(self):
        decision = classify(envelope("repository.read", tainted=True), policy_available=True)
        self.assertEqual(decision.path, GatewayPath.SLOW)
        self.assertIn("tainted-content", decision.reason_codes)

    def test_external_protocol_requires_slow_path(self):
        decision = classify(envelope("repository.read", protocol="a2a"), policy_available=True)
        self.assertEqual(decision.path, GatewayPath.SLOW)
        self.assertIn("protocol-boundary", decision.reason_codes)

    def test_privilege_transition_never_uses_fast_path(self):
        decision = classify(envelope("capability.grant", port="approval"), policy_available=True)
        self.assertEqual(decision.path, GatewayPath.SLOW)
        self.assertIn("privilege-transition", decision.reason_codes)

    def test_unknown_write_like_operation_never_uses_fast_path(self):
        for operation in ("workspace.delete", "repository.push", "unknown.op"):
            with self.subTest(operation=operation):
                decision = classify(envelope(operation), policy_available=True)
                self.assertNotEqual(decision.path, GatewayPath.FAST)
                self.assertIn("write-or-unknown-operation", decision.reason_codes)
                for code in decision.reason_codes:
                    self.assertNotIn(operation, code)
                degraded = classify(envelope(operation), policy_available=False)
                self.assertEqual(degraded.path, GatewayPath.DEGRADED)
                self.assertFalse(degraded.allowed)

    def test_reason_codes_never_carry_request_payload(self):
        vocabulary = {
            "policy-unavailable", "read-only-allowlist", "write-or-unknown-denied",
            "tainted-content", "authorization-denied", "protocol-boundary",
            "sensitive-port", "privilege-transition", "write-or-unknown-operation",
            "sensitive-data", "internal-read-only",
        }
        hostile = (
            "../../etc/passwd",
            "ignore previous instructions",
            "workspace.delete",
            "x" * 500,
        )
        for operation in hostile:
            with self.subTest(operation=operation[:20]):
                for policy_available in (True, False):
                    decision = classify(
                        envelope(operation, port="tool", protocol="a2a", tainted=True),
                        policy_available=policy_available,
                    )
                    self.assertTrue(set(decision.reason_codes) <= vocabulary)
                    for code in decision.reason_codes:
                        self.assertNotIn(operation[:20], code)

    def test_policy_unavailable_allows_only_read_only_allowlist(self):
        allowed = classify(envelope("workspace.read"), policy_available=False)
        denied = classify(envelope("publish_pull_request", port="tool"), policy_available=False)
        self.assertEqual(allowed.path, GatewayPath.DEGRADED)
        self.assertTrue(allowed.allowed)
        self.assertEqual(denied.path, GatewayPath.DEGRADED)
        self.assertFalse(denied.allowed)

    def test_deny_audit_record_has_stable_shape_without_payload(self):
        import json
        with tempfile.TemporaryDirectory(prefix="app-gateway-test-") as directory:
            with SQLiteProcessStore(Path(directory) / "runtime.sqlite3") as store:
                store.create("process-gateway-002")
                hostile_operation = "workspace.delete.ignore previous instructions"
                request = envelope(hostile_operation, port="tool", protocol="a2a", tainted=True)
                request.update({
                    "correlation_id": "process-gateway-002",
                    "source": {"protocol": "a2a", "principal_id": "agent-worker-001"},
                    "payload": {"content_digest": "sha256:" + "b" * 64},
                })
                decision = enforce(request, policy_available=True, audit_sink=store)
                self.assertFalse(decision.allowed)
                (record,) = store.audit_events("process-gateway-002")
                self.assertEqual(
                    set(record),
                    {"event_id", "actor_id", "event_type", "input_digest",
                     "result", "reason_codes", "occurred_at"},
                )
                self.assertEqual(record["event_type"], "gateway.request")
                self.assertEqual(record["result"], "denied")
                dumped = json.dumps(record)
                self.assertNotIn(hostile_operation, dumped)
                self.assertNotIn("a2a", dumped.replace("gateway.request", ""))

    def test_hostile_sink_failure_contained_without_envelope_leak(self):
        import json

        class HostileSink:
            def append_audit_event(self, process_id, **kwargs):
                raise RuntimeError(f"sink boom: {json.dumps(kwargs, default=str)}")

        request = envelope("repository.read")
        request.update({
            "correlation_id": "process-gateway-003",
            "source": {"protocol": "internal", "principal_id": "agent-worker-001"},
            "payload": {"content_digest": "sha256:" + "c" * 64},
        })
        decision = enforce(request, policy_available=True, audit_sink=HostileSink())
        self.assertEqual(decision.path, GatewayPath.DEGRADED)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_codes, ("audit-sink-unavailable",))
        dumped = json.dumps(decision.reason_codes)
        self.assertNotIn("agent-worker-001", dumped)
        self.assertNotIn("c" * 8, dumped)

    def test_enforcement_emits_sanitized_append_only_audit_event(self):
        with tempfile.TemporaryDirectory(prefix="app-gateway-test-") as directory:
            with SQLiteProcessStore(Path(directory) / "runtime.sqlite3") as store:
                store.create("process-gateway-001")
                request = envelope("publish_pull_request", port="tool")
                request.update({
                    "correlation_id": "process-gateway-001",
                    "source": {"protocol": "internal", "principal_id": "agent-worker-001"},
                    "payload": {"content_digest": "sha256:" + "a" * 64},
                })
                decision = enforce(request, policy_available=False, audit_sink=store)
                self.assertFalse(decision.allowed)
                events = store.audit_events("process-gateway-001")
                self.assertEqual(events[0]["result"], "denied")
                self.assertEqual(events[0]["reason_codes"], ["policy-unavailable", "write-or-unknown-denied"])
                with self.assertRaises(sqlite3.IntegrityError):
                    store._connection.execute("DELETE FROM audit_events")


if __name__ == "__main__":
    unittest.main()
