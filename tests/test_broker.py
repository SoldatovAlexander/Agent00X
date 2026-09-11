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


NOW = datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc)


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
            now=NOW,
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
            now=NOW,
            approval=self.chain["approval"],
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
                now=NOW,
                approval=self.chain["approval"],
            )

        with self.assertRaisesRegex(RuntimeError, "injected provider failure"):
            attempt()
        with self.assertRaisesRegex(ContractValidationError, "already used"):
            attempt()
        self.assertEqual(calls, ["factory"])
        self.assertNotIn("token", json.dumps(self.chain["credential_use_grant"]))

    def test_malformed_grant_never_reaches_channel_factory(self):
        calls = []
        broker = InMemoryCredentialBroker(lambda: calls.append("factory"))
        for missing in ("credential_grant_id", "actuator_id", "repository_id", "operation", "request_digest", "single_use"):
            with self.subTest(missing=missing):
                grant = dict(self.chain["credential_use_grant"])
                del grant[missing]
                with self.assertRaisesRegex(ContractValidationError, "grant is malformed") as raised:
                    broker.open_github_publication_channel(grant, self.chain["actuator_request"], now=NOW)
                self.assertNotIn("token", str(raised.exception))
        with self.assertRaisesRegex(ContractValidationError, "grant is malformed"):
            broker.open_github_publication_channel("not-a-grant", self.chain["actuator_request"], now=NOW)
        self.assertEqual(calls, [])

    def test_malformed_request_never_reaches_channel_factory(self):
        calls = []
        broker = InMemoryCredentialBroker(lambda: calls.append("factory"))
        grant = self.chain["credential_use_grant"]
        bad_requests = [
            None,
            "not-a-mapping",
            {},
            {"actuator_id": "actuator-github-001", "token": "caller-secret-001"},
        ]
        for bad in bad_requests:
            with self.subTest(request=type(bad).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "actuator request is malformed"
                ) as raised:
                    broker.open_github_publication_channel(grant, bad, now=NOW)
                self.assertNotIn("caller-secret-001", str(raised.exception))
        self.assertEqual(calls, [])

    def test_empty_or_typed_binding_values_never_reach_factory(self):
        calls = []
        broker = InMemoryCredentialBroker(lambda: calls.append("factory"))
        for field in ("actuator_id", "repository_id", "operation"):
            for bad in ("", 123, None, ["caller-secret-001"]):
                with self.subTest(field=field, value=type(bad).__name__):
                    grant = dict(self.chain["credential_use_grant"])
                    grant[field] = bad
                    with self.assertRaisesRegex(
                        ContractValidationError, "^broker: binding value is invalid$"
                    ) as raised:
                        broker.open_github_publication_channel(grant, self.chain["actuator_request"], now=NOW)
                    self.assertNotIn("caller-secret-001", str(raised.exception))
                    request = dict(self.chain["actuator_request"])
                    request[field] = bad
                    with self.assertRaisesRegex(
                        ContractValidationError, "binding value is invalid"
                    ):
                        broker.open_github_publication_channel(
                            self.chain["credential_use_grant"], request, now=NOW
                        )
        self.assertEqual(calls, [])

    def test_malformed_grant_identifier_never_reaches_factory(self):
        calls = []
        broker = InMemoryCredentialBroker(lambda: calls.append("factory"))
        for bad in (None, 123, "", ["grant-001"]):
            with self.subTest(identifier=type(bad).__name__):
                grant = dict(self.chain["credential_use_grant"])
                grant["credential_grant_id"] = bad
                with self.assertRaisesRegex(
                    ContractValidationError, "^broker: binding value is invalid$"
                ):
                    broker.open_github_publication_channel(grant, self.chain["actuator_request"], now=NOW)
        self.assertEqual(calls, [])

    def test_expired_or_malformed_grant_never_reaches_factory(self):
        calls = []
        broker = InMemoryCredentialBroker(lambda: calls.append("factory"))
        valid_now = datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc)
        expired = [
            datetime(2026, 9, 4, 12, 11, tzinfo=timezone.utc),
            datetime(2026, 9, 4, 12, 12, tzinfo=timezone.utc),
        ]
        for moment in expired:
            with self.subTest(now=moment.isoformat()):
                with self.assertRaisesRegex(ContractValidationError, "^broker: credential grant expired$"):
                    broker.open_github_publication_channel(
                        self.chain["credential_use_grant"], self.chain["actuator_request"], now=moment,
                    )
        for bad_expiry in ("not-a-time", "2026-09-04T12:11:00", 123, None):
            with self.subTest(expiry=bad_expiry):
                grant = dict(self.chain["credential_use_grant"])
                if bad_expiry is None:
                    del grant["expires_at"]
                else:
                    grant["expires_at"] = bad_expiry
                with self.assertRaisesRegex(
                    ContractValidationError, "^broker: credential grant expiry is invalid$"
                ):
                    broker.open_github_publication_channel(
                        grant, self.chain["actuator_request"], now=valid_now,
                    )
        self.assertEqual(calls, [])
        broker.open_github_publication_channel(
            self.chain["credential_use_grant"], self.chain["actuator_request"], now=valid_now,
        )
        self.assertEqual(calls, ["factory"])

    def test_missing_now_is_refused_before_channel_factory(self):
        calls = []
        broker = InMemoryCredentialBroker(lambda: calls.append("factory"))
        with self.assertRaises(TypeError):
            broker.open_github_publication_channel(
                self.chain["credential_use_grant"], self.chain["actuator_request"],
            )
        self.assertEqual(calls, [])
        self.assertEqual(broker.opened_grants, [])

    def test_brokered_publish_without_now_is_refused_before_channel(self):
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        actuator = BrokeredGitHubActuator(broker)
        with self.assertRaises(TypeError):
            actuator.publish_pull_request(
                actuator_request=self.chain["actuator_request"],
                credential_grant=self.chain["credential_use_grant"],
                policy_decision=self.decision,
                approval_valid=True,
                gateway_decision=self.gateway,
                intent=self.chain["intent"],
                approval=self.chain["approval"],
            )
        self.assertEqual(broker.opened_grants, [])
        self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))

    def test_invalid_grant_class_never_reaches_factory(self):
        calls = []
        broker = InMemoryCredentialBroker(lambda: calls.append("factory"))
        for bad in ("superuser", "", None, 123):
            with self.subTest(grant_class=bad):
                grant = dict(self.chain["credential_use_grant"])
                grant["credential_class"] = bad
                with self.assertRaisesRegex(
                    ContractValidationError, "^broker: credential class mismatch$"
                ):
                    broker.open_github_publication_channel(
                        grant, self.chain["actuator_request"], now=NOW
                    )
        missing = dict(self.chain["credential_use_grant"])
        del missing["credential_class"]
        with self.assertRaisesRegex(ContractValidationError, "credential class mismatch"):
            broker.open_github_publication_channel(
                missing, self.chain["actuator_request"], now=NOW
            )
        self.assertEqual(calls, [])

    def test_malformed_request_digest_never_reaches_factory(self):
        calls = []
        broker = InMemoryCredentialBroker(lambda: calls.append("factory"))
        digest_cases = [123, None, ["sha256:" + "a" * 64], ""]
        for bad in digest_cases:
            with self.subTest(digest=type(bad).__name__):
                grant = dict(self.chain["credential_use_grant"])
                grant["request_digest"] = bad
                with self.assertRaises(ContractValidationError):
                    broker.open_github_publication_channel(
                        grant, self.chain["actuator_request"], now=NOW
                    )
        missing = dict(self.chain["credential_use_grant"])
        del missing["request_digest"]
        with self.assertRaises(ContractValidationError):
            broker.open_github_publication_channel(
                missing, self.chain["actuator_request"], now=NOW
            )
        self.assertEqual(calls, [])

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
                now=NOW,
                approval=self.chain["approval"],
            )
        self.assertIsNone(endpoint.find_by_idempotency_key(evil_request["idempotency_key"]))
        self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))

    def test_brokered_coordinated_triple_swap_is_rejected_before_provider(self):
        import copy

        from app_contracts.authority import DeterministicPolicy, PolicyConfig
        from app_contracts.digests import sha256_digest
        from datetime import datetime, timezone

        now = datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc)
        digest = self.chain["actuator_request"]["staged_change_digest"]
        evil_request = copy.deepcopy(self.chain["actuator_request"])
        evil_request["branch_namespace"] = "agent/process-evil-001"
        evil_request["idempotency_key"] = f"publish/process-evil-001/{digest}"
        evil_intent = copy.deepcopy(self.chain["intent"])
        evil_intent["branch_namespace"] = "agent/process-evil-001"
        evil_intent["idempotency_key"] = f"publish/process-evil-001/{digest}"
        evil_grant = copy.deepcopy(self.chain["credential_use_grant"])
        evil_grant["credential_grant_id"] = "credential-grant-evil-051"
        evil_grant["request_digest"] = sha256_digest(evil_request)

        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({"github-installation/42/repository/1001"}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        fresh = policy.decide(
            decision_id="decision-evil-051",
            actuator_request=evil_request, approval=self.chain["approval"],
            staged_change=self.chain["staged_change"], intent=evil_intent, now=now,
        )
        self.assertEqual(fresh["effect"], "deny")
        self.assertEqual(fresh["reason_codes"], ["approval-approved-intent-digest-mismatch"])

        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        actuator = BrokeredGitHubActuator(broker)
        with self.assertRaisesRegex(ContractValidationError, "approved intent digest mismatch") as raised:
            actuator.publish_pull_request(
                actuator_request=evil_request,
                credential_grant=evil_grant,
                policy_decision=self.decision,
                approval_valid=True,
                gateway_decision=self.gateway,
                intent=evil_intent,
                now=NOW,
                approval=self.chain["approval"],
            )
        self.assertEqual(broker.opened_grants, [])
        self.assertIsNone(endpoint.find_by_idempotency_key(evil_request["idempotency_key"]))
        self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))
        leaked = str(raised.exception)
        self.assertNotIn(evil_intent["branch_namespace"], leaked)
        self.assertNotIn(evil_grant["request_digest"], leaked)

    def test_brokered_missing_approval_is_refused_before_channel(self):
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        actuator = BrokeredGitHubActuator(broker)
        with self.assertRaisesRegex(ContractValidationError, "approval is required") as raised:
            actuator.publish_pull_request(
                actuator_request=self.chain["actuator_request"],
                credential_grant=self.chain["credential_use_grant"],
                policy_decision=self.decision,
                approval_valid=True,
                gateway_decision=self.gateway,
                intent=self.chain["intent"],
                now=NOW,
                approval=None,
            )
        self.assertEqual(broker.opened_grants, [])
        self.assertIsNone(endpoint.find_by_idempotency_key(self.chain["intent"]["idempotency_key"]))
        leaked = str(raised.exception)
        self.assertNotIn(self.chain["approval"]["approval_id"], leaked)
        self.assertNotIn(self.chain["intent"]["idempotency_key"], leaked)


if __name__ == "__main__":
    unittest.main()
