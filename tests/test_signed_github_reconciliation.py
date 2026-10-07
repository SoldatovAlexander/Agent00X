from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import unquote
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.authority import DeterministicPolicy
from app_contracts.controlled_publication import (
    ControlledPublicationError,
    run_controlled_local_publication,
)
from app_contracts.digests import sha256_digest
from app_contracts.durable_stage import (
    SQLiteStagedArtifactStore,
    build_staged_artifact,
)
from app_contracts.github_app import (
    GitHubAppBrokerConfig,
    GitHubAppCredentialBroker,
    GitHubAppReadOnlyReconciliationBroker,
    GitHubAppReadOnlyReconciliationChannel,
    GitHubPullRequest,
    _InstallationToken,
)
from app_contracts.publication import PublicationJournal
from app_contracts.publication_seed import (
    PublicationSeed,
    bind_publication_seed_to_target,
    derive_publication_intent,
)
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts.validator import ContractValidationError
from app_contracts.signed_github_reconciliation import (
    SignedGitHubReconciliationError,
    reconcile_signed_stage_github,
)
from test_durable_stage import get_verified_artifact
import app_contracts.signed_github_reconciliation as reconciler


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
PROVIDER_REPOSITORY_ID = "github-installation/456/repository/1001"


class FakeMinter:
    def __init__(self):
        self.grants = []

    def mint(self, grant):
        self.grants.append(dict(grant))
        return _InstallationToken("synthetic-token-never-used", "2026-10-08T13:00:00Z")


