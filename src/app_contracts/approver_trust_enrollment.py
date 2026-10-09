"""Authority-signed, scope-bound enrollment for an approval signing key.

The authority signature binds a key to a declared approver and exact review
scope. It does not independently prove the person's identity; the authority
key and its issuance process must be governed out of band.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


ENROLLMENT_SCHEMA = "approver-trust-enrollment/v1"
MAX_ENROLLMENT_BYTES = 65_536
MAX_ENROLLMENT_WINDOW = timedelta(days=30)
MAX_CLOCK_SKEW = timedelta(seconds=30)
_DOMAIN = b"agent00x-approver-trust-enrollment-ed25519-v1\0"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_APPROVER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}\Z")
_REPOSITORY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KEY = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{128}\Z")
_FIELDS = frozenset(
    {
        "schema",
        "enrollment_id",
        "authority_key_id",
        "approver_id",
        "approver_public_key",
        "trust_profile_digest",
        "provider_repository_id",
        "operation",
        "issued_at",
        "expires_at",
        "signature",
    }
)


class ApproverTrustEnrollmentError(ValueError):
    """An approver enrollment is malformed, untrusted, out of scope or expired."""


@dataclass(frozen=True)
class VerifiedApproverTrustEnrollment:
    enrollment_id: str
    authority_key_id: str
    approver_id: str
    approver_public_key: bytes = field(repr=False)
    trust_profile_digest: str = ""
    provider_repository_id: str = ""
    operation: str = "publish_pull_request"
    issued_at: str = ""
    expires_at: str = ""
    enrollment_digest: str = ""
    authority_signature_valid: bool = True
    human_identity_authenticated: bool = False

    def __repr__(self) -> str:
        return (
            "VerifiedApproverTrustEnrollment("
            f"enrollment_id={self.enrollment_id!r}, "
            f"authority_key_id={self.authority_key_id!r}, "
            f"approver_id={self.approver_id!r}, "
            "authority_signature_valid=True, "
            "human_identity_authenticated=False)"
        )


def build_signed_approver_trust_enrollment(
    *,
    enrollment_id: str,
    authority_key_id: str,
    approver_id: str,
    approver_public_key: bytes,
    trust_profile_digest: str,
    provider_repository_id: str,
    signing_key: Ed25519PrivateKey,
    issued_at: datetime,
    expires_at: datetime,
) -> bytes:
    """Build a canonical bounded enrollment; this does not provision a key."""
    try:
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise ValueError
        payload = _validate_fields(
            {
                "schema": ENROLLMENT_SCHEMA,
                "enrollment_id": enrollment_id,
                "authority_key_id": authority_key_id,
                "approver_id": approver_id,
                "approver_public_key": (
                    approver_public_key.hex()
                    if type(approver_public_key) is bytes
                    else None
                ),
                "trust_profile_digest": trust_profile_digest,
                "provider_repository_id": provider_repository_id,
                "operation": "publish_pull_request",
                "issued_at": _format_time(issued_at),
                "expires_at": _format_time(expires_at),
            }
        )
        issued = _parse_time(payload["issued_at"])
        expires = _parse_time(payload["expires_at"])
        _validate_window(issued, expires, now=issued)
        encoded = _canonical_json(
            {**payload, "signature": signing_key.sign(_DOMAIN + _canonical_json(payload)).hex()}
        )
        if len(encoded) > MAX_ENROLLMENT_BYTES:
            raise ValueError
        return encoded
    except Exception:
        raise ApproverTrustEnrollmentError(
            "approver trust enrollment: record rejected"
        ) from None


def verify_approver_trust_enrollment(
    enrollment_bytes: object,
    *,
    trusted_authority_keys: object,
    expected_approver_id: object,
    expected_trust_profile_digest: object,
    expected_provider_repository_id: object,
    now: datetime | None = None,
) -> VerifiedApproverTrustEnrollment:
    """Verify exact scope only against a caller-pinned authority public key."""
    try:
        if (
            type(enrollment_bytes) is not bytes
            or not enrollment_bytes
            or len(enrollment_bytes) > MAX_ENROLLMENT_BYTES
        ):
            raise ValueError
        record = json.loads(
            enrollment_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
        if type(record) is not dict or set(record) != _FIELDS:
            raise ValueError
        signature = record.pop("signature")
        payload = _validate_fields(record)
        if _canonical_json({**payload, "signature": signature}) != enrollment_bytes:
            raise ValueError
        if (
            type(expected_approver_id) is not str
            or type(expected_trust_profile_digest) is not str
            or type(expected_provider_repository_id) is not str
            or payload["approver_id"] != expected_approver_id
            or payload["trust_profile_digest"] != expected_trust_profile_digest
            or payload["provider_repository_id"] != expected_provider_repository_id
        ):
            raise ValueError
        if (
            type(trusted_authority_keys) is not dict
            or not 1 <= len(trusted_authority_keys) <= 32
            or any(
                type(key_id) is not str
                or _ID.fullmatch(key_id) is None
                or type(key_bytes) is not bytes
                or len(key_bytes) != 32
                for key_id, key_bytes in trusted_authority_keys.items()
            )
        ):
            raise ValueError
        authority_key = trusted_authority_keys.get(payload["authority_key_id"])
        if authority_key is None or type(signature) is not str or _SIGNATURE.fullmatch(signature) is None:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(authority_key).verify(
            bytes.fromhex(signature), _DOMAIN + _canonical_json(payload)
        )
        moment = _validate_clock(datetime.now(timezone.utc) if now is None else now)
        issued = _parse_time(payload["issued_at"])
        expires = _parse_time(payload["expires_at"])
        _validate_window(issued, expires, now=moment)
        canonical = _canonical_json({**payload, "signature": signature})
        return VerifiedApproverTrustEnrollment(
            enrollment_id=payload["enrollment_id"],
            authority_key_id=payload["authority_key_id"],
            approver_id=payload["approver_id"],
            approver_public_key=bytes.fromhex(payload["approver_public_key"]),
            trust_profile_digest=payload["trust_profile_digest"],
            provider_repository_id=payload["provider_repository_id"],
            operation=payload["operation"],
            issued_at=payload["issued_at"],
            expires_at=payload["expires_at"],
            enrollment_digest=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        )
    except ApproverTrustEnrollmentError:
        raise
    except Exception:
        raise ApproverTrustEnrollmentError(
            "approver trust enrollment: verification failed"
        ) from None


def _validate_fields(value: object) -> dict[str, str]:
    if type(value) is not dict or set(value) != (_FIELDS - {"signature"}):
        raise ValueError
    if (
        value.get("schema") != ENROLLMENT_SCHEMA
        or type(value.get("enrollment_id")) is not str
        or _ID.fullmatch(value["enrollment_id"]) is None
        or type(value.get("authority_key_id")) is not str
        or _ID.fullmatch(value["authority_key_id"]) is None
        or type(value.get("approver_id")) is not str
        or _APPROVER_ID.fullmatch(value["approver_id"]) is None
        or type(value.get("approver_public_key")) is not str
        or _KEY.fullmatch(value["approver_public_key"]) is None
        or type(value.get("trust_profile_digest")) is not str
        or _DIGEST.fullmatch(value["trust_profile_digest"]) is None
        or type(value.get("provider_repository_id")) is not str
        or _REPOSITORY_ID.fullmatch(value["provider_repository_id"]) is None
        or value.get("operation") != "publish_pull_request"
        or type(value.get("issued_at")) is not str
        or type(value.get("expires_at")) is not str
    ):
        raise ValueError
    _parse_time(value["issued_at"])
    _parse_time(value["expires_at"])
    return dict(value)


def _validate_window(issued: datetime, expires: datetime, *, now: datetime) -> None:
    if (
        expires <= issued
        or expires - issued > MAX_ENROLLMENT_WINDOW
        or issued > now + MAX_CLOCK_SKEW
        or expires <= now
    ):
        raise ValueError


def _format_time(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond != 0
    ):
        raise ValueError
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    if type(value) is not str or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
    ) is None:
        raise ValueError
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise ValueError
    return parsed.astimezone(timezone.utc)


def _validate_clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError
    return value.astimezone(timezone.utc)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _reject_duplicate_pairs(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError
        record[key] = value
    return record


def _reject_constant(_value):
    raise ValueError
