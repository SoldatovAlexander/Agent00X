"""Compose one validated R5 WorkerInput through the existing execution spine.

The caller injects the pinned snapshot and bounded collaborators. This module
adds no model, credential, network, approval, publication, or Docker creation
capability of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from .brainbooster_target_profile import (
    PINNED_COMMIT,
    PINNED_CONTENT_DIGEST,
    PINNED_FILE_COUNT,
    PINNED_HTTP_DB_TEST_COMMAND,
    PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
)
from .deepseek_worker import build_chat_completions_payload
from .digests import canonical_json, sha256_bytes
from .executor import ExecutionError, ExecutionResult, ExecutionStatus, WorkerInput
from .github_snapshot import (
    GitCommitObject,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
)
from .remote_snapshot_pipeline import run_remote_snapshot_execution
from .remote_snapshot_workspace import RemoteSnapshotWorkspaceError
from .repository_process import SAFE_TARGET_TEST_FAILURE_CODES
from .validator import ContractValidationError
from .observer_runtime import JournaledProposalWorker, WorkerJournalError
from scripts.r5_batch_selection import select_r5_attempts


_ATTEMPT_ID = re.compile(r"R5-(?:00[1-9]|0[1-9][0-9]|100)\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CHANGE_PATH = "backend/routes.py"
_ALLOWED_COMMANDS = frozenset({"python3"})
_PROCESS_ID = "process-r5-preregistered-study-v1"
_SOURCE_DIGEST = "sha256:32847307337ab9e9f02bec60c69ed1b581206f453f6d6f59ef6ea15938de1cf7"
_INVALID_PROPOSAL_ERRORS = frozenset(
    {
        "execution proposal: shape is invalid",
        "execution proposal: scope is invalid",
        "execution proposal: content is invalid",
        "execution proposal: limits exceeded",
    }
)
R5_UNKNOWN_PHASE_CODES = frozenset(
    {
        "input-validation-error",
        "executor-uncaught-error",
        "result-validation-error",
        "executor-request-rejected",
        "executor-worker-rejected",
        "executor-sandbox-rejected",
        "executor-snapshot-rejected",
        "executor-preparation-rejected",
        "executor-verifier-rejected",
        "executor-stage-rejected",
        "executor-marker-unmapped",
        "executor-value-error",
        "executor-type-error",
        "executor-os-error",
        "executor-runtime-error",
        "executor-key-error",
        "executor-attribute-error",
        "executor-workspace-error",
        "executor-contract-invalid",
        "executor-test-result-malformed",
    }
)
_TARGET_TEST_FAILURE_PREFIX = (
    "verification failed; staged change was not created: "
)
_TARGET_TEST_FAILURE_REASON_CODES = {
    "readiness-exit": "target-test-readiness-exit",
    "readiness-timeout": "target-test-readiness-timeout",
    "malformed-status": "target-test-malformed-status",
    "malformed-no-write": "target-test-malformed-no-write",
    "overflow-status": "target-test-overflow-status",
    "overflow-no-write": "target-test-overflow-no-write",
    "sqlite-range-status": "target-test-sqlite-range-status",
    "sqlite-range-no-write": "target-test-sqlite-range-no-write",
    "valid-status": "target-test-valid-status",
    "valid-body": "target-test-valid-body",
    "valid-row": "target-test-valid-row",
    "allowlisted-tests-failed": "target-tests-failed",
}
_WORKER_PREPARATION_FAILURE_MESSAGES = frozenset(
    {
        "change proposal is empty",
        "change proposal is malformed",
        "change proposal has invalid path",
        "proposed content is unchanged: backend/routes.py",
        "generated patch is empty",
    }
)
_CONTRACT_VALIDATION_UNKNOWN_MESSAGES = {
    "test result is malformed": "executor-test-result-malformed",
}
_EXECUTION_ERROR_REASON_CODES = {
    **{
        message: "executor-request-rejected"
        for message in (
            "execution request: worker input is invalid",
            "execution request: type is invalid",
            "execution request: pinned snapshot mode is invalid",
            "execution request: durable stage mode is invalid",
            "execution request: pinned snapshot is required",
            "execution sandbox: explicit remote backend is required",
            "execution worker: collaborator is invalid",
            "execution verifier: collaborator is invalid",
            "execution verifier: collaborator is aliased",
            "execution request: identity field is invalid",
            "execution request: snapshot path is invalid",
            "execution request: pinned snapshot binding is invalid",
            "execution request: remote snapshot binding is invalid",
            "execution request: remote snapshot is invalid",
            "execution request: remote snapshot workspace is invalid",
            "execution request: remote snapshot workspace binding is invalid",
            "execution request: command allowlist is invalid",
            "execution request: declared paths are invalid",
            "execution request: test command is invalid",
            "execution request: test timeout is invalid",
        )
    },
    **{
        message: "executor-worker-rejected"
        for message in (
            "execution worker: result is invalid",
        )
    },
    **{
        message: "executor-sandbox-rejected"
        for message in (
            "execution sandbox: backend is invalid",
            "execution sandbox: session is invalid",
        )
    },
    **{
        message: "executor-snapshot-rejected"
        for message in (
            "execution snapshot: digest check failed",
            "execution snapshot: digest mismatch",
            "execution snapshot: claim mismatch",
        )
    },
    **{
        message: "executor-preparation-rejected"
        for message in (
            "execution preparation: binding mismatch",
            "execution preparation: verified contents are missing",
            "execution preparation: pinned snapshot is missing",
            "execution preparation: pinned source changed",
            "execution preparation: pinned artifact binding mismatch",
            "execution preparation: pinned source binding mismatch",
            "execution preparation: pinned base mismatch",
        )
    },
    **{
        message: "executor-verifier-rejected"
        for message in (
            "execution verifier input: prepared scope is invalid",
            "execution verifier input: limits exceeded",
            "execution verifier input: snapshot binding is invalid",
            "execution verifier input: pinned snapshot is invalid",
            "execution verifier replay: snapshot binding is required",
            "execution verifier replay: snapshot binding is invalid",
            "execution verifier replay: session is invalid",
            "execution verifier replay: pinned tree mismatch",
            "execution verifier replay: prepared path is invalid",
            "execution verifier replay: command failed",
            "execution verifier replay: remote claim is invalid",
            "execution verifier: result shape is invalid",
            "execution verifier: result binding mismatch",
        )
    },
    **{
        message: "executor-stage-rejected"
        for message in (
            "execution stage: durable sink is required",
            "execution stage: durable sink is invalid",
        )
    },
}
_BUILTIN_EXCEPTION_REASON_CODES = {
    ValueError: "executor-value-error",
    TypeError: "executor-type-error",
    OSError: "executor-os-error",
    RuntimeError: "executor-runtime-error",
    KeyError: "executor-key-error",
    AttributeError: "executor-attribute-error",
}


class R5ExecutionError(ValueError):
    """A fixed, redacted error for invalid R5 execution inputs."""

    def __init__(self, reason_code: str = "pipeline-error") -> None:
        self.reason_code = (
            reason_code
            if type(reason_code) is str and reason_code in R5_UNKNOWN_PHASE_CODES
            else "pipeline-error"
        )
        super().__init__("R5 execution: fixed inputs or pipeline rejected")


@dataclass(frozen=True, repr=False)
class R5ExecutionRecord:
    attempt_id: str
    input_digest: str
    result: ExecutionResult = field(repr=False, compare=False)

    def __repr__(self) -> str:
        return (
            "R5ExecutionRecord("
            f"attempt_id={self.attempt_id!r}, input_digest={self.input_digest!r}, "
            f"status={self.result.status.value!r})"
        )


def run_r5_attempt(
    selected_attempt: object,
    snapshot: object,
    *,
    worker: object,
    verifier: object,
    sandbox_backend: object,
    stage_sink: object,
    observation_store: object | None = None,
) -> R5ExecutionRecord:
    try:
        record = _run_r5_attempt_impl(
            selected_attempt,
            snapshot,
            worker=worker,
            verifier=verifier,
            sandbox_backend=sandbox_backend,
            stage_sink=stage_sink,
            observation_store=observation_store,
        )
    except Exception:
        _finish_r5_invocation(worker, status="failed")
        raise
    status = "ok" if record.result.status is ExecutionStatus.VERIFIED else "failed"
    _finish_r5_invocation(worker, status=status)
    return record


def _finish_r5_invocation(worker: object, *, status: str) -> None:
    if type(worker) is JournaledProposalWorker:
        try:
            worker.finish_agent_invocation(status=status)
        except WorkerJournalError:
            # Pending/unknown work is deliberately left open for Control Plane review.
            pass


def _run_r5_attempt_impl(
    selected_attempt: object,
    snapshot: object,
    *,
    worker: object,
    verifier: object,
    sandbox_backend: object,
    stage_sink: object,
    observation_store: object | None = None,
) -> R5ExecutionRecord:
    """Run one already-selected input once through the shared executor path."""

    reason_code = "input-validation-error"
    try:
        attempt_id = getattr(selected_attempt, "attempt_id", None)
        scenario_id = getattr(selected_attempt, "scenario_id", None)
        arm_id = getattr(selected_attempt, "arm_id", None)
        input_digest = getattr(selected_attempt, "input_digest", None)
        worker_input = getattr(selected_attempt, "worker_input", None)
        if (
            type(attempt_id) is not str
            or _ATTEMPT_ID.fullmatch(attempt_id) is None
            or type(scenario_id) is not str
            or type(arm_id) is not str
            or type(input_digest) is not str
            or _DIGEST.fullmatch(input_digest) is None
            or type(worker_input) is not WorkerInput
            or type(snapshot) is not GitHubSnapshotContents
            or not callable(getattr(worker, "propose", None))
            or not callable(getattr(verifier, "verify", None))
            or not callable(getattr(sandbox_backend, "create", None))
            or not callable(getattr(stage_sink, "save", None))
            or not callable(getattr(stage_sink, "load", None))
        ):
            raise ValueError

        scheduled = select_r5_attempts((attempt_id,))[0]
        if selected_attempt != scheduled or worker_input != scheduled.worker_input:
            raise ValueError

        payload = build_chat_completions_payload(worker_input)
        actual_input_digest = sha256_bytes(canonical_json(payload))
        user_content = payload["messages"][1]["content"]
        source = next(
            blob.content
            for blob in snapshot.files
            if blob.path == _CHANGE_PATH
        )
        claim = snapshot.claim
        if (
            actual_input_digest != input_digest
            or worker_input.process_id != _PROCESS_ID
            or worker_input.task_id != "task-" + attempt_id.lower()
            or worker_input.repository_id != f"{PINNED_OWNER}/{PINNED_REPOSITORY}"
            or worker_input.base_commit != PINNED_COMMIT
            or worker_input.declared_change_paths != (_CHANGE_PATH,)
            or worker_input.snapshot_tree_digest != PINNED_CONTENT_DIGEST
            or worker_input.snapshot_claim_digest != PINNED_CONTENT_DIGEST
            or worker_input.snapshot_origin != "github_codeload_archive"
            or len(worker_input.context_files) != 1
            or worker_input.context_files[0][0] != _CHANGE_PATH
            or type(source) is not bytes
            or sha256_bytes(source) != _SOURCE_DIGEST
            or worker_input.context_files[0][1].encode("utf-8") != source
            or type(claim) is not GitHubSnapshotClaim
            or claim.owner != PINNED_OWNER
            or claim.repository != PINNED_REPOSITORY
            or claim.commit_oid != PINNED_COMMIT
            or claim.tree_oid != PINNED_TREE
            or claim.content_digest != PINNED_CONTENT_DIGEST
            or claim.evidence_origin != "github_codeload_archive"
            or not claim.full_snapshot
            or len(snapshot.files) != PINNED_FILE_COUNT
            or type(snapshot.verified_commit_object) is not GitCommitObject
            or snapshot.verified_commit_object.commit_oid != PINNED_COMMIT
            or snapshot.verified_commit_object.tree_oid != PINNED_TREE
            or attempt_id in user_content
            or scenario_id in user_content
            or "arm_id" in user_content
        ):
            raise ValueError
        if observation_store is not None and (
            not callable(getattr(observation_store, "append", None))
            or not callable(getattr(observation_store, "events", None))
            or not callable(getattr(observation_store, "record_checkpoint", None))
        ):
            raise ValueError

        reason_code = "executor-uncaught-error"
        try:
            result = run_remote_snapshot_execution(
                snapshot,
                process_id=worker_input.process_id,
                task_id=worker_input.task_id,
                task_instruction=worker_input.task_instruction,
                declared_change_paths=worker_input.declared_change_paths,
                allowed_commands=_ALLOWED_COMMANDS,
                test_command=PINNED_HTTP_DB_TEST_COMMAND,
                worker=worker,
                verifier=verifier,
                sandbox_backend=sandbox_backend,
                context_files=worker_input.context_files,
                test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                stage_sink=stage_sink,
                require_durable_stage=True,
                observation_store=observation_store,
            )
        except ExecutionError as exc:
            if type(exc) is not ExecutionError:
                raise
            message = str(exc)
            if message in _INVALID_PROPOSAL_ERRORS:
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    snapshot_tree_digest=claim.content_digest,
                    snapshot_origin=claim.evidence_origin,
                    failure_code="worker-proposal-invalid",
                )
            else:
                mapped_reason_code = _EXECUTION_ERROR_REASON_CODES.get(message)
                if mapped_reason_code is None:
                    raise
                raise R5ExecutionError(mapped_reason_code) from None
        except ContractValidationError as exc:
            if type(exc) is not ContractValidationError:
                raise
            message = str(exc)
            failure_reason = None
            if message.startswith(_TARGET_TEST_FAILURE_PREFIX):
                category = message.removeprefix(_TARGET_TEST_FAILURE_PREFIX)
                failure_reason = _TARGET_TEST_FAILURE_REASON_CODES.get(category)
                if failure_reason is None:
                    candidate_reason = "target-test-" + category
                    if candidate_reason in SAFE_TARGET_TEST_FAILURE_CODES:
                        failure_reason = candidate_reason
            if failure_reason is not None:
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    snapshot_tree_digest=claim.content_digest,
                    snapshot_origin=claim.evidence_origin,
                    failure_code=failure_reason,
                )
            elif message in _WORKER_PREPARATION_FAILURE_MESSAGES:
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    snapshot_tree_digest=claim.content_digest,
                    snapshot_origin=claim.evidence_origin,
                    failure_code="worker-proposal-invalid",
                )
            elif message in _CONTRACT_VALIDATION_UNKNOWN_MESSAGES:
                raise R5ExecutionError(
                    _CONTRACT_VALIDATION_UNKNOWN_MESSAGES[message]
                ) from None
            else:
                raise
        reason_code = "result-validation-error"
        if type(result) is not ExecutionResult:
            raise ValueError
        return R5ExecutionRecord(attempt_id, input_digest, result)
    except R5ExecutionError:
        raise
    except ExecutionError:
        if reason_code == "executor-uncaught-error":
            raise R5ExecutionError("executor-marker-unmapped") from None
        raise R5ExecutionError(reason_code) from None
    except Exception as exc:
        if reason_code == "executor-uncaught-error":
            if type(exc) is RemoteSnapshotWorkspaceError:
                reason_code = "executor-workspace-error"
            elif type(exc) is ContractValidationError:
                reason_code = "executor-contract-invalid"
            else:
                reason_code = _BUILTIN_EXCEPTION_REASON_CODES.get(
                    type(exc), reason_code
                )
        raise R5ExecutionError(reason_code) from None
