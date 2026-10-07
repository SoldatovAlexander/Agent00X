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
import stat
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from .repository_process import prepare_change
from .sandbox import LocalProcessSandboxBackend
from .digests import sha256_bytes, sha256_digest
from .pinned_snapshot import (
    MAX_SNAPSHOT_FILE_BYTES,
    SNAPSHOT_DIGEST_CANONICALIZATION,
    PinnedSnapshot,
    compute_snapshot_tree_digest,
)

if TYPE_CHECKING:
    from .github_snapshot import (
        GitHubBlobClaim,
        GitHubSnapshotClaim,
        GitHubSnapshotContents,
    )
    from .remote_snapshot_workspace import MaterializedGitHubSnapshot


class ExecutionError(ValueError):
    """A local execution request or collaborator result is invalid."""


MAX_PROPOSAL_FILES = 20
MAX_PROPOSAL_PATH_BYTES = 240
MAX_PROPOSAL_FILE_BYTES = 100_000
MAX_PROPOSAL_TOTAL_BYTES = 1_000_000
MAX_VERIFIER_BLOCKER_CODES = 16
MAX_TASK_INSTRUCTION_BYTES = 4096
MAX_CONTEXT_FILES = 8
MAX_CONTEXT_FILE_BYTES = 12_000
MAX_CONTEXT_TOTAL_BYTES = 20_000
MAX_VERIFIER_SNAPSHOT_FILES = 256
MAX_VERIFIER_SNAPSHOT_PATH_BYTES = 240
MAX_VERIFIER_SNAPSHOT_FILE_BYTES = MAX_SNAPSHOT_FILE_BYTES
MAX_VERIFIER_SNAPSHOT_TOTAL_BYTES = 512_000


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
    task_instruction: str | None = None
    context_files: tuple[tuple[str, str], ...] = ()
    remote_snapshot: GitHubSnapshotContents | None = None
    remote_workspace: MaterializedGitHubSnapshot | None = None

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
    staged_change_digest: str | None = None
    snapshot_tree_digest: str | None = None
    snapshot_origin: Literal[
        "local_git_commit", "github_rest_api_claim", "unverified_local_test"
    ] = "unverified_local_test"
    verifier_result: VerifierResult | None = None
    failure_code: str | None = None
    evidence_origin: Literal["local_test"] = "local_test"
    limitations: tuple[str, ...] = (
        "injected_worker",
        "remote_snapshot_unverified",
        "production_sandbox_unproven",
        "publication_not_attempted",
    )
    snapshot_claim_digest: str | None = None
    verifier_attestation_digest: str | None = None
    verifier_attestation_key_id: str | None = None
    verifier_attestation_profile_digest: str | None = None
    verifier_signature_valid: bool | None = None
    verifier_independent_host_trust_established: bool | None = None


@dataclass(frozen=True)
class WorkerInput:
    """Narrow task envelope; filesystem and command capabilities stay outside."""

    process_id: str
    task_id: str
    repository_id: str
    base_commit: str
    declared_change_paths: tuple[str, ...]
    snapshot_tree_digest: str | None = None
    snapshot_origin: Literal[
        "local_git_commit", "github_rest_api_claim", "unverified_local_test"
    ] = "unverified_local_test"
    task_instruction: str | None = None
    context_files: tuple[tuple[str, str], ...] = ()
    snapshot_claim_digest: str | None = None

    def __post_init__(self) -> None:
        _validate_worker_input(self.task_instruction, self.context_files, self.declared_change_paths)
        if self.snapshot_origin == "github_rest_api_claim":
            if not _is_safe_digest(self.snapshot_claim_digest):
                raise ExecutionError("execution request: worker input is invalid")
        elif self.snapshot_claim_digest is not None:
            raise ExecutionError("execution request: worker input is invalid")
        detached = tuple((path, text) for path, text in self.context_files)
        object.__setattr__(self, "context_files", detached)


@dataclass(frozen=True)
class WorkerProposal:
    """Proposed relative-path text replacements returned as data."""

    changes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class VerifierInput:
    process_id: str
    repository_id: str
    base_commit: str
    snapshot_tree_digest: str | None
    declared_change_paths: tuple[str, ...]
    verified_contents: tuple[tuple[str, str], ...]
    test_command: tuple[str, ...]
    test_timeout_seconds: int
    patch_digest: str
    evidence_digest: str
    verification_digest: str
    verified_contents_digest: str
    evidence_origin: Literal["local_test"] = "local_test"
    replay_result_digest: str | None = None
    snapshot_files: tuple[tuple[str, str, bytes], ...] = ()
    snapshot_claim_digest: str | None = None


class VerifierVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class VerifierResult:
    process_id: str
    base_commit: str
    snapshot_tree_digest: str | None
    replay_result_digest: str | None
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
    stage_sink: object | None = None,
    require_durable_stage: bool = False,
) -> ExecutionResult:
    """Run one injected proposal through local sandbox preparation only.

    The default LocalProcessSandboxBackend is a development-only fallback, not
    a security boundary or evidence of network/kernel isolation.
    """

    if not isinstance(request, ExecutionRequest):
        raise ExecutionError("execution request: type is invalid")
    _validate_live_remote_workspace(request)
    _revalidate_remote_snapshot(request)
    if not isinstance(require_pinned_snapshot, bool):
        raise ExecutionError("execution request: pinned snapshot mode is invalid")
    if not isinstance(require_durable_stage, bool):
        raise ExecutionError("execution request: durable stage mode is invalid")
    if require_durable_stage and stage_sink is None:
        raise ExecutionError("execution stage: durable sink is required")
    if stage_sink is not None and (
        not callable(getattr(stage_sink, "save", None))
        or not callable(getattr(stage_sink, "load", None))
    ):
        raise ExecutionError("execution stage: durable sink is invalid")
    if require_pinned_snapshot and request.pinned_snapshot is None:
        raise ExecutionError("execution request: pinned snapshot is required")
    if request.remote_snapshot is not None and sandbox_backend is None:
        raise ExecutionError("execution sandbox: explicit remote backend is required")
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
        if request.remote_snapshot is not None:
            try:
                claim = request.remote_snapshot.claim
                remote_files = _read_pinned_snapshot_files(
                    request.snapshot_path, claim.content_digest
                )
                claimed_files = tuple(
                    (blob.path, blob.mode, blob.content)
                    for blob in request.remote_snapshot.files
                )
                sandbox_files = _read_pinned_snapshot_files(
                    sandbox.snapshot, claim.content_digest
                )
            except Exception:
                raise ExecutionError("execution snapshot: claim mismatch") from None
            if remote_files != claimed_files or sandbox_files != claimed_files:
                raise ExecutionError("execution snapshot: claim mismatch")
        worker_input = WorkerInput(
            process_id=request.process_id,
            task_id=request.task_id,
            repository_id=request.repository_id,
            base_commit=request.base_commit,
            declared_change_paths=request.declared_change_paths,
            snapshot_tree_digest=_request_snapshot_tree_digest(request),
            snapshot_origin=_request_snapshot_origin(request),
            task_instruction=request.task_instruction,
            context_files=tuple((path, text) for path, text in request.context_files),
            snapshot_claim_digest=_request_snapshot_claim_digest(request),
        )
        try:
            raw_proposal = worker.propose(worker_input)
        except Exception:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                snapshot_tree_digest=_request_snapshot_tree_digest(request),
                snapshot_origin=_request_snapshot_origin(request),
                snapshot_claim_digest=_request_snapshot_claim_digest(request),
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
        if request.pinned_snapshot is not None:
            _validate_prepared_snapshot_binding(
                prepared,
                request,
                staged,
                proposal,
                verified_contents,
            )
        verified_contents_digest = sha256_digest(verified_contents)
        replay_result_digest = None
        if request.pinned_snapshot is not None or request.remote_snapshot is not None:
            try:
                replay_result_digest = _run_snapshot_verifier_replay(
                    request=request,
                    backend=backend,
                    source_sandbox=sandbox,
                    verified_contents=verified_contents,
                    verified_contents_digest=verified_contents_digest,
                )
            except Exception:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    patch_digest=staged["patch_digest"],
                    evidence_digest=staged["evidence_digest"],
                    verification_digest=staged["verification_digest"],
                    verified_contents_digest=verified_contents_digest,
                    staged_change_digest=_staged_change_digest(staged),
                    snapshot_tree_digest=_request_snapshot_tree_digest(request),
                    snapshot_origin=_request_snapshot_origin(request),
                    snapshot_claim_digest=_request_snapshot_claim_digest(request),
                    failure_code="verification-replay-failed",
                )
        verifier_input = _build_verifier_input(
            request=request,
            proposal=proposal,
            staged=staged,
            verified_contents=verified_contents,
            verified_contents_digest=verified_contents_digest,
            replay_result_digest=replay_result_digest,
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
                staged_change_digest=_staged_change_digest(staged),
                snapshot_tree_digest=_request_snapshot_tree_digest(request),
                snapshot_origin=_request_snapshot_origin(request),
                snapshot_claim_digest=_request_snapshot_claim_digest(request),
                failure_code="verifier-failed",
            )
        # A signed receipt authenticates bytes, but the verifier host is not
        # independently trusted yet. Preserve only bounded receipt metadata and
        # stop before any durable staging operation.
        from .verifier_attestation import VerifiedVerifierAttestation

        if type(raw_verifier_result) is VerifiedVerifierAttestation:
            try:
                from .digests import sha256_bytes
                from .verifier_process import VerifierProcessRequest, serialize_verifier_request

                attested_result = validate_verifier_result(
                    raw_verifier_result.verifier_result, verifier_input
                )
                exact_request_digest = sha256_bytes(
                    serialize_verifier_request(
                        VerifierProcessRequest.from_verifier_input(verifier_input)
                    )
                )
                if (
                    raw_verifier_result.signature_valid is not True
                    or raw_verifier_result.independent_host_trust_established is not False
                    or not _is_sha256_digest(raw_verifier_result.attestation_digest)
                    or raw_verifier_result.request_digest != exact_request_digest
                    or not _is_sha256_digest(raw_verifier_result.verifier_profile_digest)
                    or not _is_safe_verifier_key_id(raw_verifier_result.key_id)
                ):
                    raise ValueError
            except Exception:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    patch_digest=staged["patch_digest"],
                    evidence_digest=staged["evidence_digest"],
                    verification_digest=staged["verification_digest"],
                    verified_contents_digest=verified_contents_digest,
                    staged_change_digest=_staged_change_digest(staged),
                    snapshot_tree_digest=_request_snapshot_tree_digest(request),
                    snapshot_origin=_request_snapshot_origin(request),
                    snapshot_claim_digest=_request_snapshot_claim_digest(request),
                    failure_code="verifier-attestation-invalid",
                )
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                patch_digest=staged["patch_digest"],
                evidence_digest=staged["evidence_digest"],
                verification_digest=staged["verification_digest"],
                verified_contents_digest=verified_contents_digest,
                staged_change_digest=_staged_change_digest(staged),
                verifier_result=attested_result,
                snapshot_tree_digest=_request_snapshot_tree_digest(request),
                snapshot_origin=_request_snapshot_origin(request),
                snapshot_claim_digest=_request_snapshot_claim_digest(request),
                verifier_attestation_digest=raw_verifier_result.attestation_digest,
                verifier_attestation_key_id=raw_verifier_result.key_id,
                verifier_attestation_profile_digest=raw_verifier_result.verifier_profile_digest,
                verifier_signature_valid=True,
                verifier_independent_host_trust_established=False,
                failure_code="verifier-trust-unestablished",
            )
        verifier_result = validate_verifier_result(raw_verifier_result, verifier_input)
        if verifier_result.verdict != VerifierVerdict.PASS:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                patch_digest=staged["patch_digest"],
                evidence_digest=staged["evidence_digest"],
                verification_digest=staged["verification_digest"],
                verified_contents_digest=verified_contents_digest,
                staged_change_digest=_staged_change_digest(staged),
                verifier_result=verifier_result,
                snapshot_tree_digest=_request_snapshot_tree_digest(request),
                snapshot_origin=_request_snapshot_origin(request),
                snapshot_claim_digest=_request_snapshot_claim_digest(request),
                failure_code="verifier-not-pass",
            )
        verified_result = ExecutionResult(
            status=ExecutionStatus.VERIFIED,
            prepared_change_id=staged["staged_change_id"],
            patch_digest=staged["patch_digest"],
            evidence_digest=staged["evidence_digest"],
            verification_digest=staged["verification_digest"],
            verified_contents_digest=verified_contents_digest,
            staged_change_digest=_staged_change_digest(staged),
            snapshot_tree_digest=_request_snapshot_tree_digest(request),
            snapshot_origin=_request_snapshot_origin(request),
            verifier_result=verifier_result,
            snapshot_claim_digest=_request_snapshot_claim_digest(request),
        )
        if stage_sink is None:
            return verified_result
        try:
            # Local import avoids coupling the executor contracts to SQLite.
            from .durable_stage import StagedArtifact, build_staged_artifact

            artifact = build_staged_artifact(request, prepared, verified_result)
            saved = stage_sink.save(artifact)
            loaded = stage_sink.load(verified_result.staged_change_digest)
            if (
                type(saved) is not StagedArtifact
                or type(loaded) is not StagedArtifact
                or saved.staged_change_digest != verified_result.staged_change_digest
                or saved.verified_contents_digest != verified_result.verified_contents_digest
                or saved.artifact_digest != artifact.artifact_digest
                or saved.canonical_payload != artifact.canonical_payload
                or loaded.staged_change_digest != verified_result.staged_change_digest
                or loaded.verified_contents_digest != verified_result.verified_contents_digest
                or loaded.artifact_digest != artifact.artifact_digest
                or loaded.canonical_payload != artifact.canonical_payload
            ):
                raise ValueError("stage readback mismatch")
        except Exception:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                patch_digest=staged["patch_digest"],
                evidence_digest=staged["evidence_digest"],
                verification_digest=staged["verification_digest"],
                verified_contents_digest=verified_contents_digest,
                staged_change_digest=_staged_change_digest(staged),
                snapshot_tree_digest=_request_snapshot_tree_digest(request),
                snapshot_origin=_request_snapshot_origin(request),
                verifier_result=verifier_result,
                snapshot_claim_digest=_request_snapshot_claim_digest(request),
                failure_code="stage-persistence-failed",
            )
        return verified_result
    finally:
        close = getattr(sandbox, "close", None)
        if callable(close):
            close()


