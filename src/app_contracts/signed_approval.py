"""Read-only verification of an externally signed exact-stage approval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from .approval_request import (
    MAX_APPROVAL_REQUEST_BYTES,
    ApprovalRequestError,
    build_approval_request,
)
from .authority import DeterministicPolicy, PolicyConfig
from .digests import sha256_digest
from .durable_stage import (
    DurableStageStoreError,
    SQLiteStagedArtifactStore,
    StagedArtifact,
)
from .repository_binding import RepositoryTargetBinding

MAX_SIGNED_APPROVAL_INPUT_BYTES = MAX_APPROVAL_REQUEST_BYTES
MAX_TRUST_PROFILE_BYTES = 64_000
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_APPROVAL_FIELDS = frozenset(
    {
        "schema_version", "approval_id", "approver_id", "process_id",
        "operation", "repository_id", "staged_change_digest",
        "approved_intent_digest", "policy_version", "approved_at", "expires_at",
    }
)


class SignedApprovalError(ValueError):
    """A signed approval cannot be safely verified for the supplied stage."""


@dataclass(frozen=True)
class VerifiedSignedApproval:
    """One parsed and stage-bound approval plus its deterministic policy result.

    The trust profile is still operator-supplied and unauthenticated. This
    internal value grants no provider capability and performs no effects.
    """

    result: dict[str, Any]
    artifact: StagedArtifact
    request: dict[str, Any]
    approval: dict[str, Any]
    binding: RepositoryTargetBinding
    policy_config: PolicyConfig


def verify_signed_approval(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    signed_approval_path: str | Path,
    trust_profile_path: str | Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify a signed EXP-552 request through policy without downstream effects."""
    return load_verified_signed_approval(
        database_path,
        staged_change_digest,
        request_path,
        signed_approval_path,
        trust_profile_path,
        now=now,
    ).result


def load_verified_signed_approval(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    signed_approval_path: str | Path,
    trust_profile_path: str | Path,
    *,
    now: datetime | None = None,
) -> VerifiedSignedApproval:
    """Load one exact verified signature result for a local Control Plane use.

    This returns the same untrusted operator profile and policy verdict as the
    read-only CLI. It does not authenticate a person, persist approval, or
    authorize a provider effect; downstream local gates must re-evaluate policy.
    """
    moment = _validate_clock(datetime.now(timezone.utc) if now is None else now)
    request = _read_json(request_path, MAX_SIGNED_APPROVAL_INPUT_BYTES)
    signed_envelope = _read_json(signed_approval_path, MAX_SIGNED_APPROVAL_INPUT_BYTES)
    profile = _read_json(trust_profile_path, MAX_TRUST_PROFILE_BYTES)
    binding, policy_config, profile_digest = _parse_trust_profile(profile)
    if (
        type(staged_change_digest) is not str
        or _DIGEST_PATTERN.fullmatch(staged_change_digest) is None
    ):
        raise SignedApprovalError("signed approval: stage digest is invalid")
    database = _existing_file(database_path, "signed approval: stage database is unavailable")
    try:
        with SQLiteStagedArtifactStore(database, read_only=True) as store:
            artifact = store.load(staged_change_digest)
        if type(artifact) is not StagedArtifact:
            raise SignedApprovalError("signed approval: stage is invalid")
        expected_request = _rebuild_request(artifact, binding, request)
        if _canonical_json(request) != _canonical_json(expected_request):
            raise SignedApprovalError("signed approval: request does not match stage")
        approval = _parse_signed_envelope(signed_envelope, expected_request)
        intent = expected_request["intent"]
        payload = artifact.payload_copy()
        staged_change = payload["staged_change"]
        actuator_id = "github-app-actuator"
        actuator_request = {
            "operation": "publish_pull_request",
            "repository_id": intent["repository_id"],
            "actuator_id": actuator_id,
            "staged_change_digest": artifact.staged_change_digest,
            "branch_namespace": intent["branch_namespace"],
            "idempotency_key": intent["idempotency_key"],
        }
        decision = DeterministicPolicy(policy_config).decide(
            decision_id="local-signed-approval-verification",
            actuator_request=actuator_request,
            approval=approval,
            staged_change=staged_change,
            intent=intent,
            now=moment,
        )
        result = {
            "schema": "signed-approval-verification/v1",
            "status": "policy_allowed" if decision["effect"] == "allow" else "denied",
            "decision": decision["effect"],
            "reason_codes": decision["reason_codes"],
            "staged_change_digest": artifact.staged_change_digest,
            "intent_digest": sha256_digest(intent),
            "policy_version": policy_config.version,
            "trust_profile_digest": profile_digest,
            "trust_profile_origin": "operator_supplied_unverified",
            "identity_authenticated": False,
            "provider_write": False,
        }
        return VerifiedSignedApproval(
            result=result,
            artifact=artifact,
            request=expected_request,
            approval=approval,
            binding=binding,
            policy_config=policy_config,
        )
    except SignedApprovalError:
        raise
    except (ApprovalRequestError, DurableStageStoreError):
        raise SignedApprovalError("signed approval: input verification failed") from None
    except Exception:
        raise SignedApprovalError("signed approval: input verification failed") from None


