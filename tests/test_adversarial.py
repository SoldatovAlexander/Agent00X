from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.actuator import publish_authorized_request
from app_contracts.authority import DeterministicPolicy, PolicyConfig
from app_contracts.chain import validate_chain
from app_contracts.gateway import GatewayDecision, GatewayPath, enforce
from app_contracts.mock_github import MockGitHubEndpoint
from app_contracts.runtime_store import SQLiteProcessStore
from app_contracts.validator import ContractValidationError


NOW = datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc)


class AdversarialFlowTests(unittest.TestCase):
    def setUp(self):
        self.chain = json.loads((ROOT / "fixtures" / "valid" / "mvp-chain.json").read_text())
        self.policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({"github-installation/42/repository/1001"}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))

    def _publication_envelope(self) -> dict:
        envelope = json.loads(json.dumps(self.chain["canonical_envelope"]))
        envelope["intent"] = {"operation": "publish_pull_request", "risk_class": "critical"}
        envelope["destination"] = {"principal_id": "actuator-github-001", "port": "tool"}
        return envelope

    def test_tainted_payload_cannot_authorize_or_reach_actuator(self):
        self.chain["canonical_envelope"]["security"]["tainted"] = True
        with self.assertRaisesRegex(ContractValidationError, "tainted envelope"):
            validate_chain(self.chain)

        with tempfile.TemporaryDirectory(prefix="app-adversarial-") as directory:
            with SQLiteProcessStore(Path(directory) / "runtime.sqlite3") as store:
                store.create("process-demo-001")
                envelope = self._publication_envelope()
                envelope["security"]["tainted"] = True
                decision = enforce(envelope, policy_available=True, audit_sink=store)
                self.assertEqual(decision.path, GatewayPath.SLOW)
                self.assertFalse(decision.allowed)
                self.assertEqual(store.audit_events("process-demo-001")[0]["result"], "denied")

    def test_policy_outage_blocks_full_publication_path(self):
        with tempfile.TemporaryDirectory(prefix="app-adversarial-") as directory:
            with SQLiteProcessStore(Path(directory) / "runtime.sqlite3") as store:
                store.create("process-demo-001")
                gateway = enforce(self._publication_envelope(), policy_available=False, audit_sink=store)
                self.assertFalse(gateway.allowed)
                self.assertEqual(gateway.path, GatewayPath.DEGRADED)
                self.assertIn("policy-unavailable", gateway.reason_codes)

    def test_replay_returns_original_side_effect_only(self):
        endpoint = MockGitHubEndpoint()
        decision = self.policy.decide(
            decision_id="decision-demo-001",
            actuator_request=self.chain["actuator_request"], approval=self.chain["approval"],
            staged_change=self.chain["staged_change"], intent=self.chain["intent"], now=NOW,
        )
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        first = publish_authorized_request(
            endpoint, self.chain["actuator_request"], decision,
            approval_valid=True, gateway_decision=gateway, intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
        )
        second = publish_authorized_request(
            endpoint, self.chain["actuator_request"], decision,
            approval_valid=True, gateway_decision=gateway, intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
        )
        self.assertEqual(first, second)
        self.assertEqual(first.pull_request_id, 1)


    def test_post_allow_request_swaps_are_rejected_before_mock_boundary(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        digest = self.chain["actuator_request"]["staged_change_digest"]

        def allow_decision():
            return self.policy.decide(
                decision_id="decision-demo-002",
                actuator_request=self.chain["actuator_request"], approval=self.chain["approval"],
                staged_change=self.chain["staged_change"], intent=self.chain["intent"], now=NOW,
            )

        swaps = {
            "repository": {"repository_id": "github-installation/42/repository/9999"},
            "branch": {
                "branch_namespace": "agent/process-evil-001",
                "idempotency_key": f"publish/process-evil-001/{digest}",
            },
            "digest": {"staged_change_digest": "sha256:" + "0" * 64},
            "idempotency_key": {"idempotency_key": f"publish/process-demo-001/{'sha256:' + '0' * 64}"},
        }
        for name, mutation in swaps.items():
            with self.subTest(swap=name):
                endpoint = MockGitHubEndpoint()
                decision = allow_decision()
                self.assertEqual(decision["effect"], "allow")
                request = json.loads(json.dumps(self.chain["actuator_request"]))
                request.update(mutation)
                with self.assertRaises(ContractValidationError):
                    publish_authorized_request(
                        endpoint, request, decision, approval_valid=True,
                        gateway_decision=gateway, intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
                    )
                self.assertIsNone(endpoint.find_by_idempotency_key(request["idempotency_key"]))
                self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))

    def test_coordinated_triple_swap_is_rejected_by_approval_digest(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        digest = self.chain["actuator_request"]["staged_change_digest"]
        evil_request = json.loads(json.dumps(self.chain["actuator_request"]))
        evil_request["branch_namespace"] = "agent/process-evil-001"
        evil_request["idempotency_key"] = f"publish/process-evil-001/{digest}"
        evil_intent = json.loads(json.dumps(self.chain["intent"]))
        evil_intent["branch_namespace"] = "agent/process-evil-001"
        evil_intent["idempotency_key"] = f"publish/process-evil-001/{digest}"
        endpoint = MockGitHubEndpoint()
        with self.assertRaisesRegex(ContractValidationError, "approved intent digest mismatch") as raised:
            publish_authorized_request(
                endpoint, evil_request, self.policy.decide(
                    decision_id="decision-demo-006",
                    actuator_request=self.chain["actuator_request"], approval=self.chain["approval"],
                    staged_change=self.chain["staged_change"], intent=self.chain["intent"], now=NOW,
                ),
                approval_valid=True, gateway_decision=gateway,
                intent=evil_intent, now=NOW, approval=self.chain["approval"],
            )
        self.assertIsNone(endpoint.find_by_idempotency_key(evil_request["idempotency_key"]))
        self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))
        leaked = str(raised.exception)
        self.assertNotIn(evil_intent["branch_namespace"], leaked)
        self.assertNotIn(self.chain["approval"]["approval_id"], leaked)

    def test_branch_only_swap_is_rejected_without_intent(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        endpoint = MockGitHubEndpoint()
        decision = self.policy.decide(
            decision_id="decision-demo-003",
            actuator_request=self.chain["actuator_request"], approval=self.chain["approval"],
            staged_change=self.chain["staged_change"], intent=self.chain["intent"], now=NOW,
        )
        request = json.loads(json.dumps(self.chain["actuator_request"]))
        request["branch_namespace"] = "agent/process-evil-001"
        with self.assertRaisesRegex(ContractValidationError, "approved intent branch_namespace mismatch"):
            publish_authorized_request(
                endpoint, request, decision, approval_valid=True, gateway_decision=gateway,
                intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
            )
        self.assertIsNone(endpoint.find_by_idempotency_key(request["idempotency_key"]))

    def test_coordinated_swap_without_intent_is_rejected_before_mock_boundary(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        endpoint = MockGitHubEndpoint()
        decision = self.policy.decide(
            decision_id="decision-demo-005",
            actuator_request=self.chain["actuator_request"], approval=self.chain["approval"],
            staged_change=self.chain["staged_change"], intent=self.chain["intent"], now=NOW,
        )
        digest = self.chain["actuator_request"]["staged_change_digest"]
        request = json.loads(json.dumps(self.chain["actuator_request"]))
        request["branch_namespace"] = "agent/process-evil-001"
        request["idempotency_key"] = f"publish/process-evil-001/{digest}"
        with self.assertRaises(TypeError):
            publish_authorized_request(  # type: ignore[call-arg]
                endpoint, request, decision, approval_valid=True, gateway_decision=gateway,
                now=NOW,
            )
        self.assertIsNone(endpoint.find_by_idempotency_key(request["idempotency_key"]))
        self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))

    def test_matching_bound_request_reaches_mock_boundary(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        endpoint = MockGitHubEndpoint()
        decision = self.policy.decide(
            decision_id="decision-demo-004",
            actuator_request=self.chain["actuator_request"], approval=self.chain["approval"],
            staged_change=self.chain["staged_change"], intent=self.chain["intent"], now=NOW,
        )
        result = publish_authorized_request(
            endpoint, self.chain["actuator_request"], decision, approval_valid=True,
            gateway_decision=gateway, intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
        )
        self.assertEqual(result.pull_request_id, 1)
        self.assertIsNotNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))


if __name__ == "__main__":
    unittest.main()
