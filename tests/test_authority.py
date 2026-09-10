from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.authority import (
    DeterministicPolicy,
    PolicyConfig,
    PolicyUnavailable,
    check_decision_usable,
    validate_approval,
)
from app_contracts.validator import ContractValidationError, validate


NOW = datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc)


def load_chain() -> dict:
    return json.loads((ROOT / "fixtures" / "valid" / "mvp-chain.json").read_text())


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.chain = load_chain()
        self.config = PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({"github-installation/42/repository/1001"}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        )
        self.policy = DeterministicPolicy(self.config)

    def test_matching_approval_is_valid(self):
        validate_approval(
            self.chain["approval"], self.chain["staged_change"], self.chain["intent"],
            policy_version="policy-1", now=NOW,
        )

    def test_changed_destination_invalidates_approval(self):
        self.chain["intent"]["repository_id"] = "github-installation/42/repository/9999"
        with self.assertRaisesRegex(ValueError, "repository_id mismatch"):
            validate_approval(
                self.chain["approval"], self.chain["staged_change"], self.chain["intent"],
                policy_version="policy-1", now=NOW,
            )

    def test_expired_approval_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "expired"):
            validate_approval(
                self.chain["approval"], self.chain["staged_change"], self.chain["intent"],
                policy_version="policy-1", now=datetime(2026, 9, 6, tzinfo=timezone.utc),
            )

    def test_policy_returns_allow_for_bound_request(self):
        decision = self.policy.decide(
            decision_id="decision-policy-001",
            actuator_request=self.chain["actuator_request"],
            approval=self.chain["approval"],
            staged_change=self.chain["staged_change"],
            intent=self.chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "allow")
        self.assertEqual(decision["staged_change_digest"], self.chain["approval"]["staged_change_digest"])
        schema = json.loads((ROOT / "schemas" / "policy-decision.schema.json").read_text())
        validate(decision, schema)

    def test_policy_denies_unknown_repository(self):
        self.chain["actuator_request"]["repository_id"] = "github-installation/42/repository/9999"
        decision = self.policy.decide(
            decision_id="decision-policy-002",
            actuator_request=self.chain["actuator_request"],
            approval=self.chain["approval"],
            staged_change=self.chain["staged_change"],
            intent=self.chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "deny")
        self.assertEqual(decision["reason_codes"], ["repository-not-allowlisted"])

    def test_policy_denies_swapped_request_digest(self):
        forged = "sha256:" + "0" * 64
        self.assertNotEqual(forged, self.chain["approval"]["staged_change_digest"])
        self.chain["actuator_request"]["staged_change_digest"] = forged
        decision = self.policy.decide(
            decision_id="decision-policy-004",
            actuator_request=self.chain["actuator_request"],
            approval=self.chain["approval"],
            staged_change=self.chain["staged_change"],
            intent=self.chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "deny")
        self.assertEqual(decision["reason_codes"], ["request-digest-mismatch"])
        self.assertEqual(decision["staged_change_digest"], self.chain["approval"]["staged_change_digest"])
        self.assertNotEqual(decision["staged_change_digest"], forged)
        schema = json.loads((ROOT / "schemas" / "policy-decision.schema.json").read_text())
        validate(decision, schema)

    def test_policy_denies_request_intent_branch_mismatch(self):
        digest = self.chain["actuator_request"]["staged_change_digest"]
        self.chain["actuator_request"]["branch_namespace"] = "agent/process-evil-001"
        self.chain["actuator_request"]["idempotency_key"] = f"publish/process-evil-001/{digest}"
        decision = self.policy.decide(
            decision_id="decision-policy-006",
            actuator_request=self.chain["actuator_request"],
            approval=self.chain["approval"],
            staged_change=self.chain["staged_change"],
            intent=self.chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "deny")
        self.assertEqual(decision["reason_codes"], ["request-intent-mismatch"])
        schema = json.loads((ROOT / "schemas" / "policy-decision.schema.json").read_text())
        validate(decision, schema)

    def test_approval_with_tampered_intent_digest_is_rejected(self):
        self.chain["approval"]["approved_intent_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "approved intent digest mismatch"):
            validate_approval(
                self.chain["approval"], self.chain["staged_change"], self.chain["intent"],
                policy_version="policy-1", now=NOW,
            )
        decision = self.policy.decide(
            decision_id="decision-policy-007",
            actuator_request=self.chain["actuator_request"],
            approval=self.chain["approval"],
            staged_change=self.chain["staged_change"],
            intent=self.chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "deny")
        self.assertEqual(decision["reason_codes"], ["approval-approved-intent-digest-mismatch"])
        schema = json.loads((ROOT / "schemas" / "policy-decision.schema.json").read_text())
        validate(decision, schema)

    def test_coordinated_triple_swap_is_rejected_by_intent_digest(self):
        digest = self.chain["actuator_request"]["staged_change_digest"]
        for name in ("actuator_request", "intent"):
            self.chain[name]["branch_namespace"] = "agent/process-evil-001"
            self.chain[name]["idempotency_key"] = f"publish/process-evil-001/{digest}"
        decision = self.policy.decide(
            decision_id="decision-policy-008",
            actuator_request=self.chain["actuator_request"],
            approval=self.chain["approval"],
            staged_change=self.chain["staged_change"],
            intent=self.chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "deny")
        self.assertEqual(decision["reason_codes"], ["approval-approved-intent-digest-mismatch"])
        schema = json.loads((ROOT / "schemas" / "policy-decision.schema.json").read_text())
        validate(decision, schema)

    def test_allow_decision_expiry_boundary(self):
        decision = self.policy.decide(
            decision_id="decision-policy-005",
            actuator_request=self.chain["actuator_request"],
            approval=self.chain["approval"],
            staged_change=self.chain["staged_change"],
            intent=self.chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "allow")
        expires_at = datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00"))
        check_decision_usable(decision, now=NOW)
        check_decision_usable(decision, now=expires_at - timedelta(seconds=1))
        for moment in (expires_at, expires_at + timedelta(seconds=1)):
            with self.subTest(now=moment):
                with self.assertRaisesRegex(ContractValidationError, "decision: expired") as raised:
                    check_decision_usable(decision, now=moment)
                leaked = str(raised.exception)
                self.assertNotIn(self.chain["approval"]["approval_id"], leaked)
                self.assertNotIn(self.chain["approval"]["staged_change_digest"], leaked)

    def test_policy_unavailable_fails_closed(self):
        unavailable = DeterministicPolicy(self.config, available=False)
        with self.assertRaises(PolicyUnavailable):
            unavailable.decide(
                decision_id="decision-policy-003",
                actuator_request=self.chain["actuator_request"],
                approval=self.chain["approval"],
                staged_change=self.chain["staged_change"],
                intent=self.chain["intent"], now=NOW,
            )


class DecisionUseBoundary:
    """Test-local mock boundary gated by the authority use-time check.

    It mirrors the pattern production actuator/provider boundaries must
    follow: verify the allow decision is still usable at the current instant
    before recording any side effect. An expired, non-allow, or malformed
    decision never reaches the mock side effect.
    """

    def __init__(self) -> None:
        self.side_effects: list[str] = []

    def publish(self, decision: dict, *, now: datetime) -> str:
        check_decision_usable(decision, now=now)
        self.side_effects.append("mock-receipt")
        return "mock-receipt"


class RealActuatorExpiryTests(unittest.TestCase):
    """Actual-call regression on the real actuator boundary.

    The production `publish_authorized_request` (and the brokered actuator
    built on it) must enforce the allow-decision expiry at use time:
    before-expiry use reaches the mock boundary, at/after-expiry use is
    refused with no mock side effect and no approval-content leakage.
    """

    def _allow_decision(self):
        chain = load_chain()
        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({"github-installation/42/repository/1001"}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        decision = policy.decide(
            decision_id="decision-use-010",
            actuator_request=chain["actuator_request"],
            approval=chain["approval"],
            staged_change=chain["staged_change"],
            intent=chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "allow")
        return chain, decision

    def test_real_boundary_enforces_before_at_after_expiry(self):
        from app_contracts.actuator import publish_authorized_request
        from app_contracts.gateway import GatewayDecision, GatewayPath
        from app_contracts.mock_github import MockGitHubEndpoint

        chain, decision = self._allow_decision()
        expires_at = datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00"))
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        for moment in (NOW, expires_at - timedelta(seconds=1)):
            with self.subTest(now=moment):
                endpoint = MockGitHubEndpoint()
                result = publish_authorized_request(
                    endpoint, chain["actuator_request"], decision, approval_valid=True,
                    gateway_decision=gateway, intent=chain["intent"], now=moment,
                    approval=chain["approval"],
                )
                self.assertEqual(result.pull_request_id, 1)
                self.assertIsNotNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))
        for moment in (expires_at, expires_at + timedelta(seconds=1)):
            with self.subTest(now=moment):
                endpoint = MockGitHubEndpoint()
                with self.assertRaisesRegex(ContractValidationError, "decision: expired") as raised:
                    publish_authorized_request(
                        endpoint, chain["actuator_request"], decision, approval_valid=True,
                        gateway_decision=gateway, intent=chain["intent"], now=moment,
                        approval=chain["approval"],
                    )
                self.assertIsNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))
                leaked = str(raised.exception)
                self.assertNotIn(chain["approval"]["approval_id"], leaked)
                self.assertNotIn(chain["approval"]["staged_change_digest"], leaked)

    def test_brokered_boundary_rejects_expired_before_provider(self):
        from app_contracts.broker import InMemoryCredentialBroker
        from app_contracts.gateway import GatewayDecision, GatewayPath
        from app_contracts.github_actuator import BrokeredGitHubActuator
        from app_contracts.mock_github import MockGitHubEndpoint

        chain, decision = self._allow_decision()
        expires_at = datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00"))
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        actuator = BrokeredGitHubActuator(broker)
        with self.assertRaisesRegex(ContractValidationError, "decision: expired"):
            actuator.publish_pull_request(
                actuator_request=chain["actuator_request"],
                credential_grant=chain["credential_use_grant"],
                policy_decision=decision,
                approval_valid=True,
                gateway_decision=gateway,
                intent=chain["intent"],
                now=expires_at + timedelta(seconds=1),
                approval=chain["approval"],
            )
        self.assertEqual(broker.opened_grants, [])
        self.assertIsNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))


