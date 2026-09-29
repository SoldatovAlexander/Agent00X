"""Typed records for the local, preparation-only execution spine.

These records do not represent an LLM worker, verified remote snapshot, approval,
or publication capability. Validation and orchestration are added separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import posixpath
from typing import Protocol, runtime_checkable

from .repository_process import prepare_change
from .sandbox import LocalProcessSandboxBackend


class ExecutionError(ValueError):
    """A local execution request or collaborator result is invalid."""


MAX_PROPOSAL_FILES = 20
MAX_PROPOSAL_PATH_BYTES = 240
MAX_PROPOSAL_FILE_BYTES = 100_000
MAX_PROPOSAL_TOTAL_BYTES = 1_000_000


@dataclass(frozen=True)
class ExecutionRequest:
    """Caller-declared inputs for one local preparation attempt."""

    process_id: str
    task_id: str
    repository_id: str
    base_commit: str
    snapshot_path: Path
    allowed_commands: frozenset[str]
    declared_change_paths: tuple[str, ...]
    test_command: tuple[str, ...]
    test_timeout_seconds: int = 30

    def __post_init__(self) -> None:
        for value in (self.process_id, self.task_id, self.repository_id, self.base_commit):
            _validate_identity(value)
        _validate_request_shape(self)


class ExecutionStatus(str, Enum):
    PREPARED = "prepared"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionResult:
    """Bounded result metadata; never carries prompts or raw command output."""

    status: ExecutionStatus
    prepared_change_id: str | None = None
    patch_digest: str | None = None
    evidence_digest: str | None = None
    verification_digest: str | None = None
    failure_code: str | None = None


@dataclass(frozen=True)
class WorkerInput:
    """Narrow task envelope; filesystem and command capabilities stay outside."""

    process_id: str
    task_id: str
    repository_id: str
    base_commit: str
    declared_change_paths: tuple[str, ...]


@dataclass(frozen=True)
class WorkerProposal:
    """Proposed relative-path text replacements returned as data."""

    changes: tuple[tuple[str, str], ...]


@runtime_checkable
class ProposalWorker(Protocol):
    def propose(self, task: WorkerInput) -> WorkerProposal: ...


@runtime_checkable
class ExecutorSandboxBackend(Protocol):
    def create(self, snapshot: Path, allowed_commands: set[str]) -> object: ...


def validate_worker_proposal(value: object, request: ExecutionRequest) -> WorkerProposal:
    """Validate, scope and detach the worker's bounded text proposal."""

    if type(value) is not WorkerProposal or not isinstance(value.changes, tuple) or not value.changes:
        raise ExecutionError("execution proposal: shape is invalid")
    detached: list[tuple[str, str]] = []
    normalized_paths: set[str] = set()
    total_bytes = 0
    declared_paths = {posixpath.normpath(path) for path in request.declared_change_paths}
    for change in value.changes:
        if (
            type(change) is not tuple
            or len(change) != 2
            or not isinstance(change[0], str)
            or not change[0]
            or not isinstance(change[1], str)
        ):
            raise ExecutionError("execution proposal: shape is invalid")
        path, content = change
        try:
            path_bytes = path.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ExecutionError("execution proposal: scope is invalid") from exc
        normalized_path = posixpath.normpath(path)
        if (
            not _is_safe_relative_path(path)
            or len(path_bytes) > MAX_PROPOSAL_PATH_BYTES
            or normalized_path in normalized_paths
            or normalized_path not in declared_paths
        ):
            raise ExecutionError("execution proposal: scope is invalid")
        normalized_paths.add(normalized_path)
        try:
            content_bytes = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ExecutionError("execution proposal: content is invalid") from exc
        if len(content_bytes) > MAX_PROPOSAL_FILE_BYTES:
            raise ExecutionError("execution proposal: limits exceeded")
        total_bytes += len(path_bytes) + len(content_bytes)
        if total_bytes > MAX_PROPOSAL_TOTAL_BYTES:
            raise ExecutionError("execution proposal: limits exceeded")
        detached.append((path, content))
    if len(detached) > MAX_PROPOSAL_FILES:
        raise ExecutionError("execution proposal: limits exceeded")
    return WorkerProposal(tuple(detached))


