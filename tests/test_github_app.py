from __future__ import annotations

from datetime import datetime, timezone
import base64
import json
from pathlib import Path
import os
import subprocess
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
    GitHubAppCredentialBroker,
    _InstallationToken,
)
from app_contracts.digests import sha256_digest
from app_contracts.repository_process import PublishableFile
from app_contracts.gateway import GatewayDecision, GatewayPath
from app_contracts.github_actuator import BrokeredGitHubActuator
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
                get_json=lambda _url, _headers: [],
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
        self.assertIn("agent-process-idempotency", calls[0][2]["body"])

    def test_publication_channel_reconciles_existing_pr_without_second_post(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o600)
            from app_contracts.github_app import GitHubAppPublicationChannel
            request = {"operation": "publish_pull_request", "repository_id": "github-installation/456/repository/1001", "branch": "agent/process-demo-001", "staged_change_digest": "sha256:" + "a" * 64, "idempotency_key": "publish/process-demo-001/sha256:" + "a" * 64, "policy_effect": "allow", "approval_valid": True}
            marker = f"<!-- agent-process-idempotency: {request['idempotency_key']} -->"
            channel = GitHubAppPublicationChannel(
                GitHubAppBrokerConfig.from_environment(self._environment(key_path)), _InstallationToken("opaque", "future"),
                post_json=lambda *_args: self.fail("a reconciled request must not create a second PR"),
                get_json=lambda _url, _headers: [{"number": 9, "html_url": "https://github.com/example/agent00x-sandbox/pull/9", "body": marker}],
            )
            result = channel.publish_pull_request(request)
        self.assertEqual(result.pull_request_id, 9)

    def test_publication_channel_rejects_unallowlisted_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o600)
            from app_contracts.github_app import _InstallationToken, GitHubAppPublicationChannel
            channel = GitHubAppPublicationChannel(GitHubAppBrokerConfig.from_environment(self._environment(key_path)), _InstallationToken("opaque", "future"))
            with self.assertRaisesRegex(ContractValidationError, "not allowlisted"):
                channel.publish_pull_request({"operation": "publish_pull_request", "repository_id": "github-installation/456/repository/999", "branch": "agent/process-demo-001", "staged_change_digest": "sha256:" + "a" * 64, "idempotency_key": "key", "policy_effect": "allow", "approval_valid": True})

    def test_verified_manifest_creates_scoped_branch_and_contents_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o600)
            from app_contracts.github_app import GitHubAppPublicationChannel
            posts, puts = [], []
            content = "verified content\n"
            channel = GitHubAppPublicationChannel(
                GitHubAppBrokerConfig.from_environment(self._environment(key_path)), _InstallationToken("opaque", "future"),
                post_json=lambda url, headers, payload: posts.append((url, payload)) or {"ref": payload["ref"]},
                get_json=lambda _url, _headers: (_ for _ in ()).throw(FileNotFoundError("confirmed 404: absent branch")),
                put_json=lambda url, headers, payload: puts.append((url, payload)) or {"commit": {"sha": "d" * 40}},
            )
            sha = channel.publish_verified_files(
                branch="agent/process-demo-001",
                staged_change={"repository_id": "github-installation/456/repository/1001", "base_commit": "a" * 40, "patch_digest": "sha256:" + "b" * 64},
                files=[PublishableFile("proof.txt", content, __import__("app_contracts.digests", fromlist=["sha256_bytes"]).sha256_bytes(content.encode()))],
            )
        self.assertEqual(sha, "d" * 40)
        self.assertEqual(posts[0][1], {"ref": "refs/heads/agent/process-demo-001", "sha": "a" * 40})
        self.assertEqual(puts[0][1]["branch"], "agent/process-demo-001")

    def test_preflight_rejects_key_file_with_broad_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o644)
            with self.assertRaisesRegex(GitHubAppConfigurationError, "group or others"):
                GitHubAppBrokerConfig.from_environment(self._environment(key_path))

    def test_preflight_command_reports_metadata_without_key_path_or_content(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("private-key-canary", encoding="utf-8")
            key_path.chmod(0o600)
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "github_app_preflight.py")],
                env={**os.environ, **self._environment(key_path)},
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("preflight passed", completed.stdout)
        self.assertNotIn("private-key-canary", completed.stdout + completed.stderr)
        self.assertNotIn(str(key_path), completed.stdout + completed.stderr)

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
        self.assertEqual(calls[0][2], {"repositories": ["agent00x-sandbox"], "permissions": {"contents": "write", "pull_requests": "write"}})
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

    def test_broker_to_actuator_path_keeps_token_private_and_grant_single_use(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "github-app.pem"
            key_path.write_text("unused", encoding="utf-8")
            key_path.chmod(0o600)
            config = GitHubAppBrokerConfig.from_environment(self._environment(key_path))
            minted_grants, api_calls = [], []

            class FakeMinter:
                def mint(self, grant):
                    minted_grants.append(grant["credential_grant_id"])
                    return _InstallationToken("opaque-private-token", "2026-09-04T12:10:00Z")

            broker = GitHubAppCredentialBroker(
                config, FakeMinter(),
                post_json=lambda url, headers, payload: api_calls.append((url, headers, payload)) or {"number": 8, "html_url": "https://github.com/example/agent00x-sandbox/pull/8"},
                get_json=lambda _url, _headers: [],
            )
            actuator_request = {
                "actuator_id": "actuator-github-001",
                "operation": "publish_pull_request",
                "repository_id": "github-installation/456/repository/1001",
                "branch_namespace": "agent/process-demo-001",
                "staged_change_digest": "sha256:" + "b" * 64,
                "idempotency_key": "publish/process-demo-001/sha256:" + "b" * 64,
            }
            grant = {
                "credential_grant_id": "credential-grant-demo-001",
                "credential_class": "github-app-installation",
                "installation_id": 456,
                "repository_id": actuator_request["repository_id"],
                "permissions": ["contents:write", "pull_requests:write"],
                "actuator_id": actuator_request["actuator_id"],
                "operation": actuator_request["operation"],
                "request_digest": sha256_digest(actuator_request),
                "single_use": True,
            }
            intent = {
                "branch_namespace": actuator_request["branch_namespace"],
                "idempotency_key": actuator_request["idempotency_key"],
            }
            approval = {"approved_intent_digest": sha256_digest(intent)}
            now = datetime(2026, 9, 4, 12, 7, tzinfo=timezone.utc)
            policy_decision = {"effect": "allow", "operation": "publish_pull_request", "repository_id": actuator_request["repository_id"], "staged_change_digest": actuator_request["staged_change_digest"], "expires_at": "2026-09-04T12:12:00Z"}
            result = BrokeredGitHubActuator(broker).publish_pull_request(
                actuator_request=actuator_request,
                credential_grant=grant,
                policy_decision=policy_decision,
                approval_valid=True,
                gateway_decision=GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",)),
                intent=intent,
                now=now,
                approval=approval,
            )
            self.assertEqual(result.pull_request_id, 8)
            self.assertEqual(minted_grants, ["credential-grant-demo-001"])
            self.assertNotIn("opaque-private-token", repr(actuator_request))
            self.assertEqual(api_calls[0][2]["head"], "agent/process-demo-001")
            with self.assertRaisesRegex(ContractValidationError, "already used"):
                BrokeredGitHubActuator(broker).publish_pull_request(
                    actuator_request=actuator_request, credential_grant=grant,
                    policy_decision=policy_decision,
                    approval_valid=True, gateway_decision=GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",)),
                    intent=intent,
                    now=now,
                    approval=approval,
                )


class GitHubReconciliationTests(unittest.TestCase):
    def _channel(self, config_factory_post_get_put):
        from app_contracts.github_app import GitHubAppPublicationChannel
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_path = Path(directory.name) / "github-app.pem"
        key_path.write_text("unused", encoding="utf-8")
        key_path.chmod(0o600)
        environment = {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
            "AGENT_GITHUB_TEST_REPOSITORY": "example/agent00x-sandbox",
            "AGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
        }
        post_json, get_json, put_json = config_factory_post_get_put
        return GitHubAppPublicationChannel(
            GitHubAppBrokerConfig.from_environment(environment),
            _InstallationToken("opaque", "future"),
            post_json=post_json, get_json=get_json, put_json=put_json,
        )

    def _staged_change(self):
        return {
            "repository_id": "github-installation/456/repository/1001",
            "base_commit": "a" * 40,
            "patch_digest": "sha256:" + "b" * 64,
        }

    def _files(self):
        from app_contracts.digests import sha256_bytes
        content = "verified content\n"
        return [PublishableFile("proof.txt", content, sha256_bytes(content.encode()))]

    def test_branch_failure_then_retry_skips_duplicate_branch_post(self):
        refs_posts = []
        channel = self._channel((
            lambda url, headers, payload: refs_posts.append(payload) or {"ref": payload["ref"]},
            lambda _url, _headers: (_ for _ in ()).throw(FileNotFoundError("confirmed 404: absent branch")),
            lambda _url, _headers, _payload: (_ for _ in ()).throw(RuntimeError("injected failure after branch")),
        ))
        with self.assertRaisesRegex(RuntimeError, "injected failure after branch"):
            channel.publish_verified_files(
                branch="agent/process-demo-001", staged_change=self._staged_change(), files=self._files(),
            )
        self.assertEqual(len(refs_posts), 1)

        retry_posts = []
        retry = self._channel((
            lambda _url, _headers, _payload: self.fail("a reconciled retry must not recreate the branch"),
            lambda _url, _headers: {"ref": "refs/heads/agent/process-demo-001"},
            lambda url, headers, payload: {"commit": {"sha": "e" * 40}},
        ))
        sha = retry.publish_verified_files(
            branch="agent/process-demo-001", staged_change=self._staged_change(), files=self._files(),
        )
        self.assertEqual(sha, "e" * 40)
        self.assertEqual(retry_posts, [])

    def test_unknown_branch_outcome_blocks_retry_without_side_effect(self):
        calls = []
        channel = self._channel((
            lambda url, headers, payload: calls.append(("post", payload)),
            lambda _url, _headers: (_ for _ in ()).throw(RuntimeError("injected transport failure")),
            lambda url, headers, payload: calls.append(("put", payload)),
        ))
        with self.assertRaisesRegex(GitHubAppBrokerError, "outcome unknown"):
            channel.publish_verified_files(
                branch="agent/process-demo-001", staged_change=self._staged_change(), files=self._files(),
            )
        self.assertEqual(calls, [])

    def test_lost_pr_response_reconciles_to_existing_receipt(self):
        from app_contracts.github_app import GitHubAppPublicationChannel
        branch = "agent/process-demo-001"
        digest = "sha256:" + "c" * 64
        key = f"publish/process-demo-001/{digest}"
        marker = f"<!-- agent-process-idempotency: {key} -->"
        request = {
            "operation": "publish_pull_request",
            "repository_id": "github-installation/456/repository/1001",
            "branch": branch,
            "staged_change_digest": digest,
            "idempotency_key": key,
            "policy_effect": "allow",
            "approval_valid": True,
        }
        channel = self._channel((
            lambda *_args: self.fail("a reconciled retry must not create a second PR"),
            lambda _url, _headers: [{"number": 13, "html_url": "https://github.com/example/agent00x-sandbox/pull/13", "body": marker}],
            None,
        ))
        result = channel.publish_pull_request(request)
        self.assertEqual(result.pull_request_id, 13)
        self.assertIsInstance(channel, GitHubAppPublicationChannel)
        receipt = channel.reconcile_pull_request(branch=branch, idempotency_key=key, staged_change_digest=digest)
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual(receipt.pull_request_id, 13)
        self.assertEqual(receipt.idempotency_key, key)

    def test_reconcile_returns_unknown_when_lookup_fails(self):
        channel = self._channel((
            None,
            lambda _url, _headers: (_ for _ in ()).throw(RuntimeError("injected lookup failure")),
            None,
        ))
        self.assertIsNone(channel.reconcile_pull_request(
            branch="agent/process-demo-001",
            idempotency_key="publish/process-demo-001/sha256:" + "c" * 64,
        ))
        self.assertIsNone(channel.reconcile_branch("agent/process-demo-001"))


class ManifestDigestTests(unittest.TestCase):
    def _recording_channel(self, calls):
        from app_contracts.github_app import GitHubAppPublicationChannel
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_path = Path(directory.name) / "github-app.pem"
        key_path.write_text("unused", encoding="utf-8")
        key_path.chmod(0o600)
        environment = {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
            "AGENT_GITHUB_TEST_REPOSITORY": "example/agent00x-sandbox",
            "AGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
        }
        return GitHubAppPublicationChannel(
            GitHubAppBrokerConfig.from_environment(environment),
            _InstallationToken("opaque", "future"),
            post_json=lambda url, headers, payload: calls.append(("POST", url)) or {"ref": payload["ref"]},
            get_json=lambda _url, _headers: (_ for _ in ()).throw(FileNotFoundError("confirmed 404: absent branch")),
            put_json=lambda url, headers, payload: calls.append(("PUT", url)) or {"commit": {"sha": "f" * 40}},
        )

    def _staged_change(self):
        return {
            "repository_id": "github-installation/456/repository/1001",
            "base_commit": "a" * 40,
            "patch_digest": "sha256:" + "b" * 64,
        }

    def test_tampered_content_is_rejected_before_any_provider_call(self):
        from app_contracts.digests import sha256_bytes
        calls = []
        channel = self._recording_channel(calls)
        content = "verified content\n"
        forged = PublishableFile("proof.txt", "forged content\n", sha256_bytes(content.encode()))
        with self.assertRaisesRegex(ContractValidationError, "content digest mismatch"):
            channel.publish_verified_files(
                branch="agent/process-demo-001", staged_change=self._staged_change(), files=[forged],
            )
        self.assertEqual(calls, [])

    def test_tampered_digest_is_rejected_before_any_provider_call(self):
        calls = []
        channel = self._recording_channel(calls)
        forged = PublishableFile("proof.txt", "verified content\n", "sha256:" + "0" * 64)
        with self.assertRaisesRegex(ContractValidationError, "content digest mismatch"):
            channel.publish_verified_files(
                branch="agent/process-demo-001", staged_change=self._staged_change(), files=[forged],
            )
        self.assertEqual(calls, [])

    def test_matching_verified_file_keeps_happy_path(self):
        from app_contracts.digests import sha256_bytes
        calls = []
        channel = self._recording_channel(calls)
        content = "verified content\n"
        result = channel.publish_verified_files(
            branch="agent/process-demo-001",
            staged_change=self._staged_change(),
            files=[PublishableFile("proof.txt", content, sha256_bytes(content.encode()))],
        )
        self.assertEqual(result, "f" * 40)
        self.assertEqual([method for method, _ in calls], ["POST", "PUT"])


class MalformedReconciliationTests(unittest.TestCase):
    def _branch_channel(self, calls, branch_payload):
        from app_contracts.github_app import GitHubAppPublicationChannel
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_path = Path(directory.name) / "github-app.pem"
        key_path.write_text("unused", encoding="utf-8")
        key_path.chmod(0o600)
        environment = {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
            "AGENT_GITHUB_TEST_REPOSITORY": "example/agent00x-sandbox",
            "AGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
        }
        return GitHubAppPublicationChannel(
            GitHubAppBrokerConfig.from_environment(environment),
            _InstallationToken("opaque", "future"),
            post_json=lambda url, headers, payload: calls.append(("POST", url)) or {"ref": payload["ref"]},
            get_json=lambda _url, _headers: branch_payload,
            put_json=lambda url, headers, payload: calls.append(("PUT", url)) or {"commit": {"sha": "f" * 40}},
        )

    def _staged_change(self):
        return {
            "repository_id": "github-installation/456/repository/1001",
            "base_commit": "a" * 40,
            "patch_digest": "sha256:" + "b" * 64,
        }

    def _files(self):
        from app_contracts.digests import sha256_bytes
        content = "verified content\n"
        return [PublishableFile("proof.txt", content, sha256_bytes(content.encode()))]

    def test_malformed_branch_payload_causes_unknown_not_side_effect(self):
        from app_contracts.github_app import GitHubAppBrokerError
        for malformed in (None, "ok", 42, [], {"unexpected": "shape"}, [{"ref": "refs/heads/agent/process-demo-001"}]):
            with self.subTest(payload=malformed):
                calls = []
                channel = self._branch_channel(calls, malformed)
                self.assertIsNone(channel.reconcile_branch("agent/process-demo-001"))
                with self.assertRaisesRegex(GitHubAppBrokerError, "outcome unknown"):
                    channel.publish_verified_files(
                        branch="agent/process-demo-001",
                        staged_change=self._staged_change(),
                        files=self._files(),
                    )
                self.assertEqual(calls, [])

    def _absent_branch_channel(self, calls):
        from app_contracts.github_app import GitHubAppPublicationChannel
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_path = Path(directory.name) / "github-app.pem"
        key_path.write_text("unused", encoding="utf-8")
        key_path.chmod(0o600)
        environment = {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
            "AGENT_GITHUB_TEST_REPOSITORY": "example/agent00x-sandbox",
            "AGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
        }
        return GitHubAppPublicationChannel(
            GitHubAppBrokerConfig.from_environment(environment),
            _InstallationToken("opaque", "future"),
            post_json=lambda url, headers, payload: calls.append(("POST", url)) or {"ref": payload["ref"]},
            get_json=lambda _url, _headers: (_ for _ in ()).throw(FileNotFoundError("confirmed 404: absent branch")),
            put_json=lambda url, headers, payload: calls.append(("PUT", url)) or {"commit": {"sha": "f" * 40}},
        )

    def test_absent_branch_is_distinct_from_malformed(self):
        calls = []
        channel = self._absent_branch_channel(calls)
        self.assertFalse(channel.reconcile_branch("agent/process-demo-001"))
        sha = channel.publish_verified_files(
            branch="agent/process-demo-001", staged_change=self._staged_change(), files=self._files(),
        )
        self.assertEqual(sha, "f" * 40)
        self.assertEqual([method for method, _ in calls], ["POST", "PUT"])

    def test_confirmed_http_404_is_absent_while_other_errors_stay_unknown(self):
        from urllib.error import HTTPError

        from app_contracts.github_app import GitHubAppBrokerError, GitHubAppPublicationChannel
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_path = Path(directory.name) / "github-app.pem"
        key_path.write_text("unused", encoding="utf-8")
        key_path.chmod(0o600)
        environment = {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
            "AGENT_GITHUB_TEST_REPOSITORY": "example/agent00x-sandbox",
            "AGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
        }

        def channel_with(get_json, calls):
            return GitHubAppPublicationChannel(
                GitHubAppBrokerConfig.from_environment(environment),
                _InstallationToken("opaque", "future"),
                post_json=lambda url, headers, payload: calls.append(("POST", url)) or {"ref": payload["ref"]},
                get_json=get_json,
                put_json=lambda url, headers, payload: calls.append(("PUT", url)) or {"commit": {"sha": "f" * 40}},
            )

        calls_404: list = []
        channel_404 = channel_with(
            lambda _url, _headers: (_ for _ in ()).throw(
                HTTPError("https://api.github.com/x", 404, "Not Found", {}, None)
            ),
            calls_404,
        )
        self.assertFalse(channel_404.reconcile_branch("agent/process-demo-001"))
        sha = channel_404.publish_verified_files(
            branch="agent/process-demo-001", staged_change=self._staged_change(), files=self._files(),
        )
        self.assertEqual(sha, "f" * 40)

        calls_500: list = []
        channel_500 = channel_with(
            lambda _url, _headers: (_ for _ in ()).throw(
                HTTPError("https://api.github.com/x", 500, "Server Error", {}, None)
            ),
            calls_500,
        )
        self.assertIsNone(channel_500.reconcile_branch("agent/process-demo-001"))
        with self.assertRaisesRegex(GitHubAppBrokerError, "outcome unknown"):
            channel_500.publish_verified_files(
                branch="agent/process-demo-001", staged_change=self._staged_change(), files=self._files(),
            )
        self.assertEqual(calls_500, [])

    def test_production_get_json_maps_confirmed_404_to_absent(self):
        from unittest.mock import patch
        from urllib.error import HTTPError

        from app_contracts import github_app

        def raise_404(*_args, **_kwargs):
            raise HTTPError("https://api.github.com/x", 404, "Not Found", {}, None)

        def raise_500(*_args, **_kwargs):
            raise HTTPError("https://api.github.com/x", 500, "Server Error", {}, None)

        with patch.object(github_app, "urlopen", side_effect=raise_404):
            with self.assertRaises(FileNotFoundError):
                github_app._get_json("https://api.github.com/x", {})
        with patch.object(github_app, "urlopen", side_effect=raise_500):
            with self.assertRaisesRegex(GitHubAppBrokerError, "reconciliation failed"):
                github_app._get_json("https://api.github.com/x", {})

    def test_malformed_pr_entry_blocks_post(self):
        from app_contracts.github_app import GitHubAppBrokerError, GitHubAppPublicationChannel
        digest = "sha256:" + "d" * 64
        key = f"publish/process-demo-001/{digest}"
        marker = f"<!-- agent-process-idempotency: {key} -->"
        request = {
            "operation": "publish_pull_request",
            "repository_id": "github-installation/456/repository/1001",
            "branch": "agent/process-demo-001",
            "staged_change_digest": digest,
            "idempotency_key": key,
            "policy_effect": "allow",
            "approval_valid": True,
        }
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_path = Path(directory.name) / "github-app.pem"
        key_path.write_text("unused", encoding="utf-8")
        key_path.chmod(0o600)
        environment = {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
            "AGENT_GITHUB_TEST_REPOSITORY": "example/agent00x-sandbox",
            "AGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
        }
        calls = []
        channel = GitHubAppPublicationChannel(
            GitHubAppBrokerConfig.from_environment(environment),
            _InstallationToken("opaque", "future"),
            post_json=lambda *_args: calls.append("POST"),
            get_json=lambda _url, _headers: [{"number": "NaN", "html_url": "https://github.com/example/x/pull/1", "body": marker}],
        )
        with self.assertRaisesRegex(GitHubAppBrokerError, "malformed"):
            channel.publish_pull_request(request)
        self.assertEqual(calls, [])
        self.assertIsNone(channel.reconcile_pull_request(branch=request["branch"], idempotency_key=key))


class ContentPathEncodingTests(unittest.TestCase):
    def _recording_channel(self, calls):
        from app_contracts.github_app import GitHubAppPublicationChannel
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_path = Path(directory.name) / "github-app.pem"
        key_path.write_text("unused", encoding="utf-8")
        key_path.chmod(0o600)
        environment = {
            "AGENT_GITHUB_APP_ID": "123",
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
            "AGENT_GITHUB_TEST_REPOSITORY": "example/agent00x-sandbox",
            "AGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
        }
        return GitHubAppPublicationChannel(
            GitHubAppBrokerConfig.from_environment(environment),
            _InstallationToken("opaque", "future"),
            post_json=lambda url, headers, payload: calls.append(("POST", url, payload)) or {"ref": payload["ref"]},
            get_json=lambda _url, _headers: (_ for _ in ()).throw(FileNotFoundError("confirmed 404: absent branch")),
            put_json=lambda url, headers, payload: calls.append(("PUT", url, payload)) or {"commit": {"sha": "f" * 40}},
        )

    def _staged_change(self):
        return {
            "repository_id": "github-installation/456/repository/1001",
            "base_commit": "a" * 40,
            "patch_digest": "sha256:" + "b" * 64,
        }

    def test_special_characters_encode_as_single_content_resource(self):
        import base64
        from app_contracts.digests import sha256_bytes
        calls = []
        channel = self._recording_channel(calls)
        content = "special path content\n"
        special = "my dir/file #1.txt"
        sha = channel.publish_verified_files(
            branch="agent/process-demo-001",
            staged_change=self._staged_change(),
            files=[PublishableFile(special, content, sha256_bytes(content.encode()))],
        )
        self.assertEqual(sha, "f" * 40)
        puts = [call for call in calls if call[0] == "PUT"]
        self.assertEqual(len(puts), 1)
        _, url, payload = puts[0]
        self.assertEqual(
            url,
            "https://api.github.com/repos/example/agent00x-sandbox/contents/my%20dir/file%20%231.txt",
        )
        self.assertEqual(payload["branch"], "agent/process-demo-001")
        self.assertEqual(base64.b64decode(payload["content"]).decode("utf-8"), content)

    def test_traversal_and_absolute_paths_stay_forbidden(self):
        from app_contracts.digests import sha256_bytes
        for unsafe in ("a/../b.txt", "/abs/file.txt", "../escape.txt"):
            with self.subTest(path=unsafe):
                calls = []
                channel = self._recording_channel(calls)
                content = "x\n"
                forged = PublishableFile(unsafe, content, sha256_bytes(content.encode()))
                with self.assertRaisesRegex(ContractValidationError, "manifest path is unsafe"):
                    channel.publish_verified_files(
                        branch="agent/process-demo-001",
                        staged_change=self._staged_change(),
                        files=[forged],
                    )
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