def _rebuild_request(
    artifact: StagedArtifact,
    binding: RepositoryTargetBinding,
    request: object,
) -> dict:
    if (
        type(request) is not dict
        or request.get("schema") != "approval-request/v1"
        or request.get("status") != "unsigned"
        or request.get("approval") != "not_created"
        or request.get("provider_write") is not False
        or type(request.get("intent")) is not dict
        or type(request.get("unsigned_approval")) is not dict
    ):
        raise SignedApprovalError("signed approval: request is invalid")
    intent = request["intent"]
    unsigned = request["unsigned_approval"]
    if set(unsigned) != _APPROVAL_FIELDS:
        raise SignedApprovalError("signed approval: request is invalid")
    if (
        intent.get("branch") is None
        or intent.get("base_branch") is None
        or intent.get("approval_id") != unsigned.get("approval_id")
        or intent.get("expires_at") != unsigned.get("expires_at")
    ):
        raise SignedApprovalError("signed approval: request is invalid")
    approved_at_raw = unsigned.get("approved_at")
    if type(approved_at_raw) is not str:
        raise SignedApprovalError("signed approval: request is invalid")
    try:
        approved_at = datetime.fromisoformat(approved_at_raw.replace("Z", "+00:00"))
    except ValueError:
        raise SignedApprovalError("signed approval: request is invalid") from None
    if (
        approved_at.tzinfo is None
        or approved_at.utcoffset() is None
        or approved_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        != approved_at_raw
    ):
        raise SignedApprovalError("signed approval: request is invalid")
    try:
        return build_approval_request(
            artifact,
            binding,
            branch=intent["branch"],
            base_branch=intent["base_branch"],
            approval_id=unsigned["approval_id"],
            approver_id=unsigned["approver_id"],
            policy_version=unsigned["policy_version"],
            now=approved_at,
        )
    except Exception:
        raise SignedApprovalError("signed approval: request is invalid") from None


def _parse_signed_envelope(envelope: object, request: dict) -> dict:
    if (
        type(envelope) is not dict
        or set(envelope) != {"schema", "approval"}
        or envelope.get("schema") != "signed-approval/v1"
        or type(envelope.get("approval")) is not dict
    ):
        raise SignedApprovalError("signed approval: signed artifact is invalid")
    approval = envelope["approval"]
    unsigned = request["unsigned_approval"]
    if set(approval) != _APPROVAL_FIELDS | {"signature"} or any(
        approval.get(field) != unsigned.get(field) for field in _APPROVAL_FIELDS
    ):
        raise SignedApprovalError("signed approval: signed fields mismatch")
    return approval


