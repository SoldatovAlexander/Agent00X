"""Canonical, validated bundle for a verified change awaiting durable storage.

This module defines an in-memory artifact contract only. It performs no file,
database, network, credential, approval, or publication operations.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import difflib
import hashlib
import json
import posixpath
from pathlib import Path
import re
import sqlite3

from .digests import canonical_json, sha256_bytes, sha256_digest
from .executor import (
    MAX_PROPOSAL_FILE_BYTES,
    MAX_PROPOSAL_FILES,
    MAX_PROPOSAL_PATH_BYTES,
    MAX_PROPOSAL_TOTAL_BYTES,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from .publication_seed import PublicationSeed, build_publication_seed
from .verifier_attestation import MAX_ATTESTATION_BYTES
from .verifier_process import (
    MAX_VERIFIER_REQUEST_BYTES,
    parse_verifier_request,
    serialize_verifier_request,
    verifier_snapshot_tree_digest,
)
from .verifier_host_trust_decision import MAX_DECISION_BYTES
from .verifier_trust_enrollment import MAX_ENROLLMENT_BYTES
from .pinned_snapshot import MAX_SNAPSHOT_FILE_BYTES
from .repository_process import PreparedChange
from .secret_scan import CredentialLeakDetected, assert_no_credential_pattern_content

STAGED_ARTIFACT_SCHEMA_VERSION = 1
STAGED_ARTIFACT_CANONICALIZATION = "durable-staged-artifact/v1"
MAX_STAGED_ARTIFACT_BYTES = 8_000_000
MAX_STAGED_PATCH_BYTES = 2_100_000
MAX_STAGED_RECORD_BYTES = 256_000
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class DurableStageError(ValueError):
    """A verified stage bundle is malformed, unbounded, or unsafe to retain."""


class DurableStageStoreError(RuntimeError):
    """SQLite stage-store operation failed without exposing stored payloads."""


class DurableStageNotFound(DurableStageStoreError):
    """No validated stage exists for the requested digest."""


class DurableStageConflict(DurableStageStoreError):
    """A different record already occupies the content-addressed stage key."""


@dataclass(frozen=True, repr=False)
class StagedArtifact:
    """Immutable canonical JSON bundle; repr intentionally contains metadata only."""

    staged_change_digest: str
    verified_contents_digest: str
    artifact_digest: str
    canonical_payload: str

    def __post_init__(self) -> None:
        _validate_canonical_artifact(self)

    def __repr__(self) -> str:
        return (
            "StagedArtifact("
            f"staged_change_digest={self.staged_change_digest!r}, "
            f"verified_contents_digest={self.verified_contents_digest!r}, "
            f"artifact_digest={self.artifact_digest!r}, "
            f"size_bytes={len(self.canonical_payload.encode('utf-8'))})"
        )

    def payload_copy(self) -> dict:
        """Return a detached object for a future persistence adapter."""
        try:
            return json.loads(self.canonical_payload)
        except Exception:
            raise DurableStageError("durable stage: artifact is invalid") from None


def build_staged_artifact(
    request: ExecutionRequest,
    prepared: PreparedChange,
    result: ExecutionResult,
) -> StagedArtifact:
    """Validate and canonically bundle one verified, pinned prepared change."""
    if (
        type(request) is not ExecutionRequest
        or type(prepared) is not PreparedChange
        or type(result) is not ExecutionResult
        or result.status is not ExecutionStatus.VERIFIED
    ):
        raise DurableStageError("durable stage: verified execution is required")
    try:
        seed = build_publication_seed(request, result)
        if request.remote_snapshot is None:
            raise DurableStageError("durable stage: full remote snapshot is required")
        if (
            type(prepared.staged_change) is not dict
            or type(prepared.evidence_bundle) is not dict
            or type(prepared.verification_report) is not dict
            or type(prepared.patch) is not str
            or type(prepared.verified_contents) is not tuple
            or not prepared.verified_contents
            or len(prepared.verified_contents) > MAX_PROPOSAL_FILES
            or len(prepared.patch.encode("utf-8", errors="strict")) > MAX_STAGED_PATCH_BYTES
            or len(canonical_json(prepared.evidence_bundle)) > MAX_STAGED_RECORD_BYTES
            or len(canonical_json(prepared.verification_report)) > MAX_STAGED_RECORD_BYTES
        ):
            raise DurableStageError("durable stage: artifact input is invalid")
        base_by_path = {
            blob.path: blob
            for blob in request.remote_snapshot.files
        }
        base_contents = []
        previous_path = None
        proposed_total = 0
        base_total = 0
        for entry in prepared.verified_contents:
            if type(entry) is not tuple or len(entry) != 2:
                raise DurableStageError("durable stage: artifact input is invalid")
            path, content = entry
            if type(path) is not str or type(content) is not str or _safe_relative_path(path) != path:
                raise DurableStageError("durable stage: artifact input is invalid")
            if (
                (previous_path is not None and path <= previous_path)
                or path not in request.declared_change_paths
            ):
                raise DurableStageError("durable stage: artifact input is invalid")
            previous_path = path
            path_size = len(path.encode("utf-8", errors="strict"))
            content_bytes = content.encode("utf-8", errors="strict")
            if path_size > MAX_PROPOSAL_PATH_BYTES or len(content_bytes) > MAX_PROPOSAL_FILE_BYTES:
                raise DurableStageError("durable stage: artifact input is invalid")
            proposed_total += path_size + len(content_bytes)
            if proposed_total > MAX_PROPOSAL_TOTAL_BYTES:
                raise DurableStageError("durable stage: artifact input is invalid")
            blob = base_by_path.get(path)
            if blob is None:
                raise DurableStageError("durable stage: source binding is invalid")
            if type(blob.content) is not bytes or len(blob.content) > MAX_SNAPSHOT_FILE_BYTES:
                raise DurableStageError("durable stage: source binding is invalid")
            try:
                source = blob.content.decode("utf-8", errors="strict")
            except Exception:
                raise DurableStageError("durable stage: source binding is invalid") from None
            base_total += path_size + len(blob.content)
            if base_total > MAX_PROPOSAL_TOTAL_BYTES:
                raise DurableStageError("durable stage: source binding is invalid")
            expected_blob_sha = hashlib.sha1(
                b"blob " + str(len(blob.content)).encode("ascii") + b"\0" + blob.content
            ).hexdigest()
            if blob.sha != expected_blob_sha:
                raise DurableStageError("durable stage: source binding is invalid")
            base_contents.append(
                {
                    "path": path,
                    "content": source,
                    "git_blob_sha": blob.sha,
                }
            )
        payload = {
            "schema_version": STAGED_ARTIFACT_SCHEMA_VERSION,
            "canonicalization": STAGED_ARTIFACT_CANONICALIZATION,
            "seed": asdict(seed),
            "declared_change_paths": list(request.declared_change_paths),
            "staged_change": prepared.staged_change,
            "patch": prepared.patch,
            "evidence_bundle": prepared.evidence_bundle,
            "verification_report": prepared.verification_report,
            "verifier_result": _verifier_result_payload(result),
            "base_contents": base_contents,
            "verified_contents": [
                {"path": path, "content": content}
                for path, content in prepared.verified_contents
            ],
        }
        verifier_evidence = _build_verifier_trust_evidence(result, seed, request)
        if verifier_evidence is not None:
            payload["verifier_trust_evidence"] = verifier_evidence
        canonical = canonical_json(payload)
        if len(canonical) > MAX_STAGED_ARTIFACT_BYTES:
            raise DurableStageError("durable stage: artifact exceeds size limit")
        artifact = StagedArtifact(
            staged_change_digest=seed.staged_change_digest,
            verified_contents_digest=seed.verified_contents_digest,
            artifact_digest=sha256_bytes(canonical),
            canonical_payload=canonical.decode("utf-8", errors="strict"),
        )
        return artifact
    except DurableStageError:
        raise
    except Exception:
        raise DurableStageError("durable stage: execution binding is invalid") from None


def _validate_canonical_artifact(artifact: StagedArtifact) -> None:
    try:
        if (
            not isinstance(artifact.staged_change_digest, str)
            or not isinstance(artifact.verified_contents_digest, str)
            or not isinstance(artifact.artifact_digest, str)
            or not isinstance(artifact.canonical_payload, str)
        ):
            raise ValueError
        raw = artifact.canonical_payload.encode("utf-8", errors="strict")
        if len(raw) > MAX_STAGED_ARTIFACT_BYTES:
            raise DurableStageError("durable stage: artifact exceeds size limit")
        if sha256_bytes(raw) != artifact.artifact_digest:
            raise ValueError
        payload = json.loads(artifact.canonical_payload)
        if type(payload) is not dict or canonical_json(payload) != raw:
            raise ValueError
        base_payload_fields = {
            "schema_version",
            "canonicalization",
            "seed",
            "declared_change_paths",
            "staged_change",
            "patch",
            "evidence_bundle",
            "verification_report",
            "verifier_result",
            "base_contents",
            "verified_contents",
        }
        if frozenset(payload) not in {
            frozenset(base_payload_fields),
            frozenset(base_payload_fields | {"verifier_trust_evidence"}),
        }:
            raise ValueError
        if (
            payload["schema_version"] != STAGED_ARTIFACT_SCHEMA_VERSION
            or payload["canonicalization"] != STAGED_ARTIFACT_CANONICALIZATION
        ):
            raise ValueError
        declared_paths = payload["declared_change_paths"]
        if (
            type(declared_paths) is not list
            or not declared_paths
            or any(type(path) is not str or _safe_relative_path(path) != path for path in declared_paths)
            or declared_paths != sorted(set(declared_paths))
        ):
            raise ValueError

        seed_payload = payload["seed"]
        if type(seed_payload) is not dict:
            raise ValueError
        seed = PublicationSeed(**seed_payload)
        staged = payload["staged_change"]
        if type(staged) is not dict or sha256_digest(staged) != seed.staged_change_digest:
            raise ValueError
        evidence = payload["evidence_bundle"]
        verification = payload["verification_report"]
        verifier_result = payload["verifier_result"]
        verifier_fields = {
            "process_id",
            "base_commit",
            "snapshot_tree_digest",
            "replay_result_digest",
            "verifier_id",
            "patch_digest",
            "evidence_digest",
            "verification_digest",
            "verified_contents_digest",
            "verdict",
            "blocker_codes",
            "evidence_origin",
        }
        if (
            staged.get("process_id") != seed.process_id
            or staged.get("repository_id") != seed.repository_id
            or staged.get("base_commit") != seed.base_commit
            or staged.get("patch_digest") != sha256_bytes(payload["patch"].encode("utf-8"))
            or staged.get("evidence_digest") != sha256_digest(evidence)
            or staged.get("verification_digest") != sha256_digest(verification)
            or type(evidence) is not dict
            or evidence.get("process_id") != seed.process_id
            or evidence.get("patch_digest") != staged.get("patch_digest")
            or type(verification) is not dict
            or verification.get("evidence_digest") != staged.get("evidence_digest")
            or verification.get("verdict") != "pass"
            or type(verifier_result) is not dict
            or set(verifier_result) != verifier_fields
            or verifier_result.get("process_id") != seed.process_id
            or verifier_result.get("base_commit") != seed.base_commit
            or verifier_result.get("verifier_id") != seed.verifier_id
            or verifier_result.get("verdict") != seed.verdict
            or verifier_result.get("patch_digest") != staged.get("patch_digest")
            or verifier_result.get("evidence_digest") != staged.get("evidence_digest")
            or verifier_result.get("verification_digest") != staged.get("verification_digest")
            or verifier_result.get("verified_contents_digest") != seed.verified_contents_digest
            or verifier_result.get("replay_result_digest") != seed.replay_result_digest
            or verifier_result.get("snapshot_tree_digest") != seed.snapshot_tree_digest
            or verifier_result.get("blocker_codes") != []
            or verifier_result.get("evidence_origin") != "local_test"
        ):
            raise ValueError

        _validate_verifier_trust_evidence(
            payload.get("verifier_trust_evidence"),
            seed,
            verifier_result,
            payload,
        )

        base_records = payload["base_contents"]
        records = payload["verified_contents"]
        if type(records) is not list or not records or len(records) > MAX_PROPOSAL_FILES:
            raise ValueError
        if type(base_records) is not list or len(base_records) != len(records):
            raise ValueError
        contents: list[tuple[str, str]] = []
        credential_scan: list[tuple[str, bytes]] = []
        base_credential_scan: list[tuple[str, bytes]] = []
        base_contents: list[tuple[str, str]] = []
        base_content_digests: list[str] = []
        previous_path: str | None = None
        proposed_total_bytes = 0
        base_total_bytes = 0
        for base_record, record in zip(base_records, records, strict=True):
            if (
                type(base_record) is not dict
                or set(base_record) != {"path", "content", "git_blob_sha"}
            ):
                raise ValueError
            base_path, base_text, blob_sha = (
                base_record["path"],
                base_record["content"],
                base_record["git_blob_sha"],
            )
            if type(record) is not dict or set(record) != {"path", "content"}:
                raise ValueError
            path, content = record["path"], record["content"]
            if (
                type(path) is not str
                or type(content) is not str
                or type(base_path) is not str
                or type(base_text) is not str
                or type(blob_sha) is not str
                or base_path != path
            ):
                raise ValueError
            path_bytes = path.encode("utf-8", errors="strict")
            content_bytes = content.encode("utf-8", errors="strict")
            base_bytes = base_text.encode("utf-8", errors="strict")
            normalized = _safe_relative_path(path)
            if (
                normalized != path
                or len(path_bytes) > MAX_PROPOSAL_PATH_BYTES
                or len(content_bytes) > MAX_PROPOSAL_FILE_BYTES
                or len(base_bytes) > MAX_SNAPSHOT_FILE_BYTES
                or (previous_path is not None and path <= previous_path)
            ):
                raise ValueError
            previous_path = path
            if path not in declared_paths:
                raise ValueError
            proposed_total_bytes += len(path_bytes) + len(content_bytes)
            base_total_bytes += len(path_bytes) + len(base_bytes)
            if (
                proposed_total_bytes > MAX_PROPOSAL_TOTAL_BYTES
                or base_total_bytes > MAX_PROPOSAL_TOTAL_BYTES
            ):
                raise ValueError
            expected_blob_sha = hashlib.sha1(
                b"blob " + str(len(base_bytes)).encode("ascii") + b"\0" + base_bytes
            ).hexdigest()
            if blob_sha != expected_blob_sha:
                raise ValueError
            contents.append((path, content))
            base_contents.append((path, base_text))
            base_content_digests.append(sha256_bytes(base_bytes))
            base_credential_scan.append((path, base_bytes))
            credential_scan.append((path, content_bytes))
        contents_tuple = tuple(contents)
        source_digests = evidence.get("source_digests")
        if (
            type(source_digests) is not list
            or source_digests != base_content_digests
        ):
            raise ValueError
        if _render_patch(tuple(base_contents), contents_tuple) != payload["patch"]:
            raise ValueError
        if sha256_digest(contents_tuple) != seed.verified_contents_digest:
            raise ValueError
        assert_no_credential_pattern_content(tuple(credential_scan))
        assert_no_credential_pattern_content(tuple(base_credential_scan))
        if (
            artifact.staged_change_digest != seed.staged_change_digest
            or artifact.verified_contents_digest != seed.verified_contents_digest
        ):
            raise ValueError
    except DurableStageError:
        raise
    except CredentialLeakDetected:
        raise DurableStageError("durable stage: credential-shaped content detected") from None
    except Exception:
        raise DurableStageError("durable stage: artifact is invalid") from None


def _build_verifier_trust_evidence(
    result: ExecutionResult, seed: PublicationSeed, request: ExecutionRequest
) -> dict[str, object] | None:
    response = result.verifier_attestation_bytes
    enrollment = result.verifier_trust_enrollment_bytes
    decision = result.verifier_host_trust_decision_bytes
    request_digest = result.verifier_request_digest
    verifier_request = result.verifier_request_bytes
    if all(value is None for value in (response, enrollment, decision, request_digest)):
        if any((
            seed.verifier_attestation_digest,
            seed.verifier_trust_enrollment_digest,
            seed.verifier_host_trust_decision_digest,
        )):
            raise DurableStageError("durable stage: verifier evidence is unavailable")
        return None
    if (
        type(response) is not bytes
        or len(response) > MAX_ATTESTATION_BYTES
        or type(request_digest) is not str
        or _DIGEST_PATTERN.fullmatch(request_digest) is None
        or (enrollment is not None and type(enrollment) is not bytes)
        or (decision is not None and type(decision) is not bytes)
        or (verifier_request is not None and type(verifier_request) is not bytes)
    ):
        raise DurableStageError("durable stage: verifier evidence is invalid")
    if (
        (enrollment is None) != (seed.verifier_trust_enrollment_digest is None)
        or (decision is None) != (seed.verifier_host_trust_decision_digest is None)
        or (decision is not None and enrollment is None)
    ):
        raise DurableStageError("durable stage: verifier evidence is incomplete")
    try:
        envelope = _parse_canonical_public_record(response, MAX_ATTESTATION_BYTES)
        if (
            sha256_bytes(response) != seed.verifier_attestation_digest
            or envelope.get("key_id") != seed.verifier_attestation_key_id
            or envelope.get("verifier_profile_digest")
            != seed.verifier_attestation_profile_digest
            or envelope.get("request_digest") != request_digest
        ):
            raise ValueError
        if enrollment is not None:
            enrollment_record = _parse_canonical_public_record(
                enrollment, MAX_ENROLLMENT_BYTES
            )
            if (
                sha256_bytes(enrollment) != seed.verifier_trust_enrollment_digest
                or enrollment_record.get("verifier_key_id")
                != seed.verifier_attestation_key_id
                or enrollment_record.get("verifier_profile_digest")
                != seed.verifier_attestation_profile_digest
            ):
                raise ValueError
        if decision is not None:
            decision_record = _parse_canonical_public_record(
                decision, MAX_DECISION_BYTES
            )
            if (
                sha256_bytes(decision) != seed.verifier_host_trust_decision_digest
                or decision_record.get("enrollment_digest")
                != seed.verifier_trust_enrollment_digest
                or any(
                    decision_record.get(field) != enrollment_record.get(field)
                    for field in (
                        "endpoint_url", "verifier_id", "verifier_profile_digest",
                        "verifier_key_id", "worker_host_id", "verifier_host_id",
                        "host_separation_evidence_digest",
                    )
                )
            ):
                raise ValueError
        evidence = {
            "schema": (
                "persisted-verifier-trust-evidence/v2"
                if verifier_request is not None else "persisted-verifier-trust-evidence/v1"
            ),
            "request_digest": request_digest,
            "signed_response_base64": base64.b64encode(response).decode("ascii"),
            "trust_enrollment_base64": (
                base64.b64encode(enrollment).decode("ascii")
                if enrollment is not None else None
            ),
            "host_trust_decision_base64": (
                base64.b64encode(decision).decode("ascii")
                if decision is not None else None
            ),
        }
        if verifier_request is not None:
            if (
                len(verifier_request) > MAX_VERIFIER_REQUEST_BYTES
                or sha256_bytes(verifier_request) != request_digest
            ):
                raise ValueError
            evidence["verifier_request_base64"] = base64.b64encode(
                verifier_request
            ).decode("ascii")
            evidence["request_context"] = {
                "test_command": list(request.test_command),
                "test_timeout_seconds": request.test_timeout_seconds,
            }
        return evidence
    except DurableStageError:
        raise
    except Exception:
        raise DurableStageError("durable stage: verifier evidence is invalid") from None


def _validate_verifier_trust_evidence(
    evidence: object,
    seed: PublicationSeed,
    verifier_result: object,
    payload: dict[str, object],
) -> None:
    # Absence is valid for legacy stages. It is not evidence that the verifier
    # signature or its authority provenance can be revalidated after reopen.
    if evidence is None:
        return
    if (
        type(evidence) is not dict
        or set(evidence) not in ({
            "schema", "request_digest", "signed_response_base64",
            "trust_enrollment_base64", "host_trust_decision_base64",
        }, {
            "schema", "request_digest", "signed_response_base64",
            "trust_enrollment_base64", "host_trust_decision_base64",
            "verifier_request_base64", "request_context",
        })
        or evidence.get("schema") not in {
            "persisted-verifier-trust-evidence/v1",
            "persisted-verifier-trust-evidence/v2",
        }
        or type(evidence.get("request_digest")) is not str
        or _DIGEST_PATTERN.fullmatch(evidence["request_digest"]) is None
        or type(evidence.get("signed_response_base64")) is not str
    ):
        raise DurableStageError("durable stage: verifier evidence is invalid")
    try:
        response = _decode_evidence_bytes(
            evidence["signed_response_base64"], MAX_ATTESTATION_BYTES
        )
        envelope = _parse_canonical_public_record(response, MAX_ATTESTATION_BYTES)
        if (
            sha256_bytes(response) != seed.verifier_attestation_digest
            or envelope.get("request_digest") != evidence["request_digest"]
            or envelope.get("key_id") != seed.verifier_attestation_key_id
            or envelope.get("verifier_profile_digest")
            != seed.verifier_attestation_profile_digest
            or type(envelope.get("response")) is not dict
            or envelope["response"].get("verifier_result") != verifier_result
        ):
            raise ValueError
        has_request = "verifier_request_base64" in evidence
        if has_request != (
            evidence.get("schema") == "persisted-verifier-trust-evidence/v2"
        ):
            raise ValueError
        if has_request:
            request_bytes = _decode_evidence_bytes(
                evidence["verifier_request_base64"], MAX_VERIFIER_REQUEST_BYTES
            )
            request = parse_verifier_request(request_bytes)
            if serialize_verifier_request(request) != request_bytes:
                raise ValueError
            validate_verifier_request_binding(
                request,
                evidence.get("request_context"),
                seed,
                payload,
                evidence["request_digest"],
            )
        enrollment_b64 = evidence["trust_enrollment_base64"]
        decision_b64 = evidence["host_trust_decision_base64"]
        if (enrollment_b64 is None) != (
            seed.verifier_trust_enrollment_digest is None
        ) or (decision_b64 is None) != (
            seed.verifier_host_trust_decision_digest is None
        ) or (decision_b64 is not None and enrollment_b64 is None):
            raise ValueError
        enrollment_record = None
        if enrollment_b64 is not None:
            if type(enrollment_b64) is not str:
                raise ValueError
            enrollment = _decode_evidence_bytes(enrollment_b64, MAX_ENROLLMENT_BYTES)
            enrollment_record = _parse_canonical_public_record(
                enrollment, MAX_ENROLLMENT_BYTES
            )
            if (
                sha256_bytes(enrollment) != seed.verifier_trust_enrollment_digest
                or enrollment_record.get("verifier_key_id")
                != seed.verifier_attestation_key_id
                or enrollment_record.get("verifier_profile_digest")
                != seed.verifier_attestation_profile_digest
            ):
                raise ValueError
        if decision_b64 is not None:
            if type(decision_b64) is not str or enrollment_record is None:
                raise ValueError
            decision = _decode_evidence_bytes(decision_b64, MAX_DECISION_BYTES)
            decision_record = _parse_canonical_public_record(
                decision, MAX_DECISION_BYTES
            )
            if (
                sha256_bytes(decision) != seed.verifier_host_trust_decision_digest
                or decision_record.get("enrollment_digest")
                != seed.verifier_trust_enrollment_digest
                or any(
                    decision_record.get(field) != enrollment_record.get(field)
                    for field in (
                        "endpoint_url", "verifier_id", "verifier_profile_digest",
                        "verifier_key_id", "worker_host_id", "verifier_host_id",
                        "host_separation_evidence_digest",
                    )
                )
            ):
                raise ValueError
    except DurableStageError:
        raise
    except Exception:
        raise DurableStageError("durable stage: verifier evidence is invalid") from None


def validate_verifier_request_binding(
    request: object,
    request_context: object,
    seed: PublicationSeed,
    payload: dict[str, object],
    request_digest: str,
) -> None:
    try:
        verifier_input = request.verifier_input
        staged = payload["staged_change"]
        evidence_bundle = payload["evidence_bundle"]
        verification_report = payload["verification_report"]
        verifier_result = payload["verifier_result"]
        expected_contents = tuple(
            (item["path"], item["content"])
            for item in payload["verified_contents"]
        )
        if (
            type(request_context) is not dict
            or set(request_context) != {"test_command", "test_timeout_seconds"}
            or request_context["test_command"] != list(verifier_input.test_command)
            or request_context["test_timeout_seconds"]
            != verifier_input.test_timeout_seconds
            or verifier_input.process_id != seed.process_id
            or verifier_input.repository_id != seed.repository_id
            or verifier_input.base_commit != seed.base_commit
            or verifier_input.snapshot_tree_digest != seed.snapshot_tree_digest
            or verifier_input.snapshot_claim_digest != seed.snapshot_claim_digest
            or verifier_input.declared_change_paths
            != tuple(payload["declared_change_paths"])
            or verifier_input.verified_contents != expected_contents
            or verifier_input.patch_digest != staged["patch_digest"]
            or verifier_input.evidence_digest != staged["evidence_digest"]
            or verifier_input.verification_digest != staged["verification_digest"]
            or verifier_input.verified_contents_digest
            != seed.verified_contents_digest
            or verifier_input.replay_result_digest != seed.replay_result_digest
            or verifier_input.evidence_origin != "local_test"
            or request_digest != sha256_bytes(serialize_verifier_request(request))
            or verifier_input.patch_digest != sha256_bytes(payload["patch"].encode("utf-8"))
            or verifier_input.evidence_digest != sha256_digest(evidence_bundle)
            or verifier_input.verification_digest != sha256_digest(verification_report)
            or verifier_input.verified_contents_digest
            != sha256_digest(tuple((entry["path"], entry["content"]) for entry in payload["verified_contents"]))
            or verifier_result.get("process_id") != verifier_input.process_id
            or verifier_result.get("base_commit") != verifier_input.base_commit
            or verifier_result.get("snapshot_tree_digest")
            != verifier_input.snapshot_tree_digest
            or verifier_result.get("replay_result_digest")
            != verifier_input.replay_result_digest
            or verifier_result.get("patch_digest") != verifier_input.patch_digest
            or verifier_result.get("evidence_digest") != verifier_input.evidence_digest
            or verifier_result.get("verification_digest")
            != verifier_input.verification_digest
            or verifier_result.get("verified_contents_digest")
            != verifier_input.verified_contents_digest
        ):
            raise ValueError
        if verifier_input.snapshot_tree_digest is None:
            if verifier_input.snapshot_files:
                raise ValueError
        elif verifier_snapshot_tree_digest(
            verifier_input.snapshot_files
        ) != verifier_input.snapshot_tree_digest:
            raise ValueError
        assert_no_credential_pattern_content(
            tuple(
                (path, content)
                for path, _mode, content in verifier_input.snapshot_files
            )
        )
    except Exception:
        raise DurableStageError("durable stage: verifier evidence is invalid") from None


def _decode_evidence_bytes(value: str, limit: int) -> bytes:
    try:
        if type(value) is not str or len(value) > ((limit + 2) // 3) * 4:
            raise ValueError
        raw = base64.b64decode(value, validate=True)
        if not raw or len(raw) > limit:
            raise ValueError
        return raw
    except Exception:
        raise DurableStageError("durable stage: verifier evidence is invalid") from None


def _parse_canonical_public_record(raw: bytes, limit: int) -> dict:
    try:
        if type(raw) is not bytes or not raw or len(raw) > limit:
            raise ValueError
        record = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        if type(record) is not dict or canonical_json(record) != raw:
            raise ValueError
        return record
    except Exception:
        raise DurableStageError("durable stage: verifier evidence is invalid") from None


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _safe_relative_path(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or value.startswith("/")
        or "\\" in value
        or "//" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError
    normalized = posixpath.normpath(value)
    if normalized in {"", "."} or normalized.startswith("../") or normalized == "..":
        raise ValueError
    return normalized


def _render_patch(
    base_contents: tuple[tuple[str, str], ...],
    verified_contents: tuple[tuple[str, str], ...],
) -> str:
    base_by_path = dict(base_contents)
    rendered: list[str] = []
    for path, content in verified_contents:
        before = base_by_path.get(path)
        if before is None or before == content:
            raise ValueError
        rendered.extend(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
    patch_text = "".join(rendered)
    if not patch_text:
        raise ValueError
    return patch_text


def _verifier_result_payload(result: ExecutionResult) -> dict:
    verifier = result.verifier_result
    if verifier is None:
        raise DurableStageError("durable stage: verifier result is missing")
    return {
        "process_id": verifier.process_id,
        "base_commit": verifier.base_commit,
        "snapshot_tree_digest": verifier.snapshot_tree_digest,
        "replay_result_digest": verifier.replay_result_digest,
        "verifier_id": verifier.verifier_id,
        "patch_digest": verifier.patch_digest,
        "evidence_digest": verifier.evidence_digest,
        "verification_digest": verifier.verification_digest,
        "verified_contents_digest": verifier.verified_contents_digest,
        "verdict": verifier.verdict.value,
        "blocker_codes": list(verifier.blocker_codes),
        "evidence_origin": verifier.evidence_origin,
    }


class SQLiteStagedArtifactStore:
    """Local SQLite storage keyed by the approval-bound staged-change digest.

    This prototype is not encrypted, does not resist privileged host tampering,
    and does not provide production multi-process writer guarantees.
    """

    def __init__(self, path: Path | str, *, read_only: bool = False) -> None:
        if isinstance(path, Path):
            path_text = str(path)
        elif isinstance(path, str):
            path_text = path
        else:
            path_text = ""
        if not path_text or path_text == ":memory:":
            raise DurableStageStoreError("durable stage store: database path is invalid")
        if type(read_only) is not bool:
            raise DurableStageStoreError("durable stage store: mode is invalid")
        self._connection: sqlite3.Connection | None = None
        self._read_only = read_only
        try:
            if read_only:
                path_object = Path(path_text)
                if path_object.is_symlink() or not path_object.is_file():
                    raise sqlite3.DatabaseError("read-only database path unavailable")
                if (
                    path_object.with_name(path_object.name + "-wal").exists()
                    or path_object.with_name(path_object.name + "-shm").exists()
                ):
                    raise sqlite3.DatabaseError("database is not quiescent")
                database_uri = (
                    path_object.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
                )
                connection = sqlite3.connect(
                    database_uri, timeout=5.0, isolation_level=None, uri=True
                )
            else:
                connection = sqlite3.connect(path_text, timeout=5.0, isolation_level=None)
            connection.row_factory = sqlite3.Row
            if read_only:
                connection.execute("PRAGMA query_only=ON")
                connection.execute(
                    """SELECT staged_change_digest, artifact_digest, canonical_payload
                       FROM staged_artifacts LIMIT 0"""
                )
            else:
                journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
                connection.execute("PRAGMA synchronous=FULL")
                synchronous = connection.execute("PRAGMA synchronous").fetchone()
                if (
                    not journal_mode
                    or type(journal_mode[0]) is not str
                    or journal_mode[0].lower() != "wal"
                    or not synchronous
                    or synchronous[0] != 2
                ):
                    raise sqlite3.DatabaseError("required local journal mode unavailable")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS staged_artifacts (
                        staged_change_digest TEXT PRIMARY KEY NOT NULL,
                        artifact_digest TEXT NOT NULL,
                        canonical_payload BLOB NOT NULL
                    ) WITHOUT ROWID"""
                )
        except Exception:
            try:
                connection.close()  # type: ignore[possibly-undefined]
            except Exception:
                pass
            raise DurableStageStoreError("durable stage store: database is unavailable") from None
        self._connection = connection

    def __repr__(self) -> str:
        return f"SQLiteStagedArtifactStore(open={self._connection is not None})"

    def __enter__(self) -> SQLiteStagedArtifactStore:
        self._require_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.close()
        return False

    def close(self) -> None:
        connection = self._connection
        if connection is None:
            return
        self._connection = None
        try:
            connection.close()
        except Exception:
            raise DurableStageStoreError("durable stage store: close failed") from None

    def save(self, artifact: StagedArtifact) -> StagedArtifact:
        connection = self._require_open()
        if self._read_only:
            raise DurableStageStoreError("durable stage store: store is read-only")
        candidate = _revalidate_artifact(artifact)
        raw = candidate.canonical_payload.encode("utf-8", errors="strict")
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT staged_change_digest, artifact_digest, canonical_payload
                   FROM staged_artifacts WHERE staged_change_digest = ?""",
                (candidate.staged_change_digest,),
            ).fetchone()
            if row is not None:
                existing = _artifact_from_row(row, candidate.staged_change_digest)
                if (
                    existing.artifact_digest == candidate.artifact_digest
                    and existing.canonical_payload == candidate.canonical_payload
                ):
                    connection.execute("COMMIT")
                    return existing
                raise DurableStageConflict("durable stage store: digest key conflict")
            connection.execute(
                """INSERT INTO staged_artifacts
                   (staged_change_digest, artifact_digest, canonical_payload)
                   VALUES (?, ?, ?)""",
                (
                    candidate.staged_change_digest,
                    candidate.artifact_digest,
                    sqlite3.Binary(raw),
                ),
            )
            connection.execute("COMMIT")
            return candidate
        except DurableStageStoreError:
            _rollback(connection)
            raise
        except Exception:
            _rollback(connection)
            raise DurableStageStoreError("durable stage store: save failed") from None

    def load(self, staged_change_digest: str) -> StagedArtifact:
        connection = self._require_open()
        if (
            not isinstance(staged_change_digest, str)
            or _DIGEST_PATTERN.fullmatch(staged_change_digest) is None
        ):
            raise DurableStageStoreError("durable stage store: digest is invalid")
        try:
            row = connection.execute(
                """SELECT staged_change_digest, artifact_digest, canonical_payload
                   FROM staged_artifacts WHERE staged_change_digest = ?""",
                (staged_change_digest,),
            ).fetchone()
        except Exception:
            raise DurableStageStoreError("durable stage store: load failed") from None
        if row is None:
            raise DurableStageNotFound("durable stage store: stage not found")
        return _artifact_from_row(row, staged_change_digest)

    def _require_open(self) -> sqlite3.Connection:
        if self._connection is None:
            raise DurableStageStoreError("durable stage store: store is closed")
        return self._connection


def _revalidate_artifact(artifact: StagedArtifact) -> StagedArtifact:
    if type(artifact) is not StagedArtifact:
        raise DurableStageStoreError("durable stage store: artifact is invalid")
    try:
        return StagedArtifact(
            staged_change_digest=artifact.staged_change_digest,
            verified_contents_digest=artifact.verified_contents_digest,
            artifact_digest=artifact.artifact_digest,
            canonical_payload=artifact.canonical_payload,
        )
    except Exception:
        raise DurableStageStoreError("durable stage store: artifact is invalid") from None


def _artifact_from_row(row: object, expected_digest: str) -> StagedArtifact:
    try:
        if (
            not isinstance(row, sqlite3.Row)
            or set(row.keys()) != {
                "staged_change_digest",
                "artifact_digest",
                "canonical_payload",
            }
            or type(row["staged_change_digest"]) is not str
            or type(row["artifact_digest"]) is not str
            or type(row["canonical_payload"]) is not bytes
            or row["staged_change_digest"] != expected_digest
        ):
            raise ValueError
        artifact = StagedArtifact(
            staged_change_digest=row["staged_change_digest"],
            verified_contents_digest=_verified_digest_from_payload(row["canonical_payload"]),
            artifact_digest=row["artifact_digest"],
            canonical_payload=row["canonical_payload"].decode("utf-8", errors="strict"),
        )
        return artifact
    except Exception:
        raise DurableStageStoreError("durable stage store: stored artifact is invalid") from None


def _verified_digest_from_payload(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
        value = payload["seed"]["verified_contents_digest"]
        if type(value) is not str or _DIGEST_PATTERN.fullmatch(value) is None:
            raise ValueError
        return value
    except Exception:
        raise DurableStageStoreError("durable stage store: stored artifact is invalid") from None


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except Exception:
        pass
