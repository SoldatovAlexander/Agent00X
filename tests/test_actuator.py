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
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        for bad_proof in (False, None, "yes", 0, []):
            with self.subTest(proof=bad_proof):
                endpoint = MockGitHubEndpoint()
                with self.assertRaisesRegex(
                    ContractValidationError, "^actuator: approval proof is invalid$"
                ):
                    publish_authorized_request(
                        endpoint, self.chain["actuator_request"], self.decision,
                        approval_valid=bad_proof, gateway_decision=gateway,
                        intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
                    )
                self.assertIsNone(
                    endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"])
                )

    def test_malformed_request_identity_denied_before_publish(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        malformed = [
            ("non-mapping", "not-a-mapping"),
            ("missing-branch", {k: v for k, v in self.chain["actuator_request"].items() if k != "branch_namespace"}),
            ("empty-operation", dict(self.chain["actuator_request"], operation="")),
            ("non-string-repo", dict(self.chain["actuator_request"], repository_id=42)),
            ("none-digest", dict(self.chain["actuator_request"], staged_change_digest=None)),
        ]
        for label, request in malformed:
            with self.subTest(case=label):
                endpoint = MockGitHubEndpoint()
                with self.assertRaises(ContractValidationError) as raised:
                    publish_authorized_request(
                        endpoint, request, self.decision, approval_valid=True,
                        gateway_decision=gateway, intent=self.chain["intent"],
                        now=NOW, approval=self.chain["approval"],
                    )
                self.assertIsNone(
                    endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"])
                )
                self.assertNotIn("caller-secret", str(raised.exception))

    def test_unregistered_operation_denied_before_provider_call(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        request = dict(self.chain["actuator_request"], operation="workspace.delete")
        decision = dict(self.decision, operation="workspace.delete")
        intent = dict(self.chain["intent"], operation="workspace.delete")
        for label, triple in (
            ("request-only", (request, self.decision, self.chain["intent"])),
            ("coordinated", (request, decision, intent)),
        ):
            with self.subTest(case=label):
                endpoint = MockGitHubEndpoint()
                asked_request, asked_decision, asked_intent = triple
                with self.assertRaisesRegex(
                    ContractValidationError, "^actuator: operation is not registered$"
                ):
                    publish_authorized_request(
                        endpoint, asked_request, asked_decision, approval_valid=True,
                        gateway_decision=gateway, intent=asked_intent,
                        now=NOW, approval=self.chain["approval"],
                    )
                self.assertIsNone(
                    endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"])
                )

    def test_non_mapping_request_denied_with_zero_side_effect(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        for bad in (None, 123, "request", ["operation"], (("operation", "x"),)):
            with self.subTest(request=type(bad).__name__):
                endpoint = MockGitHubEndpoint()
                with self.assertRaisesRegex(
                    ContractValidationError, "^actuator: request is malformed$"
                ):
                    publish_authorized_request(
                        endpoint, bad, self.decision, approval_valid=True,
                        gateway_decision=gateway, intent=self.chain["intent"],
                        now=NOW, approval=self.chain["approval"],
                    )
                self.assertIsNone(
                    endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"])
                )

    def test_malformed_gateway_decision_denied_before_endpoint(self):
        for bad in (None, "slow", {"allowed": True, "path": "slow"}, 42, []):
            with self.subTest(decision=type(bad).__name__):
                endpoint = MockGitHubEndpoint()
                with self.assertRaisesRegex(
                    ContractValidationError, "^actuator: gateway decision is malformed$"
                ):
                    publish_authorized_request(
                        endpoint, self.chain["actuator_request"], self.decision,
                        approval_valid=True, gateway_decision=bad,
                        intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
                    )
                self.assertIsNone(
                    endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"])
                )

    def test_malformed_policy_decision_denied_before_endpoint(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        for bad in (None, ["decision"], "decision", 42):
            with self.subTest(decision=type(bad).__name__):
                endpoint = MockGitHubEndpoint()
                with self.assertRaises(ContractValidationError) as raised:
                    publish_authorized_request(
                        endpoint, self.chain["actuator_request"], bad,
                        approval_valid=True, gateway_decision=gateway,
                        intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
                    )
                self.assertNotIsInstance(raised.exception, (TypeError, AttributeError, KeyError))
                self.assertIsNone(
                    endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"])
                )

    def test_malformed_endpoint_denied_without_side_effect(self):
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        for bad in (None, "endpoint", 42, {}, object()):
            with self.subTest(endpoint=type(bad).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "^actuator: endpoint is malformed$"
                ):
                    publish_authorized_request(
                        bad, self.chain["actuator_request"], self.decision,
                        approval_valid=True, gateway_decision=gateway,
                        intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
                    )
        result = publish_authorized_request(
            self.endpoint, self.chain["actuator_request"], self.decision,
            approval_valid=True, gateway_decision=gateway,
            intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
        )
        self.assertEqual(result.pull_request_id, 1)

    def test_fast_path_cannot_reach_actuator(self):
        with self.assertRaisesRegex(ContractValidationError, "gateway has not authorized"):
            publish_authorized_request(
                self.endpoint, self.chain["actuator_request"], self.decision, approval_valid=True,
                gateway_decision=GatewayDecision(GatewayPath.FAST, True, ("internal-read-only",)),
                intent=self.chain["intent"], now=NOW, approval=self.chain["approval"],
            )

    def test_missing_approval_is_refused_before_mock_boundary(self):
        endpoint = MockGitHubEndpoint()
        with self.assertRaisesRegex(ContractValidationError, "approval is required") as raised:
            publish_authorized_request(
                endpoint, self.chain["actuator_request"], self.decision, approval_valid=True,
                gateway_decision=GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",)),
                intent=self.chain["intent"], now=NOW, approval=None,
            )
        self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))
        leaked = str(raised.exception)
        self.assertNotIn(self.chain["approval"]["approval_id"], leaked)
        self.assertNotIn(self.chain["intent"]["idempotency_key"], leaked)


if __name__ == "__main__":
    unittest.main()
