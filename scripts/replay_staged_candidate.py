"""Replay one saved, verified candidate through the fixed public-snapshot path.

This is an operator tool for the pinned BrainBooster experiment. It has no
Worker channel, credential source, approval, or publication adapter. Its only
input data is a validated local staged artifact; the candidate is never taken
from CLI arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
for _import_path in (ROOT / "src",):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

from app_contracts.durable_stage import (  # noqa: E402
    DurableStageStoreError,
    SQLiteStagedArtifactStore,
    StagedArtifact,
)
from app_contracts.brainbooster_target_profile import (  # noqa: E402
    PINNED_COMMIT,
    PINNED_SNAPSHOT_TREE_DIGEST,
    PINNED_FILE_COUNT,
    PINNED_HTTP_DB_TEST_COMMAND,
    PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
    PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
    TARGET_RUNTIME_IMAGE_ID,
)
from app_contracts.verifier_image_pin import (  # noqa: E402
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.executor import ExecutionStatus, WorkerProposal  # noqa: E402
from app_contracts.observation_store import SQLiteObservationStore  # noqa: E402
from app_contracts.observer_runtime import (  # noqa: E402
    JournaledProposalWorker,
    WorkerJournalError,
)
from app_contracts.github_http_transport import (  # noqa: E402
    GitHubAnonymousSnapshotTransport,
    GitHubHTTPTransportError,
)
from app_contracts.github_git_commit_source import (  # noqa: E402
    GitHubRawCommitObjectSource,
)
from app_contracts.github_snapshot import (  # noqa: E402
    GitCommitObject,
    GitHubSnapshotRequest,
    GitHubSnapshotError,
    read_github_snapshot_contents,
)
from app_contracts.sandbox import DockerSandboxBackend  # noqa: E402
from app_contracts.stage_preview import render_stage_preview  # noqa: E402
from app_contracts.verifier_container import (  # noqa: E402
    DockerContainerVerifier,
    VerifierContainerConfig,
)
from app_contracts.pinned_verifier_cli import (  # noqa: E402
    PINNED_SIGNED_VERIFIER_ENDPOINT_URL,
    VERIFIER_TRUST_ARTIFACT_ARGUMENTS,
    has_any_verifier_trust_artifact_args,
    load_pinned_signed_verifier_client,
)
from app_contracts.signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE  # noqa: E402
from app_contracts.remote_snapshot_pipeline import run_remote_snapshot_execution  # noqa: E402
from app_contracts.repository_process import _safe_test_failure_category  # noqa: E402
from app_contracts.validator import ContractValidationError  # noqa: E402

ALLOWED_CHANGE_PATH = "backend/routes.py"
REMOTE_REPOSITORY_OWNER = PINNED_OWNER
REMOTE_REPOSITORY_NAME = PINNED_REPOSITORY
REMOTE_REPOSITORY_COMMIT = PINNED_COMMIT
REMOTE_REPOSITORY_TREE = PINNED_TREE
REMOTE_REPOSITORY_CONTENT_DIGEST = PINNED_SNAPSHOT_TREE_DIGEST
REMOTE_REPOSITORY_FILE_COUNT = PINNED_FILE_COUNT
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TASK_INSTRUCTION = (
    "In backend/routes.py, reject malformed or non-finite numeric fields in "
    "/save-session with HTTP 422 before any database write. Preserve valid "
    "behavior (HTTP 200 and exactly one expected row). Change only this route "
    "file; do not add unrelated changes."
)
_ALLOWED_COMMANDS = frozenset({"python3"})
_VERIFIER_ID = (
    f"docker-image:{VERIFIER_RUNTIME_IMAGE_ID}/code:{VERIFIER_RUNTIME_CODE_DIGEST}"
)
_REPLAY_FAILURE_CODES = {
    "replay: source and output databases must differ": "database-paths-invalid",
    "replay: source digest is invalid": "source-digest-invalid",
    "replay: runtime is unavailable": "runtime-unavailable",
    "replay: docker is unavailable": "runtime-unavailable",
    "replay: verifier trust material unavailable": "verifier-trust-material-unavailable",
    "replay: verifier backend configuration is invalid": "verifier-backend-configuration-invalid",
    "replay: readiness request failed": "readiness-request-failed",
    "replay: readiness HTTP status failed": "readiness-http-status-failed",
    "replay: readiness metadata is invalid": "readiness-metadata-invalid",
    "replay: readiness quota is insufficient": "readiness-quota-low",
    "replay: pinned snapshot fetch failed": "snapshot-fetch-failed",
    "replay: pinned snapshot mismatch": "snapshot-pin-mismatch",
    "replay: raw commit proof mismatch": "raw-commit-proof-mismatch",
    "replay: pinned target file is invalid": "snapshot-target-invalid",
    "replay: candidate verification failed": "candidate-verification-failed",
    "replay: exact stage readback failed": "stage-readback-failed",
    "replay: committed stage readback failed": "stage-readback-failed",
    "replay: output database commit failed": "stage-persist-failed",
    "replay: evidence is invalid": "evidence-validation-failed",
    "replay: source stage is invalid": "source-stage-invalid",
    "replay: source database is unavailable": "source-stage-invalid",
    "replay: output database path is unavailable": "output-path-invalid",
    "replay: database paths are invalid": "output-path-invalid",
    "replay: output database already exists": "output-path-invalid",
}
_SAFE_TARGET_TEST_FAILURE_CODES = frozenset(
    {
        "readiness-exit",
        "readiness-timeout",
        "malformed-status",
        "malformed-no-write",
        "overflow-status",
        "overflow-no-write",
        "sqlite-range-status",
        "sqlite-range-no-write",
        "valid-status",
        "valid-body",
        "valid-row",
    }
)
_TEST_FAILURE_MESSAGE_PREFIX = (
    "verification failed; staged change was not created: "
)


class ReplayError(ValueError):
    """A stored-candidate replay failed a bounded validation gate."""


def _safe_failure_marker(error: object) -> str:
    """Render only a fixed failure category; never expose exception text."""

    code = "operation-failed"
    if isinstance(error, ReplayError):
        code = _REPLAY_FAILURE_CODES.get(str(error), code)
    elif type(error) is ContractValidationError:
        message = str(error)
        if message.startswith(_TEST_FAILURE_MESSAGE_PREFIX):
            category = message.removeprefix(_TEST_FAILURE_MESSAGE_PREFIX)
            safe_category = _safe_test_failure_category(
                f"agent00x:test-failure:{category}"
            )
            if safe_category in _SAFE_TARGET_TEST_FAILURE_CODES:
                code = f"target-test-{safe_category}"
    return f"replay: operation failed closed [{code}]"


class _StoredCandidateWorker:
    def __init__(self, content: str) -> None:
        self._content = content

    def propose(self, _task) -> WorkerProposal:
        return WorkerProposal(changes=((ALLOWED_CHANGE_PATH, self._content),))


def replay_staged_candidate(
    source_database: Path | str,
    source_digest: str,
    output_database: Path | str,
    *,
    transport: object,
    sandbox_backend: object,
    verifier: object,
    commit_object_source: object,
    test_command: tuple[str, ...] = PINNED_HTTP_DB_TEST_COMMAND,
    snapshot_reader: Callable = read_github_snapshot_contents,
    observation_store: object | None = None,
    verifier_trust_evidence: dict | None = None,
    _commit_output: Callable[[Path, Path], None] | None = None,
) -> dict:
    invocation: list[object] = []
    try:
        evidence = _replay_staged_candidate_impl(
            source_database,
            source_digest,
            output_database,
            transport=transport,
            sandbox_backend=sandbox_backend,
            verifier=verifier,
            commit_object_source=commit_object_source,
            test_command=test_command,
            snapshot_reader=snapshot_reader,
            observation_store=observation_store,
            verifier_trust_evidence=verifier_trust_evidence,
            _commit_output=_commit_output,
            _invocation_out=invocation,
        )
    except Exception:
        _finish_replay_invocation(invocation, status="failed")
        raise
    _finish_replay_invocation(invocation, status="ok")
    if invocation and type(invocation[0]) is JournaledProposalWorker:
        evidence["observer"] = invocation[0].observer_reference()
    return evidence


def _finish_replay_invocation(invocation: list[object], *, status: str) -> None:
    if invocation and type(invocation[0]) is JournaledProposalWorker:
        try:
            invocation[0].finish_agent_invocation(status=status)
        except WorkerJournalError:
            # Keep pending or unknown replay effects open for Control Plane review.
            pass


def _replay_staged_candidate_impl(
    source_database: Path | str,
    source_digest: str,
    output_database: Path | str,
    *,
    transport: object,
    sandbox_backend: object,
    verifier: object,
    commit_object_source: object,
    test_command: tuple[str, ...] = PINNED_HTTP_DB_TEST_COMMAND,
    snapshot_reader: Callable = read_github_snapshot_contents,
    observation_store: object | None = None,
    verifier_trust_evidence: dict | None = None,
    _commit_output: Callable[[Path, Path], None] | None = None,
    _invocation_out: list[object] | None = None,
) -> dict:
    """Verify a source stage, re-fetch its exact public pin, and persist replay.

    Network, sandbox and verifier dependencies are fixed by the production CLI;
    narrow injection points exist for deterministic offline tests only.
    """
    source_path = _validate_existing_database(source_database)
    output_path = _validate_new_database_path(output_database)
    if _paths_alias(source_path, output_path):
        raise ReplayError("replay: source and output databases must differ")
    if not isinstance(source_digest, str) or _DIGEST_PATTERN.fullmatch(source_digest) is None:
        raise ReplayError("replay: source digest is invalid")
    if (
        not callable(getattr(transport, "read_rate_limit", None))
        or not callable(getattr(sandbox_backend, "create", None))
        or not callable(getattr(verifier, "verify", None))
        or not callable(commit_object_source)
        or not callable(snapshot_reader)
        or type(test_command) is not tuple
        or not test_command
    ):
        raise ReplayError("replay: runtime is unavailable")
    if verifier_trust_evidence is not None and not _valid_verifier_trust_evidence(
        verifier_trust_evidence
    ):
        raise ReplayError("replay: evidence is invalid")

    artifact, candidate = _load_source_candidate(source_path, source_digest)
    process_id = f"process-replay-{source_digest[-12:]}"
    task_id = f"task-replay-{source_digest[-12:]}"
    execution_worker: object = _StoredCandidateWorker(candidate)
    if observation_store is not None:
        try:
            execution_worker = JournaledProposalWorker(
                execution_worker,
                observation_store,
                process_id=process_id,
                task_id=task_id,
            )
        except Exception:
            raise ReplayError("replay: observer is unavailable") from None
        if _invocation_out is not None:
            _invocation_out.append(execution_worker)
    try:
        readiness_dispatch = transport.read_rate_limit
        if type(execution_worker) is JournaledProposalWorker:
            readiness = execution_worker.run_controlled_step(
                "GitHubReadiness.fetch",
                readiness_dispatch,
                process_id=process_id,
            )
        else:
            readiness = readiness_dispatch()
    except Exception:
        raise ReplayError("replay: readiness request failed") from None
    status = getattr(readiness, "status", None)
    remaining = getattr(readiness, "remaining", None)
    reset_unix = getattr(readiness, "reset_unix", None)
    if type(status) is not int or status != 200:
        raise ReplayError("replay: readiness HTTP status failed")
    if (
        type(remaining) is not int
        or not 0 <= remaining <= 1_000_000
        or type(reset_unix) is not int
        or not 0 < reset_unix <= 9_999_999_999_999
    ):
        raise ReplayError("replay: readiness metadata is invalid")
    permit_eligible = remaining >= 25
    if type(execution_worker) is JournaledProposalWorker:
        permit_eligible = execution_worker.run_controlled_step(
            "RemoteExecutionPermit.issue",
            lambda: permit_eligible,
            process_id=process_id,
        )
    if permit_eligible is not True:
        raise ReplayError("replay: readiness quota is insufficient")

    request = GitHubSnapshotRequest(
        owner=REMOTE_REPOSITORY_OWNER,
        repository=REMOTE_REPOSITORY_NAME,
        commit_oid=REMOTE_REPOSITORY_COMMIT,
    )
    snapshot_transport = transport
    observed_commit_source = commit_object_source
    if type(execution_worker) is JournaledProposalWorker:
        snapshot_transport = execution_worker.snapshot_transport(transport)
        observed_commit_source = execution_worker.raw_commit_source(commit_object_source)
    try:
        snapshot = snapshot_reader(
            request,
            snapshot_transport,
            commit_object_source=observed_commit_source,
        )
    except Exception:
        raise ReplayError("replay: pinned snapshot fetch failed") from None
    claim = getattr(snapshot, "claim", None)
    files = getattr(snapshot, "files", None)
    verified_commit_object = getattr(snapshot, "verified_commit_object", None)
    pin_matches = not (
        getattr(claim, "owner", None) != REMOTE_REPOSITORY_OWNER
        or getattr(claim, "repository", None) != REMOTE_REPOSITORY_NAME
        or getattr(claim, "commit_oid", None) != REMOTE_REPOSITORY_COMMIT
        or getattr(claim, "tree_oid", None) != REMOTE_REPOSITORY_TREE
        or getattr(claim, "content_digest", None) != REMOTE_REPOSITORY_CONTENT_DIGEST
        or getattr(claim, "full_snapshot", None) is not True
        or type(files) is not tuple
        or len(files) != REMOTE_REPOSITORY_FILE_COUNT
        or sum(getattr(blob, "path", None) == ALLOWED_CHANGE_PATH for blob in files) != 1
    )
    if type(execution_worker) is JournaledProposalWorker:
        try:
            pin_matches = execution_worker.record_snapshot_pin_decision(pin_matches)
        except Exception:
            raise ReplayError("replay: snapshot observer is unavailable") from None
    if not pin_matches:
        raise ReplayError("replay: pinned snapshot mismatch")
    if (
        type(verified_commit_object) is not GitCommitObject
        or verified_commit_object.commit_oid != REMOTE_REPOSITORY_COMMIT
        or verified_commit_object.tree_oid != REMOTE_REPOSITORY_TREE
        or verified_commit_object.commit_oid != claim.commit_oid
        or verified_commit_object.tree_oid != claim.tree_oid
    ):
        raise ReplayError("replay: raw commit proof mismatch")
    try:
        original_content = next(
            blob.content.decode("utf-8", errors="strict")
            for blob in files
            if blob.path == ALLOWED_CHANGE_PATH
        )
    except Exception:
        raise ReplayError("replay: pinned target file is invalid") from None

    output_path.parent.mkdir(parents=False, exist_ok=True)
    if output_path.exists() or output_path.is_symlink():
        raise ReplayError("replay: output database already exists")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".agent00x-stage-replay-", suffix=".sqlite3", dir=output_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with SQLiteStagedArtifactStore(temporary_path) as stage_sink:
            result = run_remote_snapshot_execution(
                snapshot,
                process_id=process_id,
                task_id=task_id,
                task_instruction=_TASK_INSTRUCTION,
                declared_change_paths=(ALLOWED_CHANGE_PATH,),
                allowed_commands=_ALLOWED_COMMANDS,
                test_command=test_command,
                worker=execution_worker,
                verifier=verifier,
                sandbox_backend=sandbox_backend,
                context_files=((ALLOWED_CHANGE_PATH, original_content),),
                test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                stage_sink=stage_sink,
                observation_store=observation_store,
            )
            if result.status is not ExecutionStatus.VERIFIED or not result.staged_change_digest:
                raise ReplayError("replay: candidate verification failed")
            replay_artifact = stage_sink.load(result.staged_change_digest)
            preview = json.loads(render_stage_preview(replay_artifact))
            replay_payload = replay_artifact.payload_copy()
            if (
                preview["change"]["repository_id"]
                != f"{REMOTE_REPOSITORY_OWNER}/{REMOTE_REPOSITORY_NAME}"
                or preview["change"]["base_commit"] != REMOTE_REPOSITORY_COMMIT
                or preview["change"]["declared_change_paths"] != [ALLOWED_CHANGE_PATH]
                or preview["verification"]["verifier_id"] != _VERIFIER_ID
                or preview["verification"]["verdict"] != "pass"
                or replay_payload["verified_contents"]
                != [{"path": ALLOWED_CHANGE_PATH, "content": candidate}]
            ):
                raise ReplayError("replay: exact stage readback failed")

        commit_output = _commit_output or _link_without_overwrite
        commit_output(temporary_path, output_path)
        with SQLiteStagedArtifactStore(output_path, read_only=True) as readonly:
            committed = readonly.load(result.staged_change_digest)
        committed_preview = json.loads(render_stage_preview(committed))
        if committed_preview != preview:
            raise ReplayError("replay: committed stage readback failed")
        verifier_id = getattr(result.verifier_result, "verifier_id", None)
        digests = {
            "snapshot_claim_digest": result.snapshot_claim_digest,
            "staged_change_digest": result.staged_change_digest,
            "verified_contents_digest": result.verified_contents_digest,
            "verification_digest": result.verification_digest,
        }
        if (
            verifier_id != _VERIFIER_ID
            or any(
                type(value) is not str or _DIGEST_PATTERN.fullmatch(value) is None
                for value in digests.values()
            )
        ):
            raise ReplayError("replay: evidence is invalid")
        evidence = {
            "schema": "stored-candidate-replay-evidence/v1",
            "status": "verified",
            "verifier_backend": (
                "trusted-https" if verifier_trust_evidence is not None else "pinned-docker"
            ),
            "source_stage_digest": artifact.staged_change_digest,
            "source_database": str(source_path),
            "repository_id": f"{REMOTE_REPOSITORY_OWNER}/{REMOTE_REPOSITORY_NAME}",
            "commit": REMOTE_REPOSITORY_COMMIT,
            "tree": REMOTE_REPOSITORY_TREE,
            "content_digest": REMOTE_REPOSITORY_CONTENT_DIGEST,
            "raw_commit_object": {
                "status": "verified-by-object-hash",
                "commit_oid": verified_commit_object.commit_oid,
                "root_tree_oid": verified_commit_object.tree_oid,
            },
            **digests,
            "verifier_identity_digest": "sha256:"
            + hashlib.sha256(verifier_id.encode("utf-8")).hexdigest(),
            "source_stage_verifier_result": "not_carried_forward",
            "current_verification_status": "fresh_pass",
            "artifact_digest": committed.artifact_digest,
            "output_database": str(output_path),
            "approval": "not_created",
            "publication": "not_attempted",
            "external_write": False,
            "limitations": [
                "replayed-not-live-worker",
                "raw-commit-object-and-content-hashes-verified",
                "github-tls-transport-provenance-not-independent",
                "human-authorship-not-independently-verified",
                (
                    "host-separation-trust-is-only-the-caller-pinned-signed-claim"
                    if verifier_trust_evidence is not None
                    else "same-host-verifier-trust-not-independent"
                ),
            ],
        }
        if verifier_trust_evidence is not None:
            evidence["verifier_trust"] = verifier_trust_evidence
        if type(execution_worker) is JournaledProposalWorker:
            evidence["observer"] = execution_worker.observer_reference()
        return evidence
    except Exception:
        try:
            output_is_owned = (
                output_path.exists()
                and not output_path.is_symlink()
                and temporary_path.exists()
                and os.path.samefile(output_path, temporary_path)
            )
        except OSError:
            output_is_owned = False
        if output_is_owned:
            # Remove only a final link proven to be this operation's artifact.
            try:
                output_path.unlink()
            except OSError:
                pass
        _remove_temporary_database(temporary_path)
        raise
    finally:
        _remove_temporary_database(temporary_path)


def _load_source_candidate(path: Path, digest: str) -> tuple[StagedArtifact, str]:
    try:
        with SQLiteStagedArtifactStore(path, read_only=True) as store:
            artifact = store.load(digest)
        payload = artifact.payload_copy()
        seed = payload["seed"]
        result = payload["verifier_result"]
        changes = payload["verified_contents"]
        if (
            seed["repository_id"] != f"{REMOTE_REPOSITORY_OWNER}/{REMOTE_REPOSITORY_NAME}"
            or seed["base_commit"] != REMOTE_REPOSITORY_COMMIT
            or seed["staged_change_digest"] != digest
            or seed["snapshot_origin"] != "github_rest_api_claim"
            or seed["verdict"] != "pass"
            or result["verdict"] != "pass"
            or payload["declared_change_paths"] != [ALLOWED_CHANGE_PATH]
            or type(changes) is not list
            or len(changes) != 1
            or changes[0]["path"] != ALLOWED_CHANGE_PATH
            or type(changes[0]["content"]) is not str
        ):
            raise ValueError
        # Historical verifier identity is not carried forward as trust: this
        # candidate is re-run through the current pinned target and verifier.
        StagedArtifact(
            staged_change_digest=artifact.staged_change_digest,
            verified_contents_digest=artifact.verified_contents_digest,
            artifact_digest=artifact.artifact_digest,
            canonical_payload=artifact.canonical_payload,
        )
        return artifact, changes[0]["content"]
    except Exception:
        raise ReplayError("replay: source stage is invalid") from None


def _validate_existing_database(value: Path | str) -> Path:
    try:
        path = Path(value)
        if path.is_symlink() or not path.is_absolute() or not path.is_file():
            raise ValueError
        return path
    except Exception:
        raise ReplayError("replay: source database is unavailable") from None


def _validate_new_database_path(value: Path | str) -> Path:
    try:
        path = Path(value)
        parent = path.parent
        if (
            not path.is_absolute()
            or not parent.is_dir()
            or parent.is_symlink()
            or path.exists()
            or path.is_symlink()
        ):
            raise ValueError
        return path
    except Exception:
        raise ReplayError("replay: output database path is unavailable") from None


def _paths_alias(first: Path, second: Path) -> bool:
    try:
        return first.resolve(strict=True) == second.resolve(strict=False)
    except Exception:
        raise ReplayError("replay: database paths are invalid") from None


def _link_without_overwrite(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ReplayError("replay: output database already exists")
    try:
        os.link(source, destination)
    except Exception:
        raise ReplayError("replay: output database commit failed") from None


def _remove_temporary_database(path: Path) -> None:
    for candidate in (path, Path(str(path) + "-journal"), Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


def _production_runtime(args=None):
    if args is not None:
        _validate_verifier_backend_args(args)
    docker = shutil.which("docker")
    if docker is None:
        raise ReplayError("replay: docker is unavailable")
    verifier_backend = "pinned-docker" if args is None else args.verifier_backend
    trust_evidence = None
    if verifier_backend == "pinned-docker":
        verifier = DockerContainerVerifier(
            VerifierContainerConfig(
                docker_executable=docker,
                runtime_image_id=VERIFIER_RUNTIME_IMAGE_ID,
                verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
                timeout_seconds=PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
                max_stdout_bytes=65536,
                max_stderr_bytes=16384,
            )
        )
    elif verifier_backend == "trusted-https" and args is not None:
        try:
            verifier, worker_host_id, verifier_host_id, trust_digests = (
                load_pinned_signed_verifier_client(
                    args,
                    expected_endpoint_url=PINNED_SIGNED_VERIFIER_ENDPOINT_URL,
                )
            )
            trust_evidence = {
                "endpoint_url": PINNED_SIGNED_VERIFIER_ENDPOINT_URL,
                "verifier_profile_digest": BRAINBOOSTER_VERIFIER_PROFILE.profile_digest,
                "worker_host_id": worker_host_id,
                "verifier_host_id": verifier_host_id,
                "digests": trust_digests,
                "host_trust_basis": "caller-pinned-signed-claim",
            }
        except Exception:
            raise ReplayError("replay: verifier trust material unavailable") from None
    else:
        raise ReplayError("replay: verifier backend configuration is invalid")
    return (
        GitHubAnonymousSnapshotTransport(timeout_seconds=15),
        DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID),
        verifier,
        GitHubRawCommitObjectSource("/usr/bin/git", timeout_seconds=15),
        trust_evidence,
    )


def _valid_verifier_trust_evidence(value: object) -> bool:
    if type(value) is not dict or set(value) != {
        "endpoint_url",
        "verifier_profile_digest",
        "worker_host_id",
        "verifier_host_id",
        "digests",
        "host_trust_basis",
    }:
        return False
    digests = value.get("digests")
    worker_host_id = value.get("worker_host_id")
    verifier_host_id = value.get("verifier_host_id")
    return (
        value.get("endpoint_url") == PINNED_SIGNED_VERIFIER_ENDPOINT_URL
        and value.get("verifier_profile_digest")
        == BRAINBOOSTER_VERIFIER_PROFILE.profile_digest
        and type(worker_host_id) is str
        and 1 <= len(worker_host_id) <= 128
        and type(verifier_host_id) is str
        and 1 <= len(verifier_host_id) <= 128
        and worker_host_id != verifier_host_id
        and value.get("host_trust_basis") == "caller-pinned-signed-claim"
        and type(digests) is dict
        and set(digests)
        == {
            "authority_key_set_sha256",
            "enrollment_sha256",
            "host_decision_sha256",
            "ca_bundle_sha256",
        }
        and all(
            type(digest) is str and _DIGEST_PATTERN.fullmatch(digest) is not None
            for digest in digests.values()
        )
    )


def _validate_verifier_backend_args(args: argparse.Namespace) -> None:
    backend = getattr(args, "verifier_backend", None)
    trust_values = tuple(
        getattr(args, name, None) for name in VERIFIER_TRUST_ARTIFACT_ARGUMENTS
    )
    connect_address = getattr(args, "verifier_connect_address", None)
    connect_port = getattr(args, "verifier_connect_port", None)
    if backend == "pinned-docker":
        if any(value is not None for value in trust_values) or any(
            value is not None for value in (connect_address, connect_port)
        ):
            raise ReplayError("replay: verifier backend configuration is invalid")
        return
    if backend != "trusted-https":
        raise ReplayError("replay: verifier backend configuration is invalid")
    if any(value is None for value in trust_values):
        raise ReplayError("replay: verifier trust material unavailable")
    if (connect_address is None) != (connect_port is None):
        raise ReplayError("replay: verifier backend configuration is invalid")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay one stored verified candidate through the fixed pinned target."
    )
    parser.add_argument("source_database")
    parser.add_argument("source_stage_digest")
    parser.add_argument("output_database")
    parser.add_argument(
        "--observer-database",
        help="optional new SQLite database for a partial replay observation run",
    )
    parser.add_argument(
        "--verifier-backend",
        choices=("pinned-docker", "trusted-https"),
        default="pinned-docker",
        help="use the local pinned Docker verifier or caller-pinned HTTPS verifier",
    )
    parser.add_argument("--verifier-authority-key-set")
    parser.add_argument("--verifier-authority-key-set-sha256")
    parser.add_argument("--verifier-enrollment")
    parser.add_argument("--verifier-enrollment-sha256")
    parser.add_argument("--verifier-host-decision")
    parser.add_argument("--verifier-host-decision-sha256")
    parser.add_argument("--verifier-ca-bundle")
    parser.add_argument("--verifier-ca-bundle-sha256")
    parser.add_argument("--expected-worker-host-id")
    parser.add_argument("--expected-verifier-host-id")
    parser.add_argument(
        "--verifier-connect-address",
        help="optional IP-literal forward destination; TLS identity remains testdev.local",
    )
    parser.add_argument(
        "--verifier-connect-port",
        type=int,
        help="optional forwarded TCP port; requires --verifier-connect-address",
    )
    args = parser.parse_args(argv)
    try:
        _validate_verifier_backend_args(args)
    except ReplayError as exc:
        print(_safe_failure_marker(exc), file=sys.stderr)
        return 2
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        print("replay: explicit Docker opt-in is required", file=sys.stderr)
        return 2
    try:
        source_path = _validate_existing_database(args.source_database)
        output_path = _validate_new_database_path(args.output_database)
        if not isinstance(args.source_stage_digest, str) or _DIGEST_PATTERN.fullmatch(
            args.source_stage_digest
        ) is None:
            raise ReplayError("replay: source digest is invalid")
        _load_source_candidate(source_path, args.source_stage_digest)
        observer_path = None
        if args.observer_database is not None:
            observer_path = _validate_new_database_path(args.observer_database)
            if observer_path.resolve(strict=False) == output_path.resolve(strict=False):
                raise ReplayError("replay: observer and stage databases must differ")
        if _paths_alias(source_path, output_path):
            raise ReplayError("replay: source and output databases must differ")
        transport, sandbox, verifier, commit_object_source, trust_evidence = (
            _production_runtime(args)
        )
        if observer_path is None:
            evidence = replay_staged_candidate(
                args.source_database,
                args.source_stage_digest,
                args.output_database,
                transport=transport,
                sandbox_backend=sandbox,
                verifier=verifier,
                commit_object_source=commit_object_source,
                verifier_trust_evidence=trust_evidence,
            )
        else:
            with SQLiteObservationStore(observer_path) as observation_store:
                evidence = replay_staged_candidate(
                    args.source_database,
                    args.source_stage_digest,
                    args.output_database,
                    transport=transport,
                    sandbox_backend=sandbox,
                    verifier=verifier,
                    commit_object_source=commit_object_source,
                    observation_store=observation_store,
                    verifier_trust_evidence=trust_evidence,
                )
    except (ReplayError, DurableStageStoreError, GitHubHTTPTransportError, GitHubSnapshotError) as exc:
        print(_safe_failure_marker(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(_safe_failure_marker(exc), file=sys.stderr)
        return 2
    print(json.dumps(evidence, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