def _staged_change_digest(staged: dict) -> str:
    """Return the canonical digest-only binding for one verified staged change."""
    return sha256_digest(staged)


def _is_sha256_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _is_safe_verifier_key_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None


def _request_snapshot_tree_digest(request: ExecutionRequest) -> str | None:
    if request.pinned_snapshot is not None:
        return request.pinned_snapshot.tree_digest
    if request.remote_snapshot is not None:
        return request.remote_snapshot.claim.content_digest
    return None


def _request_snapshot_origin(request: ExecutionRequest) -> str:
    if request.pinned_snapshot is not None:
        return request.pinned_snapshot.evidence_origin
    if request.remote_snapshot is not None:
        return request.remote_snapshot.claim.evidence_origin
    return "unverified_local_test"


def _request_snapshot_claim_digest(request: ExecutionRequest) -> str | None:
    if request.remote_snapshot is None:
        return None
    claim = request.remote_snapshot.claim
    return sha256_digest(
        {
            "canonicalization": "github-rest-snapshot-claim/v1",
            "owner": claim.owner,
            "repository": claim.repository,
            "commit_oid": claim.commit_oid,
            "tree_oid": claim.tree_oid,
            "content_digest": claim.content_digest,
            "full_snapshot": claim.full_snapshot,
            "selected_paths": claim.selected_paths,
            "evidence_origin": claim.evidence_origin,
        }
    )


