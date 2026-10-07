"""Ed25519 verification for digest-bound approval records."""

from __future__ import annotations

import json
import re
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


APPROVAL_SIGNED_FIELDS = (
    "schema_version",
    "approval_id",
    "approver_id",
    "process_id",
    "operation",
    "repository_id",
    "staged_change_digest",
    "approved_intent_digest",
    "policy_version",
    "approved_at",
    "expires_at",
)
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{128}\Z")


def approval_signature_payload(approval: dict[str, Any]) -> bytes:
    """Return canonical UTF-8 bytes for every security-relevant approval field."""
    if not isinstance(approval, dict) or set(approval) not in (
        set(APPROVAL_SIGNED_FIELDS),
        {*APPROVAL_SIGNED_FIELDS, "signature"},
    ):
        raise ValueError("approval signature: payload is invalid")
    payload = {field: approval[field] for field in APPROVAL_SIGNED_FIELDS}
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("approval signature: payload is invalid") from None
    return b"agent00x-approval-ed25519-v1\0" + encoded


def verify_approval_signature(
    approval: dict[str, Any], public_key_bytes: bytes
) -> bool:
    """Fail closed unless a canonical approval payload has a valid Ed25519 signature."""
    if (
        not isinstance(public_key_bytes, bytes)
        or len(public_key_bytes) != 32
        or not isinstance(approval, dict)
        or not isinstance(approval.get("signature"), str)
        or _SIGNATURE_PATTERN.fullmatch(approval["signature"]) is None
    ):
        return False
    try:
        signature = bytes.fromhex(approval["signature"])
        payload = approval_signature_payload(approval)
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, payload)
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True
