"""Compose an already-validated remote snapshot through the generic executor.

This module deliberately has no Worker, credential, approval, or publication
adapter imports. Callers inject the bounded proposal, sandbox, verifier and
stage sink explicitly.
"""

from __future__ import annotations

from .executor import ExecutionRequest, ExecutionResult, run_local_execution
from .github_snapshot import GitHubBlobClaim, GitHubSnapshotContents
from .remote_snapshot_workspace import materialize_github_snapshot


def run_remote_snapshot_execution(
    snapshot: object,
    *,
    process_id: str,
    task_id: str,
    task_instruction: str,
    declared_change_paths: tuple[str, ...],
    allowed_commands: frozenset[str],
    test_command: tuple[str, ...],
    worker: object,
    verifier: object,
    sandbox_backend: object,
    context_files: tuple[tuple[str, str], ...] = (),
    test_timeout_seconds: int = 30,
    stage_sink: object | None = None,
    require_durable_stage: bool = True,
    observation_store: object | None = None,
) -> ExecutionResult:
    """Run one exact snapshot through an injected Worker/verifier boundary.

    The snapshot workspace lease is always closed, including executor errors.
    Durable exact-digest stage readback is required by default; synthetic tests
    must opt out explicitly.
    """
    if type(require_durable_stage) is not bool:
        raise ValueError("remote CLI request is invalid")
    if require_durable_stage and stage_sink is None:
        raise ValueError("remote CLI durable stage is required")
    if stage_sink is not None and (
        not callable(getattr(stage_sink, "save", None))
        or not callable(getattr(stage_sink, "load", None))
    ):
        raise ValueError("remote CLI durable stage is invalid")

    try:
        if type(snapshot) is not GitHubSnapshotContents or type(snapshot.files) is not tuple:
            raise ValueError()
        if any(type(blob) is not GitHubBlobClaim for blob in snapshot.files):
            raise ValueError()
        available_paths = {blob.path for blob in snapshot.files}
        if (
            type(declared_change_paths) is not tuple
            or not declared_change_paths
            or any(type(path) is not str or path not in available_paths for path in declared_change_paths)
            or declared_change_paths != tuple(sorted(declared_change_paths))
            or len(declared_change_paths) != len(set(declared_change_paths))
        ):
            raise ValueError()
    except Exception:
        raise ValueError("remote CLI request is invalid") from None

    with materialize_github_snapshot(snapshot) as workspace:
        claim = workspace.snapshot.claim
        request = ExecutionRequest(
            process_id=process_id,
            task_id=task_id,
            repository_id=f"{claim.owner}/{claim.repository}",
            base_commit=claim.commit_oid,
            snapshot_path=workspace.path,
            allowed_commands=allowed_commands,
            declared_change_paths=declared_change_paths,
            test_command=test_command,
            test_timeout_seconds=test_timeout_seconds,
            task_instruction=task_instruction,
            context_files=context_files,
            remote_snapshot=workspace.snapshot,
            remote_workspace=workspace,
        )
        execution_options = {
            "verifier": verifier,
            "sandbox_backend": sandbox_backend,
            "stage_sink": stage_sink,
            "require_durable_stage": require_durable_stage,
        }
        if observation_store is not None:
            execution_options["observation_store"] = observation_store
        result = run_local_execution(request, worker, **execution_options)
        if type(result) is not ExecutionResult:
            raise ValueError("remote CLI execution result is invalid")
        return result
