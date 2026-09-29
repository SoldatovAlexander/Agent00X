"""Typed records for the local, preparation-only execution spine.

These records do not represent an LLM worker, verified remote snapshot, approval,
or publication capability. Validation and orchestration are added separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import posixpath
import re
from typing import Literal, Protocol, runtime_checkable

from .repository_process import prepare_change
from .sandbox import LocalProcessSandboxBackend
from .digests import sha256_digest
from .pinned_snapshot import PinnedSnapshot, compute_snapshot_tree_digest


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
    pinned_snapshot: PinnedSnapshot | None = None

    def __post_init__(self) -> None:
        for value in (self.process_id, self.task_id, self.repository_id, self.base_commit):
            _validate_identity(value)
        _validate_request_shape(self)


class ExecutionStatus(str, Enum):
    PREPARED = "prepared"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionResult:
    """Bounded result metadata; never carries prompts or raw command output."""

    status: ExecutionStatus
    prepared_change_id: str | None = None
    patch_digest: str | None = None
    evidence_digest: str | None = None
    verification_digest: str | None = None
    verified_contents_digest: str | None = None
    verifier_result: VerifierResult | None = None
    failure_code: str | None = None
    evidence_origin: Literal["local_test"] = "local_test"
    limitations: tuple[str, ...] = (
        "injected_worker",
        "remote_snapshot_unverified",
        "production_sandbox_unproven",
        "publication_not_attempted",
    )


@dataclass(frozen=True)
class WorkerInput:
    """Narrow task envelope; filesystem and command capabilities stay outside."""

    process_id: str
    task_id: str
    repository_id: str
    base_commit: str
    declared_change_paths: tuple[str, ...]
    snapshot_tree_digest: str | None = None
    snapshot_origin: Literal["local_git_commit", "unverified_local_test"] = "unverified_local_test"


@dataclass(frozen=True)
class WorkerProposal:
    """Proposed relative-path text replacements returned as data."""

    changes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class VerifierInput:
    process_id: str
    patch_digest: str
    evidence_digest: str
    verification_digest: str
    verified_contents_digest: str
    evidence_origin: Literal["local_test"] = "local_test"


class VerifierVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class VerifierResult:
    process_id: str
    verifier_id: str
    patch_digest: str
    evidence_digest: str
    verification_digest: str
    verified_contents_digest: str
    verdict: VerifierVerdict
    blocker_codes: tuple[str, ...] = ()
    evidence_origin: Literal["local_test"] = "local_test"


@runtime_checkable
class ProposalWorker(Protocol):
    def propose(self, task: WorkerInput) -> WorkerProposal: ...


@runtime_checkable
class IndependentVerifier(Protocol):
    def verify(self, prepared: VerifierInput) -> VerifierResult: ...


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
    verifier: IndependentVerifier | None = None,
    sandbox_backend: ExecutorSandboxBackend | None = None,
    require_pinned_snapshot: bool = False,
) -> ExecutionResult:
    """Run one injected proposal through local sandbox preparation only.

    The default LocalProcessSandboxBackend is a development-only fallback, not
    a security boundary or evidence of network/kernel isolation.
    """

    if not isinstance(request, ExecutionRequest):
        raise ExecutionError("execution request: type is invalid")
    if not isinstance(require_pinned_snapshot, bool):
        raise ExecutionError("execution request: pinned snapshot mode is invalid")
    if require_pinned_snapshot and request.pinned_snapshot is None:
        raise ExecutionError("execution request: pinned snapshot is required")
    if not callable(getattr(worker, "propose", None)):
        raise ExecutionError("execution worker: collaborator is invalid")
    verify = getattr(verifier, "verify", None)
    propose = getattr(worker, "propose", None)
    if verifier is None or not callable(verify):
        raise ExecutionError("execution verifier: collaborator is invalid")
    if verifier is worker or _same_callable(verify, propose):
        raise ExecutionError("execution verifier: collaborator is aliased")
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
        if request.pinned_snapshot is not None:
            try:
                source_tree_digest = compute_snapshot_tree_digest(request.snapshot_path)
                source_content_digest = compute_snapshot_tree_digest(
                    request.snapshot_path, include_mode=False
                )
                copied_content_digest = compute_snapshot_tree_digest(
                    sandbox.snapshot, include_mode=False
                )
            except Exception:
                raise ExecutionError("execution snapshot: digest check failed") from None
            if source_tree_digest != request.pinned_snapshot.tree_digest:
                raise ExecutionError("execution snapshot: digest mismatch")
            if copied_content_digest != source_content_digest:
                raise ExecutionError("execution snapshot: digest mismatch")
        worker_input = WorkerInput(
            process_id=request.process_id,
            task_id=request.task_id,
            repository_id=request.repository_id,
            base_commit=request.base_commit,
            declared_change_paths=request.declared_change_paths,
            snapshot_tree_digest=(
                request.pinned_snapshot.tree_digest
                if request.pinned_snapshot is not None
                else None
            ),
            snapshot_origin=(
                request.pinned_snapshot.evidence_origin
                if request.pinned_snapshot is not None
                else "unverified_local_test"
            ),
        )
        try:
            raw_proposal = worker.propose(worker_input)
        except Exception:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                failure_code="worker-failed",
            )
        proposal = validate_worker_proposal(raw_proposal, request)
        prepared = prepare_change(
            sandbox,
            process_id=request.process_id,
            task_id=request.task_id,
            repository_id=request.repository_id,
            base_commit=request.base_commit,
            changes=dict(proposal.changes),
            test_command=request.test_command,
        )
        staged = getattr(prepared, "staged_change", None)
        if (
            not isinstance(staged, dict)
            or staged.get("process_id") != request.process_id
            or staged.get("repository_id") != request.repository_id
            or staged.get("base_commit") != request.base_commit
        ):
            raise ExecutionError("execution preparation: binding mismatch")
        verified_contents = getattr(prepared, "verified_contents", None)
        if not isinstance(verified_contents, tuple) or not verified_contents:
            raise ExecutionError("execution preparation: verified contents are missing")
        verified_contents_digest = sha256_digest(verified_contents)
        verifier_input = VerifierInput(
            process_id=request.process_id,
            patch_digest=staged["patch_digest"],
            evidence_digest=staged["evidence_digest"],
            verification_digest=staged["verification_digest"],
            verified_contents_digest=verified_contents_digest,
        )
        try:
            raw_verifier_result = verify(verifier_input)
        except Exception:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                patch_digest=staged["patch_digest"],
                evidence_digest=staged["evidence_digest"],
                verification_digest=staged["verification_digest"],
                verified_contents_digest=verified_contents_digest,
                failure_code="verifier-failed",
            )
        verifier_result = validate_verifier_result(raw_verifier_result, verifier_input)
        if verifier_result.verdict != VerifierVerdict.PASS:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                patch_digest=staged["patch_digest"],
                evidence_digest=staged["evidence_digest"],
                verification_digest=staged["verification_digest"],
                verified_contents_digest=verified_contents_digest,
                verifier_result=verifier_result,
                failure_code="verifier-not-pass",
            )
        return ExecutionResult(
            status=ExecutionStatus.VERIFIED,
            prepared_change_id=staged["staged_change_id"],
            patch_digest=staged["patch_digest"],
            evidence_digest=staged["evidence_digest"],
            verification_digest=staged["verification_digest"],
            verified_contents_digest=verified_contents_digest,
            verifier_result=verifier_result,
        )
    finally:
        close = getattr(sandbox, "close", None)
        if callable(close):
            close()


def _same_callable(first: object, second: object) -> bool:
    if first is second:
        return True
    return (
        getattr(first, "__self__", None) is getattr(second, "__self__", object())
        and getattr(first, "__func__", None) is getattr(second, "__func__", object())
    )


def validate_verifier_result(value: object, expected: VerifierInput) -> VerifierResult:
    """Validate and detach the exact bounded verifier response for one input."""

    if type(value) is not VerifierResult:
        raise ExecutionError("execution verifier: result shape is invalid")
    if (
        not _is_safe_label(value.process_id)
        or not _is_safe_label(value.verifier_id)
        or type(value.verdict) is not VerifierVerdict
        or not isinstance(value.blocker_codes, tuple)
        or any(
            not isinstance(code, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", code) is None
            for code in value.blocker_codes
        )
        or value.evidence_origin != "local_test"
        or any(
            not isinstance(digest, str)
            for digest in (
                value.patch_digest,
                value.evidence_digest,
                value.verification_digest,
                value.verified_contents_digest,
            )
        )
    ):
        raise ExecutionError("execution verifier: result shape is invalid")
    if (
        value.process_id != expected.process_id
        or value.patch_digest != expected.patch_digest
        or value.evidence_digest != expected.evidence_digest
        or value.verification_digest != expected.verification_digest
        or value.verified_contents_digest != expected.verified_contents_digest
    ):
        raise ExecutionError("execution verifier: result binding mismatch")
    return VerifierResult(
        process_id=value.process_id,
        verifier_id=value.verifier_id,
        patch_digest=value.patch_digest,
        evidence_digest=value.evidence_digest,
        verification_digest=value.verification_digest,
        verified_contents_digest=value.verified_contents_digest,
        verdict=value.verdict,
        blocker_codes=tuple(value.blocker_codes),
        evidence_origin="local_test",
    )


def _is_safe_label(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None
    )


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
    pinned_snapshot = request.pinned_snapshot
    if pinned_snapshot is not None and (
        not isinstance(pinned_snapshot, PinnedSnapshot)
        or pinned_snapshot.repository_id != request.repository_id
        or pinned_snapshot.commit_oid != request.base_commit
        or pinned_snapshot.snapshot_path != snapshot
    ):
        raise ExecutionError("execution request: pinned snapshot binding is invalid")
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
