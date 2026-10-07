"""Fail-closed CLI for local demos and injected pinned-snapshot execution.

The no-argument demo and explicit remote-fixture-preview mode are fixed
synthetic runs. Pinned remote execution requires an explicitly injected
Control Plane runtime profile. No credential lookup is performed here. The
sandbox or verifier's security properties are not inferred by the CLI.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .executor import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    MAX_VERIFIER_SNAPSHOT_FILE_BYTES,
    MAX_VERIFIER_SNAPSHOT_TOTAL_BYTES,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    run_local_execution,
)
from .openai_worker import OpenAIProposalWorker, ResponsesModelResult
from .credential_source import CredentialSource
from .deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
    DeepSeekProposalWorker,
)
from .deepseek_http_channel import DeepSeekHTTPChannel
from .durable_stage import SQLiteStagedArtifactStore
from .github_snapshot import (
    GitHubBlobClaim,
    GitHubSnapshotError,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
    GitHubSnapshotRequest,
    read_github_snapshot_contents,
    read_github_snapshot_metadata,
)
from .github_http_transport import (
    GitHubAnonymousSnapshotTransport,
    GitHubRateLimitEvidence,
)
from .remote_snapshot_pipeline import run_remote_snapshot_execution
from .digests import sha256_bytes, sha256_digest
from .pinned_snapshot import SNAPSHOT_DIGEST_CANONICALIZATION
from .publication_seed import build_publication_seed, derive_publication_intent
from .sandbox import DockerSandboxBackend, LocalProcessSandboxBackend
from .verifier_container import DockerContainerVerifier, VerifierContainerConfig
from .verifier_process import SubprocessVerifier, VerifierProcessConfig

DEMO_NAME = "worker-cli-synthetic"
DEMO_DECLARED_PATHS = ("calculator.py",)
DEMO_ALLOWED_COMMANDS = frozenset({"python3"})
DEMO_TEST_COMMAND = ("python3", "-m", "unittest", "discover", "-s", ".", "-p", "test_calculator.py", "-q")
DEMO_INSTRUCTION = "Add a synthetic demo comment to calculator.py"
DEMO_CONTEXT = (("calculator.py", "synthetic demo context"),)
DEMO_PROCESS_ID = "process-cli-demo-001"
DEMO_TASK_ID = "task-cli-demo-001"
DEMO_REPOSITORY_ID = "fixture-repository"
DEMO_BASE_COMMIT = "fixture-base-cli-001"
DEMO_VERIFIER_ID = "cli-demo-verifier"
REMOTE_DEMO_NAME = "remote-fixture-publication-preview"
DEEPSEEK_REMOTE_DEMO_NAME = "deepseek-remote-fixture-publication-preview"
REMOTE_DEMO_PROCESS_ID = "process-remote-fixture-cli-001"
REMOTE_DEMO_TASK_ID = "task-remote-fixture-cli-001"
REMOTE_DEMO_COMMIT = "c" * 40
REMOTE_DEMO_TREE = "d" * 40
REMOTE_DEMO_VERIFIER_NONCE = "e" * 64
REMOTE_DEMO_BRANCH = "agent/remote-fixture-preview"
REMOTE_REPOSITORY_OWNER = "SoldatovAlexander"
REMOTE_REPOSITORY_NAME = "brainbooster_full_v11"
REMOTE_REPOSITORY_COMMIT = "2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e"
REMOTE_REPOSITORY_TREE = "2007066217aadafd9887fb3e3069220333b4fddb"
REMOTE_REPOSITORY_FILE_COUNT = 23
REMOTE_REPOSITORY_CONTENT_DIGEST = (
    "sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad"
)
REMOTE_EXECUTION_IMAGE = (
    "python:3.11.16-slim@sha256:"
    "8b29ec24b5f3c929a79b55772b95c93311b7133f1cf7fa0a6141ef621f8e3c57"
)
_IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IMAGE_PATH_COMPONENT = r"[a-z0-9]+(?:[._-][a-z0-9]+)*"
_IMAGE_REGISTRY = (
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*(?::[0-9]{1,5})?"
)
_PINNED_IMAGE_REFERENCE_PATTERN = re.compile(
    rf"(?:{_IMAGE_REGISTRY}/)?{_IMAGE_PATH_COMPONENT}"
    rf"(?:/{_IMAGE_PATH_COMPONENT})*"
    rf"(?::[A-Za-z0-9_][A-Za-z0-9_.-]{{0,127}})?"
    rf"@sha256:[0-9a-f]{{64}}\Z"
)
_SAFE_EXECUTION_FAILURE_CODES = frozenset(
    {
        "worker-failed",
        "verification-replay-failed",
        "verifier-failed",
        "verifier-not-pass",
        "verifier-trust-unestablished",
        "verifier-attestation-invalid",
        "stage-persistence-failed",
    }
)
_READINESS_THRESHOLD = 25
_READINESS_MAX_AGE_SECONDS = 120.0
_CARD_ID_PATTERN = re.compile(r"EXP-[0-9]{3,6}\Z")
_PERMIT_SEAL = object()


@dataclass(frozen=True)
class RemoteSnapshotExecutionProfile:
    """Control Plane-approved task and runtime dependencies for one remote run.

    This object is injected by the trusted outer runtime; it is not populated
    from CLI arguments, repository files, environment variables, or a prompt.
    """

    process_id: str
    task_id: str
    task_instruction: str
    declared_change_paths: tuple[str, ...]
    allowed_commands: frozenset[str]
    test_command: tuple[str, ...]
    worker: object
    verifier: object
    sandbox_backend: object
    stage_sink: object
    test_timeout_seconds: int = 30
    stage_database_path: Path | None = None


class RemoteExecutionPermitError(ValueError):
    """A single-use Control Plane authorization is absent, stale, or invalid."""


class RemoteExecutionPermit:
    """Process-local one-use authorization for one fresh pinned remote run.

    This limits accidental reuse only. It is not authentication or a security
    boundary against code running inside the trusted Control Plane process.
    """

    def __init__(
        self,
        *,
        seal: object,
        card_id: str,
        process_id: str,
        task_id: str,
        readiness: GitHubRateLimitEvidence,
    ) -> None:
        if seal is not _PERMIT_SEAL:
            raise RemoteExecutionPermitError("remote CLI authorization is invalid")
        self.card_id = card_id
        self.process_id = process_id
        self.task_id = task_id
        self.owner = REMOTE_REPOSITORY_OWNER
        self.repository = REMOTE_REPOSITORY_NAME
        self.commit_oid = REMOTE_REPOSITORY_COMMIT
        self.readiness = readiness
        self._lock = threading.Lock()
        self._consumed = False

    def __repr__(self) -> str:
        return (
            "RemoteExecutionPermit("
            f"card_id={self.card_id!r}, process_id={self.process_id!r}, "
            f"task_id={self.task_id!r}, consumed={self._consumed})"
        )

    def validate(self, *, process_id: str, task_id: str) -> None:
        with self._lock:
            if self._consumed:
                raise RemoteExecutionPermitError(
                    "remote CLI authorization is unavailable"
                )
            self._validate_binding(process_id=process_id, task_id=task_id)

    def consume(self, *, process_id: str, task_id: str) -> None:
        with self._lock:
            if self._consumed:
                raise RemoteExecutionPermitError(
                    "remote CLI authorization is unavailable"
                )
            # Burn before checking bindings: a failed attempt cannot be probed
            # or retried with the same permit.
            self._consumed = True
            self._validate_binding(process_id=process_id, task_id=task_id)

    def _validate_binding(self, *, process_id: str, task_id: str) -> None:
        age = time.monotonic() - self.readiness.observed_monotonic
        if (
            self.process_id != process_id
            or self.task_id != task_id
            or self.owner != REMOTE_REPOSITORY_OWNER
            or self.repository != REMOTE_REPOSITORY_NAME
            or self.commit_oid != REMOTE_REPOSITORY_COMMIT
            or self.readiness.status != 200
            or self.readiness.remaining is None
            or self.readiness.remaining < _READINESS_THRESHOLD
            or self.readiness.reset_unix is None
            or age < 0
            or age > _READINESS_MAX_AGE_SECONDS
        ):
            raise RemoteExecutionPermitError(
                "remote CLI authorization is unavailable"
            )


def issue_remote_execution_permit(
    *,
    card_id: str,
    process_id: str,
    task_id: str,
    readiness: GitHubRateLimitEvidence,
    provider_call_approved: bool,
) -> RemoteExecutionPermit:
    """Issue one ephemeral permit after an explicit Control Plane decision.

    `provider_call_approved` is a trusted Control Plane input, not authentication;
    callers must obtain the user's fresh approval outside this module.
    """

    try:
        if (
            type(card_id) is not str
            or _CARD_ID_PATTERN.fullmatch(card_id) is None
            or type(process_id) is not str
            or type(task_id) is not str
            or type(provider_call_approved) is not bool
            or provider_call_approved is not True
            or type(readiness) is not GitHubRateLimitEvidence
            or readiness.status != 200
            or readiness.remaining is None
            or readiness.remaining < _READINESS_THRESHOLD
            or readiness.reset_unix is None
        ):
            raise ValueError()
        permit = RemoteExecutionPermit(
            seal=_PERMIT_SEAL,
            card_id=card_id,
            process_id=process_id,
            task_id=task_id,
            readiness=readiness,
        )
        permit.validate(process_id=process_id, task_id=task_id)
        return permit
    except Exception:
        raise RemoteExecutionPermitError(
            "remote CLI authorization is unavailable"
        ) from None


def build_deepseek_remote_execution_profile(
    *,
    process_id: str,
    task_id: str,
    task_instruction: str,
    declared_change_paths: tuple[str, ...],
    allowed_commands: frozenset[str],
    test_command: tuple[str, ...],
    credential_source: CredentialSource,
    verifier: object,
    sandbox_backend: object,
    stage_sink: object,
    test_timeout_seconds: int = 30,
) -> RemoteSnapshotExecutionProfile:
    """Assemble one pinned CLI profile with a lazily injected DeepSeek source.

    This factory does not resolve or call the credential source. It creates a
    one-attempt HTTP channel; the secret is requested only if the Worker is
    later invoked after pinned snapshot intake and the executor's checks.
    """

    if not callable(credential_source):
        raise ValueError("remote CLI runtime is unavailable")
    try:
        profile = RemoteSnapshotExecutionProfile(
            process_id=process_id,
            task_id=task_id,
            task_instruction=task_instruction,
            declared_change_paths=declared_change_paths,
            allowed_commands=allowed_commands,
            test_command=test_command,
            worker=DeepSeekProposalWorker(
                channel=DeepSeekHTTPChannel(credential_source)
            ),
            verifier=verifier,
            sandbox_backend=sandbox_backend,
            stage_sink=stage_sink,
            test_timeout_seconds=test_timeout_seconds,
        )
        return _validate_remote_execution_profile(profile)
    except Exception:
        raise ValueError("remote CLI runtime is unavailable") from None


class _UnopenedStageSink:
    """Shape-only dependency used to validate a profile before opening SQLite."""

    def save(self, _artifact: object) -> None:
        raise RuntimeError("stage store is not open")

    def load(self, _digest: str) -> None:
        raise RuntimeError("stage store is not open")


def run_remote_snapshot_with_runtime(
    *,
    process_id: str,
    task_id: str,
    task_instruction: str,
    declared_change_paths: tuple[str, ...],
    allowed_commands: frozenset[str],
    test_command: tuple[str, ...],
    execution_image: str,
    credential_source: CredentialSource,
    verifier_config: VerifierContainerConfig,
    stage_database_path: Path | str,
    execution_permit: RemoteExecutionPermit,
    test_timeout_seconds: int = 30,
    stdout=None,
    stderr=None,
) -> int:
    """Run the pinned CLI with explicit Docker, credential and SQLite wiring.

    This function performs the remote workflow when called. It never discovers
    configuration from the environment or filesystem; in particular the
    credential source remains lazy and is called only by the Worker. It is not
    called from the module's default CLI entrypoint.
    """

    if (
        type(verifier_config) is not VerifierContainerConfig
        or type(execution_image) is not str
        or (
            _IMAGE_ID_PATTERN.fullmatch(execution_image) is None
            and _PINNED_IMAGE_REFERENCE_PATTERN.fullmatch(execution_image) is None
        )
    ):
        raise ValueError("remote CLI runtime is unavailable")
    if isinstance(stage_database_path, Path):
        database_path = stage_database_path
    elif type(stage_database_path) is str and stage_database_path:
        database_path = Path(stage_database_path)
    else:
        raise ValueError("remote CLI runtime is unavailable")
    try:
        if (
            not database_path.is_absolute()
            or str(database_path) == ":memory:"
            or database_path.is_symlink()
            or (database_path.exists() and not database_path.is_file())
        ):
            raise ValueError()
        verifier = DockerContainerVerifier(verifier_config)
        sandbox_backend = DockerSandboxBackend(execution_image)
        validated_profile = build_deepseek_remote_execution_profile(
            process_id=process_id,
            task_id=task_id,
            task_instruction=task_instruction,
            declared_change_paths=declared_change_paths,
            allowed_commands=allowed_commands,
            test_command=test_command,
            credential_source=credential_source,
            verifier=verifier,
            sandbox_backend=sandbox_backend,
            stage_sink=_UnopenedStageSink(),
            test_timeout_seconds=test_timeout_seconds,
        )
        validated_profile = replace(
            validated_profile, stage_database_path=database_path
        )
        _validate_remote_execution_profile(validated_profile)
        if type(execution_permit) is not RemoteExecutionPermit:
            raise ValueError()
        execution_permit.validate(
            process_id=validated_profile.process_id,
            task_id=validated_profile.task_id,
        )
    except Exception:
        raise ValueError("remote CLI runtime is unavailable") from None

    with SQLiteStagedArtifactStore(database_path) as stage_store:
        profile = replace(validated_profile, stage_sink=stage_store)
        return main(
            ["--remote-snapshot-execute"],
            stdout=stdout,
            stderr=stderr,
            remote_execution_profile=profile,
            execution_permit=execution_permit,
        )

_FIXTURE_ORIGINAL = (
    '"""Tiny repository fixture used by the repository-change process tests."""\n'
    "\n"
    "\n"
    "def add(left: int, right: int) -> int:\n"
    "    return left + right\n"
)
_FIXTURE_PROPOSED = _FIXTURE_ORIGINAL + "\n# cli-demo-synthetic\n"


class _DemoChannel:
    """Local fake Responses channel returning a fixed synthetic proposal."""

    def __init__(self) -> None:
        self.calls = 0

    def create_response(self, payload: dict, *, timeout_seconds: float) -> ResponsesModelResult:
        self.calls += 1
        proposal = {"changes": [{"path": "calculator.py", "content": _FIXTURE_PROPOSED}]}
        return ResponsesModelResult(status="completed", output_text=json.dumps(proposal))


class _DemoVerifier:
    """Explicitly demonstrational verifier; not independent."""

    def __init__(self) -> None:
        self.calls = 0

    def verify(self, prepared: VerifierInput) -> VerifierResult:
        self.calls += 1
        return VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id=DEMO_VERIFIER_ID,
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
        )


def _demo_snapshot_path() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "repository" / "project"


def _demo_request() -> ExecutionRequest:
    return ExecutionRequest(
        process_id=DEMO_PROCESS_ID,
        task_id=DEMO_TASK_ID,
        repository_id=DEMO_REPOSITORY_ID,
        base_commit=DEMO_BASE_COMMIT,
        snapshot_path=_demo_snapshot_path(),
        allowed_commands=DEMO_ALLOWED_COMMANDS,
        declared_change_paths=DEMO_DECLARED_PATHS,
        test_command=DEMO_TEST_COMMAND,
        task_instruction=DEMO_INSTRUCTION,
        context_files=DEMO_CONTEXT,
    )


def _remote_demo_snapshot() -> tuple[GitHubSnapshotContents, str]:
    """Build a fixed synthetic full snapshot from the checked-in calculator fixture."""
    content = _FIXTURE_ORIGINAL.encode("utf-8")
    blob = GitHubBlobClaim(
        path="calculator.py",
        mode="100644",
        sha=hashlib.sha1(
            b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        ).hexdigest(),
        size=len(content),
        content=content,
        content_digest=sha256_bytes(content),
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
    return (
        GitHubSnapshotContents(
            claim=GitHubSnapshotClaim(
                owner="FixtureOwner",
                repository="calculator-fixture",
                commit_oid=REMOTE_DEMO_COMMIT,
                tree_oid=REMOTE_DEMO_TREE,
                content_digest=content_digest,
            ),
            files=(blob,),
        ),
        content.decode("utf-8"),
    )


def _remote_demo_worker() -> OpenAIProposalWorker:
    _, base_content = _remote_demo_snapshot()
    proposed = base_content + "\n# remote-fixture-preview\n"
    return OpenAIProposalWorker(channel=_FixedRemoteDemoChannel(proposed))


def _remote_deepseek_demo_worker() -> DeepSeekProposalWorker:
    _, base_content = _remote_demo_snapshot()
    proposed = base_content + "\n# deepseek-remote-fixture-preview\n"
    return DeepSeekProposalWorker(channel=_FixedDeepSeekRemoteDemoChannel(proposed))


class _FixedRemoteDemoChannel:
    """Fake Responses transport with one hard-coded fixture-only proposal."""

    def __init__(self, content: str) -> None:
        self._content = content

    def create_response(self, payload: dict, *, timeout_seconds: float) -> ResponsesModelResult:
        del payload, timeout_seconds
        return ResponsesModelResult(
            status="completed",
            output_text=json.dumps(
                {"changes": [{"path": "calculator.py", "content": self._content}]},
                separators=(",", ":"),
            ),
        )


class _FixedDeepSeekRemoteDemoChannel:
    """Fake Chat Completions channel with one synthetic fixture proposal."""

    def __init__(self, content: str) -> None:
        self._content = content

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        del payload, timeout_seconds
        return ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=json.dumps(
                            {"changes": [{"path": "calculator.py", "content": self._content}]},
                            separators=(",", ":"),
                        ),
                        reasoning_content="synthetic reasoning is ignored",
                    ),
                ),
            )
        )


def _remote_demo_verifier() -> SubprocessVerifier:
    return SubprocessVerifier(
        VerifierProcessConfig(
            executable=sys.executable,
            argv=(
                sys.executable,
                "-m",
                "app_contracts.verifier_container_entrypoint",
                "--invocation-nonce=" + REMOTE_DEMO_VERIFIER_NONCE,
            ),
            timeout_seconds=30,
            max_stdout_bytes=65_536,
            max_stderr_bytes=4_096,
        ),
        environ={"PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )


def _run_remote_fixture_preview(
    worker: object, verifier: object, *, deepseek: bool = False
) -> dict:
    snapshot, base_content = _remote_demo_snapshot()
    if worker is not None:
        active_worker = worker
    elif deepseek:
        active_worker = _remote_deepseek_demo_worker()
    else:
        active_worker = _remote_demo_worker()
    active_verifier = verifier if verifier is not None else _remote_demo_verifier()
    result = run_remote_snapshot_execution(
        snapshot,
        process_id=REMOTE_DEMO_PROCESS_ID,
        task_id=REMOTE_DEMO_TASK_ID,
        task_instruction="Add a harmless comment to the synthetic calculator fixture",
        declared_change_paths=("calculator.py",),
        allowed_commands=frozenset({Path(sys.executable).name}),
        test_command=(
            sys.executable,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        ),
        worker=active_worker,
        verifier=active_verifier,
        sandbox_backend=LocalProcessSandboxBackend(),
        context_files=(("calculator.py", base_content),),
        require_durable_stage=False,
    )
    if result.status is not ExecutionStatus.VERIFIED:
        raise ValueError("remote fixture preview did not verify")
    seed = build_publication_seed(
        # The execution API owns and closes the workspace, so reconstruct the
        # exact request binding while the helper returns only an execution result.
        _remote_demo_request(snapshot, base_content),
        result,
    )
    branch = "agent/deepseek-remote-fixture-preview" if deepseek else REMOTE_DEMO_BRANCH
    intent = derive_publication_intent(seed, branch, "master")
    return {
        "status": "preview_ready",
        "demo": DEEPSEEK_REMOTE_DEMO_NAME if deepseek else REMOTE_DEMO_NAME,
        "evidence_origin": "local_synthetic_test",
        "repository_id": intent.repository_id,
        "base_commit": intent.base_commit,
        "base_branch": intent.base_branch,
        "branch_preview": intent.branch,
        "staged_change_digest": intent.staged_change_digest,
        "snapshot_claim_digest": seed.snapshot_claim_digest,
        "verified_contents_digest": seed.verified_contents_digest,
        "publication": "not_attempted",
    }


def _remote_demo_request(snapshot: GitHubSnapshotContents, base_content: str) -> ExecutionRequest:
    # Rebuild the same request identity solely to let the pure seed constructor
    # check the just-produced evidence. Its materialized path is ephemeral and
    # no file or target repository is read here.
    return ExecutionRequest(
        process_id=REMOTE_DEMO_PROCESS_ID,
        task_id=REMOTE_DEMO_TASK_ID,
        repository_id=f"{snapshot.claim.owner}/{snapshot.claim.repository}",
        base_commit=snapshot.claim.commit_oid,
        snapshot_path=_demo_snapshot_path(),
        allowed_commands=frozenset({Path(sys.executable).name}),
        declared_change_paths=("calculator.py",),
        test_command=(
            sys.executable,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        ),
        task_instruction="Add a harmless comment to the synthetic calculator fixture",
        context_files=(("calculator.py", base_content),),
        remote_snapshot=snapshot,
    )


def _remote_snapshot_metadata() -> dict:
    request = GitHubSnapshotRequest(
        owner=REMOTE_REPOSITORY_OWNER,
        repository=REMOTE_REPOSITORY_NAME,
        commit_oid=REMOTE_REPOSITORY_COMMIT,
    )
    tree = read_github_snapshot_metadata(
        request, GitHubAnonymousSnapshotTransport()
    )
    if (
        tree.owner != REMOTE_REPOSITORY_OWNER
        or tree.repository != REMOTE_REPOSITORY_NAME
        or tree.tree_oid != REMOTE_REPOSITORY_TREE
    ):
        raise ValueError("remote snapshot pin mismatch")
    blobs = tuple(entry for entry in tree.entries if entry.entry_type == "blob")
    if len(blobs) != REMOTE_REPOSITORY_FILE_COUNT or any(
        type(entry.size) is not int for entry in blobs
    ):
        raise ValueError("remote snapshot metadata is incomplete")
    sizes = tuple(entry.size for entry in blobs)
    total_bytes = sum(sizes)
    return {
        "schema": "github-snapshot-metadata/v1",
        "status": "snapshot_metadata_ready",
        "evidence_origin": tree.evidence_origin,
        "authenticated": False,
        "repository_id": f"{tree.owner}/{tree.repository}",
        "commit": REMOTE_REPOSITORY_COMMIT,
        "tree": tree.tree_oid,
        "blob_count": len(blobs),
        "total_blob_bytes": total_bytes,
        "max_blob_bytes": max(sizes, default=0),
        "executable_blob_count": sum(entry.mode == "100755" for entry in blobs),
        "blobs_over_verifier_file_limit": sum(
            size > MAX_VERIFIER_SNAPSHOT_FILE_BYTES for size in sizes
        ),
        "total_over_verifier_limit": total_bytes > MAX_VERIFIER_SNAPSHOT_TOTAL_BYTES,
        "blob_contents_fetched": False,
        "snapshot_content_verified": False,
    }


def _validate_remote_execution_profile(
    profile: object,
) -> RemoteSnapshotExecutionProfile:
    if type(profile) is not RemoteSnapshotExecutionProfile:
        raise ValueError("remote CLI runtime is unavailable")
    if (
        not callable(getattr(profile.worker, "propose", None))
        or not callable(getattr(profile.verifier, "verify", None))
        or not callable(getattr(profile.sandbox_backend, "create", None))
        or not callable(getattr(profile.stage_sink, "save", None))
        or not callable(getattr(profile.stage_sink, "load", None))
    ):
        raise ValueError("remote CLI runtime is unavailable")
    if profile.stage_database_path is not None:
        _validate_stage_database_locator(profile.stage_database_path)
    # Reuse the execution contract before any public API request so malformed
    # IDs, path scopes, command allowlists, or test arguments spend no rate limit.
    ExecutionRequest(
        process_id=profile.process_id,
        task_id=profile.task_id,
        repository_id=f"{REMOTE_REPOSITORY_OWNER}/{REMOTE_REPOSITORY_NAME}",
        base_commit=REMOTE_REPOSITORY_COMMIT,
        snapshot_path=Path.cwd(),
        allowed_commands=profile.allowed_commands,
        declared_change_paths=profile.declared_change_paths,
        test_command=profile.test_command,
        test_timeout_seconds=profile.test_timeout_seconds,
        task_instruction=profile.task_instruction,
    )
    return profile


def _validate_stage_database_locator(path: object) -> Path:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or path.is_symlink()
        or (path.exists() and not path.is_file())
    ):
        raise ValueError("remote CLI runtime is unavailable")
    return path


def _run_pinned_remote_execution(
    profile: RemoteSnapshotExecutionProfile,
) -> dict:
    profile = _validate_remote_execution_profile(profile)
    request = GitHubSnapshotRequest(
        owner=REMOTE_REPOSITORY_OWNER,
        repository=REMOTE_REPOSITORY_NAME,
        commit_oid=REMOTE_REPOSITORY_COMMIT,
    )
    snapshot = read_github_snapshot_contents(
        request,
        GitHubAnonymousSnapshotTransport(timeout_seconds=15),
    )
    claim = snapshot.claim
    if (
        claim.owner != REMOTE_REPOSITORY_OWNER
        or claim.repository != REMOTE_REPOSITORY_NAME
        or claim.commit_oid != REMOTE_REPOSITORY_COMMIT
        or claim.tree_oid != REMOTE_REPOSITORY_TREE
        or claim.content_digest != REMOTE_REPOSITORY_CONTENT_DIGEST
        or not claim.full_snapshot
        or len(snapshot.files) != REMOTE_REPOSITORY_FILE_COUNT
    ):
        raise ValueError("remote snapshot pin mismatch")
    files_by_path = {blob.path: blob for blob in snapshot.files}
    if any(path not in files_by_path for path in profile.declared_change_paths):
        raise ValueError("remote CLI request is invalid")
    context_files = tuple(
        (
            path,
            files_by_path[path].content.decode("utf-8", errors="strict"),
        )
        for path in profile.declared_change_paths
    )
    result = run_remote_snapshot_execution(
        snapshot,
        process_id=profile.process_id,
        task_id=profile.task_id,
        task_instruction=profile.task_instruction,
        declared_change_paths=profile.declared_change_paths,
        allowed_commands=profile.allowed_commands,
        test_command=profile.test_command,
        test_timeout_seconds=profile.test_timeout_seconds,
        worker=profile.worker,
        verifier=profile.verifier,
        sandbox_backend=profile.sandbox_backend,
        context_files=context_files,
        stage_sink=profile.stage_sink,
    )
    return _remote_execution_evidence(
        result, stage_database_path=profile.stage_database_path
    )


def _remote_execution_evidence(
    result: ExecutionResult, *, stage_database_path: Path | None = None
) -> dict:
    if type(result) is not ExecutionResult:
        raise ValueError("remote CLI execution result is invalid")
    base = {
        "schema": "remote-snapshot-execution-evidence/v1",
        "evidence_origin": "github_rest_api_claim",
        "repository_id": f"{REMOTE_REPOSITORY_OWNER}/{REMOTE_REPOSITORY_NAME}",
        "commit": REMOTE_REPOSITORY_COMMIT,
        "tree": REMOTE_REPOSITORY_TREE,
        "content_digest": REMOTE_REPOSITORY_CONTENT_DIGEST,
        "external_write": False,
        "approval": "not_created",
        "publication": "not_attempted",
        "limitations": [
            "snapshot-provenance-is-unauthenticated-github-api-claim",
            "runtime-components-are-injected-by-control-plane",
            "independent-verifier-trust-is-not-attested-by-this-cli",
            "production-durability-is-not-established",
        ],
    }
    attestation_fields = (
        result.verifier_attestation_digest,
        result.verifier_attestation_key_id,
        result.verifier_attestation_profile_digest,
        result.verifier_signature_valid,
        result.verifier_independent_host_trust_established,
    )
    if any(value is not None for value in attestation_fields):
        digest, key_id, profile_digest, signature_valid, independent_host = attestation_fields
        attestation = None
        failure_code = "verifier-attestation-invalid"
        if (
            isinstance(digest, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is not None
            and isinstance(key_id, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", key_id) is not None
            and isinstance(profile_digest, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", profile_digest) is not None
            and signature_valid is True
            and independent_host is False
        ):
            failure_code = "verifier-trust-unestablished"
            attestation = {
                "attestation_digest": digest,
                "key_id": key_id,
                "verifier_profile_digest": profile_digest,
                "signature_valid": True,
                "independent_host_trust_established": False,
            }
        evidence = {**base, "status": "failed", "failure_code": failure_code}
        if attestation is not None:
            evidence["verifier_attestation"] = attestation
        return evidence
    if result.status == ExecutionStatus.VERIFIED:
        digests = {
            "snapshot_claim_digest": result.snapshot_claim_digest,
            "verified_contents_digest": result.verified_contents_digest,
            "verification_digest": result.verification_digest,
            "staged_change_digest": result.staged_change_digest,
        }
        if any(
            not isinstance(value, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            for value in digests.values()
        ):
            raise ValueError("remote CLI evidence is invalid")
        verifier_id = getattr(result.verifier_result, "verifier_id", None)
        if not isinstance(verifier_id, str) or not verifier_id:
            raise ValueError("remote CLI evidence is invalid")
        evidence = {
            **base,
            "status": "verified",
            **digests,
            "verifier_identity_digest": "sha256:"
            + hashlib.sha256(verifier_id.encode("utf-8")).hexdigest(),
        }
        if stage_database_path is not None:
            validated_path = _validate_stage_database_locator(stage_database_path)
            if not validated_path.is_file():
                raise ValueError("remote CLI evidence is invalid")
            connection = None
            try:
                connection = sqlite3.connect(
                    f"{validated_path.resolve(strict=True).as_uri()}?mode=ro&immutable=1",
                    uri=True,
                )
                connection.execute("PRAGMA schema_version").fetchone()
            except Exception:
                raise ValueError("remote CLI evidence is invalid") from None
            finally:
                if connection is not None:
                    connection.close()
            evidence["stage_database_path"] = str(validated_path)
        return evidence
    failure_code = result.failure_code
    if failure_code not in _SAFE_EXECUTION_FAILURE_CODES:
        failure_code = "remote-snapshot-execution-failed"
    return {**base, "status": "failed", "failure_code": failure_code}


def main(
    argv=None,
    worker=None,
    verifier=None,
    stdout=None,
    stderr=None,
    *,
    remote_execution_profile: RemoteSnapshotExecutionProfile | None = None,
    execution_permit: RemoteExecutionPermit | None = None,
) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr
    if argv == ["--remote-snapshot-execute"]:
        if remote_execution_profile is None:
            stdout.write(
                '{"status":"error","failure_code":"remote-execution-runtime-unavailable"}\n'
            )
            return 2
        try:
            _validate_remote_execution_profile(remote_execution_profile)
        except Exception:
            stdout.write(
                '{"status":"error","failure_code":"remote-execution-profile-invalid"}\n'
            )
            return 2
        try:
            if type(execution_permit) is not RemoteExecutionPermit:
                raise ValueError()
            execution_permit.consume(
                process_id=remote_execution_profile.process_id,
                task_id=remote_execution_profile.task_id,
            )
        except Exception:
            stdout.write(
                '{"status":"error","failure_code":"remote-execution-authorization-unavailable"}\n'
            )
            return 2
        try:
            payload = _run_pinned_remote_execution(remote_execution_profile)
        except GitHubSnapshotError as exc:
            failure_code = (
                f"remote-snapshot-http-{exc.http_status}"
                if exc.http_status is not None
                else "remote-snapshot-fetch-failed"
            )
            payload = {"status": "failed", "failure_code": failure_code}
        except Exception:
            payload = {
                "status": "failed",
                "failure_code": "remote-snapshot-execution-failed",
            }
        stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        return 0 if payload.get("status") == "verified" else 1
    if argv == ["--remote-snapshot-metadata"]:
        try:
            payload = _remote_snapshot_metadata()
        except GitHubSnapshotError as exc:
            failure_code = (
                f"remote-snapshot-http-{exc.http_status}"
                if exc.http_status is not None
                else "remote-snapshot-fetch-failed"
            )
            stdout.write(
                json.dumps(
                    {"status": "failed", "failure_code": failure_code},
                    separators=(",", ":"),
                )
                + "\n"
            )
            return 1
        except Exception:
            stdout.write('{"status":"failed","failure_code":"remote-snapshot-fetch-failed"}\n')
            return 1
        stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    if argv == ["--remote-fixture-preview"]:
        try:
            payload = _run_remote_fixture_preview(worker, verifier)
        except Exception:
            stdout.write('{"status":"failed","failure_code":"remote-fixture-preview-failed"}\n')
            return 1
        stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    if argv == ["--deepseek-remote-fixture-preview"]:
        try:
            payload = _run_remote_fixture_preview(worker, verifier, deepseek=True)
        except Exception:
            stdout.write('{"status":"failed","failure_code":"deepseek-fixture-preview-failed"}\n')
            return 1
        stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    if len(argv) != 0:
        stderr.write('{"status":"error","failure_code":"cli-usage-invalid"}\n')
        return 2
    request = _demo_request()
    active_worker = worker if worker is not None else OpenAIProposalWorker(channel=_DemoChannel())
    active_verifier = verifier if verifier is not None else _DemoVerifier()
    try:
        result = run_local_execution(request, active_worker, verifier=active_verifier)
    except Exception:
        stdout.write('{"status":"failed","failure_code":"cli-execution-failed"}\n')
        return 1
    if not isinstance(result, ExecutionResult):
        stdout.write('{"status":"failed","failure_code":"cli-execution-failed"}\n')
        return 1
    if result.status == ExecutionStatus.VERIFIED:
        stdout.write(
            json.dumps(
                {"status": "verified", "demo": DEMO_NAME, "evidence_origin": "local_test"}
            )
            + "\n"
        )
        return 0
    code = result.failure_code if isinstance(result.failure_code, str) and result.failure_code else "cli-execution-failed"
    stdout.write(json.dumps({"status": "failed", "failure_code": code}) + "\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
