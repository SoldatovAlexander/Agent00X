from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app_contracts.deepseek_worker import build_chat_completions_payload
from app_contracts.brainbooster_target_profile import PINNED_HTTP_DB_FAILURE_CATEGORIES
from app_contracts.digests import canonical_json, sha256_bytes, sha256_digest
from app_contracts.executor import (
    ExecutionError,
    ExecutionResult,
    ExecutionStatus,
    WorkerInput,
    WorkerTerminalOutcome,
)
from app_contracts.github_snapshot import (
    GitCommitObject,
    GitHubBlobClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
)
from app_contracts.pinned_snapshot import SNAPSHOT_DIGEST_CANONICALIZATION
from app_contracts.r5_execution import R5ExecutionError, run_r5_attempt
from app_contracts.remote_snapshot_workspace import RemoteSnapshotWorkspaceError
from app_contracts.validator import ContractValidationError
from scripts import r5_batch_selection


ROOT = Path(__file__).resolve().parents[1]
ROUTE_BYTES = (ROOT / "fixtures/experiments/r5-pinned-backend-routes.py").read_bytes()
FIXTURE_OWNER = "FixtureOwner"
FIXTURE_REPOSITORY = "r5-fixture"
FIXTURE_COMMIT = "a" * 40
FIXTURE_TREE = "b" * 40


def _snapshot():
    blob = GitHubBlobClaim(
        path="backend/routes.py",
        mode="100644",
        sha=hashlib.sha1(
            b"blob " + str(len(ROUTE_BYTES)).encode("ascii") + b"\0" + ROUTE_BYTES
        ).hexdigest(),
        size=len(ROUTE_BYTES),
        content=ROUTE_BYTES,
        content_digest=sha256_bytes(ROUTE_BYTES),
        evidence_origin="github_codeload_archive",
    )
    content_digest = sha256_digest(
        {
            "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
            "files": [
                {
                    "path": blob.path,
                    "content_digest": blob.content_digest,
                    "mode": blob.mode,
                }
            ],
        }
    )
    snapshot = GitHubSnapshotContents(
        claim=GitHubSnapshotClaim(
            owner=FIXTURE_OWNER,
            repository=FIXTURE_REPOSITORY,
            commit_oid=FIXTURE_COMMIT,
            tree_oid=FIXTURE_TREE,
            content_digest=content_digest,
            evidence_origin="github_codeload_archive",
        ),
        files=(blob,),
        verified_commit_object=GitCommitObject(FIXTURE_COMMIT, FIXTURE_TREE),
    )
    return snapshot, content_digest


def _selected(snapshot_digest: str, attempt_id: str = "R5-001"):
    worker_input = WorkerInput(
        process_id="process-r5-preregistered-study-v1",
        task_id="task-" + attempt_id.lower(),
        repository_id=f"{FIXTURE_OWNER}/{FIXTURE_REPOSITORY}",
        base_commit=FIXTURE_COMMIT,
        declared_change_paths=("backend/routes.py",),
        snapshot_tree_digest=snapshot_digest,
        snapshot_origin="github_codeload_archive",
        task_instruction="Perform the frozen synthetic task without unrelated changes.",
        context_files=(("backend/routes.py", ROUTE_BYTES.decode("utf-8")),),
        snapshot_claim_digest=snapshot_digest,
    )
    payload = build_chat_completions_payload(worker_input)
    return SimpleNamespace(
        attempt_id=attempt_id,
        scenario_id="S1-canonical-repair",
        arm_id="A",
        input_digest=sha256_bytes(canonical_json(payload)),
        worker_input=worker_input,
        casebook_digest="sha256:" + r5_batch_selection.CASEBOOK_SHA256,
        source_digest="sha256:" + r5_batch_selection.SOURCE_SHA256,
        context_digest="sha256:" + "c" * 64,
        repeat=3,
    )


