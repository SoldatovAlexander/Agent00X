"""One-shot signing of a human-reviewed approval bound to an exact saved stage.

Signing is local and creates no provider effect. A trusted outer runtime must
inject the approver seed; this module does not provision or persist credentials
and does not authenticate the human who controls the key.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .approval_signature import approval_signature_payload
from .authority_key_set import load_control_plane_authority_key_set
from .credential_protocol import CredentialSource
from .durable_stage import SQLiteStagedArtifactStore
from .repository_binding import RepositoryTargetBinding
from .signed_approval import (
    MAX_SIGNED_APPROVAL_INPUT_BYTES,
    SignedApprovalError,
    _canonical_json,
    _existing_file,
    _read_json,
    _rebuild_request,
)
from .signer_key_source import Ed25519SeedCredentialSource


class ApprovalSigningError(ValueError):
    """An approval request is not eligible for one-shot signing."""


ReviewConfirmation = Callable[[dict, str], str]
Clock = Callable[[], datetime]


def _validated_now(clock: Clock) -> datetime:
    try:
        value = clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError
        offset = value.utcoffset()
        if offset is None:
            raise ValueError
        return value.astimezone(timezone.utc)
    except Exception:
        raise ApprovalSigningError("approval signer: clock is unavailable") from None


def _check_expiry(request: dict, moment: datetime) -> None:
    try:
        raw = request["unsigned_approval"]["expires_at"]
        if type(raw) is not str:
            raise ValueError
        expires_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError
        if moment >= expires_at.astimezone(timezone.utc):
            raise ValueError
    except Exception:
        raise ApprovalSigningError("approval signer: request is expired or invalid") from None


def sign_approval_request(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    binding: RepositoryTargetBinding,
    signer_key_source: Ed25519SeedCredentialSource,
    confirm_review: ReviewConfirmation,
    *,
    clock: Clock = lambda: datetime.now(timezone.utc),
    trusted_verifier_authority_keys: object | None = None,
) -> dict:
    """Rebuild, review, confirm, then sign one exact-stage approval request.

    The source is not consulted until after the operator returns the exact
    confirmation phrase. No signing key or signature is persisted here.
    """
    if (
        type(binding) is not RepositoryTargetBinding
        or not isinstance(signer_key_source, Ed25519SeedCredentialSource)
        or not callable(confirm_review)
    ):
        raise ApprovalSigningError("approval signer: configuration is invalid")
    try:
        raw_request = _read_json(request_path, MAX_SIGNED_APPROVAL_INPUT_BYTES)
        database = _existing_file(
            database_path, "approval signer: stage database is unavailable"
        )
        with SQLiteStagedArtifactStore(database, read_only=True) as store:
            artifact = store.load(staged_change_digest)
        rebuilt = _rebuild_request(
            artifact,
            binding,
            raw_request,
            trusted_verifier_authority_keys=trusted_verifier_authority_keys,
        )
        if _canonical_json(raw_request) != _canonical_json(rebuilt):
            raise ApprovalSigningError(
                "approval signer: request does not match exact stage"
            )
        _check_expiry(rebuilt, _validated_now(clock))
        unsigned = rebuilt["unsigned_approval"]
        signing_bytes = approval_signature_payload(unsigned)
        confirmation = (
            f"SIGN APPROVAL {unsigned['approval_id']} {artifact.staged_change_digest}"
        )
        review = rebuilt["review"]
    except ApprovalSigningError:
        raise
    except Exception:
        raise ApprovalSigningError(
            "approval signer: request does not match exact stage"
        ) from None

    try:
        supplied = confirm_review(review, confirmation)
    except Exception:
        raise ApprovalSigningError("approval signer: confirmation unavailable") from None
    if type(supplied) is not str or supplied != confirmation:
        raise ApprovalSigningError("approval signer: confirmation did not match")

    # A slow review must not allow an expired request to be signed.
    _check_expiry(rebuilt, _validated_now(clock))
    try:
        private_key = signer_key_source()
        signature = private_key.sign(signing_bytes).hex()
    except Exception:
        raise ApprovalSigningError("approval signer: credential unavailable") from None

    approval = dict(unsigned)
    approval["signature"] = signature
    return {"schema": "signed-approval/v1", "approval": approval}


def load_verifier_authority_keys(
    path: str | Path | None, expected_digest: str | None
) -> object | None:
    """Load an optional caller-pinned verifier authority set for remote stages."""
    if (path is None) != (expected_digest is None):
        raise ApprovalSigningError(
            "approval signer: verifier authority key set is unavailable"
        )
    if path is None:
        return None
    try:
        keys, _digest = load_control_plane_authority_key_set(
            path, expected_digest=expected_digest
        )
        return keys
    except Exception:
        raise ApprovalSigningError(
            "approval signer: verifier authority key set is invalid"
        ) from None
