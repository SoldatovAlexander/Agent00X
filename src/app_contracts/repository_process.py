"""Reference M1 implementation of safe local change preparation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import difflib
from pathlib import Path
from typing import Mapping, Sequence

from .digests import sha256_bytes, sha256_digest
from .sandbox import LocalProcessSandbox
from .validator import ContractValidationError


@dataclass(frozen=True)
class PreparedChange:
    patch: str
    evidence_bundle: dict
    verification_report: dict
    staged_change: dict


@dataclass(frozen=True)
class PublishableFile:
    path: str
    content: str
    content_digest: str


def prepare_change(
    sandbox: LocalProcessSandbox,
    *,
    process_id: str,
    task_id: str,
    repository_id: str,
    base_commit: str,
    changes: Mapping[str, str],
    test_command: Sequence[str],
    now: datetime | None = None,
) -> PreparedChange:
    """Apply scoped text replacements and produce verified immutable artifacts."""

    if not changes:
        raise ContractValidationError("change proposal is empty")
    timestamp = now or datetime.now(timezone.utc)
    changed_paths: list[str] = []
    patch_parts: list[str] = []
    source_digests: list[str] = []

    for relative_name, new_content in sorted(changes.items()):
        relative = _safe_relative_path(relative_name)
        snapshot_file = _contained_file(sandbox.snapshot, relative)
        workspace_file = _contained_file(sandbox.workspace, relative)
        if not snapshot_file.is_file() or snapshot_file.is_symlink():
            raise ContractValidationError(f"source file is unavailable: {relative_name}")
        if workspace_file.is_symlink():
            raise ContractValidationError(f"workspace symlink is forbidden: {relative_name}")

        old_content = snapshot_file.read_text(encoding="utf-8")
        if old_content == new_content:
            raise ContractValidationError(f"proposed content is unchanged: {relative_name}")
        workspace_file.write_text(new_content, encoding="utf-8")
        changed_paths.append(relative.as_posix())
        source_digests.append(sha256_bytes(old_content.encode("utf-8")))
        patch_parts.extend(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{relative.as_posix()}",
                tofile=f"b/{relative.as_posix()}",
            )
        )

    patch = "".join(patch_parts)
    if not patch:
        raise ContractValidationError("generated patch is empty")

    test_result = sandbox.run(test_command)
    test_status = "passed" if test_result.returncode == 0 else "failed"
    report_payload = (test_result.stdout + "\n" + test_result.stderr).encode("utf-8")
    patch_digest = sha256_bytes(patch.encode("utf-8"))

    evidence = {
        "schema_version": 1,
        "evidence_id": f"evidence-{process_id.removeprefix('process-')}",
        "process_id": process_id,
        "task_id": task_id,
        "worker_build_id": "build-reference-worker-v1",
        "patch_digest": patch_digest,
        "test_results": [{
            "test_id": "allowlisted-tests",
            "status": test_status,
            "report_digest": sha256_bytes(report_payload),
        }],
        "source_digests": source_digests,
        "assumptions": ["Input snapshot is the authorized process snapshot"],
        "limitations": [] if test_status == "passed" else ["Allowlisted tests failed"],
        "created_at": _format_time(timestamp),
    }
    evidence_digest = sha256_digest(evidence)

    verification = {
        "schema_version": 1,
        "verification_id": f"verification-{process_id.removeprefix('process-')}",
        "process_id": process_id,
        "evidence_digest": evidence_digest,
        "verifier_id": "deterministic-verifier-v1",
        "verifier_build_id": "build-deterministic-verifier-v1",
        "checks": [
            {
                "criterion": "Allowlisted tests pass",
                "status": "passed" if test_status == "passed" else "failed",
                "evidence_ref": "artifact://reports/allowlisted-tests",
            },
            {
                "criterion": "Patch is limited to declared paths",
                "status": "passed",
                "evidence_ref": "artifact://patches/declared-paths",
            },
        ],
        "verdict": "pass" if test_status == "passed" else "fail",
        "blockers": [] if test_status == "passed" else ["tests-failed"],
        "created_at": _format_time(timestamp),
    }
    if verification["verdict"] != "pass":
        raise ContractValidationError("verification failed; staged change was not created")

    verification_digest = sha256_digest(verification)
    staged = {
        "schema_version": 1,
        "staged_change_id": f"staged-{process_id.removeprefix('process-')}",
        "process_id": process_id,
        "repository_id": repository_id,
        "base_commit": base_commit,
        "patch_artifact_ref": f"artifact://patches/{process_id}",
        "patch_digest": patch_digest,
        "evidence_digest": evidence_digest,
        "verification_digest": verification_digest,
        "created_at": _format_time(timestamp),
        "expires_at": _format_time(timestamp + timedelta(hours=24)),
    }
    return PreparedChange(patch, evidence, verification, staged)


def build_publish_manifest(sandbox: LocalProcessSandbox, prepared: PreparedChange, changes: Mapping[str, str]) -> tuple[PublishableFile, ...]:
    """Export only verified workspace files after re-binding them to the staged patch."""

    if sha256_bytes(prepared.patch.encode("utf-8")) != prepared.staged_change["patch_digest"]:
        raise ContractValidationError("staged change patch digest no longer matches prepared change")
    manifest: list[PublishableFile] = []
    for relative_name, expected_content in sorted(changes.items()):
        relative = _safe_relative_path(relative_name)
        workspace_file = _contained_file(sandbox.workspace, relative)
        if not workspace_file.is_file() or workspace_file.is_symlink():
            raise ContractValidationError(f"verified workspace file is unavailable: {relative_name}")
        content = workspace_file.read_text(encoding="utf-8")
        if content != expected_content:
            raise ContractValidationError(f"verified workspace content changed: {relative_name}")
        manifest.append(PublishableFile(relative.as_posix(), content, sha256_bytes(content.encode("utf-8"))))
    if not manifest:
        raise ContractValidationError("publish manifest is empty")
    return tuple(manifest)


def _safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value in {"", "."}:
        raise ContractValidationError(f"unsafe relative path: {value}")
    return path


def _contained_file(root: Path, relative: Path) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ContractValidationError(f"path escapes workspace: {relative}")
    return candidate


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
