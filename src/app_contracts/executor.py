"""Typed records for the local, preparation-only execution spine.

These records do not represent an LLM worker, verified remote snapshot, approval,
or publication capability. Validation and orchestration are added separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


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


def _validate_identity(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ExecutionError("execution request: identity field is invalid")
