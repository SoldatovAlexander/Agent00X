from __future__ import annotations

from datetime import datetime, timezone
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.github_app import (
    GitHubAppBrokerConfig,
    GitHubAppConfigurationError,
    GitHubAppInstallationTokenMinter,
    GitHubAppBrokerError,
)
from app_contracts.validator import ContractValidationError


class GitHubAppConfigurationTests(unittest.TestCase):
    def _environment(self, key_path: Path) -> dict[str, str]:
        return {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
            "AGENT_GITHUB_TEST_REPOSITORY": "example/agent00x-sandbox",
            "AGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
        }

    def test_preflight_accepts_metadata_and_private_key_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("test key is never read by preflight", encoding="utf-8")
            key_path.chmod(0o600)
            config = GitHubAppBrokerConfig.from_environment(self._environment(key_path))
        self.assertEqual(config.app_id, 123)
        self.assertEqual(config.installation_id, 456)
        self.assertEqual(config.repository_id, 1001)
        self.assertEqual(config.repository, "example/agent00x-sandbox")
        self.assertEqual(config.api_url, "https://api.github.com")

    def test_preflight_fails_closed_for_missing_or_invalid_metadata(self):
        with self.assertRaisesRegex(GitHubAppConfigurationError, "AGENT_GITHUB_APP_ID is required"):
            GitHubAppBrokerConfig.from_environment({})
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o600)
            environment = self._environment(key_path)
            environment["AGENT_GITHUB_TEST_REPOSITORY"] = "not-a-repository"
            with self.assertRaisesRegex(GitHubAppConfigurationError, "owner/name"):
                GitHubAppBrokerConfig.from_environment(environment)
            environment = self._environment(key_path)
            environment["AGENT_GITHUB_API_URL"] = "http://api.github.com"
            with self.assertRaisesRegex(GitHubAppConfigurationError, "https"):
                GitHubAppBrokerConfig.from_environment(environment)

    def test_publication_channel_posts_only_allowlisted_typed_request(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o600)
            config = GitHubAppBrokerConfig.from_environment(self._environment(key_path))
            calls = []
            from app_contracts.github_app import _InstallationToken, GitHubAppPublicationChannel
            channel = GitHubAppPublicationChannel(
                config, _InstallationToken("opaque-token", "2026-09-04T12:10:00Z"),
                post_json=lambda url, headers, payload: calls.append((url, headers, payload)) or {"number": 7, "html_url": "https://github.com/example/agent00x-sandbox/pull/7"},
            )
            result = channel.publish_pull_request({
                "operation": "publish_pull_request",
                "repository_id": "github-installation/456/repository/1001",
                "branch": "agent/process-demo-001",
                "staged_change_digest": "sha256:" + "a" * 64,
                "idempotency_key": "publish/process-demo-001/sha256:" + "a" * 64,
                "policy_effect": "allow",
                "approval_valid": True,
            })
        self.assertEqual(result.pull_request_id, 7)
        self.assertEqual(calls[0][0], "https://api.github.com/repos/example/agent00x-sandbox/pulls")
        self.assertEqual(calls[0][2]["head"], "agent/process-demo-001")
        self.assertEqual(calls[0][2]["base"], "main")

    def test_publication_channel_rejects_unallowlisted_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o600)
            from app_contracts.github_app import _InstallationToken, GitHubAppPublicationChannel
            channel = GitHubAppPublicationChannel(GitHubAppBrokerConfig.from_environment(self._environment(key_path)), _InstallationToken("opaque", "future"))
            with self.assertRaisesRegex(ContractValidationError, "not allowlisted"):
                channel.publish_pull_request({"operation": "publish_pull_request", "repository_id": "github-installation/456/repository/999", "branch": "agent/process-demo-001", "staged_change_digest": "sha256:" + "a" * 64, "idempotency_key": "key", "policy_effect": "allow", "approval_valid": True})

    def test_preflight_rejects_key_file_with_broad_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o644)
            with self.assertRaisesRegex(GitHubAppConfigurationError, "group or others"):
                GitHubAppBrokerConfig.from_environment(self._environment(key_path))

    def test_trusted_minter_signs_jwt_and_scopes_token_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            generated = __import__("subprocess").run(
                ["openssl", "genrsa", "-out", str(key_path), "2048"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            key_path.chmod(0o600)
            config = GitHubAppBrokerConfig.from_environment(self._environment(key_path))
            calls = []

            def post_json(url, headers, payload):
                calls.append((url, headers, payload))
                return {"token": "github-token-opaque", "expires_at": "2026-09-04T12:10:00Z"}

            minter = GitHubAppInstallationTokenMinter(
                config, post_json=post_json,
                now=lambda: datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
            )
            token = minter.mint({
                "credential_class": "github-app-installation",
                "installation_id": 456,
                "permissions": ["contents:write", "pull_requests:write"],
            })
        self.assertEqual(token.value, "github-token-opaque")
        self.assertEqual(token.expires_at, "2026-09-04T12:10:00Z")
        self.assertEqual(calls[0][0], "https://api.github.com/app/installations/456/access_tokens")
        self.assertEqual(calls[0][2], {"repositories": ["example/agent00x-sandbox"], "permissions": {"contents": "write", "pull_requests": "write"}})
        jwt = calls[0][1]["Authorization"].removeprefix("Bearer ")
        header, payload, signature = jwt.split(".")
        self.assertEqual(json.loads(base64.urlsafe_b64decode(header + "==")), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(json.loads(base64.urlsafe_b64decode(payload + "=="))["iss"], "123")
        self.assertTrue(signature)

    def test_minter_rejects_wrong_installation_without_token_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o600)
            minter = GitHubAppInstallationTokenMinter(GitHubAppBrokerConfig.from_environment(self._environment(key_path)))
            with self.assertRaisesRegex(GitHubAppBrokerError, "does not match"):
                minter.mint({"credential_class": "github-app-installation", "installation_id": 999, "permissions": ["contents:write"]})


if __name__ == "__main__":
    unittest.main()