class R5ExecutionTests(unittest.TestCase):
    @staticmethod
    def _collaborators():
        worker = SimpleNamespace(propose=lambda _task: None)
        verifier = SimpleNamespace(verify=lambda _request: None)
        sandbox = SimpleNamespace(create=lambda *_args, **_kwargs: None)
        stage = SimpleNamespace(
            save=lambda *_args, **_kwargs: None,
            load=lambda *_args, **_kwargs: None,
        )
        return worker, verifier, sandbox, stage

    def _profile_patches(self, snapshot_digest: str):
        return (
            patch("app_contracts.r5_execution.PINNED_OWNER", FIXTURE_OWNER),
            patch("app_contracts.r5_execution.PINNED_REPOSITORY", FIXTURE_REPOSITORY),
            patch("app_contracts.r5_execution.PINNED_COMMIT", FIXTURE_COMMIT),
            patch("app_contracts.r5_execution.PINNED_TREE", FIXTURE_TREE),
            patch("app_contracts.r5_execution.PINNED_CONTENT_DIGEST", snapshot_digest),
            patch("app_contracts.r5_execution.PINNED_FILE_COUNT", 1),
        )

    def test_delegates_exactly_once_to_shared_pinned_execution_pipeline(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        worker, verifier, sandbox, stage = self._collaborators()
        result = ExecutionResult(status=ExecutionStatus.FAILED)
        patches = self._profile_patches(content_digest)
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch(
                "app_contracts.r5_execution.run_remote_snapshot_execution",
                return_value=result,
            ) as run,
        ):
            record = run_r5_attempt(
                selected,
                snapshot,
                worker=worker,
                verifier=verifier,
                sandbox_backend=sandbox,
                stage_sink=stage,
            )

        self.assertEqual(run.call_count, 1)
        kwargs = run.call_args.kwargs
        self.assertIs(run.call_args.args[0], snapshot)
        self.assertEqual(kwargs["process_id"], selected.worker_input.process_id)
        self.assertEqual(kwargs["task_id"], selected.worker_input.task_id)
        self.assertEqual(kwargs["task_instruction"], selected.worker_input.task_instruction)
        self.assertEqual(kwargs["declared_change_paths"], ("backend/routes.py",))
        self.assertEqual(kwargs["context_files"], selected.worker_input.context_files)
        self.assertIs(kwargs["worker"], worker)
        self.assertIs(kwargs["verifier"], verifier)
        self.assertIs(kwargs["sandbox_backend"], sandbox)
        self.assertIs(kwargs["stage_sink"], stage)
        self.assertTrue(kwargs["require_durable_stage"])
        self.assertIs(record.result, result)
        self.assertEqual(record.attempt_id, "R5-001")
        self.assertNotIn("Perform the frozen", repr(record))

    def test_accepts_exact_later_preregistered_attempt(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest, "R5-006")
        worker, verifier, sandbox, stage = self._collaborators()
        result = ExecutionResult(status=ExecutionStatus.VERIFIED)
        profile_patches = self._profile_patches(content_digest)
        with (
            profile_patches[0], profile_patches[1], profile_patches[2],
            profile_patches[3], profile_patches[4], profile_patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ) as select_attempts,
            patch(
                "app_contracts.r5_execution.run_remote_snapshot_execution",
                return_value=result,
            ) as run,
        ):
            record = run_r5_attempt(
                selected,
                snapshot,
                worker=worker,
                verifier=verifier,
                sandbox_backend=sandbox,
                stage_sink=stage,
            )

        select_attempts.assert_called_once_with(("R5-006",))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(record.attempt_id, "R5-006")
        self.assertIs(record.result, result)

    def test_fixed_invalid_worker_proposal_errors_become_known_failure(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        fixed_errors = (
            "execution proposal: shape is invalid",
            "execution proposal: scope is invalid",
            "execution proposal: content is invalid",
            "execution proposal: limits exceeded",
        )
        profile_patches = self._profile_patches(content_digest)
        for message in fixed_errors:
            with (
                self.subTest(message=message),
                profile_patches[0], profile_patches[1], profile_patches[2],
                profile_patches[3], profile_patches[4], profile_patches[5],
                patch(
                    "app_contracts.r5_execution.select_r5_attempts",
                    return_value=(selected,),
                ),
                patch(
                    "app_contracts.r5_execution.run_remote_snapshot_execution",
                    side_effect=ExecutionError(message),
                ) as run,
            ):
                record = run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )

            self.assertEqual(run.call_count, 1)
            self.assertEqual(record.result.status, ExecutionStatus.FAILED)
            self.assertEqual(record.result.failure_code, "worker-proposal-invalid")
            self.assertEqual(record.result.snapshot_tree_digest, content_digest)
            self.assertEqual(record.result.snapshot_origin, "github_codeload_archive")
            self.assertNotIn(message, repr(record))

    def test_unexpected_execution_error_remains_sanitized_unknown(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        profile_patches = self._profile_patches(content_digest)
        marker = "private-unexpected-execution-canary"
        with (
            profile_patches[0], profile_patches[1], profile_patches[2],
            profile_patches[3], profile_patches[4], profile_patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch(
                "app_contracts.r5_execution.run_remote_snapshot_execution",
                side_effect=ExecutionError(marker),
            ),
        ):
            with self.assertRaises(R5ExecutionError) as raised:
                run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )

        self.assertEqual(
            str(raised.exception),
            "R5 execution: fixed inputs or pipeline rejected",
        )
        self.assertEqual(
            raised.exception.reason_code, "executor-marker-unmapped"
        )
        self.assertNotIn(marker, str(raised.exception))

    def test_non_execution_exception_keeps_executor_uncaught_fallback(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        profile_patches = self._profile_patches(content_digest)
        with (
            profile_patches[0], profile_patches[1], profile_patches[2],
            profile_patches[3], profile_patches[4], profile_patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch(
                "app_contracts.r5_execution.run_remote_snapshot_execution",
                side_effect=LookupError("private runtime detail"),
            ),
        ):
            with self.assertRaises(R5ExecutionError) as raised:
                run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )

        self.assertEqual(raised.exception.reason_code, "executor-uncaught-error")
        self.assertNotIn("private runtime detail", str(raised.exception))

    def test_exact_builtin_exception_types_have_fixed_codes(self) -> None:
        cases = (
            (ValueError, "executor-value-error"),
            (TypeError, "executor-type-error"),
            (OSError, "executor-os-error"),
            (RuntimeError, "executor-runtime-error"),
            (KeyError, "executor-key-error"),
            (AttributeError, "executor-attribute-error"),
        )
        snapshot, content_digest = _snapshot()
        for error_type, reason_code in cases:
            selected = _selected(content_digest)
            profile_patches = self._profile_patches(content_digest)
            with (
                self.subTest(reason_code=reason_code),
                profile_patches[0], profile_patches[1], profile_patches[2],
                profile_patches[3], profile_patches[4], profile_patches[5],
                patch(
                    "app_contracts.r5_execution.select_r5_attempts",
                    return_value=(selected,),
                ),
                patch(
                    "app_contracts.r5_execution.run_remote_snapshot_execution",
                    side_effect=error_type("private builtin detail"),
                ),
            ):
                with self.assertRaises(R5ExecutionError) as raised:
                    run_r5_attempt(
                        selected,
                        snapshot,
                        worker=self._collaborators()[0],
                        verifier=self._collaborators()[1],
                        sandbox_backend=self._collaborators()[2],
                        stage_sink=self._collaborators()[3],
                    )
            self.assertEqual(raised.exception.reason_code, reason_code)
            self.assertNotIn("private builtin detail", str(raised.exception))

    def test_builtin_exception_subclass_keeps_generic_executor_fallback(self) -> None:
        class CustomRuntimeError(RuntimeError):
            pass

        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        profile_patches = self._profile_patches(content_digest)
        with (
            profile_patches[0], profile_patches[1], profile_patches[2],
            profile_patches[3], profile_patches[4], profile_patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch(
                "app_contracts.r5_execution.run_remote_snapshot_execution",
                side_effect=CustomRuntimeError("private subclass detail"),
            ),
        ):
            with self.assertRaises(R5ExecutionError) as raised:
                run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )

        self.assertEqual(raised.exception.reason_code, "executor-uncaught-error")
        self.assertNotIn("private subclass detail", str(raised.exception))

    def test_exact_workspace_error_has_fixed_code_and_unlisted_subclass_stays_generic(self) -> None:
        class UnlistedValueError(ValueError):
            pass

        snapshot, content_digest = _snapshot()
        cases = (
            (
                RemoteSnapshotWorkspaceError("private workspace detail"),
                "executor-workspace-error",
            ),
            (
                ContractValidationError("private contract detail"),
                "executor-contract-invalid",
            ),
            (
                UnlistedValueError("private custom value detail"),
                "executor-uncaught-error",
            ),
        )
        for error, reason_code in cases:
            selected = _selected(content_digest)
            profile_patches = self._profile_patches(content_digest)
            with (
                self.subTest(reason_code=reason_code),
                profile_patches[0], profile_patches[1], profile_patches[2],
                profile_patches[3], profile_patches[4], profile_patches[5],
                patch(
                    "app_contracts.r5_execution.select_r5_attempts",
                    return_value=(selected,),
                ),
                patch(
                    "app_contracts.r5_execution.run_remote_snapshot_execution",
                    side_effect=error,
                ),
            ):
                with self.assertRaises(R5ExecutionError) as raised:
                    run_r5_attempt(
                        selected,
                        snapshot,
                        worker=self._collaborators()[0],
                        verifier=self._collaborators()[1],
                        sandbox_backend=self._collaborators()[2],
                        stage_sink=self._collaborators()[3],
                    )
            self.assertEqual(raised.exception.reason_code, reason_code)
            self.assertNotIn("private", str(raised.exception))

    def test_fixed_target_test_failure_categories_become_redacted_failed_results(self) -> None:
        categories = (
            ("readiness-exit", "target-test-readiness-exit"),
            ("readiness-timeout", "target-test-readiness-timeout"),
            ("malformed-status", "target-test-malformed-status"),
            ("malformed-no-write", "target-test-malformed-no-write"),
            ("overflow-status", "target-test-overflow-status"),
            ("overflow-no-write", "target-test-overflow-no-write"),
            ("sqlite-range-status", "target-test-sqlite-range-status"),
            ("sqlite-range-no-write", "target-test-sqlite-range-no-write"),
            ("valid-status", "target-test-valid-status"),
            ("valid-body", "target-test-valid-body"),
            ("valid-row", "target-test-valid-row"),
            ("allowlisted-tests-failed", "target-tests-failed"),
        ) + tuple(
            (category, "target-test-" + category)
            for category in sorted(PINNED_HTTP_DB_FAILURE_CATEGORIES)
        )
        snapshot, content_digest = _snapshot()
        for number, (category, reason_code) in enumerate(categories, start=1):
            selected = _selected(content_digest, f"R5-{number:03d}")
            profile_patches = self._profile_patches(content_digest)
            private_detail = "verification failed; staged change was not created: " + category
            with (
                self.subTest(category=category),
                profile_patches[0], profile_patches[1], profile_patches[2],
                profile_patches[3], profile_patches[4], profile_patches[5],
                patch(
                    "app_contracts.r5_execution.select_r5_attempts",
                    return_value=(selected,),
                ),
                patch(
                    "app_contracts.r5_execution.run_remote_snapshot_execution",
                    side_effect=ContractValidationError(private_detail),
                ) as run,
            ):
                record = run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )
            self.assertEqual(run.call_count, 1)
            self.assertIs(record.result.status, ExecutionStatus.FAILED)
            self.assertEqual(record.result.failure_code, reason_code)
            self.assertEqual(record.result.snapshot_tree_digest, content_digest)
            self.assertEqual(record.result.snapshot_origin, "github_codeload_archive")
            self.assertNotIn(category, repr(record))
            self.assertNotIn("verification failed", repr(record))

    def test_unrecognized_target_test_marker_stays_unknown_and_redacted(self) -> None:
        messages = (
            "verification failed; staged change was not created: private-token",
            "prefix verification failed; staged change was not created: valid-row",
            "verification failed; staged change was not created: valid-row token=SECRET",
        )
        snapshot, content_digest = _snapshot()
        for message in messages:
            selected = _selected(content_digest)
            profile_patches = self._profile_patches(content_digest)
            with (
                self.subTest(message=message),
                profile_patches[0], profile_patches[1], profile_patches[2],
                profile_patches[3], profile_patches[4], profile_patches[5],
                patch(
                    "app_contracts.r5_execution.select_r5_attempts",
                    return_value=(selected,),
                ),
                patch(
                    "app_contracts.r5_execution.run_remote_snapshot_execution",
                    side_effect=ContractValidationError(message),
                ),
            ):
                with self.assertRaises(R5ExecutionError) as raised:
                    run_r5_attempt(
                        selected,
                        snapshot,
                        worker=self._collaborators()[0],
                        verifier=self._collaborators()[1],
                        sandbox_backend=self._collaborators()[2],
                        stage_sink=self._collaborators()[3],
                    )
            self.assertEqual(raised.exception.reason_code, "executor-contract-invalid")
            self.assertNotIn("SECRET", str(raised.exception))
            self.assertNotIn("private-token", str(raised.exception))

    def test_exact_preparation_contract_markers_are_classified_without_text(self) -> None:
        snapshot, content_digest = _snapshot()
        worker_failures = (
            "change proposal is empty",
            "change proposal is malformed",
            "change proposal has invalid path",
            "proposed content is unchanged: backend/routes.py",
            "generated patch is empty",
        )
        for message in worker_failures:
            selected = _selected(content_digest)
            profile_patches = self._profile_patches(content_digest)
            with (
                self.subTest(kind="worker-proposal-invalid"),
                profile_patches[0], profile_patches[1], profile_patches[2],
                profile_patches[3], profile_patches[4], profile_patches[5],
                patch(
                    "app_contracts.r5_execution.select_r5_attempts",
                    return_value=(selected,),
                ),
                patch(
                    "app_contracts.r5_execution.run_remote_snapshot_execution",
                    side_effect=ContractValidationError(message),
                ),
            ):
                record = run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )
            self.assertIs(record.result.status, ExecutionStatus.FAILED)
            self.assertEqual(record.result.failure_code, "worker-proposal-invalid")
            self.assertNotIn(message, repr(record))

        selected = _selected(content_digest)
        profile_patches = self._profile_patches(content_digest)
        with (
            profile_patches[0], profile_patches[1], profile_patches[2],
            profile_patches[3], profile_patches[4], profile_patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch(
                "app_contracts.r5_execution.run_remote_snapshot_execution",
                side_effect=ContractValidationError("test result is malformed"),
            ),
        ):
            with self.assertRaises(R5ExecutionError) as raised:
                run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )
        self.assertEqual(
            raised.exception.reason_code, "executor-test-result-malformed"
        )
        self.assertNotIn("PRIVATE", str(raised.exception))

    def test_invalid_executor_result_has_fixed_result_phase(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        profile_patches = self._profile_patches(content_digest)
        with (
            profile_patches[0], profile_patches[1], profile_patches[2],
            profile_patches[3], profile_patches[4], profile_patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch(
                "app_contracts.r5_execution.run_remote_snapshot_execution",
                return_value=object(),
            ),
        ):
            with self.assertRaises(R5ExecutionError) as raised:
                run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )

        self.assertEqual(raised.exception.reason_code, "result-validation-error")
        self.assertEqual(
            str(raised.exception),
            "R5 execution: fixed inputs or pipeline rejected",
        )

    def test_exact_fixed_executor_errors_map_to_redacted_categories(self) -> None:
        cases = (
            ("execution request: worker input is invalid", "executor-request-rejected"),
            ("execution worker: result is invalid", "executor-worker-rejected"),
            ("execution sandbox: session is invalid", "executor-sandbox-rejected"),
            ("execution snapshot: claim mismatch", "executor-snapshot-rejected"),
            ("execution preparation: pinned base mismatch", "executor-preparation-rejected"),
            ("execution verifier replay: pinned tree mismatch", "executor-verifier-rejected"),
            ("execution stage: durable sink is required", "executor-stage-rejected"),
        )
        snapshot, content_digest = _snapshot()
        for message, reason_code in cases:
            selected = _selected(content_digest)
            patches = self._profile_patches(content_digest)
            with (
                self.subTest(reason_code=reason_code),
                patches[0], patches[1], patches[2],
                patches[3], patches[4], patches[5],
                patch(
                    "app_contracts.r5_execution.select_r5_attempts",
                    return_value=(selected,),
                ),
                patch(
                    "app_contracts.r5_execution.run_remote_snapshot_execution",
                    side_effect=ExecutionError(message),
                ),
            ):
                with self.assertRaises(R5ExecutionError) as raised:
                    run_r5_attempt(
                        selected,
                        snapshot,
                        worker=self._collaborators()[0],
                        verifier=self._collaborators()[1],
                        sandbox_backend=self._collaborators()[2],
                        stage_sink=self._collaborators()[3],
                    )
            self.assertEqual(raised.exception.reason_code, reason_code)
            self.assertNotIn(message, str(raised.exception))

    def test_rejects_snapshot_or_worker_input_mismatch_before_pipeline(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        patches = self._profile_patches("sha256:" + "0" * 64)
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch("app_contracts.r5_execution.run_remote_snapshot_execution") as run,
        ):
            with self.assertRaises(R5ExecutionError) as raised:
                run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )
            self.assertEqual(raised.exception.reason_code, "input-validation-error")
            run.assert_not_called()

    def test_rejects_stale_rest_origin_before_pipeline(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        snapshot = replace(
            snapshot,
            claim=replace(snapshot.claim, evidence_origin="github_rest_api_claim"),
            files=(
                replace(snapshot.files[0], evidence_origin="github_rest_api_claim"),
            ),
        )
        patches = self._profile_patches(content_digest)
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch("app_contracts.r5_execution.run_remote_snapshot_execution") as run,
        ):
            with self.assertRaises(R5ExecutionError):
                run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )
        run.assert_not_called()

    def test_rejects_wrong_input_digest_before_pipeline(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        selected.input_digest = "sha256:" + "0" * 64
        patches = self._profile_patches(content_digest)
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
            patch(
                "app_contracts.r5_execution.select_r5_attempts",
                return_value=(selected,),
            ),
            patch("app_contracts.r5_execution.run_remote_snapshot_execution") as run,
        ):
            with self.assertRaises(R5ExecutionError):
                run_r5_attempt(
                    selected,
                    snapshot,
                    worker=self._collaborators()[0],
                    verifier=self._collaborators()[1],
                    sandbox_backend=self._collaborators()[2],
                    stage_sink=self._collaborators()[3],
                )
            run.assert_not_called()

    def test_terminal_worker_outcomes_stop_before_target_verifier_and_stage(self) -> None:
        snapshot, content_digest = _snapshot()
        selected = _selected(content_digest)
        for outcome, reason in (
            ("clarification_required", "conflicting_requirements"),
            ("blocked", "target_test_outcome_unknown"),
            ("denied", "publication_not_authorized"),
        ):
            calls = []
            patches = self._profile_patches(content_digest)

            class Session:
                def __init__(self, path):
                    self.snapshot = path
                    self.workspace = path

                def run(self, *_args, **_kwargs):
                    calls.append("target-test")
                    raise AssertionError("terminal result must stop before target tests")

                def close(self):
                    calls.append("sandbox.close")

            class Backend:
                def create(self, path, _allowed_commands):
                    calls.append("sandbox.create")
                    return Session(path)

            class Worker:
                def propose(self, _task):
                    calls.append("worker.propose")
                    return WorkerTerminalOutcome(outcome, reason)

            class Verifier:
                def verify(self, _request):
                    calls.append("verifier")
                    raise AssertionError("terminal result must stop before verifier")

            class StageSink:
                def save(self, _artifact):
                    calls.append("stage.save")
                    raise AssertionError("terminal result must not stage")

                def load(self, _digest):
                    calls.append("stage.load")
                    raise AssertionError("terminal result must not read back stage")

            with (
                patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
                patch(
                    "app_contracts.r5_execution.select_r5_attempts",
                    return_value=(selected,),
                ),
            ):
                record = run_r5_attempt(
                    selected,
                    snapshot,
                    worker=Worker(),
                    verifier=Verifier(),
                    sandbox_backend=Backend(),
                    stage_sink=StageSink(),
                )

            self.assertEqual(record.result.status, ExecutionStatus.FAILED)
            self.assertEqual(record.result.worker_terminal_outcome, outcome)
            self.assertEqual(
                calls, ["sandbox.create", "worker.propose", "sandbox.close"]
            )


if __name__ == "__main__":
    unittest.main()
