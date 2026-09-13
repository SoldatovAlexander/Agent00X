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


if __name__ == "__main__":
    unittest.main()
