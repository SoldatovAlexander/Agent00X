"""Read-only preparation of an unsigned, digest-bound human approval request."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Mapping

from .approval_signature import approval_signature_payload
from .digests import sha256_bytes, sha256_digest
from .durable_stage import (
    DurableStageStoreError,
    SQLiteStagedArtifactStore,
    StagedArtifact,
)
from .publication_seed import (
    PublicationSeed,
    PublicationSeedError,
    bind_publication_seed_to_target,
    derive_publication_intent,
)
from .repository_binding import RepositoryTargetBinding, provider_repository_id
from .stage_preview import MAX_PREVIEW_BYTES, StagePreviewError, build_stage_preview


APPROVAL_REQUEST_TTL_SECONDS = 300
MAX_APPROVAL_REQUEST_BYTES = MAX_PREVIEW_BYTES + 32_768
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_APPROVAL_ID_PATTERN = re.compile(r"approval-[a-z0-9-]{1,96}\Z")
_PRINCIPAL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}\Z")
_POLICY_VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class ApprovalRequestError(ValueError):
    """An unsigned approval request cannot be safely prepared."""


def _validate_clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ApprovalRequestError("approval request: clock is invalid")
    try:
        if value.utcoffset() is None:
            raise ApprovalRequestError("approval request: clock is invalid")
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise ApprovalRequestError("approval request: clock is invalid") from None


def repository_target_binding_from_metadata(
    metadata: Mapping[str, str],
) -> RepositoryTargetBinding:
    """Build a target binding from non-secret GitHub App metadata only."""
    if not isinstance(metadata, Mapping):
        raise ApprovalRequestError("approval request: target metadata is invalid")
    source = metadata.get("AGENT_GITHUB_TEST_REPOSITORY")
    installation = metadata.get("AGENT_GITHUB_INSTALLATION_ID")
    repository = metadata.get("AGENT_GITHUB_REPOSITORY_ID")
    if (
        type(source) is not str
        or type(installation) is not str
        or re.fullmatch(r"[1-9][0-9]*", installation) is None
        or type(repository) is not str
        or re.fullmatch(r"[1-9][0-9]*", repository) is None
    ):
        raise ApprovalRequestError("approval request: target metadata is invalid")
    try:
        authority_id = provider_repository_id(int(installation), int(repository))
        return RepositoryTargetBinding(source, authority_id)
    except Exception:
        raise ApprovalRequestError("approval request: target metadata is invalid") from None


def build_approval_request(
    artifact: StagedArtifact,
    binding: RepositoryTargetBinding,
    *,
    branch: str,
    base_branch: str,
    approval_id: str,
    approver_id: str,
    policy_version: str,
    now: datetime,
) -> dict:
    """Create a bounded, unsigned request and exact bytes for out-of-band signing."""
    if type(artifact) is not StagedArtifact or type(binding) is not RepositoryTargetBinding:
        raise ApprovalRequestError("approval request: verified stage or target is invalid")
    moment = _validate_clock(now)
    if (
        type(approval_id) is not str
        or _APPROVAL_ID_PATTERN.fullmatch(approval_id) is None
        or type(approver_id) is not str
        or _PRINCIPAL_PATTERN.fullmatch(approver_id) is None
        or type(policy_version) is not str
        or _POLICY_VERSION_PATTERN.fullmatch(policy_version) is None
    ):
        raise ApprovalRequestError("approval request: approval metadata is invalid")
    try:
        validated = StagedArtifact(
            staged_change_digest=artifact.staged_change_digest,
            verified_contents_digest=artifact.verified_contents_digest,
            artifact_digest=artifact.artifact_digest,
            canonical_payload=artifact.canonical_payload,
        )
        payload = validated.payload_copy()
        source_seed = PublicationSeed(**payload["seed"])
        seed = bind_publication_seed_to_target(source_seed, binding)
        intent = derive_publication_intent(seed, branch, base_branch)
        source_stage = payload["staged_change"]
        if (
            not isinstance(source_stage, dict)
            or source_stage.get("repository_id") != binding.source_repository_id
            or source_stage.get("base_commit") != seed.base_commit
            or seed.verdict != "pass"
        ):
            raise ApprovalRequestError("approval request: stage binding is invalid")

        approved_at = moment.isoformat().replace("+00:00", "Z")
        expires_at = (moment + timedelta(seconds=APPROVAL_REQUEST_TTL_SECONDS)).isoformat().replace(
            "+00:00", "Z"
        )
        engine_intent = {
            "process_id": intent.process_id,
            "repository_id": intent.repository_id,
            "source_repository_id": intent.source_repository_id,
            "base_commit": intent.base_commit,
            "base_branch": intent.base_branch,
            "branch": intent.branch,
            "operation": "publish_pull_request",
            "approval_id": approval_id,
            "expires_at": expires_at,
            "branch_namespace": intent.branch.split("/", 1)[0],
            "idempotency_key": intent.idempotency_key,
            "staged_change_digest": intent.staged_change_digest,
        }
        unsigned_approval = {
            "schema_version": 1,
            "approval_id": approval_id,
            "approver_id": approver_id,
            "process_id": intent.process_id,
            "operation": "publish_pull_request",
            "repository_id": intent.repository_id,
            "staged_change_digest": intent.staged_change_digest,
            "approved_intent_digest": sha256_digest(engine_intent),
            "policy_version": policy_version,
            "approved_at": approved_at,
            "expires_at": expires_at,
        }
        signing_bytes = approval_signature_payload(unsigned_approval)
        review = build_stage_preview(validated)
        review["requested_action"] = {
            "operation": "publish_pull_request",
            "source_repository_id": binding.source_repository_id,
            "provider_repository_id": binding.provider_repository_id,
            "base_commit": intent.base_commit,
            "base_branch": intent.base_branch,
            "branch": intent.branch,
            "staged_change_digest": intent.staged_change_digest,
            "verified_contents_digest": seed.verified_contents_digest,
            "intent_digest": sha256_digest(engine_intent),
            "approver_id": approver_id,
            "policy_version": policy_version,
            "expires_at": expires_at,
        }
        request = {
            "schema": "approval-request/v1",
            "status": "unsigned",
            "approval": "not_created",
            "provider_write": False,
            "target": {
                "source_repository_id": binding.source_repository_id,
                "provider_repository_id": binding.provider_repository_id,
            },
            "stage": {
                "staged_change_digest": validated.staged_change_digest,
                "artifact_digest": validated.artifact_digest,
                "verified_contents_digest": validated.verified_contents_digest,
            },
            "intent": engine_intent,
            "unsigned_approval": unsigned_approval,
            "signing_payload_base64": base64.b64encode(signing_bytes).decode("ascii"),
            "signing_payload_digest": sha256_bytes(signing_bytes),
            "review": review,
        }
        encoded = json.dumps(
            request, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
        ).encode("utf-8")
        if len(encoded) > MAX_APPROVAL_REQUEST_BYTES:
            raise ApprovalRequestError("approval request: output exceeds size limit")
        return request
    except ApprovalRequestError:
        raise
    except (DurableStageStoreError, PublicationSeedError, StagePreviewError):
        raise ApprovalRequestError("approval request: verified stage or target is invalid") from None
    except Exception:
        raise ApprovalRequestError("approval request: verified stage or target is invalid") from None


def load_approval_request(
    database_path: str | Path,
    staged_change_digest: str,
    binding: RepositoryTargetBinding,
    **request_fields,
) -> dict:
    """Load exactly one stage read-only and build an unsigned review request."""
    if type(staged_change_digest) is not str or _DIGEST_PATTERN.fullmatch(
        staged_change_digest
    ) is None:
        raise ApprovalRequestError("approval request: stage digest is invalid")
    try:
        path = Path(database_path)
        if path.is_symlink() or not path.is_file():
            raise ApprovalRequestError("approval request: stage database is unavailable")
        with SQLiteStagedArtifactStore(path, read_only=True) as store:
            artifact = store.load(staged_change_digest)
        return build_approval_request(artifact, binding, **request_fields)
    except ApprovalRequestError:
        raise
    except Exception:
        raise ApprovalRequestError("approval request: stage database is unavailable") from None


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an unsigned human review request for an exact verified stage."
    )
    parser.add_argument("database", help="existing local SQLite stage database")
    parser.add_argument("staged_change_digest", help="exact sha256 stage digest")
    parser.add_argument("branch", help="explicit branch in the agent/ namespace")
    parser.add_argument("base_branch", help="explicit pull-request base branch")
    parser.add_argument("approval_id", help="unique approval-... identifier")
    parser.add_argument("approver_id", help="trusted approver principal identifier")
    parser.add_argument("policy_version", help="exact policy version for later validation")
    args = parser.parse_args(argv)
    metadata = os.environ if environ is None else environ
    try:
        binding = repository_target_binding_from_metadata(metadata)
        generated_at = datetime.now(timezone.utc) if now is None else now
        request = load_approval_request(
            args.database,
            args.staged_change_digest,
            binding,
            branch=args.branch,
            base_branch=args.base_branch,
            approval_id=args.approval_id,
            approver_id=args.approver_id,
            policy_version=args.policy_version,
            now=generated_at,
        )
    except ApprovalRequestError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(request, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2))
    return 0
