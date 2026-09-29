"""Typed records for the local, preparation-only execution spine.

These records do not represent an LLM worker, verified remote snapshot, approval,
or publication capability. Validation and orchestration are added separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable


class ExecutionError(ValueError):
    """A local execution request or collaborator result is invalid."""


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


def validate_worker_proposal(value: object) -> WorkerProposal:
    """Validate and detach the worker's untrusted, non-empty text proposal."""

    if type(value) is not WorkerProposal or not isinstance(value.changes, tuple) or not value.changes:
        raise ExecutionError("execution proposal: shape is invalid")
    detached: list[tuple[str, str]] = []
    for change in value.changes:
        if (
            type(change) is not tuple
            or len(change) != 2
            or not isinstance(change[0], str)
            or not change[0]
            or not isinstance(change[1], str)
        ):
            raise ExecutionError("execution proposal: shape is invalid")
        detached.append((change[0], change[1]))
    return WorkerProposal(tuple(detached))


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
    ):
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and value not in {"", "."}
