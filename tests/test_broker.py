from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.authority import DeterministicPolicy, PolicyConfig
from app_contracts.broker import InMemoryCredentialBroker
from app_contracts.gateway import GatewayDecision, GatewayPath
from app_contracts.github_actuator import BrokeredGitHubActuator
from app_contracts.mock_github import MockGitHubEndpoint
from app_contracts.validator import ContractValidationError


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.chain = json.loads((ROOT / "fixtures" / "valid" / "mvp-chain.json").read_text())
        self.endpoint = MockGitHubEndpoint()
        self.broker = InMemoryCredentialBroker(lambda: self.endpoint)
        self.actuator = BrokeredGitHubActuator(self.broker)
        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({"github-installation/42/repository/1001"}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        self.decision = policy.decide(
            decision_id="decision-broker-001",
            actuator_request=self.chain["actuator_request"], approval=self.chain["approval"],
            staged_change=self.chain["staged_change"], intent=self.chain["intent"],
            now=datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc),
        )
        self.gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))

    def _publish(self):
        return self.actuator.publish_pull_request(
            actuator_request=self.chain["actuator_request"],
            credential_grant=self.chain["credential_use_grant"],
            policy_decision=self.decision,
            approval_valid=True,
            gateway_decision=self.gateway,
            intent=self.chain["intent"],
        )

    def test_brokered_actuator_publishes_without_exposing_credential(self):
        result = self._publish()
        self.assertEqual(result.pull_request_id, 1)
        self.assertEqual(self.broker.opened_grants, ["credential-grant-demo-001"])
        self.assertNotIn("token", self.chain["credential_use_grant"])

    def test_credential_grant_cannot_be_reused(self):
        self._publish()
        with self.assertRaisesRegex(ContractValidationError, "already used"):
            self._publish()

    def test_grant_replay_after_channel_failure_stays_denied(self):
        calls = []

        def failing_factory():
            calls.append("factory")
            raise RuntimeError("injected provider failure")

        broker = InMemoryCredentialBroker(failing_factory)
        actuator = BrokeredGitHubActuator(broker)

        def attempt():
            return actuator.publish_pull_request(
                actuator_request=self.chain["actuator_request"],
                credential_grant=self.chain["credential_use_grant"],
                policy_decision=self.decision,
                approval_valid=True,
                gateway_decision=self.gateway,
                intent=self.chain["intent"],
            )

        with self.assertRaisesRegex(RuntimeError, "injected provider failure"):
            attempt()
        with self.assertRaisesRegex(ContractValidationError, "already used"):
            attempt()
        self.assertEqual(calls, ["factory"])
        self.assertNotIn("token", json.dumps(self.chain["credential_use_grant"]))

    def test_grant_cannot_be_used_for_mutated_request(self):
        self.chain["actuator_request"]["body_artifact_ref"] = "artifact://pr/mutated/body"
        with self.assertRaisesRegex(ContractValidationError, "request digest mismatch"):
            self._publish()

    def test_brokered_coordinated_branch_key_grant_swap_is_rejected(self):
        import copy

        from app_contracts.digests import sha256_digest

        digest = self.chain["actuator_request"]["staged_change_digest"]
        evil_request = copy.deepcopy(self.chain["actuator_request"])
        evil_request["branch_namespace"] = "agent/process-evil-001"
        evil_request["idempotency_key"] = f"publish/process-evil-001/{digest}"
        evil_grant = copy.deepcopy(self.chain["credential_use_grant"])
        evil_grant["credential_grant_id"] = "credential-grant-evil-001"
        evil_grant["request_digest"] = sha256_digest(evil_request)
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        actuator = BrokeredGitHubActuator(broker)
        with self.assertRaisesRegex(ContractValidationError, "approved intent"):
            actuator.publish_pull_request(
                actuator_request=evil_request,
                credential_grant=evil_grant,
                policy_decision=self.decision,
                approval_valid=True,
                gateway_decision=self.gateway,
                intent=self.chain["intent"],
            )
        self.assertIsNone(endpoint.find_by_idempotency_key(evil_request["idempotency_key"]))
        self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))


if __name__ == "__main__":
    unittest.main()
