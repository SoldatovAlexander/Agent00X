from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from approval_test_support import TEST_APPROVER_ID, TEST_APPROVER_PUBLIC_KEY, sign_test_approval
from app_contracts.approval_request import build_approval_request
from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts.digests import sha256_digest
from app_contracts.approver_trust_enrollment import build_signed_approver_trust_enrollment
from app_contracts.github_app import GitHubAppBrokerConfig, _InstallationToken
from app_contracts.observation_store import SQLiteObservationStore
from app_contracts.observer_runtime import JournaledProposalWorker
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts.signed_approval import load_verified_signed_approval
from app_contracts.signed_github_publication import (
    SignedGitHubPublicationError,
    main as publication_main,
    publish_signed_stage_github,
)
from test_durable_stage import as_unverified_local_approval_fixture, get_verified_artifact
import app_contracts.signed_github_publication as publisher
import app_contracts.github_app as github_app


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
SOURCE_REPOSITORY = "FixtureOwner/stage-fixture"
BINDING = RepositoryTargetBinding(
    SOURCE_REPOSITORY,
    "github-installation/456/repository/1001",
)


class FakeMinter:
    def __init__(self, events):
        self.events = events

    def mint(self, grant):
        self.events.append(("token.mint", tuple(grant["permissions"])))
        return _InstallationToken("synthetic-token-never-used", "2026-10-08T13:00:00Z")


class FakeStdin:
    def isatty(self):
        return False