def _same_callable(first: object, second: object) -> bool:
    if first is second:
        return True
    return (
        getattr(first, "__self__", None) is getattr(second, "__self__", object())
        and getattr(first, "__func__", None) is getattr(second, "__func__", object())
    )


def _validate_prepared_snapshot_binding(
    prepared: object,
    request: ExecutionRequest,
    staged: dict,
    proposal: WorkerProposal,
    verified_contents: tuple[tuple[str, str], ...],
) -> None:
    pin = request.pinned_snapshot
    if pin is None:
        raise ExecutionError("execution preparation: pinned snapshot is missing")
    try:
        if compute_snapshot_tree_digest(request.snapshot_path) != pin.tree_digest:
            raise ExecutionError("execution preparation: pinned source changed")
        evidence = getattr(prepared, "evidence_bundle", None)
        source_digests = evidence.get("source_digests") if isinstance(evidence, dict) else None
        verification = getattr(prepared, "verification_report", None)
        if (
            not isinstance(evidence, dict)
            or evidence.get("patch_digest") != staged.get("patch_digest")
            or sha256_digest(evidence) != staged.get("evidence_digest")
            or not isinstance(verification, dict)
            or verification.get("evidence_digest") != staged.get("evidence_digest")
            or sha256_digest(verification) != staged.get("verification_digest")
        ):
            raise ExecutionError("execution preparation: pinned artifact binding mismatch")
        if (
            tuple(verified_contents) != tuple(sorted(proposal.changes))
            or not isinstance(source_digests, list)
            or len(source_digests) != len(verified_contents)
        ):
            raise ExecutionError("execution preparation: pinned source binding mismatch")
        expected_digests: list[str] = []
        root = request.snapshot_path.resolve(strict=True)
        for relative_path, _content in verified_contents:
            if not _is_safe_relative_path(relative_path):
                raise ExecutionError("execution preparation: pinned source binding mismatch")
            source_file = request.snapshot_path.joinpath(*Path(relative_path).parts)
            resolved_source = source_file.resolve(strict=True)
            if (
                not resolved_source.is_relative_to(root)
                or source_file.is_symlink()
                or not resolved_source.is_file()
            ):
                raise ExecutionError("execution preparation: pinned source binding mismatch")
            expected_digests.append(
                sha256_bytes(resolved_source.read_text(encoding="utf-8").encode("utf-8"))
            )
        if source_digests != expected_digests:
            raise ExecutionError("execution preparation: pinned source binding mismatch")
        if staged.get("base_commit") != pin.commit_oid:
            raise ExecutionError("execution preparation: pinned base mismatch")
    except ExecutionError:
        raise
    except Exception:
        raise ExecutionError("execution preparation: pinned source binding mismatch") from None


