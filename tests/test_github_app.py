from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.github_app import GitHubAppBrokerConfig, GitHubAppConfigurationError


class GitHubAppConfigurationTests(unittest.TestCase):
    def _environment(self, key_path: Path) -> dict[str, str]:
        return {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
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

    def test_preflight_rejects_key_file_with_broad_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o644)
            with self.assertRaisesRegex(GitHubAppConfigurationError, "group or others"):
                GitHubAppBrokerConfig.from_environment(self._environment(key_path))


if __name__ == "__main__":
    unittest.main()