class SignedGitHubPublicationTests(unittest.TestCase):
    def setUp(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = as_unverified_local_approval_fixture(
            build_staged_artifact(request, prepared, result)
        )
        self.temporary = tempfile.TemporaryDirectory(prefix="signed-github-publication-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "stage.sqlite3"
        with SQLiteStagedArtifactStore(self.database) as store:
            store.save(artifact)
        self.process_id = artifact.payload_copy()["seed"]["process_id"]
        self.digest = artifact.staged_change_digest
        unsigned_request = build_approval_request(
            artifact,
            BINDING,
            branch="agent/process-signed-github-001",
            base_branch="master",
            approval_id="approval-signed-github-001",
            approver_id=TEST_APPROVER_ID,
            policy_version="production-policy-v1",
            now=NOW,
        )
        self.paths = {
            "request": self.root / "request.json",
            "signed": self.root / "signed.json",
            "profile": self.root / "trust.json",
            "journal": self.root / "publication.sqlite3",
            "key_reference": self.root / "unused-private-key-reference.pem",
        }
        self._write(self.paths["request"], unsigned_request)
        self._write(
            self.paths["signed"],
            {
                "schema": "signed-approval/v1",
                "approval": sign_test_approval(unsigned_request["unsigned_approval"]),
            },
        )
        profile = {
                "schema": "approval-trust-profile/v1",
                "policy_version": "production-policy-v1",
                "target": {
                    "source_repository_id": BINDING.source_repository_id,
                    "provider_repository_id": BINDING.provider_repository_id,
                },
                "allowed_repositories": [BINDING.provider_repository_id],
                "allowed_actuators": ["github-app-actuator"],
                "allowed_approver_ids": [TEST_APPROVER_ID],
                "trusted_approver_public_keys": {
                    TEST_APPROVER_ID: TEST_APPROVER_PUBLIC_KEY.hex()
                },
            }
        self._write(self.paths["profile"], profile)
        authority = Ed25519PrivateKey.generate()
        authority_id = "synthetic-publication-authority"
        public_key = authority.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.authority_keys = {authority_id: public_key}
        self.paths["enrollment"] = self.root / "enrollment.json"
        self.paths["authority_set"] = self.root / "authority-set.json"
        self.paths["enrollment"].write_bytes(build_signed_approver_trust_enrollment(
            enrollment_id="synthetic-publication-enrollment",
            authority_key_id=authority_id,
            approver_id=TEST_APPROVER_ID,
            approver_public_key=TEST_APPROVER_PUBLIC_KEY,
            trust_profile_digest=sha256_digest(profile),
            provider_repository_id=BINDING.provider_repository_id,
            signing_key=authority,
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(days=1),
        ))
        self._write(self.paths["authority_set"], {
            "schema": "control-plane-authority-key-set/v1",
            "keys": {authority_id: public_key.hex()},
        })
        self.authority_set_digest = "sha256:" + hashlib.sha256(
            self.paths["authority_set"].read_bytes()
        ).hexdigest()
        self.config = GitHubAppBrokerConfig(
            app_id=123,
            installation_id=456,
            repository_id=1001,
            repository=SOURCE_REPOSITORY,
            private_key_path=self.paths["key_reference"],
            api_url="https://api.github.com",
        )

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def _args(self, confirmation=None):
        return (
            self.database,
            self.digest,
            self.paths["request"],
            self.paths["signed"],
            self.paths["profile"],
            self.paths["journal"],
            f"PUBLISH {self.digest}" if confirmation is None else confirmation,
        )

    def _approval_kwargs(self):
        return {
            "approver_enrollment_path": self.paths["enrollment"],
            "trusted_approver_authority_keys": self.authority_keys,
        }

    def _new_observer(self, store):
        task_id = "task-signed-github-observer-fixture"
        worker = SimpleNamespace(propose=lambda _request: None)
        initial = JournaledProposalWorker(
            worker,
            store,
            process_id=self.process_id,
            task_id=task_id,
        )
        initial.propose(SimpleNamespace(process_id=self.process_id, task_id=task_id))
        initial.finish_agent_invocation(status="ok")
        run_id = initial.observer_reference()["run_id"]
        return JournaledProposalWorker.resume_existing(
            worker,
            store,
            process_id=self.process_id,
            run_id=run_id,
        )

    def _provider_patches(self, events, *, lose_pr_response=False):
        base_content = b"def add(left: int, right: int) -> int:\n    return left + right\n"
        base_blob_sha = hashlib.sha1(
            b"blob " + str(len(base_content)).encode("ascii") + b"\0" + base_content
        ).hexdigest()

        def post_json(url, _headers, payload):
            if url.endswith("/git/refs"):
                events.append(("branch.create", payload["ref"]))
                return {}
            if url.endswith("/pulls"):
                events.append(("pr.create", payload["head"], payload["base"]))
                if lose_pr_response:
                    raise OSError("synthetic lost PR response")
                return {
                    "number": 81,
                    "html_url": "https://github.com/FixtureOwner/stage-fixture/pull/81",
                    "base": {"ref": payload["base"]},
                }
            raise AssertionError("unexpected fake POST endpoint")

        def get_json(url, _headers):
            if "/contents/calculator.py?ref=" in url:
                events.append(("base.file.get", url))
                return {"type": "file", "sha": base_blob_sha}
            if "/git/ref/heads/" in url:
                events.append(("branch.get", url))
                raise FileNotFoundError
            if "/pulls?state=all&head=" in url:
                events.append(("pr.lookup", url))
                return []
            raise AssertionError("unexpected fake GET endpoint")

        def put_json(url, _headers, payload):
            events.append(("file.put", url, payload["branch"], payload["sha"]))
            return {"commit": {"sha": "c" * 40}}

        return (
            patch.object(publisher, "TARGET_REPOSITORY", SOURCE_REPOSITORY),
            patch.object(GitHubAppBrokerConfig, "from_environment", return_value=self.config),
            patch.object(publisher, "GitHubAppInstallationTokenMinter", return_value=FakeMinter(events)),
            patch.object(github_app, "_post_json", side_effect=post_json),
            patch.object(github_app, "_get_json", side_effect=get_json),
            patch.object(github_app, "_put_json", side_effect=put_json),
        )

    def test_exact_confirmation_runs_real_gate_composition_on_fake_transport(self):
        events = []
        before_inputs = {
            "database": self.database.read_bytes(),
            "request": self.paths["request"].read_bytes(),
            "signed": self.paths["signed"].read_bytes(),
            "profile": self.paths["profile"].read_bytes(),
        }
        with ExitStack() as stack:
            for active_patch in self._provider_patches(events):
                stack.enter_context(active_patch)
            result = publish_signed_stage_github(
                *self._args(), **self._approval_kwargs(), now=NOW + timedelta(seconds=1), environ={}
            )
        self.assertEqual(result["schema"], "signed-stage-github-publication/v1")
        self.assertEqual(result["status"], "pull_request_confirmed")
        self.assertNotIn("external_write", result)
        self.assertNotIn("provider_write", result)
        self.assertEqual(result["staged_change_digest"], self.digest)
        self.assertEqual(result["pull_request_id"], 81)
        self.assertEqual(result["pull_request_url"], "https://github.com/FixtureOwner/stage-fixture/pull/81")
        self.assertIs(result["identity_authenticated"], False)
        self.assertEqual(result["trust_profile_origin"], "authority_enrolled_approver_key")
        self.assertEqual(events[0][0], "token.mint")
        self.assertEqual(events[0][1], ("contents:write", "pull_requests:write"))
        event_names = [event[0] for event in events]
        self.assertEqual(event_names.count("branch.create"), 1)
        self.assertEqual(event_names.count("file.put"), 1)
        self.assertEqual(event_names.count("pr.create"), 1)
        self.assertEqual(before_inputs, {
            "database": self.database.read_bytes(),
            "request": self.paths["request"].read_bytes(),
            "signed": self.paths["signed"].read_bytes(),
            "profile": self.paths["profile"].read_bytes(),
        })
        self.assertTrue(self.paths["journal"].is_file())

    def test_observer_finishes_only_after_clean_fake_provider_receipt(self):
        events = []
        observer_path = self.root / "observer.sqlite3"
        with SQLiteObservationStore(observer_path) as store:
            observer = self._new_observer(store)
            with ExitStack() as stack:
                for active_patch in self._provider_patches(events):
                    stack.enter_context(active_patch)
                result = publish_signed_stage_github(
                    *self._args(),
                    **self._approval_kwargs(),
                    now=NOW + timedelta(seconds=1),
                    environ={},
                    observer=observer,
                )
            self.assertTrue(result["observer_run_terminal"])
            self.assertTrue(observer.publication_dispatch_completed_cleanly())
            journal = store.events()
            self.assertEqual(journal[-2]["event_type"], "agent_finished")
            self.assertEqual(journal[-2]["status"], "ok")
            self.assertEqual(journal[-1]["event_type"], "run_finished")
            self.assertEqual(journal[-1]["status"], "ok")

    def test_observer_keeps_lost_provider_response_open_as_unknown(self):
        events = []
        observer_path = self.root / "observer-unknown.sqlite3"
        with SQLiteObservationStore(observer_path) as store:
            observer = self._new_observer(store)
            with ExitStack() as stack:
                for active_patch in self._provider_patches(events, lose_pr_response=True):
                    stack.enter_context(active_patch)
                with self.assertRaises(SignedGitHubPublicationError):
                    publish_signed_stage_github(
                        *self._args(),
                        **self._approval_kwargs(),
                        now=NOW + timedelta(seconds=1),
                        environ={},
                        observer=observer,
                    )
            journal = store.events()
            terminal = [
                event for event in journal
                if event.get("decision_or_tool") == "Publication.dispatch"
                and event["event_type"] == "outcome_unknown"
            ]
            self.assertEqual(len(terminal), 1)
            self.assertFalse(observer.publication_dispatch_completed_cleanly())
            self.assertFalse(any(event["event_type"] == "run_finished" for event in journal))

    def test_invalid_observer_stops_before_provider_configuration(self):
        with patch.object(GitHubAppBrokerConfig, "from_environment") as config:
            with self.assertRaisesRegex(
                SignedGitHubPublicationError,
                "^signed GitHub publication: observer is invalid$",
            ):
                publish_signed_stage_github(
                    *self._args(),
                    **self._approval_kwargs(),
                    now=NOW + timedelta(seconds=1),
                    environ={},
                    observer=object(),
                )
        config.assert_not_called()

    def test_wrong_confirmation_stops_before_provider_configuration_or_effects(self):
        events = []
        patches = self._provider_patches(events)
        with (
            patches[0],
            patch.object(GitHubAppBrokerConfig, "from_environment") as config,
            patches[2],
            patches[3],
            patches[4],
            patches[5],
        ):
            with self.assertRaisesRegex(
                SignedGitHubPublicationError,
                "^signed GitHub publication: exact digest confirmation is required$",
            ):
                publish_signed_stage_github(
                    *self._args("PUBLISH sha256:" + "0" * 64),
                    **self._approval_kwargs(),
                    now=NOW + timedelta(seconds=1),
                    environ={},
                )
        config.assert_not_called()
        self.assertEqual(events, [])
        self.assertFalse(self.paths["journal"].exists())

    def test_policy_deny_stops_before_token_mint_and_provider_effects(self):
        events = []
        patches = self._provider_patches(events)
        with ExitStack() as stack:
            for active_patch in patches:
                stack.enter_context(active_patch)
            stack.enter_context(
                patch.object(
                    publisher.DeterministicPolicy,
                    "decide",
                    side_effect=ValueError("synthetic policy denial"),
                )
            )
            with self.assertRaises(SignedGitHubPublicationError):
                publish_signed_stage_github(
                    *self._args(), **self._approval_kwargs(), now=NOW + timedelta(seconds=1), environ={}
                )
        self.assertEqual(events, [])
        self.assertFalse(self.paths["journal"].exists())

    def test_lost_pr_response_is_not_retried(self):
        events = []
        with ExitStack() as stack:
            for active_patch in self._provider_patches(events, lose_pr_response=True):
                stack.enter_context(active_patch)
            with self.assertRaises(SignedGitHubPublicationError):
                publish_signed_stage_github(
                    *self._args(), **self._approval_kwargs(), now=NOW + timedelta(seconds=1), environ={}
                )
        event_names = [event[0] for event in events]
        self.assertEqual(event_names.count("token.mint"), 1)
        self.assertEqual(event_names.count("branch.create"), 1)
        self.assertEqual(event_names.count("file.put"), 1)
        self.assertEqual(event_names.count("pr.create"), 1)
        self.assertTrue(self.paths["journal"].is_file())

    def test_invalid_approval_stops_before_broker_construction(self):
        signed = json.loads(self.paths["signed"].read_text(encoding="utf-8"))
        signed["approval"]["signature"] = "00" * 64
        self._write(self.paths["signed"], signed)
        events = []
        with (
            patch.object(publisher, "TARGET_REPOSITORY", SOURCE_REPOSITORY),
            patch.object(GitHubAppBrokerConfig, "from_environment") as config,
            patch.object(publisher, "GitHubAppInstallationTokenMinter") as minter,
        ):
            with self.assertRaises(SignedGitHubPublicationError):
                publish_signed_stage_github(
                    *self._args(), **self._approval_kwargs(), now=NOW + timedelta(seconds=1), environ={}
                )
        config.assert_not_called()
        minter.assert_not_called()
        self.assertEqual(events, [])

    def test_authenticated_identity_claim_is_rejected_before_provider_configuration(self):
        verified = load_verified_signed_approval(
            self.database,
            self.digest,
            self.paths["request"],
            self.paths["signed"],
            self.paths["profile"],
            approver_enrollment_path=self.paths["enrollment"],
            trusted_authority_keys=self.authority_keys,
            now=NOW + timedelta(seconds=1),
        )
        forged_identity_claim = replace(
            verified,
            result={**verified.result, "identity_authenticated": True},
        )
        with (
            patch.object(
                publisher,
                "load_verified_signed_approval",
                return_value=forged_identity_claim,
            ),
            patch.object(GitHubAppBrokerConfig, "from_environment") as config,
            patch.object(publisher, "GitHubAppInstallationTokenMinter") as minter,
        ):
            with self.assertRaisesRegex(
                SignedGitHubPublicationError,
                "^signed GitHub publication: approval or target is not allowed$",
            ):
                publish_signed_stage_github(
                    *self._args(),
                    **self._approval_kwargs(),
                    now=NOW + timedelta(seconds=1),
                    environ={},
                )
        config.assert_not_called()
        minter.assert_not_called()
        self.assertFalse(self.paths["journal"].exists())

    def test_missing_enrollment_stops_before_provider_configuration(self):
        with (
            patch.object(publisher, "TARGET_REPOSITORY", SOURCE_REPOSITORY),
            patch.object(GitHubAppBrokerConfig, "from_environment") as config,
        ):
            with self.assertRaisesRegex(
                SignedGitHubPublicationError, "approver enrollment trust is required"
            ):
                publish_signed_stage_github(
                    *self._args(), now=NOW + timedelta(seconds=1), environ={}
                )
        config.assert_not_called()
        self.assertFalse(self.paths["journal"].exists())

    def test_wrong_enrollment_scope_stops_before_provider_configuration(self):
        enrollment = json.loads(self.paths["enrollment"].read_text(encoding="utf-8"))
        enrollment["provider_repository_id"] = "github-installation/999/repository/1"
        self._write(self.paths["enrollment"], enrollment)
        with (
            patch.object(publisher, "TARGET_REPOSITORY", SOURCE_REPOSITORY),
            patch.object(GitHubAppBrokerConfig, "from_environment") as config,
        ):
            with self.assertRaisesRegex(
                SignedGitHubPublicationError, "approval verification failed"
            ):
                publish_signed_stage_github(
                    *self._args(), **self._approval_kwargs(),
                    now=NOW + timedelta(seconds=1), environ={},
                )
        config.assert_not_called()
        self.assertFalse(self.paths["journal"].exists())

    def test_cli_rejects_bad_authority_pin_before_preview_or_prompt(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(GitHubAppBrokerConfig, "from_environment") as config:
            code = publication_main(
                [*(str(value) for value in self._args()[:-1]),
                 "--approver-enrollment", str(self.paths["enrollment"]),
                 "--approver-authority-key-set", str(self.paths["authority_set"]),
                 "--approver-authority-key-set-digest", "sha256:" + "0" * 64],
                now=NOW + timedelta(seconds=1),
                input_reader=lambda _: self.fail("prompt must not be reached"),
                stdout=output, stderr=errors,
            )
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("safely refused", errors.getvalue())
        config.assert_not_called()
        self.assertFalse(self.paths["journal"].exists())

    def test_cli_valid_enrollment_previews_but_wrong_phrase_stops_before_provider(self):
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(publisher, "TARGET_REPOSITORY", SOURCE_REPOSITORY),
            patch.object(GitHubAppBrokerConfig, "from_environment") as config,
        ):
            code = publication_main(
                [*(str(value) for value in self._args()[:-1]),
                 "--approver-enrollment", str(self.paths["enrollment"]),
                 "--approver-authority-key-set", str(self.paths["authority_set"]),
                 "--approver-authority-key-set-digest", self.authority_set_digest],
                now=NOW + timedelta(seconds=1),
                input_reader=lambda _: "CANCEL",
                stdout=output, stderr=errors,
            )
        self.assertEqual(code, 2)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(output.getvalue())["staged_change_digest"], self.digest)
        self.assertIn("safely refused", errors.getvalue())
        config.assert_not_called()
        self.assertFalse(self.paths["journal"].exists())

    def test_cli_non_tty_refuses_after_preview_before_provider_or_input(self):
        output, errors = io.StringIO(), io.StringIO()
        args = [
            *(str(value) for value in self._args()[:-1]),
            "--approver-enrollment", str(self.paths["enrollment"]),
            "--approver-authority-key-set", str(self.paths["authority_set"]),
            "--approver-authority-key-set-digest", self.authority_set_digest,
        ]
        with (
            patch.object(publisher, "TARGET_REPOSITORY", SOURCE_REPOSITORY),
            patch("app_contracts.signed_github_publication.sys.stdin", new=FakeStdin()),
            patch("builtins.input", side_effect=AssertionError("input must not run")) as input_call,
            patch.object(GitHubAppBrokerConfig, "from_environment") as config,
        ):
            code = publication_main(
                args,
                now=NOW + timedelta(seconds=1),
                stdout=output,
                stderr=errors,
            )

        self.assertEqual(code, 2)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(
            json.loads(output.getvalue())["staged_change_digest"], self.digest
        )
        self.assertIn("safely refused", errors.getvalue())
        input_call.assert_not_called()
        config.assert_not_called()
        self.assertFalse(self.paths["journal"].exists())


if __name__ == "__main__":
    unittest.main()
