"""Local simulation-branch declarations and bounded in-memory restoration.

Workspace materialization validates content-addressed synthetic checkpoint
artifacts but does not create a filesystem runtime or execute restored content.
Branch declarations never call a Worker, tool, sandbox, or publication adapter.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Callable

from .digests import canonical_json, sha256_bytes
from .observer_artifact_store import SQLiteObserverArtifactStore
from .observation_store import CHECKPOINT_SCHEMA, EVENT_SCHEMA
from .secret_scan import assert_no_credential_pattern_content
from .validator import ContractValidationError, validate


_RUN_ID = re.compile(r"^run-[a-z0-9-]{8,64}$")
_BRANCH_ID = re.compile(r"^branch-[a-z0-9-]{8,64}$")
_STEP_ID = re.compile(r"^step-[a-z0-9-]{8,64}$")
_WORKSPACE_MANIFEST_REF = re.compile(r"artifact://sha256/([0-9a-f]{64})\Z")
_WORKSPACE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_WORKSPACE_PATH_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_WORKSPACE_MANIFEST_BYTES = 256 * 1024
_WORKSPACE_FILE_BYTES = 96 * 1024
_WORKSPACE_FILE_BASE64_BYTES = 4 * ((_WORKSPACE_FILE_BYTES + 2) // 3)
_WORKSPACE_TOTAL_BYTES = 128 * 1024
_WORKSPACE_FILE_COUNT = 64
_SIMULATION_PATCH_BYTES = 2 * 1024 * 1024
_SENSITIVE_PATH_COMPONENT = re.compile(
    r"(?i)(?:^|[._-])(credentials?|secrets?|tokens?|private[-_]?key)(?:$|[._-])"
)
_SENSITIVE_FILENAMES = frozenset(
    {
        "authorized_keys",
        "credentials",
        "id_ed25519",
        "id_rsa",
        "known_hosts",
        "secrets",
        "tokens",
    }
)
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


def _load_correction_schema() -> dict:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "learning-correction.schema.json"
    with schema_path.open(encoding="utf-8") as handle:
        return json.load(handle)


LEARNING_CORRECTION_SCHEMA = _load_correction_schema()


class SimulationBranchError(ValueError):
    """A simulation branch could not be declared safely."""


@dataclass(frozen=True)
class MaterializedSimulationWorkspace:
    """Validated in-memory workspace contents for an isolated simulation."""

    checkpoint_id: str
    manifest_ref: str
    manifest_digest: str
    files: tuple[tuple[str, bytes], ...]

    def __repr__(self) -> str:
        return (
            "MaterializedSimulationWorkspace("
            f"checkpoint_id={self.checkpoint_id!r}, "
            f"manifest_digest={self.manifest_digest!r}, "
            f"file_count={len(self.files)}, contents='opaque')"
        )

    def evidence(self) -> dict[str, object]:
        """Return content-free evidence for the restored simulation input."""

        return {
            "checkpoint_id": self.checkpoint_id,
            "manifest_ref": self.manifest_ref,
            "manifest_digest": self.manifest_digest,
            "file_count": len(self.files),
            "files": [
                {
                    "path": path,
                    "content_digest": sha256_bytes(content),
                    "content_bytes": len(content),
                }
                for path, content in self.files
            ],
            "external_effects_replayed": False,
        }


@dataclass(frozen=True)
class SimulationStepResult:
    """Content-addressed in-memory result of one declarative branch step."""

    step_id: str
    correction_id: str
    correction_version: int
    correction_digest: str
    checkpoint_id: str
    source_manifest_digest: str
    step_digest: str
    result_digest: str
    changed_paths: tuple[str, ...]
    files: tuple[tuple[str, bytes], ...]

    def __repr__(self) -> str:
        return (
            "SimulationStepResult("
            f"step_id={self.step_id!r}, "
            f"correction_id={self.correction_id!r}, "
            f"checkpoint_id={self.checkpoint_id!r}, "
            f"result_digest={self.result_digest!r}, "
            f"changed_paths={self.changed_paths!r}, contents='opaque')"
        )

    def evidence(self) -> dict[str, object]:
        """Return bounded structural evidence without restored file contents."""

        return {
            "step_id": self.step_id,
            "correction_id": self.correction_id,
            "correction_version": self.correction_version,
            "correction_digest": self.correction_digest,
            "checkpoint_id": self.checkpoint_id,
            "source_manifest_digest": self.source_manifest_digest,
            "step_digest": self.step_digest,
            "result_digest": self.result_digest,
            "changed_paths": list(self.changed_paths),
            "file_count": len(self.files),
            "code_executed": False,
            "external_effects_replayed": False,
        }


def _workspace_path_is_safe(path: object) -> bool:
    path_parts = path.split("/") if type(path) is str else []
    return bool(
        path_parts
        and len(path) <= 1024
        and all(
            _WORKSPACE_PATH_PART.fullmatch(part) is not None
            and not part.endswith(".")
            and _SENSITIVE_PATH_COMPONENT.search(part) is None
            and part.casefold() not in _SENSITIVE_FILENAMES
            and part.split(".", 1)[0].casefold()
            not in _WINDOWS_RESERVED_BASENAMES
            for part in path_parts
        )
    )


def apply_simulation_step(
    workspace: MaterializedSimulationWorkspace, correction: object, patch: object
) -> SimulationStepResult:
    """Apply one exact file replacement to a separate in-memory simulation.

    This accepts only a versioned declarative record. It cannot execute code,
    invoke a Worker/tool, access a filesystem, or dispatch an external effect.
    """

    if type(workspace) is not MaterializedSimulationWorkspace:
        raise SimulationBranchError("simulation step workspace is invalid")
    manifest_match = (
        _WORKSPACE_MANIFEST_REF.fullmatch(workspace.manifest_ref)
        if type(workspace.manifest_ref) is str
        else None
    )
    if (
        type(workspace.checkpoint_id) is not str
        or re.fullmatch(r"checkpoint-[a-z0-9-]{8,64}", workspace.checkpoint_id)
        is None
        or manifest_match is None
        or type(workspace.manifest_digest) is not str
        or _WORKSPACE_DIGEST.fullmatch(workspace.manifest_digest) is None
        or f"sha256:{manifest_match.group(1)}" != workspace.manifest_digest
        or type(workspace.files) is not tuple
        or not 1 <= len(workspace.files) <= _WORKSPACE_FILE_COUNT
    ):
        raise SimulationBranchError("simulation step workspace is invalid")

    source_files: dict[str, bytes] = {}
    seen_paths: set[str] = set()
    total_source_bytes = 0
    for entry in workspace.files:
        if (
            type(entry) is not tuple
            or len(entry) != 2
            or not _workspace_path_is_safe(entry[0])
            or type(entry[1]) is not bytes
            or len(entry[1]) > _WORKSPACE_FILE_BYTES
            or entry[0].casefold() in seen_paths
        ):
            raise SimulationBranchError("simulation step workspace is invalid")
        seen_paths.add(entry[0].casefold())
        source_files[entry[0]] = entry[1]
        total_source_bytes += len(entry[1])
        if total_source_bytes > _WORKSPACE_TOTAL_BYTES:
            raise SimulationBranchError("simulation step workspace is invalid")
    if tuple(sorted(source_files.items(), key=lambda item: item[0])) != workspace.files:
        raise SimulationBranchError("simulation step workspace is invalid")
    try:
        assert_no_credential_pattern_content(workspace.files)
    except Exception:
        raise SimulationBranchError("simulation step workspace is invalid") from None

    try:
        validate(correction, LEARNING_CORRECTION_SCHEMA)
        if (
            type(correction) is not dict
            or correction["checkpoint_id"] != workspace.checkpoint_id
            or correction["review_status"] == "rejected"
        ):
            raise ValueError
        correction_digest = sha256_bytes(canonical_json(correction))
    except Exception:
        raise SimulationBranchError("simulation step correction is invalid") from None

    if (
        type(patch) is not dict
        or set(patch)
        != {
            "schema",
            "step_id",
            "correction_id",
            "correction_version",
            "correction_digest",
            "source_manifest_digest",
            "operations",
        }
        or patch.get("schema") != "simulation-step-patch/v1"
        or type(patch.get("step_id")) is not str
        or _STEP_ID.fullmatch(patch["step_id"]) is None
        or patch.get("correction_id") != correction["correction_id"]
        or type(patch.get("correction_version")) is not int
        or patch["correction_version"] != correction["version"]
        or type(patch.get("correction_digest")) is not str
        or patch["correction_digest"] != correction_digest
        or patch.get("source_manifest_digest") != workspace.manifest_digest
        or type(patch.get("operations")) is not list
        or not 1 <= len(patch["operations"]) <= len(source_files)
    ):
        raise SimulationBranchError("simulation step patch is invalid")

    try:
        patch_bytes = canonical_json(patch)
        if len(patch_bytes) > _SIMULATION_PATCH_BYTES:
            raise ValueError
        step_digest = sha256_bytes(patch_bytes)
    except Exception:
        raise SimulationBranchError("simulation step patch is invalid") from None

    replacements: dict[str, bytes] = {}
    seen_operations: set[str] = set()
    operation_paths: list[str] = []
    for operation in patch["operations"]:
        if (
            type(operation) is not dict
            or set(operation)
            != {
                "path",
                "expected_content_digest",
                "replacement_base64",
                "replacement_digest",
            }
        ):
            raise SimulationBranchError("simulation step patch is invalid")
        path = operation["path"]
        if (
            not _workspace_path_is_safe(path)
            or path not in source_files
            or path.casefold() in seen_operations
            or type(operation["expected_content_digest"]) is not str
            or _WORKSPACE_DIGEST.fullmatch(operation["expected_content_digest"])
            is None
            or type(operation["replacement_digest"]) is not str
            or _WORKSPACE_DIGEST.fullmatch(operation["replacement_digest"]) is None
            or type(operation["replacement_base64"]) is not str
            or not operation["replacement_base64"].isascii()
            or len(operation["replacement_base64"]) > _WORKSPACE_FILE_BASE64_BYTES
        ):
            raise SimulationBranchError("simulation step patch is invalid")
        encoded = operation["replacement_base64"]
        try:
            replacement = base64.b64decode(encoded.encode("ascii"), validate=True)
        except Exception:
            raise SimulationBranchError("simulation step patch is invalid") from None
        old_content = source_files[path]
        if (
            base64.b64encode(replacement).decode("ascii") != encoded
            or len(replacement) > _WORKSPACE_FILE_BYTES
            or sha256_bytes(old_content) != operation["expected_content_digest"]
            or sha256_bytes(replacement) != operation["replacement_digest"]
            or replacement == old_content
        ):
            raise SimulationBranchError("simulation step preimage or replacement is invalid")
        replacements[path] = replacement
        seen_operations.add(path.casefold())
        operation_paths.append(path)

    if operation_paths != sorted(operation_paths):
        raise SimulationBranchError("simulation step patch is invalid")
    result_files = tuple(
        (path, replacements.get(path, content)) for path, content in workspace.files
    )
    if sum(len(content) for _, content in result_files) > _WORKSPACE_TOTAL_BYTES:
        raise SimulationBranchError("simulation step replacement exceeds size limit")
    try:
        assert_no_credential_pattern_content(
            tuple((path, replacements[path]) for path in operation_paths)
        )
    except Exception:
        raise SimulationBranchError("simulation step replacement is invalid") from None

    result_record = {
        "schema": "simulation-workspace-result/v1",
        "checkpoint_id": workspace.checkpoint_id,
        "correction_id": correction["correction_id"],
        "correction_version": correction["version"],
        "correction_digest": correction_digest,
        "source_manifest_digest": workspace.manifest_digest,
        "step_digest": step_digest,
        "files": [
            {
                "path": path,
                "content_digest": sha256_bytes(content),
                "content_bytes": len(content),
            }
            for path, content in result_files
        ],
    }
    result_digest = sha256_bytes(canonical_json(result_record))
    return SimulationStepResult(
        step_id=patch["step_id"],
        correction_id=correction["correction_id"],
        correction_version=correction["version"],
        correction_digest=correction_digest,
        checkpoint_id=workspace.checkpoint_id,
        source_manifest_digest=workspace.manifest_digest,
        step_digest=step_digest,
        result_digest=result_digest,
        changed_paths=tuple(operation_paths),
        files=result_files,
    )


def materialize_simulation_workspace(
    checkpoint: object, artifact_store: object
) -> MaterializedSimulationWorkspace:
    """Restore a complete simulation checkpoint to immutable in-memory files.

    This resolves one strict content-addressed JSON manifest and validates every
    reconstructed file. It does not create a filesystem workspace or execute
    restored content.
    """

    try:
        validate(checkpoint, CHECKPOINT_SCHEMA)
        if type(checkpoint) is not dict:
            raise ValueError
        if (
            checkpoint["restore_mode"] != "simulation"
            or checkpoint["completeness"] != "complete"
            or checkpoint.get("in_flight_invocation_ids")
            or checkpoint.get("pending_action_ref")
            or checkpoint.get("external_effect_refs")
        ):
            raise ValueError
        manifest_ref = checkpoint.get("workspace_manifest_ref")
        ref_match = (
            _WORKSPACE_MANIFEST_REF.fullmatch(manifest_ref)
            if type(manifest_ref) is str
            else None
        )
        if (
            ref_match is None
            or type(artifact_store) is not SQLiteObserverArtifactStore
            or artifact_store.read_only is not True
        ):
            raise ValueError

        manifest_bytes = artifact_store.read_json(manifest_ref)
        if (
            type(manifest_bytes) is not bytes
            or not manifest_bytes
            or len(manifest_bytes) > _WORKSPACE_MANIFEST_BYTES
            or sha256_bytes(manifest_bytes) != f"sha256:{ref_match.group(1)}"
        ):
            raise ValueError
        manifest = json.loads(manifest_bytes.decode("utf-8", errors="strict"))
        if (
            type(manifest) is not dict
            or set(manifest) != {"schema", "files"}
            or manifest["schema"] != "workspace-manifest/v1"
            or canonical_json(manifest) != manifest_bytes
            or type(manifest["files"]) is not list
            or not 1 <= len(manifest["files"]) <= _WORKSPACE_FILE_COUNT
        ):
            raise ValueError

        seen_paths: set[str] = set()
        restored_files: list[tuple[str, bytes]] = []
        total_bytes = 0
        for record in manifest["files"]:
            if type(record) is not dict or set(record) != {
                "path",
                "content_base64",
                "content_digest",
            }:
                raise ValueError
            path = record["path"]
            path_parts = path.split("/") if type(path) is str else []
            if (
                not path_parts
                or len(path) > 1024
                or any(
                    _WORKSPACE_PATH_PART.fullmatch(part) is None
                    or part.endswith(".")
                    or _SENSITIVE_PATH_COMPONENT.search(part) is not None
                    or part.casefold() in _SENSITIVE_FILENAMES
                    or part.split(".", 1)[0].casefold()
                    in _WINDOWS_RESERVED_BASENAMES
                    for part in path_parts
                )
                or path.casefold() in seen_paths
                or type(record["content_base64"]) is not str
                or not record["content_base64"].isascii()
                or _WORKSPACE_DIGEST.fullmatch(record["content_digest"])
                is None
            ):
                raise ValueError
            encoded = record["content_base64"]
            content = base64.b64decode(encoded.encode("ascii"), validate=True)
            if (
                base64.b64encode(content).decode("ascii") != encoded
                or len(content) > _WORKSPACE_FILE_BYTES
                or sha256_bytes(content) != record["content_digest"]
            ):
                raise ValueError
            total_bytes += len(content)
            if total_bytes > _WORKSPACE_TOTAL_BYTES:
                raise ValueError
            assert_no_credential_pattern_content(((path, content),))
            seen_paths.add(path.casefold())
            restored_files.append((path, content))

        restored_files.sort(key=lambda item: item[0])
        return MaterializedSimulationWorkspace(
            checkpoint_id=checkpoint["checkpoint_id"],
            manifest_ref=manifest_ref,
            manifest_digest=sha256_bytes(manifest_bytes),
            files=tuple(restored_files),
        )
    except Exception:
        raise SimulationBranchError(
            "simulation branch workspace is unavailable"
        ) from None


@dataclass(frozen=True)
class SimulationBranch:
    """Safe locator for one metadata-only simulation branch declaration."""

    process_id: str
    source_run_id: str
    source_branch_id: str
    source_checkpoint_id: str
    source_event_id: str
    run_id: str
    branch_id: str
    event_id: str
    observer_cursor: int


def create_simulation_branch(
    store: object,
    *,
    checkpoint_id: str,
    correction: dict,
    run_id: str,
    branch_id: str,
    clock: Callable[[], datetime] | None = None,
) -> SimulationBranch:
    """Record a distinct simulation branch without restoring or dispatching.

    The source checkpoint must be complete, explicitly simulation-only, and
    free of pending/in-flight or known external effects. The returned branch is
    a declaration only: no artifact resolution, workspace restore, Worker call,
    or external action is exposed by this module.
    """

    if (
        type(checkpoint_id) is not str
        or not re.fullmatch(r"checkpoint-[a-z0-9-]{8,64}", checkpoint_id)
        or type(run_id) is not str
        or _RUN_ID.fullmatch(run_id) is None
        or type(branch_id) is not str
        or _BRANCH_ID.fullmatch(branch_id) is None
    ):
        raise SimulationBranchError("simulation branch request is invalid")
    if not all(
        callable(getattr(store, name, None))
        for name in ("events", "checkpoints", "check_checkpoint", "append")
    ):
        raise SimulationBranchError("simulation branch store is unavailable")

    try:
        validate(correction, LEARNING_CORRECTION_SCHEMA)
        events = store.events()
        checkpoints = store.checkpoints()
        checkpoint = next(
            item for item in checkpoints if item.get("checkpoint_id") == checkpoint_id
        )
        validate(checkpoint, CHECKPOINT_SCHEMA)
        cursor = store.check_checkpoint(checkpoint)
    except (ContractValidationError, StopIteration, TypeError, AttributeError, ValueError) as exc:
        raise SimulationBranchError("simulation branch source is invalid") from exc
    except Exception as exc:
        raise SimulationBranchError("simulation branch source is unavailable") from exc

    if (
        checkpoint["restore_mode"] != "simulation"
        or checkpoint["completeness"] != "complete"
        or checkpoint.get("in_flight_invocation_ids")
        or checkpoint.get("pending_action_ref")
        or checkpoint.get("external_effect_refs")
        or correction["checkpoint_id"] != checkpoint_id
    ):
        raise SimulationBranchError("simulation branch checkpoint is not eligible")

    source_position = None
    source_event = None
    for position, event in enumerate(events):
        if event.get("event_id") == correction["target_event_id"]:
            source_position = position
            source_event = event
            break
    if (
        source_position is None
        or source_event is None
        or source_position > cursor
        or any(
            source_event.get(field) != checkpoint.get(field)
            for field in ("process_id", "run_id", "branch_id")
        )
    ):
        raise SimulationBranchError("simulation branch target is outside checkpoint history")

    if any(
        event.get("branch_id") == branch_id or event.get("run_id") == run_id
        for event in events
    ):
        raise SimulationBranchError("simulation branch identifier already exists")

    now = datetime.now(timezone.utc) if clock is None else clock()
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise SimulationBranchError("simulation branch clock is invalid")
    timestamp = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    # Deriving the event ID from the branch ID lets the store's unique event
    # constraint arbitrate duplicate declarations even if callers race.
    event_id = f"event-branch-{branch_id.removeprefix('branch-')}"
    branch_event = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "branch_created",
        "process_id": checkpoint["process_id"],
        "run_id": run_id,
        "branch_id": branch_id,
        "task_id": source_event["task_id"],
        "agent_id": "service-simulation-branch",
        "sequence": 0,
        "occurred_at": timestamp,
        "recorded_at": timestamp,
        "causal_event_ids": [source_event["event_id"]],
        "checkpoint_id": checkpoint_id,
        "decision_or_tool": "SimulationBranch.create",
        "rationale": "Declare an isolated simulation branch; no replay is performed.",
        "expected_result": "A separate branch locator is recorded without external effects.",
        "classification": "internal",
        "redaction_status": "complete",
    }
    try:
        validate(branch_event, EVENT_SCHEMA)
        before = len(events)
        observer_cursor = store.append(branch_event)
        after = store.events()
    except Exception as exc:
        raise SimulationBranchError("simulation branch event could not be recorded") from exc
    if len(after) != before + 1 or after[-1].get("event_id") != event_id:
        raise SimulationBranchError("simulation branch identifier already exists")

    return SimulationBranch(
        process_id=checkpoint["process_id"],
        source_run_id=checkpoint["run_id"],
        source_branch_id=checkpoint["branch_id"],
        source_checkpoint_id=checkpoint_id,
        source_event_id=source_event["event_id"],
        run_id=run_id,
        branch_id=branch_id,
        event_id=event_id,
        observer_cursor=observer_cursor,
    )