def run_local_execution(
    request: ExecutionRequest,
    worker: ProposalWorker,
    *,
    sandbox_backend: ExecutorSandboxBackend | None = None,
) -> ExecutionResult:
    """Run one injected proposal through local sandbox preparation only.

    The default LocalProcessSandboxBackend is a development-only fallback, not
    a security boundary or evidence of network/kernel isolation.
    """

    if not isinstance(request, ExecutionRequest):
        raise ExecutionError("execution request: type is invalid")
    if not callable(getattr(worker, "propose", None)):
        raise ExecutionError("execution worker: collaborator is invalid")
    backend = sandbox_backend or LocalProcessSandboxBackend()
    if not callable(getattr(backend, "create", None)):
        raise ExecutionError("execution sandbox: backend is invalid")
    sandbox = None
    try:
        sandbox = backend.create(request.snapshot_path, set(request.allowed_commands))
        if (
            not isinstance(getattr(sandbox, "snapshot", None), Path)
            or not isinstance(getattr(sandbox, "workspace", None), Path)
            or not callable(getattr(sandbox, "run", None))
            or not callable(getattr(sandbox, "close", None))
        ):
            raise ExecutionError("execution sandbox: session is invalid")
        worker_input = WorkerInput(
            process_id=request.process_id,
            task_id=request.task_id,
            repository_id=request.repository_id,
            base_commit=request.base_commit,
            declared_change_paths=request.declared_change_paths,
        )
        proposal = validate_worker_proposal(worker.propose(worker_input), request)
        prepared = prepare_change(
            sandbox,
            process_id=request.process_id,
            task_id=request.task_id,
            repository_id=request.repository_id,
            base_commit=request.base_commit,
            changes=dict(proposal.changes),
            test_command=request.test_command,
        )
        staged = prepared.staged_change
        return ExecutionResult(
            status=ExecutionStatus.PREPARED,
            prepared_change_id=staged["staged_change_id"],
            patch_digest=staged["patch_digest"],
            evidence_digest=staged["evidence_digest"],
            verification_digest=staged["verification_digest"],
        )
    finally:
        close = getattr(sandbox, "close", None)
        if callable(close):
            close()


def _validate_identity(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ExecutionError("execution request: identity field is invalid")


def _validate_request_shape(request: ExecutionRequest) -> None:
    snapshot = request.snapshot_path
    if (
        not isinstance(snapshot, Path)
        or not snapshot.is_absolute()
        or snapshot == Path(snapshot.anchor)
        or ".." in snapshot.parts
    ):
        raise ExecutionError("execution request: snapshot path is invalid")
    if (
        not isinstance(request.allowed_commands, frozenset)
        or not request.allowed_commands
        or any(
            not isinstance(command, str)
            or not command
            or command != command.strip()
            or any(character.isspace() for character in command)
            or Path(command).name != command
            or any(ord(character) < 32 or ord(character) == 127 for character in command)
            for command in request.allowed_commands
        )
    ):
        raise ExecutionError("execution request: command allowlist is invalid")
    if (
        not isinstance(request.declared_change_paths, tuple)
        or not request.declared_change_paths
        or any(not _is_safe_relative_path(path) for path in request.declared_change_paths)
    ):
        raise ExecutionError("execution request: declared paths are invalid")
    command = request.test_command
    if (
        not isinstance(command, tuple)
        or not command
        or any(not isinstance(part, str) or not part or part != part.strip() for part in command)
        or Path(command[0]).name not in request.allowed_commands
    ):
        raise ExecutionError("execution request: test command is invalid")
    timeout = request.test_timeout_seconds
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise ExecutionError("execution request: test timeout is invalid")


def _is_safe_relative_path(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value.startswith("/")
        or "\\" in value
        or "//" in value
        or "/./" in value
        or value.endswith("/.")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and value not in {"", "."}