class DecisionUseBoundaryTests(unittest.TestCase):
    def _allow_decision(self) -> tuple[dict, dict]:
        chain = load_chain()
        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({"github-installation/42/repository/1001"}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        decision = policy.decide(
            decision_id="decision-use-001",
            actuator_request=chain["actuator_request"],
            approval=chain["approval"],
            staged_change=chain["staged_change"],
            intent=chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "allow")
        return chain, decision

    def test_expired_decision_never_reaches_mock_boundary(self):
        chain, decision = self._allow_decision()
        expires_at = datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00"))
        boundary = DecisionUseBoundary()
        self.assertEqual(boundary.publish(decision, now=NOW), "mock-receipt")
        self.assertEqual(
            boundary.publish(decision, now=expires_at - timedelta(seconds=1)), "mock-receipt",
        )
        self.assertEqual(len(boundary.side_effects), 2)
        for moment in (expires_at, expires_at + timedelta(seconds=1)):
            with self.subTest(now=moment):
                before = len(boundary.side_effects)
                with self.assertRaisesRegex(ContractValidationError, "decision: expired") as raised:
                    boundary.publish(decision, now=moment)
                self.assertEqual(len(boundary.side_effects), before)
                leaked = str(raised.exception)
                self.assertNotIn(chain["approval"]["approval_id"], leaked)
                self.assertNotIn(chain["approval"]["staged_change_digest"], leaked)

    def test_deny_decision_never_reaches_mock_boundary(self):
        chain = load_chain()
        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({"github-installation/42/repository/1001"}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        chain["actuator_request"]["repository_id"] = "github-installation/42/repository/9999"
        decision = policy.decide(
            decision_id="decision-use-002",
            actuator_request=chain["actuator_request"],
            approval=chain["approval"],
            staged_change=chain["staged_change"],
            intent=chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "deny")
        boundary = DecisionUseBoundary()
        with self.assertRaisesRegex(ContractValidationError, "decision: not allow"):
            boundary.publish(decision, now=NOW)
        self.assertEqual(boundary.side_effects, [])

    def test_malformed_expiry_is_invalid_without_side_effect(self):
        _, decision = self._allow_decision()
        boundary = DecisionUseBoundary()
        for broken in ("missing", "none"):
            with self.subTest(broken=broken):
                mutated = json.loads(json.dumps(decision))
                if broken == "missing":
                    del mutated["expires_at"]
                else:
                    mutated["expires_at"] = None
                with self.assertRaisesRegex(ContractValidationError, "decision: expiry is invalid"):
                    boundary.publish(mutated, now=NOW)
        self.assertEqual(boundary.side_effects, [])


if __name__ == "__main__":
    unittest.main()