def _build_verifier_input(
    *,
    request: ExecutionRequest,
    proposal: WorkerProposal,
    staged: dict,
    verified_contents: tuple[tuple[str, str], ...],
    verified_contents_digest: str,
    replay_result_digest: str | None,
) -> VerifierInput:
    expected_contents = tuple(sorted(proposal.changes))
    declared_paths = {posixpath.normpath(path) for path in request.declared_change_paths}
    total_bytes = 0
    if (
        not isinstance(verified_contents, tuple)
        or verified_contents != expected_contents
        or len(verified_contents) > MAX_PROPOSAL_FILES
    ):
        raise ExecutionError("execution verifier input: prepared scope is invalid")
    for entry in verified_contents:
        if (
            not isinstance(entry, tuple)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not isinstance(entry[1], str)
            or not _is_safe_relative_path(entry[0])
            or posixpath.normpath(entry[0]) not in declared_paths
        ):
            raise ExecutionError("execution verifier input: prepared scope is invalid")
        path, content = entry
        try:
            path_bytes = path.encode("utf-8")
            content_bytes = content.encode("utf-8")
        except UnicodeEncodeError:
            raise ExecutionError("execution verifier input: prepared scope is invalid") from None
        if len(path_bytes) > MAX_PROPOSAL_PATH_BYTES or len(content_bytes) > MAX_PROPOSAL_FILE_BYTES:
            raise ExecutionError("execution verifier input: limits exceeded")
        total_bytes += len(path_bytes) + len(content_bytes)
        if total_bytes > MAX_PROPOSAL_TOTAL_BYTES:
            raise ExecutionError("execution verifier input: limits exceeded")
    snapshot_files: tuple[tuple[str, str, bytes], ...] = ()
    if request.pinned_snapshot is not None or request.remote_snapshot is not None:
        expected_tree_digest = _request_snapshot_tree_digest(request)
        if expected_tree_digest is None:
            raise ExecutionError("execution verifier input: snapshot binding is invalid")
        snapshot_files = _read_pinned_snapshot_files(
            request.snapshot_path, expected_tree_digest
        )
    return VerifierInput(
        process_id=request.process_id,
        repository_id=request.repository_id,
        base_commit=request.base_commit,
        snapshot_tree_digest=_request_snapshot_tree_digest(request),
        declared_change_paths=request.declared_change_paths,
        verified_contents=verified_contents,
        test_command=request.test_command,
        test_timeout_seconds=request.test_timeout_seconds,
        patch_digest=staged["patch_digest"],
        evidence_digest=staged["evidence_digest"],
        verification_digest=staged["verification_digest"],
        verified_contents_digest=verified_contents_digest,
        replay_result_digest=replay_result_digest,
        snapshot_files=snapshot_files,
        snapshot_claim_digest=_request_snapshot_claim_digest(request),
    )


