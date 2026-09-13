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


if __name__ == "__main__":
    unittest.main()