class SignedGitHubReconciliationTests(unittest.TestCase):
    def setUp(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="signed-github-reconciliation-test-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "stage.sqlite3"
        self.journal_path = self.root / "publication.sqlite3"
        with SQLiteStagedArtifactStore(self.database) as store:
            store.save(artifact)
        self.artifact = artifact
        self.digest = artifact.staged_change_digest
        payload = artifact.payload_copy()
        self.source_repository = payload["seed"]["repository_id"]
        self.binding = RepositoryTargetBinding(
            self.source_repository, PROVIDER_REPOSITORY_ID
        )
        self.seed = bind_publication_seed_to_target(
            PublicationSeed(**payload["seed"]), self.binding
        )
        self.intent = derive_publication_intent(
            self.seed,
            "agent/process-reconcile-001",
            "master",
        )
        with PublicationJournal(self.journal_path) as journal:
            journal.prepare(
                self.intent.process_id,
                idempotency_key=self.intent.idempotency_key,
                request_digest=sha256_digest({"synthetic": "journal request"}),
                repository_id=self.intent.repository_id,
                verified_files_digest=self.seed.verified_contents_digest,
            )
            journal.mark_attempting(self.intent.process_id)
        self.config = GitHubAppBrokerConfig(
            app_id=123,
            installation_id=456,
            repository_id=1001,
            repository=self.source_repository,
            private_key_path=self.root / "unused-private-key-reference.pem",
            api_url="https://api.github.com",
        )

    def _call(self, confirmation=None, *, get_json=None, minter=None):
        active_minter = FakeMinter() if minter is None else minter
        with (
            patch.object(reconciler, "TARGET_REPOSITORY", self.source_repository),
            patch.object(
                GitHubAppBrokerConfig,
                "from_environment",
                return_value=self.config,
            ),
            patch.object(
                reconciler,
                "GitHubAppInstallationTokenMinter",
                return_value=active_minter,
            ),
        ):
            result = reconcile_signed_stage_github(
                self.database,
                self.digest,
                self.journal_path,
                f"RECONCILE {self.digest}" if confirmation is None else confirmation,
                now=NOW,
                environ={},
                get_json=get_json,
            )
        return result, active_minter

    def _manifest_blob_shas(self) -> dict[str, str]:
        payload = self.artifact.payload_copy()
        result = {}
        for item in payload["verified_contents"]:
            content = item["content"].encode("utf-8")
            result[item["path"]] = hashlib.sha1(
                b"blob " + str(len(content)).encode("ascii") + b"\0" + content
            ).hexdigest()
        return result

    def test_exact_pr_receipt_recovers_with_read_only_permissions_and_no_writes(self):
        calls = []

        def get_json(url, _headers):
            calls.append(url)
            decoded_url = unquote(url)
            if "/pulls?state=all&head=" in url:
                return [{
                    "number": 92,
                    "html_url": f"https://github.com/{self.source_repository}/pull/92",
                    "body": f"<!-- agent-process-idempotency: {self.intent.idempotency_key} -->",
                    "head": {"ref": self.intent.branch},
                    "base": {"ref": self.intent.base_branch},
                }]
            raise AssertionError("PR receipt should finish reconciliation immediately")

        before_stage = self.database.read_bytes()
        result, minter = self._call(get_json=get_json)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["pull_request_id"], 92)
        self.assertEqual(
            result["pull_request_url"],
            f"https://github.com/{self.source_repository}/pull/92",
        )
        self.assertIs(result["identity_authenticated"], False)
        self.assertIs(result["provider_write"], False)
        self.assertEqual(len(minter.grants), 1)
        self.assertEqual(
            minter.grants[0]["permissions"],
            ["contents:read", "pull_requests:read"],
        )
        self.assertEqual(len(calls), 1)
        self.assertNotIn("publish_pull_request", dir(GitHubAppReadOnlyReconciliationChannel))
        self.assertNotIn("publish_verified_files", dir(GitHubAppReadOnlyReconciliationChannel))
        self.assertNotIn("_post_json", dir(GitHubAppReadOnlyReconciliationChannel))
        self.assertNotIn("_put_json", dir(GitHubAppReadOnlyReconciliationChannel))
        self.assertEqual(self.database.read_bytes(), before_stage)
        with PublicationJournal(self.journal_path, create_if_missing=False) as journal:
            self.assertEqual(journal.get(self.intent.process_id).status, "completed")

    def test_no_pr_and_exact_file_state_persist_only_digest_reconciliation(self):
        calls = []
        blob_shas = self._manifest_blob_shas()

        def get_json(url, _headers):
            calls.append(url)
            decoded_url = unquote(url)
            if "/pulls?state=all&head=" in url:
                return []
            if "/git/ref/heads/" in url:
                response = {
                    "ref": f"refs/heads/{self.intent.branch}",
                    "object": {"type": "commit", "sha": "a" * 40},
                }
                calls.append(response)
                return response
            if "/contents/" in decoded_url and f"ref={self.intent.branch}" in decoded_url:
                path = decoded_url.split("/contents/", 1)[1].split("?", 1)[0]
                response = {"type": "file", "sha": blob_shas[path]}
                calls.append(response)
                return response
            raise AssertionError("unexpected fake GET")

        result, minter = self._call(get_json=get_json)
        self.assertEqual(result["status"], "reconciliation_required")
        self.assertEqual(result["verified_files_digest"], self.seed.verified_contents_digest)
        self.assertEqual(result["verified_files_outcome"], "verified", (calls, blob_shas))
        self.assertEqual(result["verified_branch_commit_sha"], "a" * 40)
        self.assertEqual(len(minter.grants), 1)
        self.assertGreaterEqual(len(calls), 3)
        with PublicationJournal(self.journal_path, create_if_missing=False) as journal:
            record = journal.get(self.intent.process_id)
            self.assertEqual(record.status, "reconciliation_required")
            self.assertEqual(record.verified_files_digest, self.seed.verified_contents_digest)
            self.assertEqual(record.verified_files_outcome, "verified")
            self.assertIsNone(record.pull_request_id)

    def test_unknown_get_state_is_persisted_unverified_without_any_write_retry(self):
        events = []

        def get_json(url, _headers):
            events.append(("GET", url))
            if "/pulls?state=all&head=" in url:
                return []
            if "/git/ref/heads/" in url:
                raise OSError("synthetic unavailable read")
            raise AssertionError("unexpected fake GET")

        result, minter = self._call(get_json=get_json)
        self.assertEqual(result["status"], "reconciliation_required")
        self.assertEqual(result["verified_files_outcome"], "unverified")
        self.assertIsNone(result["verified_branch_commit_sha"])
        self.assertTrue(all(event[0] == "GET" for event in events))
        self.assertEqual(len(minter.grants), 1)
        with PublicationJournal(self.journal_path, create_if_missing=False) as journal:
            self.assertEqual(
                journal.get(self.intent.process_id).verified_files_outcome,
                "unverified",
            )

    def test_confirmation_mismatch_stops_before_configuration_and_token(self):
        minter = FakeMinter()
        with (
            patch.object(reconciler, "TARGET_REPOSITORY", self.source_repository),
            patch.object(GitHubAppBrokerConfig, "from_environment") as config,
            patch.object(reconciler, "GitHubAppInstallationTokenMinter", return_value=minter),
        ):
            with self.assertRaises(SignedGitHubReconciliationError):
                reconcile_signed_stage_github(
                    self.database,
                    self.digest,
                    self.journal_path,
                    "RECONCILE sha256:" + "0" * 64,
                    now=NOW,
                    environ={},
                    get_json=lambda *_args: self.fail("transport must not run"),
                )
        config.assert_not_called()
        self.assertEqual(minter.grants, [])

    def test_completed_record_returns_local_receipt_without_token(self):
        with PublicationJournal(self.journal_path) as journal:
            record = journal.get(self.intent.process_id)
            receipt = GitHubPullRequest(
                93,
                f"https://github.com/{self.source_repository}/pull/93",
                self.intent.repository_id,
                self.intent.branch,
                self.intent.staged_change_digest,
                self.intent.idempotency_key,
                self.intent.base_branch,
            )
            journal.mark_completed(record.process_id, receipt)
        minter = FakeMinter()
        result, _ = self._call(minter=minter, get_json=lambda *_args: self.fail("GET must not run"))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["pull_request_id"], 93)
        self.assertEqual(minter.grants, [])

    def test_read_only_channel_is_rejected_by_write_coordinator(self):
        payload = self.artifact.payload_copy()
        files = tuple()
        config = self.config
        readonly_channel = GitHubAppReadOnlyReconciliationChannel(
            config,
            _InstallationToken("synthetic", "future"),
            get_json=lambda *_args: self.fail("transport must not run"),
        )
        broker = GitHubAppCredentialBroker(config, FakeMinter())
        with PublicationJournal(self.journal_path) as journal:
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: GitHub channel type is required$",
            ):
                run_controlled_local_publication(
                    self.seed,
                    self.intent,
                    {},
                    DeterministicPolicy({}),
                    {},
                    lambda _seed: payload["staged_change"],
                    "read-only-rejection-test",
                    lambda *_args, **_kwargs: self.fail("Gateway must not run"),
                    {},
                    broker,
                    {},
                    journal,
                    readonly_channel,
                    verified_files=files,
                    actuator_id="github-app-actuator",
                    now=NOW,
                )

    def test_read_only_broker_rejects_write_permissions_before_mint(self):
        minter = FakeMinter()
        broker = GitHubAppReadOnlyReconciliationBroker(self.config, minter)
        request = {
            "operation": "reconcile_publication",
            "repository_id": PROVIDER_REPOSITORY_ID,
            "actuator_id": "github-app-readonly-reconciliation",
            "base_branch": "master",
            "staged_change_digest": self.digest,
            "branch_namespace": "agent",
            "idempotency_key": self.intent.idempotency_key,
        }
        grant = {
            "credential_grant_id": "reconcile-test-grant",
            "credential_class": "github-app-installation",
            "installation_id": 456,
            "repository_id": PROVIDER_REPOSITORY_ID,
            "permissions": ["contents:read", "pull_requests:read"],
            "actuator_id": "github-app-readonly-reconciliation",
            "operation": "reconcile_publication",
            "request_digest": sha256_digest(request),
            "single_use": True,
            "expires_at": "2026-10-08T12:05:00Z",
        }
        channel = broker.open_read_only_reconciliation_channel(
            grant, request, now=NOW
        )
        self.assertIs(type(channel), GitHubAppReadOnlyReconciliationChannel)
        self.assertEqual(len(minter.grants), 1)
        escalated = dict(grant)
        escalated["credential_grant_id"] = "reconcile-write-escalation"
        escalated["permissions"] = ["contents:write", "pull_requests:write"]
        escalated["request_digest"] = sha256_digest(request)
        with self.assertRaisesRegex(
            ContractValidationError,
            "^GitHub actuator: read-only credential grant is invalid$",
        ):
            broker.open_read_only_reconciliation_channel(
                escalated, request, now=NOW
            )
        self.assertEqual(len(minter.grants), 1)


if __name__ == "__main__":
    unittest.main()
