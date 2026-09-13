from pathlib import Path
import sys
import unittest
from dataclasses import FrozenInstanceError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.mock_github import MockGitHubEndpoint
from app_contracts.validator import ContractValidationError


class MockGitHubTests(unittest.TestCase):
    def setUp(self):
        self.endpoint = MockGitHubEndpoint()
        digest = "sha256:" + "a" * 64
        self.request = {
            "operation": "publish_pull_request",
            "repository_id": "github-installation/42/repository/1001",
            "branch": "agent/process-demo-001",
            "staged_change_digest": digest,
            "idempotency_key": f"publish/process-demo-001/{digest}",
            "policy_effect": "allow",
            "approval_valid": True,
        }

    def test_identical_retry_returns_same_pull_request(self):
        first = self.endpoint.publish_pull_request(self.request)
        second = self.endpoint.publish_pull_request(dict(self.request))
        self.assertEqual(first, second)
        self.assertEqual(first.pull_request_id, 1)

    def test_deny_decision_cannot_publish(self):
        request = dict(self.request, policy_effect="deny")
        with self.assertRaisesRegex(ContractValidationError, "authority proof"):
            self.endpoint.publish_pull_request(request)

    def test_arbitrary_field_cannot_reach_endpoint(self):
        request = dict(self.request, token="secret")
        with self.assertRaisesRegex(ContractValidationError, "shape mismatch"):
            self.endpoint.publish_pull_request(request)

    def test_idempotency_key_cannot_mask_different_side_effect(self):
        first = self.endpoint.publish_pull_request(self.request)
        cases = (
            ("branch", "agent/process-evil-001", "idempotency key mismatch"),
            ("staged_change_digest", "sha256:" + "b" * 64, "idempotency key mismatch"),
            ("repository_id", "github-installation/42/repository/9999", "idempotency conflict"),
        )
        for field, value, reason in cases:
            with self.subTest(field=field):
                masked = dict(self.request, **{field: value})
                with self.assertRaisesRegex(ContractValidationError, reason):
                    self.endpoint.publish_pull_request(masked)
        self.assertEqual(
            self.endpoint.find_by_idempotency_key(self.request["idempotency_key"]), first
        )

    def test_cross_repository_replay_returns_no_receipt_and_no_side_effect(self):
        original = self.endpoint.publish_pull_request(self.request)
        foreign = dict(self.request, repository_id="github-installation/42/repository/9999")
        with self.assertRaisesRegex(ContractValidationError, "idempotency conflict"):
            self.endpoint.publish_pull_request(foreign)
        self.assertIsNone(
            self.endpoint.find_by_idempotency_key(
                self.request["idempotency_key"],
                repository_id="github-installation/42/repository/9999",
            )
        )
        self.assertEqual(
            self.endpoint.find_by_idempotency_key(
                self.request["idempotency_key"],
                repository_id=self.request["repository_id"],
            ),
            original,
        )
        replayed = self.endpoint.publish_pull_request(dict(self.request))
        self.assertEqual(replayed, original)
        self.assertEqual(replayed.pull_request_id, 1)

    def test_caller_mutation_cannot_alter_stored_receipt(self):
        import json
        receipt = self.endpoint.publish_pull_request(self.request)
        self.request["branch"] = "agent/process-mutated-001"
        self.request["staged_change_digest"] = "sha256:" + "f" * 64
        with self.assertRaises(FrozenInstanceError):
            receipt.branch = "agent/process-mutated-001"  # type: ignore[misc]
        reread = self.endpoint.find_by_idempotency_key(receipt.idempotency_key)
        self.assertEqual(reread, receipt)
        self.assertEqual(reread.branch, "agent/process-demo-001")
        payload = json.dumps(reread.__dict__)
        for forbidden in ("token", "secret", "password"):
            self.assertNotIn(forbidden, payload)

    def test_malformed_scalars_denied_with_zero_side_effect(self):
        cases = (
            ("branch", 123),
            ("branch", None),
            ("branch", ["agent/process-demo-001"]),
            ("repository_id", 42),
            ("staged_change_digest", 12345),
            ("idempotency_key", None),
            ("idempotency_key", ""),
        )
        for field, value in cases:
            with self.subTest(field=field, value=type(value).__name__):
                endpoint = MockGitHubEndpoint()
                request = dict(self.request, **{field: value})
                with self.assertRaises(ContractValidationError) as raised:
                    endpoint.publish_pull_request(request)
                self.assertIn(
                    str(raised.exception),
                    (
                        "mock github: boundary field is invalid",
                        "mock github: idempotency key mismatch",
                    ),
                )
                self.assertIsNone(endpoint.find_by_idempotency_key(self.request["idempotency_key"]))

    def test_non_mapping_request_stores_no_receipt(self):
        for bad in (None, 123, "request", ["operation"]):
            with self.subTest(request=type(bad).__name__):
                endpoint = MockGitHubEndpoint()
                with self.assertRaisesRegex(ContractValidationError, "request shape mismatch"):
                    endpoint.publish_pull_request(bad)
                self.assertIsNone(endpoint.find_by_idempotency_key(self.request["idempotency_key"]))

    def test_out_of_namespace_lookup_keys_disclose_nothing(self):
        original = self.endpoint.publish_pull_request(self.request)
        for bad in ("anything", "x", "PUBLISH/process-demo-001/key", "publish/", "other/publish/a/b"):
            with self.subTest(key=bad):
                with self.assertRaisesRegex(
                    ContractValidationError, "lookup key is outside the publication namespace"
                ):
                    self.endpoint.find_by_idempotency_key(bad)
        self.assertEqual(
            self.endpoint.find_by_idempotency_key(self.request["idempotency_key"]), original
        )

    def test_malformed_lookup_inputs_fail_without_receipt_change(self):
        original = self.endpoint.publish_pull_request(self.request)
        for bad_key in (None, 123, "", ["key"]):
            with self.subTest(key=type(bad_key).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "^mock github: lookup key is invalid$"
                ):
                    self.endpoint.find_by_idempotency_key(bad_key)
        for bad_repo in (123, ["repo"], ""):
            with self.subTest(repository=type(bad_repo).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "^mock github: lookup repository is invalid$"
                ):
                    self.endpoint.find_by_idempotency_key(
                        self.request["idempotency_key"], repository_id=bad_repo
                    )
        self.assertEqual(
            self.endpoint.find_by_idempotency_key(self.request["idempotency_key"]), original
        )
        self.assertEqual(
            self.endpoint.find_by_idempotency_key(
                self.request["idempotency_key"], repository_id=self.request["repository_id"]
            ),
            original,
        )

    def test_out_of_namespace_branch_makes_no_receipt(self):
        digest = "sha256:" + "a" * 64
        for branch in ("main", "other/process-demo-001", "agent", "agentprocess-001"):
            with self.subTest(branch=branch):
                endpoint = MockGitHubEndpoint()
                request = dict(
                    self.request,
                    branch=branch,
                    staged_change_digest=digest,
                    idempotency_key=f"publish/{branch.removeprefix('agent/')}/{digest}",
                )
                with self.assertRaisesRegex(
                    ContractValidationError, "branch is outside the agent namespace"
                ):
                    endpoint.publish_pull_request(request)
                self.assertIsNone(endpoint.find_by_idempotency_key(request["idempotency_key"]))

    def test_bare_namespace_branch_makes_no_receipt(self):
        digest = "sha256:" + "a" * 64
        endpoint = MockGitHubEndpoint()
        request = dict(
            self.request,
            branch="agent/",
            staged_change_digest=digest,
            idempotency_key=f"publish//{digest}",
        )
        with self.assertRaisesRegex(
            ContractValidationError, "branch is outside the agent namespace"
        ):
            endpoint.publish_pull_request(request)
        self.assertIsNone(endpoint.find_by_idempotency_key(f"publish//{digest}"))

    def test_content_unbound_idempotency_key_is_rejected(self):
        request = dict(self.request, idempotency_key="publish/process-demo-001/anything")
        with self.assertRaisesRegex(ContractValidationError, "idempotency key"):
            self.endpoint.publish_pull_request(request)


if __name__ == "__main__":
    unittest.main()
