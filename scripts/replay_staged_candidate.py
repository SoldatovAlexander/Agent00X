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
    PINNED_CONTENT_DIGEST,
    PINNED_FILE_COUNT,
    PINNED_HTTP_DB_TEST_COMMAND,
    PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
    PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
    TARGET_RUNTIME_IMAGE_ID,
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.executor import ExecutionStatus, WorkerProposal  # noqa: E402
from app_contracts.github_http_transport import (  # noqa: E402
    GitHubAnonymousSnapshotTransport,
    GitHubHTTPTransportError,
)
from app_contracts.github_snapshot import (  # noqa: E402
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
from app_contracts.remote_snapshot_pipeline import run_remote_snapshot_execution  # noqa: E402

ALLOWED_CHANGE_PATH = "backend/routes.py"
REMOTE_REPOSITORY_OWNER = PINNED_OWNER
REMOTE_REPOSITORY_NAME = PINNED_REPOSITORY
REMOTE_REPOSITORY_COMMIT = PINNED_COMMIT
REMOTE_REPOSITORY_TREE = PINNED_TREE
REMOTE_REPOSITORY_CONTENT_DIGEST = PINNED_CONTENT_DIGEST
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


class ReplayError(ValueError):
    """A stored-candidate replay failed a bounded validation gate."""


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
    test_command: tuple[str, ...] = PINNED_HTTP_DB_TEST_COMMAND,
    snapshot_reader: Callable = read_github_snapshot_contents,
    _commit_output: Callable[[Path, Path], None] | None = None,
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
        or not callable(snapshot_reader)
        or type(test_command) is not tuple
        or not test_command
    ):
        raise ReplayError("replay: runtime is unavailable")

    artifact, candidate = _load_source_candidate(source_path, source_digest)
    try:
        readiness = transport.read_rate_limit()
    except Exception:
        raise ReplayError("replay: readiness request failed") from None
    if (
        getattr(readiness, "status", None) != 200
        or type(getattr(readiness, "remaining", None)) is not int
        or readiness.remaining < 25
        or type(getattr(readiness, "reset_unix", None)) is not int
        or readiness.reset_unix <= 0
    ):
        raise ReplayError("replay: readiness gate failed")

    request = GitHubSnapshotRequest(
        owner=REMOTE_REPOSITORY_OWNER,
        repository=REMOTE_REPOSITORY_NAME,
        commit_oid=REMOTE_REPOSITORY_COMMIT,
    )
    try:
        snapshot = snapshot_reader(request, transport)
    except Exception:
        raise ReplayError("replay: pinned snapshot fetch failed") from None
    claim = getattr(snapshot, "claim", None)
    files = getattr(snapshot, "files", None)
    if (
        getattr(claim, "owner", None) != REMOTE_REPOSITORY_OWNER
        or getattr(claim, "repository", None) != REMOTE_REPOSITORY_NAME
        or getattr(claim, "commit_oid", None) != REMOTE_REPOSITORY_COMMIT
        or getattr(claim, "tree_oid", None) != REMOTE_REPOSITORY_TREE
        or getattr(claim, "content_digest", None) != REMOTE_REPOSITORY_CONTENT_DIGEST
        or getattr(claim, "full_snapshot", None) is not True
        or type(files) is not tuple
        or len(files) != REMOTE_REPOSITORY_FILE_COUNT
        or sum(getattr(blob, "path", None) == ALLOWED_CHANGE_PATH for blob in files) != 1
    ):
        raise ReplayError("replay: pinned snapshot mismatch")
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
                process_id=f"process-replay-{source_digest[-12:]}",
                task_id=f"task-replay-{source_digest[-12:]}",
                task_instruction=_TASK_INSTRUCTION,
                declared_change_paths=(ALLOWED_CHANGE_PATH,),
                allowed_commands=_ALLOWED_COMMANDS,
                test_command=test_command,
                worker=_StoredCandidateWorker(candidate),
                verifier=verifier,
                sandbox_backend=sandbox_backend,
                context_files=((ALLOWED_CHANGE_PATH, original_content),),
                test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                stage_sink=stage_sink,
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
        return {
            "schema": "stored-candidate-replay-evidence/v1",
            "status": "verified",
            "source_stage_digest": artifact.staged_change_digest,
            "source_database": str(source_path),
            "repository_id": f"{REMOTE_REPOSITORY_OWNER}/{REMOTE_REPOSITORY_NAME}",
            "commit": REMOTE_REPOSITORY_COMMIT,
            "tree": REMOTE_REPOSITORY_TREE,
            "content_digest": REMOTE_REPOSITORY_CONTENT_DIGEST,
            **digests,
            "verifier_identity_digest": "sha256:"
            + hashlib.sha256(verifier_id.encode("utf-8")).hexdigest(),
            "artifact_digest": committed.artifact_digest,
            "output_database": str(output_path),
            "approval": "not_created",
            "publication": "not_attempted",
            "external_write": False,
            "limitations": [
                "replayed-not-live-worker",
                "snapshot-is-unauthenticated-github-api-claim",
                "same-host-verifier-trust-not-independent",
            ],
        }
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
            or result["verifier_id"] != _VERIFIER_ID
            or result["verdict"] != "pass"
            or payload["declared_change_paths"] != [ALLOWED_CHANGE_PATH]
            or type(changes) is not list
            or len(changes) != 1
            or changes[0]["path"] != ALLOWED_CHANGE_PATH
            or type(changes[0]["content"]) is not str
        ):
            raise ValueError
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


def _production_runtime():
    docker = shutil.which("docker")
    if docker is None:
        raise ReplayError("replay: docker is unavailable")
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
    return (
        GitHubAnonymousSnapshotTransport(timeout_seconds=15),
        DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID),
        verifier,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay one stored verified candidate through the fixed pinned target."
    )
    parser.add_argument("source_database")
    parser.add_argument("source_stage_digest")
    parser.add_argument("output_database")
    args = parser.parse_args(argv)
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        print("replay: explicit Docker opt-in is required", file=sys.stderr)
        return 2
    try:
        transport, sandbox, verifier = _production_runtime()
        evidence = replay_staged_candidate(
            args.source_database,
            args.source_stage_digest,
            args.output_database,
            transport=transport,
            sandbox_backend=sandbox,
            verifier=verifier,
        )
    except (ReplayError, DurableStageStoreError, GitHubHTTPTransportError, GitHubSnapshotError):
        print("replay: operation failed closed", file=sys.stderr)
        return 2
    except Exception:
        print("replay: operation failed closed", file=sys.stderr)
        return 2
    print(json.dumps(evidence, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
