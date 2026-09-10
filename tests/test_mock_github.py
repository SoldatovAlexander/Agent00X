from pathlib import Path
import sys
import unittest


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

    def test_content_unbound_idempotency_key_is_rejected(self):
        request = dict(self.request, idempotency_key="publish/process-demo-001/anything")
        with self.assertRaisesRegex(ContractValidationError, "idempotency key"):
            self.endpoint.publish_pull_request(request)


if __name__ == "__main__":
    unittest.main()
