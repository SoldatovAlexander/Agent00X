from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.actuator import publish_authorized_request
from app_contracts.authority import DeterministicPolicy, PolicyConfig
from app_contracts.mock_github import MockGitHubEndpoint
from app_contracts.validator import ContractValidationError
from app_contracts.gateway import GatewayDecision, GatewayPath


NOW = datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc)


class ActuatorTests(unittest.TestCase):
    def setUp(self):
        self.chain = json.loads((ROOT / "fixtures" / "valid" / "mvp-chain.json").read_text())
        self.endpoint = MockGitHubEndpoint()
        self.policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({"github-installation/42/repository/1001"}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        self.decision = self.policy.decide(
            decision_id="decision-actuator-001",
            actuator_request=self.chain["actuator_request"],
            approval=self.chain["approval"],
            staged_change=self.chain["staged_change"],
            intent=self.chain["intent"],
            now=NOW,
        )

    def test_authorized_typed_request_reaches_mock_boundary(self):
        result = publish_authorized_request(
            self.endpoint, self.chain["actuator_request"], self.decision, approval_valid=True,
            gateway_decision=GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",)),
            intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
        )
        self.assertEqual(result.pull_request_id, 1)

    def test_policy_mismatch_cannot_reach_mock_boundary(self):
        self.decision["repository_id"] = "github-installation/42/repository/9999"
        with self.assertRaisesRegex(ContractValidationError, "repository_id mismatch"):
            publish_authorized_request(
                self.endpoint, self.chain["actuator_request"], self.decision, approval_valid=True,
                gateway_decision=GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",)),
                intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
            )

    def test_invalid_approval_cannot_reach_mock_boundary(self):
        with self.assertRaisesRegex(ContractValidationError, "authority proof"):
            publish_authorized_request(
                self.endpoint, self.chain["actuator_request"], self.decision, approval_valid=False,
                gateway_decision=GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",)),
                intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
            )

    def test_fast_path_cannot_reach_actuator(self):
        with self.assertRaisesRegex(ContractValidationError, "gateway has not authorized"):
            publish_authorized_request(
                self.endpoint, self.chain["actuator_request"], self.decision, approval_valid=True,
                gateway_decision=GatewayDecision(GatewayPath.FAST, True, ("internal-read-only",)),
                intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
            )


if __name__ == "__main__":
    unittest.main()
