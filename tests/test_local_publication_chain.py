"""Composed local-chain fixtures: one canonical process/digest/idempotency set.

Pure builders only — no side effects, no network, no Docker, no credential
values. The helpers pin an explicit timezone-aware clock. Later Batch AA
cards compose these fixtures through the real component boundaries.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.digests import sha256_digest
from app_contracts.validator import validate


NOW = datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc)

PROCESS_ID = "process-chain-001"
REPOSITORY_ID = "github-installation/42/repository/1001"
ACTUATOR_ID = "actuator-github-001"
APPROVAL_ID = "approval-chain-001"
BRANCH = "agent/process-chain-001"
BASE_COMMIT = "a" * 40


def _format_time(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def build_staged_change() -> dict:
    return {
        "schema_version": 1,
        "staged_change_id": "staged-chain-001",
        "process_id": PROCESS_ID,
        "repository_id": REPOSITORY_ID,
        "base_commit": BASE_COMMIT,
        "patch_artifact_ref": "artifact://patches/chain-001",
        "patch_digest": "sha256:" + "b" * 64,
        "evidence_digest": "sha256:" + "c" * 64,
        "verification_digest": "sha256:" + "d" * 64,
        "created_at": "2026-09-04T12:00:00Z",
        "expires_at": "2026-09-05T12:00:00Z",
    }


def build_intent(staged_change: dict) -> dict:
    digest = sha256_digest(staged_change)
    return {
        "schema_version": 1,
        "operation": "publish_pull_request",
        "process_id": PROCESS_ID,
        "repository_id": REPOSITORY_ID,
        "base_commit": BASE_COMMIT,
        "staged_change_digest": digest,
        "approval_id": APPROVAL_ID,
        "branch_namespace": BRANCH,
        "title_artifact_ref": "artifact://pr/chain-001/title",
        "body_artifact_ref": "artifact://pr/chain-001/body",
        "idempotency_key": f"publish/{PROCESS_ID}/{digest}",
        "audience": "github-installation-42",
        "expires_at": "2026-09-05T12:00:00Z",
    }


def build_approval(staged_change: dict, intent: dict) -> dict:
    return {
        "schema_version": 1,
        "approval_id": APPROVAL_ID,
        "approver_id": "user-alice",
        "process_id": PROCESS_ID,
        "operation": "publish_pull_request",
        "repository_id": REPOSITORY_ID,
        "staged_change_digest": sha256_digest(staged_change),
        "approved_intent_digest": sha256_digest(intent),
        "policy_version": "policy-1",
        "approved_at": "2026-09-04T12:05:00Z",
        "expires_at": "2026-09-05T12:00:00Z",
    }


def build_actuator_request(staged_change: dict, intent: dict) -> dict:
    digest = sha256_digest(staged_change)
    return {
        "schema_version": 1,
        "request_id": "actuator-request-chain-001",
        "actuator_id": ACTUATOR_ID,
        "operation": "publish_pull_request",
        "process_id": PROCESS_ID,
        "repository_id": REPOSITORY_ID,
        "base_commit": BASE_COMMIT,
        "staged_change_digest": digest,
        "patch_artifact_ref": "artifact://patches/chain-001",
        "approval_id": APPROVAL_ID,
        "policy_decision_id": "decision-chain-001",
        "branch_namespace": BRANCH,
        "title_artifact_ref": "artifact://pr/chain-001/title",
        "body_artifact_ref": "artifact://pr/chain-001/body",
        "idempotency_key": f"publish/{PROCESS_ID}/{digest}",
        "expires_at": "2026-09-04T12:11:00Z",
    }


def build_grant(actuator_request: dict) -> dict:
    return {
        "schema_version": 1,
        "credential_grant_id": "credential-grant-chain-001",
        "credential_class": "github-app-installation",
        "installation_id": 42,
        "repository_id": REPOSITORY_ID,
        "permissions": ["contents:write", "pull_requests:write"],
        "actuator_id": ACTUATOR_ID,
        "operation": "publish_pull_request",
        "request_digest": sha256_digest(actuator_request),
        "single_use": True,
        "issued_at": "2026-09-04T12:06:00Z",
        "expires_at": "2026-09-04T12:11:00Z",
    }


def build_journal_inputs(actuator_request: dict) -> dict:
    return {
        "process_id": PROCESS_ID,
        "idempotency_key": actuator_request["idempotency_key"],
        "request_digest": sha256_digest(actuator_request),
        "repository_id": REPOSITORY_ID,
    }


def build_chain() -> dict[str, dict]:
    staged_change = build_staged_change()
    intent = build_intent(staged_change)
    return {
        "staged_change": staged_change,
        "intent": intent,
        "approval": build_approval(staged_change, intent),
        "actuator_request": build_actuator_request(staged_change, intent),
        "credential_use_grant": build_grant(build_actuator_request(staged_change, intent)),
        "journal_inputs": build_journal_inputs(build_actuator_request(staged_change, intent)),
    }


def load_schema(name: str) -> dict:
    with (ROOT / "schemas" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


class ComposedFixtureTests(unittest.TestCase):
    def test_fixtures_are_schema_valid(self):
        chain = build_chain()
        for name, schema_file in (
            ("staged_change", "staged-change.schema.json"),
            ("intent", "publish-pull-request-intent.schema.json"),
            ("approval", "approval.schema.json"),
            ("actuator_request", "actuator-request.schema.json"),
            ("credential_use_grant", "credential-use-grant.schema.json"),
        ):
            with self.subTest(contract=name):
                validate(chain[name], load_schema(schema_file))

    def test_staged_digest_binding_is_consistent(self):
        chain = build_chain()
        expected = sha256_digest(chain["staged_change"])
        for name in ("intent", "approval", "actuator_request"):
            with self.subTest(contract=name):
                self.assertEqual(chain[name]["staged_change_digest"], expected)

    def test_approval_binds_full_canonical_intent(self):
        chain = build_chain()
        self.assertEqual(chain["approval"]["approved_intent_digest"], sha256_digest(chain["intent"]))

    def test_idempotency_key_binding_is_consistent(self):
        chain = build_chain()
        expected = f"publish/{PROCESS_ID}/{sha256_digest(chain['staged_change'])}"
        self.assertEqual(chain["intent"]["idempotency_key"], expected)
        self.assertEqual(chain["actuator_request"]["idempotency_key"], expected)
        self.assertEqual(chain["journal_inputs"]["idempotency_key"], expected)
        self.assertEqual(chain["journal_inputs"]["process_id"], PROCESS_ID)
        self.assertEqual(chain["journal_inputs"]["repository_id"], REPOSITORY_ID)

    def test_grant_binding_has_no_credential_values(self):
        chain = build_chain()
        grant = chain["credential_use_grant"]
        self.assertEqual(grant["request_digest"], sha256_digest(chain["actuator_request"]))
        self.assertEqual(grant["request_digest"], chain["journal_inputs"]["request_digest"])
        self.assertIs(grant["single_use"], True)
        serialized = json.dumps(chain)
        for forbidden in ("token", "secret", "private", "bearer", "password"):
            self.assertNotIn(forbidden, serialized)

    def test_explicit_aware_clock_is_consistent(self):
        self.assertIsNotNone(NOW.tzinfo)
        chain = build_chain()
        for name in ("intent", "approval", "actuator_request", "credential_use_grant"):
            expires_at = datetime.fromisoformat(chain[name]["expires_at"].replace("Z", "+00:00"))
            self.assertIsNotNone(expires_at.tzinfo)
            self.assertGreater(expires_at, NOW)

    def test_fixture_helpers_are_deterministic_and_side_effect_free(self):
        first = build_chain()
        second = build_chain()
        self.assertEqual(first, second)
        self.assertEqual(
            sorted(first), ["actuator_request", "approval", "credential_use_grant", "intent", "journal_inputs", "staged_change"]
        )


def _prepare_adapter(sandbox, new_content: str):
    """Adapter 1 — prepare: real scoped change on the fixture repository."""

    from app_contracts.repository_process import prepare_change

    return prepare_change(
        sandbox,
        process_id=PROCESS_ID,
        task_id="task-chain-001",
        repository_id=REPOSITORY_ID,
        base_commit=BASE_COMMIT,
        changes={"calculator.py": new_content},
        test_command=["python3", "--version"],
        now=NOW,
    )


def _approve_adapter(staged_change: dict, intent: dict):
    """Adapter 2 — approval: validate the human approval artifact binding."""

    from app_contracts.authority import validate_approval

    approval = build_approval(staged_change, intent)
    validate_approval(approval, staged_change, intent, policy_version="policy-1", now=NOW)
    return approval


def _decide_adapter(actuator_request: dict, approval: dict, staged_change: dict, intent: dict):
    """Adapter 3 — policy: fresh allow decision for the exact triple."""

    from app_contracts.authority import DeterministicPolicy, PolicyConfig

    policy = DeterministicPolicy(PolicyConfig(
        version="policy-1",
        allowed_repositories=frozenset({REPOSITORY_ID}),
        allowed_actuators=frozenset({"actuator-github-001"}),
    ))
    return policy.decide(
        decision_id="decision-chain-001",
        actuator_request=actuator_request,
        approval=approval,
        staged_change=staged_change,
        intent=intent,
        now=NOW,
    )


def _classify_adapter():
    """Adapter 4 — gateway: slow-path allow for the publication operation."""

    from app_contracts.gateway import GatewayPath, classify

    decision = classify(
        {
            "intent": {"operation": "publish_pull_request", "risk_class": "low"},
            "destination": {"port": "tool"},
            "source": {"protocol": "internal"},
            "security": {"tainted": False, "sensitivity": "internal"},
        },
        policy_available=True,
    )
    assert decision.path is GatewayPath.SLOW and decision.allowed
    return decision


def _open_adapter(grant: dict, actuator_request: dict):
    """Adapter 5 — broker: open the single-use private channel."""

    from app_contracts.broker import InMemoryCredentialBroker
    from app_contracts.mock_github import MockGitHubEndpoint

    endpoint = MockGitHubEndpoint()
    broker = InMemoryCredentialBroker(lambda: endpoint)
    return broker, endpoint, broker.open_github_publication_channel(grant, actuator_request, now=NOW)


class ComposedPositivePathTests(unittest.TestCase):
    def test_composed_path_reaches_exactly_one_receipt_and_completed_journal(self):
        import tempfile

        from app_contracts.actuator import publish_authorized_request
        from app_contracts.mock_github import MockGitHubEndpoint
        from app_contracts.publication import PublicationJournal, execute_publication
        from app_contracts.sandbox import LocalProcessSandboxBackend

        directory = tempfile.TemporaryDirectory(prefix="app-chain-harness-")
        self.addCleanup(directory.cleanup)
        fixture = ROOT / "fixtures" / "repository" / "project"
        original = (fixture / "calculator.py").read_text(encoding="utf-8")
        sandbox = LocalProcessSandboxBackend().create(fixture, {"python3"})
        self.addCleanup(sandbox.close)

        prepared = _prepare_adapter(sandbox, original + "\ndef extra():\n    return 1\n")
        staged_change = prepared.staged_change
        intent = build_intent(staged_change)
        approval = _approve_adapter(staged_change, intent)
        actuator_request = build_actuator_request(staged_change, intent)
        grant = build_grant(actuator_request)
        decision = _decide_adapter(actuator_request, approval, staged_change, intent)
        self.assertEqual(decision["effect"], "allow")
        gateway_decision = _classify_adapter()
        broker, endpoint, channel = _open_adapter(grant, actuator_request)

        first = publish_authorized_request(
            channel, actuator_request, decision, approval_valid=True,
            gateway_decision=gateway_decision, intent=intent, now=NOW, approval=approval,
        )
        journal = PublicationJournal(Path(directory.name) / "chain.sqlite3")
        self.addCleanup(journal.close)
        journal.prepare(
            PROCESS_ID,
            idempotency_key=intent["idempotency_key"],
            request_digest=sha256_digest(actuator_request),
            repository_id=REPOSITORY_ID,
        )
        boundary_request = {
            "process_id": PROCESS_ID,
            "operation": "publish_pull_request",
            "repository_id": REPOSITORY_ID,
            "branch": intent["branch_namespace"],
            "staged_change_digest": intent["staged_change_digest"],
            "idempotency_key": intent["idempotency_key"],
            "policy_effect": "allow",
            "approval_valid": True,
        }
        second = execute_publication(journal, channel, boundary_request)

        self.assertEqual(first, second)
        self.assertEqual(first.pull_request_id, 1)
        record = journal.get(PROCESS_ID)
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.idempotency_key, intent["idempotency_key"])
        self.assertEqual(record.pull_request_id, 1)
        self.assertEqual(
            endpoint.find_by_idempotency_key(intent["idempotency_key"]), first
        )
        transcript = json.dumps({
            "intent": intent, "approval": approval, "request": actuator_request,
            "grant": grant, "decision_effect": decision["effect"],
        })
        for forbidden in ("token", "secret", "private", "bearer", "password"):
            self.assertNotIn(forbidden, transcript)


def _swap_variant(chain: dict[str, dict], kind: str) -> dict[str, dict]:
    """Copy the composed fixtures with one coordinated swap applied."""

    import copy

    evil = copy.deepcopy(chain)
    digest = evil["actuator_request"]["staged_change_digest"]
    if kind == "intent-branch":
        evil["intent"]["branch_namespace"] = "agent/process-evil-001"
        evil["intent"]["idempotency_key"] = f"publish/process-evil-001/{digest}"
    elif kind == "approval-digest":
        evil["approval"]["approved_intent_digest"] = "sha256:" + "0" * 64
    elif kind == "request-branch":
        evil["actuator_request"]["branch_namespace"] = "agent/process-evil-001"
        evil["actuator_request"]["idempotency_key"] = f"publish/process-evil-001/{digest}"
    elif kind == "request-key":
        evil["actuator_request"]["idempotency_key"] = f"publish/process-chain-001/{'sha256:' + '0' * 64}"
    else:  # pragma: no cover - guarded by callers
        raise AssertionError(f"unknown swap kind: {kind}")
    evil_grant_source = evil["actuator_request"] if kind in ("request-branch", "request-key") else chain["actuator_request"]
    evil["credential_use_grant"] = build_grant(evil_grant_source)
    evil["credential_use_grant"]["credential_grant_id"] = f"credential-grant-evil-{kind}"
    return evil


class ComposedSwapDenialTests(unittest.TestCase):
    def test_each_swap_denies_before_any_channel_or_endpoint_call(self):
        from app_contracts.authority import DeterministicPolicy, PolicyConfig
        from app_contracts.broker import InMemoryCredentialBroker
        from app_contracts.gateway import GatewayDecision, GatewayPath
        from app_contracts.github_actuator import BrokeredGitHubActuator
        from app_contracts.mock_github import MockGitHubEndpoint
        from app_contracts.validator import ContractValidationError

        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({REPOSITORY_ID}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        for kind in ("intent-branch", "approval-digest", "request-branch", "request-key"):
            with self.subTest(swap=kind):
                chain = build_chain()
                evil = _swap_variant(chain, kind)
                decision = policy.decide(
                    decision_id=f"decision-evil-{kind}",
                    actuator_request=evil["actuator_request"], approval=evil["approval"],
                    staged_change=chain["staged_change"], intent=evil["intent"], now=NOW,
                )
                self.assertEqual(decision["effect"], "deny")
                endpoint = MockGitHubEndpoint()
                broker = InMemoryCredentialBroker(lambda: endpoint)
                actuator = BrokeredGitHubActuator(broker)
                with self.assertRaises(ContractValidationError):
                    actuator.publish_pull_request(
                        actuator_request=evil["actuator_request"],
                        credential_grant=evil["credential_use_grant"],
                        policy_decision=decision,
                        approval_valid=True,
                        gateway_decision=gateway,
                        intent=evil["intent"],
                        now=NOW,
                        approval=evil["approval"],
                    )
                self.assertEqual(broker.opened_grants, [])
                self.assertIsNone(endpoint.find_by_idempotency_key(evil["actuator_request"]["idempotency_key"]))
                self.assertIsNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))

    def test_reused_allow_with_evil_triple_leaves_journal_prepared(self):
        import tempfile

        from app_contracts.authority import DeterministicPolicy, PolicyConfig
        from app_contracts.broker import InMemoryCredentialBroker
        from app_contracts.digests import sha256_digest
        from app_contracts.gateway import GatewayDecision, GatewayPath
        from app_contracts.github_actuator import BrokeredGitHubActuator
        from app_contracts.mock_github import MockGitHubEndpoint
        from app_contracts.publication import PublicationJournal
        from app_contracts.validator import ContractValidationError

        chain = build_chain()
        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({REPOSITORY_ID}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        decision = policy.decide(
            decision_id="decision-chain-002",
            actuator_request=chain["actuator_request"], approval=chain["approval"],
            staged_change=chain["staged_change"], intent=chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "allow")
        evil = _swap_variant(chain, "request-branch")
        digest = evil["actuator_request"]["staged_change_digest"]
        evil["intent"]["branch_namespace"] = "agent/process-evil-001"
        evil["intent"]["idempotency_key"] = f"publish/process-evil-001/{digest}"
        evil["credential_use_grant"]["credential_grant_id"] = "credential-grant-evil-reuse-001"

        directory = tempfile.TemporaryDirectory(prefix="app-chain-swap-")
        self.addCleanup(directory.cleanup)
        journal = PublicationJournal(Path(directory.name) / "chain.sqlite3")
        self.addCleanup(journal.close)
        journal.prepare(
            PROCESS_ID,
            idempotency_key=chain["intent"]["idempotency_key"],
            request_digest=sha256_digest(chain["actuator_request"]),
            repository_id=REPOSITORY_ID,
        )
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        actuator = BrokeredGitHubActuator(broker)
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        with self.assertRaisesRegex(ContractValidationError, "approved intent digest mismatch"):
            actuator.publish_pull_request(
                actuator_request=evil["actuator_request"],
                credential_grant=evil["credential_use_grant"],
                policy_decision=decision,
                approval_valid=True,
                gateway_decision=gateway,
                intent=evil["intent"],
                now=NOW,
                approval=chain["approval"],
            )
        self.assertEqual(broker.opened_grants, [])
        self.assertEqual(journal.get(PROCESS_ID).status, "prepared")
        self.assertIsNone(endpoint.find_by_idempotency_key(evil["actuator_request"]["idempotency_key"]))


class ComposedExpiryDenialTests(unittest.TestCase):
    def _fresh_setup(self, grant_id: str):
        from app_contracts.authority import DeterministicPolicy, PolicyConfig
        from app_contracts.broker import InMemoryCredentialBroker
        from app_contracts.gateway import GatewayDecision, GatewayPath
        from app_contracts.github_actuator import BrokeredGitHubActuator
        from app_contracts.mock_github import MockGitHubEndpoint

        chain = build_chain()
        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({REPOSITORY_ID}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        decision = policy.decide(
            decision_id="decision-chain-expiry",
            actuator_request=chain["actuator_request"], approval=chain["approval"],
            staged_change=chain["staged_change"], intent=chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "allow")
        grant = dict(chain["credential_use_grant"])
        grant["credential_grant_id"] = grant_id
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)
        actuator = BrokeredGitHubActuator(broker)
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        return chain, decision, gateway, endpoint, broker, actuator, grant

    def _attempt(self, actuator, **kwargs):
        return actuator.publish_pull_request(**kwargs)

    def test_expired_decision_denies_before_channel_or_endpoint(self):
        from datetime import timedelta

        from app_contracts.validator import ContractValidationError

        chain, decision, gateway, _, _, _, _ = self._fresh_setup("unused")
        expires_at = datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00"))
        for label, moment, ok in (
            ("before", expires_at - timedelta(seconds=1), True),
            ("at", expires_at, False),
            ("after", expires_at + timedelta(seconds=1), False),
        ):
            with self.subTest(when=label):
                chain, decision, gateway, endpoint, broker, actuator, grant = self._fresh_setup(
                    f"credential-grant-decision-{label}"
                )
                grant["expires_at"] = "2026-09-04T13:00:00Z"
                expires_at = datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00"))
                moment = {
                    "before": expires_at - timedelta(seconds=1),
                    "at": expires_at,
                    "after": expires_at + timedelta(seconds=1),
                }[label]
                if ok:
                    result = self._attempt(
                        actuator,
                        actuator_request=chain["actuator_request"],
                        credential_grant=grant,
                        policy_decision=decision,
                        approval_valid=True,
                        gateway_decision=gateway,
                        intent=chain["intent"],
                        now=moment,
                        approval=chain["approval"],
                    )
                    self.assertEqual(result.pull_request_id, 1)
                else:
                    with self.assertRaisesRegex(ContractValidationError, "decision: expired") as raised:
                        self._attempt(
                            actuator,
                            actuator_request=chain["actuator_request"],
                            credential_grant=grant,
                            policy_decision=decision,
                            approval_valid=True,
                            gateway_decision=gateway,
                            intent=chain["intent"],
                            now=moment,
                            approval=chain["approval"],
                        )
                    self.assertEqual(broker.opened_grants, [])
                    self.assertIsNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))
                    self.assertNotIn(chain["approval"]["approval_id"], str(raised.exception))

    def test_expired_grant_denies_before_channel_or_endpoint(self):
        from datetime import timedelta

        from app_contracts.validator import ContractValidationError

        grant_expiry = datetime.fromisoformat("2026-09-04T12:11:00+00:00")
        for label, moment, ok in (
            ("before", grant_expiry - timedelta(seconds=1), True),
            ("at", grant_expiry, False),
            ("after", grant_expiry + timedelta(seconds=1), False),
        ):
            with self.subTest(when=label):
                chain, decision, gateway, endpoint, broker, actuator, grant = self._fresh_setup(
                    f"credential-grant-expiry-{label}"
                )
                if ok:
                    result = self._attempt(
                        actuator,
                        actuator_request=chain["actuator_request"],
                        credential_grant=grant,
                        policy_decision=decision,
                        approval_valid=True,
                        gateway_decision=gateway,
                        intent=chain["intent"],
                        now=moment,
                        approval=chain["approval"],
                    )
                    self.assertEqual(result.pull_request_id, 1)
                else:
                    with self.assertRaisesRegex(ContractValidationError, "credential grant expired") as raised:
                        self._attempt(
                            actuator,
                            actuator_request=chain["actuator_request"],
                            credential_grant=grant,
                            policy_decision=decision,
                            approval_valid=True,
                            gateway_decision=gateway,
                            intent=chain["intent"],
                            now=moment,
                            approval=chain["approval"],
                        )
                    self.assertEqual(broker.opened_grants, [])
                    self.assertIsNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))
                    self.assertNotIn(grant["request_digest"], str(raised.exception))


class ComposedGatewayDenialTests(unittest.TestCase):
    def _valid_envelope(self, **security_overrides):
        security = {"tainted": False, "sensitivity": "internal"}
        security.update(security_overrides)
        return {
            "intent": {"operation": "publish_pull_request", "risk_class": "low"},
            "destination": {"port": "tool"},
            "source": {"protocol": "internal"},
            "security": security,
        }

    def _composed_publish(self, *, gateway_decision, chain, decision, grant_id, endpoint, factory_calls):
        """Harness dispatcher: only a slow-path allow reaches broker/channel/endpoint.

        A denied, degraded, or fast verdict stops the composed path before any
        broker, channel, or endpoint use. Returns (receipt_or_None, broker).
        """

        from app_contracts.broker import InMemoryCredentialBroker
        from app_contracts.gateway import GatewayPath
        from app_contracts.github_actuator import BrokeredGitHubActuator

        broker = InMemoryCredentialBroker(lambda: factory_calls.append("factory") or endpoint)
        if not (gateway_decision.path is GatewayPath.SLOW and gateway_decision.allowed):
            return None, broker
        actuator = BrokeredGitHubActuator(broker)
        grant = dict(chain["credential_use_grant"])
        grant["credential_grant_id"] = grant_id
        return actuator.publish_pull_request(
            actuator_request=chain["actuator_request"],
            credential_grant=grant,
            policy_decision=decision,
            approval_valid=True,
            gateway_decision=gateway_decision,
            intent=chain["intent"],
            now=NOW,
            approval=chain["approval"],
        ), broker

    def _allow_decision(self, chain, decision_id):
        from app_contracts.authority import DeterministicPolicy, PolicyConfig

        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({REPOSITORY_ID}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        decision = policy.decide(
            decision_id=decision_id,
            actuator_request=chain["actuator_request"], approval=chain["approval"],
            staged_change=chain["staged_change"], intent=chain["intent"], now=NOW,
        )
        self.assertEqual(decision["effect"], "allow")
        return decision

    def test_gateway_deny_and_degraded_stop_before_broker(self):
        from app_contracts.gateway import GatewayPath, classify
        from app_contracts.mock_github import MockGitHubEndpoint

        chain = build_chain()
        decision = self._allow_decision(chain, "decision-chain-gateway")
        cases = {
            "tainted-deny": classify(self._valid_envelope(tainted=True), policy_available=True),
            "degraded-deny": classify(self._valid_envelope(), policy_available=False),
        }
        for label, gateway_decision in cases.items():
            with self.subTest(gateway=label):
                self.assertFalse(gateway_decision.allowed)
                self.assertNotEqual(gateway_decision.path, GatewayPath.FAST)
                calls: list[str] = []
                endpoint = MockGitHubEndpoint()
                result, broker = self._composed_publish(
                    gateway_decision=gateway_decision, chain=chain, decision=decision,
                    grant_id=f"credential-grant-gateway-{label}", endpoint=endpoint,
                    factory_calls=calls,
                )
                self.assertIsNone(result)
                self.assertEqual(calls, [])
                self.assertEqual(broker.opened_grants, [])
                self.assertIsNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))

    def test_audit_failure_stops_before_broker_with_journal_prepared(self):
        import tempfile

        from app_contracts.digests import sha256_digest
        from app_contracts.gateway import GatewayPath, enforce
        from app_contracts.mock_github import MockGitHubEndpoint
        from app_contracts.publication import PublicationJournal

        class FailingSink:
            def append_audit_event(self, process_id, **kwargs):
                raise RuntimeError("injected sink failure")

        chain = build_chain()
        decision = self._allow_decision(chain, "decision-chain-audit")
        request = self._valid_envelope()
        request.update({
            "correlation_id": PROCESS_ID,
            "source": {"protocol": "internal", "principal_id": "agent-worker-001"},
            "payload": {"content_digest": "sha256:" + "e" * 64},
        })
        gateway_decision = enforce(request, policy_available=True, audit_sink=FailingSink())
        self.assertEqual(gateway_decision.path, GatewayPath.DEGRADED)
        self.assertFalse(gateway_decision.allowed)

        directory = tempfile.TemporaryDirectory(prefix="app-chain-gateway-")
        self.addCleanup(directory.cleanup)
        journal = PublicationJournal(Path(directory.name) / "chain.sqlite3")
        self.addCleanup(journal.close)
        journal.prepare(
            PROCESS_ID,
            idempotency_key=chain["intent"]["idempotency_key"],
            request_digest=sha256_digest(chain["actuator_request"]),
            repository_id=REPOSITORY_ID,
        )
        calls: list[str] = []
        endpoint = MockGitHubEndpoint()
        result, broker = self._composed_publish(
            gateway_decision=gateway_decision, chain=chain, decision=decision,
            grant_id="credential-grant-gateway-audit", endpoint=endpoint,
            factory_calls=calls,
        )
        self.assertIsNone(result)
        self.assertEqual(calls, [])
        self.assertEqual(broker.opened_grants, [])
        self.assertEqual(journal.get(PROCESS_ID).status, "prepared")
        self.assertIsNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))

    def test_fast_path_cannot_publish_valid_slow_path_can(self):
        from app_contracts.gateway import GatewayPath, classify
        from app_contracts.mock_github import MockGitHubEndpoint

        chain = build_chain()
        decision = self._allow_decision(chain, "decision-chain-paths")
        fast = classify(
            {
                "intent": {"operation": "repository.read", "risk_class": "low"},
                "destination": {"port": "data"},
                "source": {"protocol": "internal"},
                "security": {"tainted": False, "sensitivity": "internal"},
            },
            policy_available=True,
        )
        self.assertEqual((fast.path, fast.allowed), (GatewayPath.FAST, True))
        calls: list[str] = []
        endpoint = MockGitHubEndpoint()
        result, broker = self._composed_publish(
            gateway_decision=fast, chain=chain, decision=decision,
            grant_id="credential-grant-fast-path", endpoint=endpoint,
            factory_calls=calls,
        )
        self.assertIsNone(result)
        self.assertEqual(calls, [])
        self.assertEqual(broker.opened_grants, [])
        slow = classify(self._valid_envelope(), policy_available=True)
        self.assertEqual((slow.path, slow.allowed), (GatewayPath.SLOW, True))
        calls = []
        endpoint = MockGitHubEndpoint()
        result, broker = self._composed_publish(
            gateway_decision=slow, chain=chain, decision=decision,
            grant_id="credential-grant-slow-path", endpoint=endpoint,
            factory_calls=calls,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.pull_request_id, 1)


def composed_publish(journal, endpoint, request):
    """Test-harness idempotency/replay boundary over one journal + endpoint.

    A repeated identical call against a completed record with matching
    process/idempotency/repository binding returns the original receipt
    without an endpoint call. A mismatched binding is denied with a stable
    error instead of replaying. Fresh records go through the normal
    journal-tracked publication path.
    """

    from app_contracts.publication import execute_publication
    from app_contracts.validator import ContractValidationError

    try:
        record = journal.get(request["process_id"])
    except KeyError:
        record = None
    if record is not None and record.status == "completed":
        if (
            record.idempotency_key != request.get("idempotency_key")
            or record.repository_id != request.get("repository_id")
        ):
            raise ContractValidationError("composed replay binding mismatch")
        return endpoint.find_by_idempotency_key(request["idempotency_key"])
    return execute_publication(journal, endpoint, request)


class ComposedReplayIdempotencyTests(unittest.TestCase):
    def _replay_fixtures(self):
        import tempfile

        from app_contracts.digests import sha256_digest
        from app_contracts.mock_github import MockGitHubEndpoint
        from app_contracts.publication import PublicationJournal

        chain = build_chain()
        endpoint_calls: list[dict] = []

        class RecordingEndpoint(MockGitHubEndpoint):
            def publish_pull_request(self, request):
                endpoint_calls.append(request)
                return super().publish_pull_request(request)

        endpoint = RecordingEndpoint()
        directory = tempfile.TemporaryDirectory(prefix="app-chain-replay-")
        self.addCleanup(directory.cleanup)
        journal = PublicationJournal(Path(directory.name) / "chain.sqlite3")
        self.addCleanup(journal.close)
        journal.prepare(
            PROCESS_ID,
            idempotency_key=chain["intent"]["idempotency_key"],
            request_digest=sha256_digest(chain["actuator_request"]),
            repository_id=REPOSITORY_ID,
        )
        boundary_request = {
            "process_id": PROCESS_ID,
            "operation": "publish_pull_request",
            "repository_id": REPOSITORY_ID,
            "branch": chain["intent"]["branch_namespace"],
            "staged_change_digest": chain["intent"]["staged_change_digest"],
            "idempotency_key": chain["intent"]["idempotency_key"],
            "policy_effect": "allow",
            "approval_valid": True,
        }
        return chain, journal, endpoint, endpoint_calls, boundary_request

    def test_identical_replay_returns_original_receipt_without_endpoint_call(self):
        chain, journal, endpoint, endpoint_calls, boundary_request = self._replay_fixtures()
        first = composed_publish(journal, endpoint, dict(boundary_request))
        self.assertEqual(first.pull_request_id, 1)
        before = journal.get(PROCESS_ID)
        self.assertEqual((before.status, before.pull_request_id), ("completed", 1))
        replayed = composed_publish(journal, endpoint, dict(boundary_request))
        self.assertEqual(replayed, first)
        self.assertEqual(len(endpoint_calls), 1)
        after = journal.get(PROCESS_ID)
        self.assertEqual(after, before)
        self.assertEqual(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]), first)

    def test_mismatched_binding_is_denied_not_replayed(self):
        from app_contracts.validator import ContractValidationError

        chain, journal, endpoint, endpoint_calls, boundary_request = self._replay_fixtures()
        first = composed_publish(journal, endpoint, dict(boundary_request))
        self.assertEqual(first.pull_request_id, 1)
        for label, mutation in (
            ("idempotency-key", {"idempotency_key": "publish/process-chain-001/sha256:" + "0" * 64}),
            ("repository", {"repository_id": "github-installation/42/repository/9999"}),
        ):
            with self.subTest(binding=label):
                forged = dict(boundary_request)
                forged.update(mutation)
                with self.assertRaisesRegex(ContractValidationError, "composed replay binding mismatch"):
                    composed_publish(journal, endpoint, forged)
        self.assertEqual(len(endpoint_calls), 1)
        record = journal.get(PROCESS_ID)
        self.assertEqual((record.status, record.pull_request_id), ("completed", 1))
        self.assertIsNone(endpoint.find_by_idempotency_key("publish/process-chain-001/sha256:" + "0" * 64))

    def test_changed_binding_is_denied_rather_than_replayed(self):
        import copy

        from app_contracts.authority import DeterministicPolicy, PolicyConfig
        from app_contracts.broker import InMemoryCredentialBroker
        from app_contracts.digests import sha256_digest
        from app_contracts.gateway import GatewayDecision, GatewayPath
        from app_contracts.github_actuator import BrokeredGitHubActuator
        from app_contracts.mock_github import MockGitHubEndpoint
        from app_contracts.validator import ContractValidationError

        chain = build_chain()
        policy = DeterministicPolicy(PolicyConfig(
            version="policy-1",
            allowed_repositories=frozenset({REPOSITORY_ID}),
            allowed_actuators=frozenset({"actuator-github-001"}),
        ))
        digest = chain["actuator_request"]["staged_change_digest"]
        variants = {
            "branch": {"branch_namespace": "agent/process-evil-001",
                       "idempotency_key": f"publish/process-evil-001/{digest}"},
            "key": {"idempotency_key": f"publish/process-chain-001/{'sha256:' + '0' * 64}"},
        }
        gateway = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        for label, mutation in variants.items():
            with self.subTest(binding=label):
                evil_request = copy.deepcopy(chain["actuator_request"])
                evil_request.update(mutation)
                evil_intent = copy.deepcopy(chain["intent"])
                if label == "branch":
                    evil_intent.update(mutation)
                decision = policy.decide(
                    decision_id=f"decision-chain-replay-{label}",
                    actuator_request=evil_request, approval=chain["approval"],
                    staged_change=chain["staged_change"], intent=evil_intent, now=NOW,
                )
                self.assertEqual(decision["effect"], "deny")
                endpoint = MockGitHubEndpoint()
                broker = InMemoryCredentialBroker(lambda: endpoint)
                actuator = BrokeredGitHubActuator(broker)
                grant = copy.deepcopy(chain["credential_use_grant"])
                grant["credential_grant_id"] = f"credential-grant-replay-{label}"
                grant["request_digest"] = sha256_digest(evil_request)
                with self.assertRaises(ContractValidationError):
                    actuator.publish_pull_request(
                        actuator_request=evil_request,
                        credential_grant=grant,
                        policy_decision=decision,
                        approval_valid=True,
                        gateway_decision=gateway,
                        intent=evil_intent,
                        now=NOW,
                        approval=chain["approval"],
                    )
                self.assertEqual(broker.opened_grants, [])
                self.assertIsNone(endpoint.find_by_idempotency_key(evil_request["idempotency_key"]))
                self.assertIsNone(endpoint.find_by_idempotency_key(chain["intent"]["idempotency_key"]))


if __name__ == "__main__":
    unittest.main()