def _parse_trust_profile(profile: object) -> tuple[RepositoryTargetBinding, PolicyConfig, str]:
    if (
        type(profile) is not dict
        or set(profile)
        != {
            "schema", "policy_version", "target", "allowed_repositories",
            "allowed_actuators", "allowed_approver_ids",
            "trusted_approver_public_keys",
        }
        or profile.get("schema") != "approval-trust-profile/v1"
    ):
        raise SignedApprovalError("signed approval: trust profile is invalid")
    target = profile["target"]
    if type(target) is not dict or set(target) != {
        "source_repository_id", "provider_repository_id"
    }:
        raise SignedApprovalError("signed approval: trust profile is invalid")
    try:
        binding = RepositoryTargetBinding(**target)
        for field in (
            "allowed_repositories", "allowed_actuators", "allowed_approver_ids"
        ):
            members = profile[field]
            if (
                type(members) is not list
                or not members
                or any(type(member) is not str or not member for member in members)
                or len(members) != len(set(members))
            ):
                raise ValueError
        key_hex = profile["trusted_approver_public_keys"]
        if type(key_hex) is not dict or not key_hex:
            raise ValueError
        keys = {
            key_id: bytes.fromhex(value)
            for key_id, value in key_hex.items()
            if type(key_id) is str and type(value) is str
        }
        if len(keys) != len(key_hex):
            raise ValueError
        config = PolicyConfig(
            version=profile["policy_version"],
            allowed_repositories=frozenset(profile["allowed_repositories"]),
            allowed_actuators=frozenset(profile["allowed_actuators"]),
            allowed_approver_ids=frozenset(profile["allowed_approver_ids"]),
            trusted_approver_public_keys=keys,
        )
        if binding.provider_repository_id not in config.allowed_repositories:
            raise ValueError
    except Exception:
        raise SignedApprovalError("signed approval: trust profile is invalid") from None
    if (
        not config.allowed_actuators
        or "github-app-actuator" not in config.allowed_actuators
    ):
        raise SignedApprovalError("signed approval: trust profile is invalid")
    profile_digest = sha256_digest(profile)
    return binding, config, profile_digest


def _read_json(path: str | Path, limit: int) -> object:
    file_path = _existing_file(path, "signed approval: input file is unavailable")
    try:
        if file_path.stat().st_size > limit:
            raise SignedApprovalError("signed approval: input exceeds limit")
        raw = file_path.read_bytes()
        if len(raw) > limit:
            raise SignedApprovalError("signed approval: input exceeds limit")

        def reject_duplicate_pairs(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError
                value[key] = item
            return value

        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except SignedApprovalError:
        raise
    except Exception:
        raise SignedApprovalError("signed approval: input JSON is invalid") from None


def _existing_file(path: str | Path, error: str) -> Path:
    try:
        candidate = Path(path)
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError
        return candidate
    except Exception:
        raise SignedApprovalError(error) from None


def _validate_clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SignedApprovalError("signed approval: clock is invalid")
    try:
        if value.utcoffset() is None:
            raise ValueError
        return value.astimezone(timezone.utc)
    except Exception:
        raise SignedApprovalError("signed approval: clock is invalid") from None


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        raise SignedApprovalError("signed approval: input JSON is invalid") from None


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify a signed approval against one exact saved stage; no provider effect."
    )
    parser.add_argument("database", help="existing verified SQLite stage database")
    parser.add_argument("staged_change_digest", help="exact sha256 staged digest")
    parser.add_argument("request", help="EXP-552 approval-request/v1 JSON")
    parser.add_argument("signed_approval", help="signed-approval/v1 JSON")
    parser.add_argument("trust_profile", help="operator-supplied public-key/policy JSON")
    args = parser.parse_args(argv)
    try:
        result = verify_signed_approval(
            args.database,
            args.staged_change_digest,
            args.request,
            args.signed_approval,
            args.trust_profile,
            now=now,
        )
    except SignedApprovalError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
    return 0 if result["decision"] == "allow" else 3
