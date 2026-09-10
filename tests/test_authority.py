from __future__ import annotations

from datetime import datetime, timezone
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
    validate_approval,
)
from app_contracts.validator import validate


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


if __name__ == "__main__":
    unittest.main()