def verifier_snapshot_tree_digest(
    snapshot_files: tuple[tuple[str, str, bytes], ...],
) -> str:
    """Compute the normalized tree digest from detached verifier bytes."""

    entries = [
        {
            "path": path,
            "content_digest": sha256_bytes(content),
            "mode": mode,
        }
        for path, mode, content in snapshot_files
    ]
    entries.sort(key=lambda entry: entry["path"])
    return sha256_digest(
        {"canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION, "files": entries}
    )


def _read_pinned_snapshot_files(
    snapshot_path: Path, expected_tree_digest: str
) -> tuple[tuple[str, str, bytes], ...]:
    """Read a bounded, regular-file-only copy of the exact pinned base tree."""

    try:
        if (
            not isinstance(snapshot_path, Path)
            or snapshot_path.is_symlink()
            or not snapshot_path.is_dir()
        ):
            raise ValueError()
        root = snapshot_path.resolve(strict=True)
        collected: list[tuple[str, str, bytes]] = []
        total_bytes = 0
        for path in root.rglob("*"):
            metadata = path.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError()
            relative = path.relative_to(root).as_posix()
            relative_bytes = relative.encode("utf-8", "strict")
            if (
                not _is_safe_relative_path(relative)
                or len(relative_bytes) > MAX_VERIFIER_SNAPSHOT_PATH_BYTES
                or metadata.st_size > MAX_VERIFIER_SNAPSHOT_FILE_BYTES
            ):
                raise ValueError()
            if len(collected) >= MAX_VERIFIER_SNAPSHOT_FILES:
                raise ValueError()
            total_bytes += metadata.st_size
            if total_bytes > MAX_VERIFIER_SNAPSHOT_TOTAL_BYTES:
                raise ValueError()
            content = path.read_bytes()
            if len(content) != metadata.st_size:
                raise ValueError()
            mode = "100755" if metadata.st_mode & 0o111 else "100644"
            collected.append((relative, mode, content))
        collected.sort(key=lambda entry: entry[0])
        result = tuple(collected)
        if verifier_snapshot_tree_digest(result) != expected_tree_digest:
            raise ValueError()
        return result
    except Exception:
        raise ExecutionError(
            "execution verifier input: pinned snapshot is invalid"
        ) from None


def _run_snapshot_verifier_replay(
    *,
    request: ExecutionRequest,
    backend: ExecutorSandboxBackend,
    source_sandbox: object,
    verified_contents: tuple[tuple[str, str], ...],
    verified_contents_digest: str,
) -> str:
    """Replay once in a fresh copy of the exact local or remote snapshot."""

    pin = request.pinned_snapshot
    if pin is None and request.remote_snapshot is None:
        raise ExecutionError("execution verifier replay: snapshot binding is required")
    snapshot_tree_digest = _request_snapshot_tree_digest(request)
    if snapshot_tree_digest is None:
        raise ExecutionError("execution verifier replay: snapshot binding is invalid")
    if request.remote_snapshot is not None:
        _validate_live_remote_workspace(request)
        _revalidate_remote_snapshot(request)
    session = backend.create(request.snapshot_path, set(request.allowed_commands))
    try:
        if (
            session is source_sandbox
            or not isinstance(getattr(session, "snapshot", None), Path)
            or not isinstance(getattr(session, "workspace", None), Path)
            or not callable(getattr(session, "run", None))
            or not callable(getattr(session, "close", None))
            or session.workspace == getattr(source_sandbox, "workspace", None)
            or session.snapshot == getattr(source_sandbox, "snapshot", None)
            or session.workspace == session.snapshot
            or session.workspace.resolve()
            == getattr(source_sandbox, "workspace").resolve()
            or session.snapshot.resolve()
            == getattr(source_sandbox, "snapshot").resolve()
        ):
            raise ExecutionError("execution verifier replay: session is invalid")
        if (
            compute_snapshot_tree_digest(request.snapshot_path) != snapshot_tree_digest
            or compute_snapshot_tree_digest(session.snapshot) != snapshot_tree_digest
            or compute_snapshot_tree_digest(session.workspace) != snapshot_tree_digest
        ):
            raise ExecutionError("execution verifier replay: pinned tree mismatch")
        root = session.workspace.resolve(strict=True)
        for relative_path, content in verified_contents:
            if not _is_safe_relative_path(relative_path):
                raise ExecutionError("execution verifier replay: prepared path is invalid")
            target = session.workspace.joinpath(*Path(relative_path).parts)
            parent = target.parent
            missing_parents: list[Path] = []
            while parent != session.workspace and not parent.exists():
                missing_parents.append(parent)
                parent = parent.parent
            if parent.is_symlink() or not parent.is_dir():
                raise ExecutionError("execution verifier replay: prepared path is invalid")
            resolved_parent = parent.resolve(strict=True)
            if not resolved_parent.is_relative_to(root):
                raise ExecutionError("execution verifier replay: prepared path is invalid")
            for missing in reversed(missing_parents):
                missing.mkdir()
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ExecutionError("execution verifier replay: prepared path is invalid")
            target.write_text(content, encoding="utf-8")
        replay = session.run(request.test_command, timeout_seconds=request.test_timeout_seconds)
        if (
            getattr(replay, "argv", None) != request.test_command
            or isinstance(getattr(replay, "returncode", None), bool)
            or not isinstance(getattr(replay, "returncode", None), int)
            or replay.returncode != 0
        ):
            raise ExecutionError("execution verifier replay: command failed")
        if pin is not None:
            replay_binding = (
                "pinned-replay-v1",
                pin.repository_id,
                pin.commit_oid,
                pin.tree_digest,
            )
        else:
            claim_digest = _request_snapshot_claim_digest(request)
            if claim_digest is None:
                raise ExecutionError("execution verifier replay: remote claim is invalid")
            replay_binding = (
                "github-remote-replay-v1",
                request.repository_id,
                request.base_commit,
                snapshot_tree_digest,
                claim_digest,
            )
        return sha256_digest(
            replay_binding
            + (
                request.test_command,
                request.test_timeout_seconds,
                verified_contents_digest,
                replay.returncode,
            )
        )
    finally:
        session.close()


def validate_verifier_result(value: object, expected: VerifierInput) -> VerifierResult:
    """Validate and detach the exact bounded verifier response for one input."""

    if type(value) is not VerifierResult:
        raise ExecutionError("execution verifier: result shape is invalid")
    if (
        not _is_safe_label(value.process_id)
        or not _is_safe_label(value.base_commit)
        or (
            value.snapshot_tree_digest is not None
            and not _is_safe_digest(value.snapshot_tree_digest)
        )
        or (
            value.replay_result_digest is not None
            and not _is_safe_digest(value.replay_result_digest)
        )
        or not _is_safe_label(value.verifier_id)
        or type(value.verdict) is not VerifierVerdict
        or not isinstance(value.blocker_codes, tuple)
        or len(value.blocker_codes) > MAX_VERIFIER_BLOCKER_CODES
        or any(
            not isinstance(code, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", code) is None
            for code in value.blocker_codes
        )
        or value.evidence_origin != "local_test"
        or any(
            not _is_safe_digest(digest)
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
        or value.base_commit != expected.base_commit
        or value.snapshot_tree_digest != expected.snapshot_tree_digest
        or value.replay_result_digest != expected.replay_result_digest
        or value.patch_digest != expected.patch_digest
        or value.evidence_digest != expected.evidence_digest
        or value.verification_digest != expected.verification_digest
        or value.verified_contents_digest != expected.verified_contents_digest
    ):
        raise ExecutionError("execution verifier: result binding mismatch")
    return VerifierResult(
        process_id=value.process_id,
        base_commit=value.base_commit,
        snapshot_tree_digest=value.snapshot_tree_digest,
        replay_result_digest=value.replay_result_digest,
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
    if not isinstance(value, str):
        return False
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None:
        return True
    return re.fullmatch(
        r"docker-image:sha256:[0-9a-f]{64}/code:sha256:[0-9a-f]{64}", value
    ) is not None


def _is_safe_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
    )


def _validate_identity(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ExecutionError("execution request: identity field is invalid")


def _validate_worker_input(
    task_instruction: object,
    context_files: object,
    declared_change_paths: object,
) -> None:
    """Validate explicit instruction and caller-selected context without filesystem reads."""
    if task_instruction is None:
        pass
    else:
        if not isinstance(task_instruction, str) or not task_instruction:
            raise ExecutionError("execution request: worker input is invalid")
        try:
            instruction_bytes = task_instruction.encode("utf-8")
        except UnicodeEncodeError:
            raise ExecutionError("execution request: worker input is invalid") from None
        if len(instruction_bytes) > MAX_TASK_INSTRUCTION_BYTES:
            raise ExecutionError("execution request: worker input is invalid")
        for character in task_instruction:
            if character in ("\n", "\t"):
                continue
            if not character.isprintable():
                raise ExecutionError("execution request: worker input is invalid")
    if not isinstance(context_files, tuple):
        raise ExecutionError("execution request: worker input is invalid")
    if len(context_files) > MAX_CONTEXT_FILES:
        raise ExecutionError("execution request: worker input is invalid")
    if not isinstance(declared_change_paths, tuple):
        raise ExecutionError("execution request: worker input is invalid")
    declared_set = (
        set(declared_change_paths)
        if all(isinstance(path, str) for path in declared_change_paths)
        else set()
    )
    seen: set[str] = set()
    total_bytes = 0
    for entry in context_files:
        if type(entry) is not tuple or len(entry) != 2:
            raise ExecutionError("execution request: worker input is invalid")
        path, text = entry
        if not isinstance(path, str) or not isinstance(text, str):
            raise ExecutionError("execution request: worker input is invalid")
        if not path or path not in declared_set or not _is_safe_relative_path(path):
            raise ExecutionError("execution request: worker input is invalid")
        if path in seen:
            raise ExecutionError("execution request: worker input is invalid")
        seen.add(path)
        try:
            path_bytes = path.encode("utf-8")
            text_bytes = text.encode("utf-8")
        except UnicodeEncodeError:
            raise ExecutionError("execution request: worker input is invalid") from None
        if len(text_bytes) > MAX_CONTEXT_FILE_BYTES:
            raise ExecutionError("execution request: worker input is invalid")
        total_bytes += len(path_bytes) + len(text_bytes)
        if total_bytes > MAX_CONTEXT_TOTAL_BYTES:
            raise ExecutionError("execution request: worker input is invalid")


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
    remote_workspace = request.remote_workspace
    if remote_workspace is not None:
        try:
            from .remote_snapshot_workspace import MaterializedGitHubSnapshot

            if type(remote_workspace) is not MaterializedGitHubSnapshot:
                raise ValueError()
            workspace_path = remote_workspace.path
            workspace_snapshot = remote_workspace.snapshot
        except Exception:
            raise ExecutionError(
                "execution request: remote snapshot workspace is invalid"
            ) from None
        if snapshot != workspace_path or pinned_snapshot is not None:
            raise ExecutionError(
                "execution request: remote snapshot workspace binding is invalid"
            )
        if request.remote_snapshot is None:
            object.__setattr__(request, "remote_snapshot", workspace_snapshot)
        elif request.remote_snapshot != workspace_snapshot:
            raise ExecutionError(
                "execution request: remote snapshot workspace binding is invalid"
            )
    remote_snapshot = request.remote_snapshot
    if remote_snapshot is not None:
        from .github_snapshot import GitHubSnapshotContents

        if (
            type(remote_snapshot) is not GitHubSnapshotContents
            or pinned_snapshot is not None
            or request.repository_id
            != f"{remote_snapshot.claim.owner}/{remote_snapshot.claim.repository}"
            or request.base_commit != remote_snapshot.claim.commit_oid
        ):
            raise ExecutionError("execution request: remote snapshot binding is invalid")
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
    _validate_worker_input(
        request.task_instruction, request.context_files, request.declared_change_paths
    )
    detached = tuple((path, text) for path, text in request.context_files)
    object.__setattr__(request, "context_files", detached)


def _validate_live_remote_workspace(request: ExecutionRequest) -> None:
    workspace = request.remote_workspace
    if workspace is None:
        return
    try:
        from .remote_snapshot_workspace import MaterializedGitHubSnapshot

        if (
            type(workspace) is not MaterializedGitHubSnapshot
            or workspace.path != request.snapshot_path
            or workspace.snapshot != request.remote_snapshot
        ):
            raise ValueError()
    except Exception:
        raise ExecutionError(
            "execution request: remote snapshot workspace is invalid"
        ) from None


def _revalidate_remote_snapshot(request: ExecutionRequest) -> None:
    snapshot = request.remote_snapshot
    if snapshot is None:
        return
    try:
        from .github_snapshot import (
            GitHubBlobClaim,
            GitHubSnapshotClaim,
            GitHubSnapshotContents,
        )

        if type(snapshot) is not GitHubSnapshotContents:
            raise ValueError()
        claim = snapshot.claim
        if type(claim) is not GitHubSnapshotClaim or type(snapshot.files) is not tuple:
            raise ValueError()
        detached = GitHubSnapshotContents(
            claim=GitHubSnapshotClaim(
                owner=claim.owner,
                repository=claim.repository,
                commit_oid=claim.commit_oid,
                tree_oid=claim.tree_oid,
                content_digest=claim.content_digest,
                selected_paths=claim.selected_paths,
                evidence_origin=claim.evidence_origin,
            ),
            files=tuple(
                GitHubBlobClaim(
                    path=blob.path,
                    mode=blob.mode,
                    sha=blob.sha,
                    size=blob.size,
                    content=blob.content,
                    content_digest=blob.content_digest,
                    evidence_origin=blob.evidence_origin,
                )
                for blob in snapshot.files
                if type(blob) is GitHubBlobClaim
            ),
        )
        if len(detached.files) != len(snapshot.files):
            raise ValueError()
    except Exception:
        raise ExecutionError("execution request: remote snapshot is invalid") from None
    object.__setattr__(request, "remote_snapshot", detached)


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
