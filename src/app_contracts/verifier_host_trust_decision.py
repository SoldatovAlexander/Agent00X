"""Authority-signed out-of-band decision for one verifier host deployment.

This record is a Control Plane assertion that deployment and host-separation
evidence were reviewed out of band. The module verifies the assertion against
caller-pinned authority keys; synthetic keys prove only protocol behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import re
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


DECISION_SCHEMA = "verifier-host-trust-decision/v1"
MAX_DECISION_BYTES = 65_536
MAX_DECISION_WINDOW = timedelta(hours=24)
MAX_CLOCK_SKEW = timedelta(seconds=30)
_DOMAIN = b"agent00x-verifier-host-trust-decision-ed25519-v1\0"
_VERIFIED_DECISION_TOKEN = object()
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KEY = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{128}\Z")
_DNS_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
_FIELDS = frozenset(
    {
        "schema",
        "decision_id",
        "authority_key_id",
        "outcome",
        "enrollment_digest",
        "endpoint_url",
        "verifier_id",
        "verifier_profile_digest",
        "verifier_key_id",
        "worker_host_id",
        "verifier_host_id",
        "host_separation_evidence_digest",
        "issued_at",
        "expires_at",
        "signature",
    }
)


class VerifierHostTrustDecisionError(ValueError):
    """A verifier-host trust decision is invalid, untrusted, or expired."""


@dataclass(frozen=True)
class VerifiedVerifierHostTrustDecision:
    """An exact authority-approved host decision with a bounded lifetime."""

    decision_id: str
    authority_key_id: str
    enrollment_digest: str
    endpoint_url: str
    verifier_id: str
    verifier_profile_digest: str
    verifier_key_id: str
    worker_host_id: str
    verifier_host_id: str
    host_separation_evidence_digest: str
    issued_at: str
    expires_at: str
    decision_digest: str
    _verification_token: object = field(repr=False, compare=False)


def is_verified_verifier_host_trust_decision(value: object) -> bool:
    """Return true only for instances emitted by the signature verifier."""

    return (
        type(value) is VerifiedVerifierHostTrustDecision
        and value._verification_token is _VERIFIED_DECISION_TOKEN
    )


def build_signed_verifier_host_trust_decision(
    *,
    decision_id: str,
    authority_key_id: str,
    enrollment_digest: str,
    endpoint_url: str,
    verifier_id: str,
    verifier_profile_digest: str,
    verifier_key_id: str,
    worker_host_id: str,
    verifier_host_id: str,
    host_separation_evidence_digest: str,
    signing_key: Ed25519PrivateKey,
    issued_at: datetime,
    expires_at: datetime,
) -> bytes:
    """Create a canonical signed approval record without storing its key."""

    try:
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise ValueError
        payload = _validate_fields(
            {
                "schema": DECISION_SCHEMA,
                "decision_id": decision_id,
                "authority_key_id": authority_key_id,
                "outcome": "approve_independent_host",
                "enrollment_digest": enrollment_digest,
                "endpoint_url": endpoint_url,
                "verifier_id": verifier_id,
                "verifier_profile_digest": verifier_profile_digest,
                "verifier_key_id": verifier_key_id,
                "worker_host_id": worker_host_id,
                "verifier_host_id": verifier_host_id,
                "host_separation_evidence_digest": host_separation_evidence_digest,
                "issued_at": _format_time(issued_at),
                "expires_at": _format_time(expires_at),
            }
        )
        issued = _parse_time(payload["issued_at"])
        expires = _parse_time(payload["expires_at"])
        _validate_window(issued, expires, now=issued)
        signature = signing_key.sign(_DOMAIN + _canonical_json(payload)).hex()
        encoded = _canonical_json({**payload, "signature": signature})
        if len(encoded) > MAX_DECISION_BYTES:
            raise ValueError
        return encoded
    except Exception:
        raise VerifierHostTrustDecisionError(
            "verifier host trust decision: record rejected"
        ) from None


def verify_verifier_host_trust_decision(
    decision_bytes: object,
    *,
    trusted_authority_keys: object,
    expected_enrollment_digest: object,
    expected_endpoint_url: object,
    expected_verifier_id: object,
    expected_verifier_profile_digest: object,
    expected_verifier_key_id: object,
    expected_worker_host_id: object,
    expected_verifier_host_id: object,
    expected_host_separation_evidence_digest: object,
    now: datetime | None = None,
) -> VerifiedVerifierHostTrustDecision:
    """Verify one exact OOB decision against a separately pinned authority."""

    try:
        if (
            type(decision_bytes) is not bytes
            or not decision_bytes
            or len(decision_bytes) > MAX_DECISION_BYTES
        ):
            raise ValueError
        record = json.loads(
            decision_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        if type(record) is not dict or set(record) != _FIELDS:
            raise ValueError
        signature_hex = record.pop("signature")
        payload = _validate_fields(record)
        if _canonical_json({**payload, "signature": signature_hex}) != decision_bytes:
            raise ValueError
        expected = {
            "enrollment_digest": expected_enrollment_digest,
            "endpoint_url": expected_endpoint_url,
            "verifier_id": expected_verifier_id,
            "verifier_profile_digest": expected_verifier_profile_digest,
            "verifier_key_id": expected_verifier_key_id,
            "worker_host_id": expected_worker_host_id,
            "verifier_host_id": expected_verifier_host_id,
            "host_separation_evidence_digest": expected_host_separation_evidence_digest,
        }
        if any(type(value) is not str for value in expected.values()) or any(
            payload[name] != value for name, value in expected.items()
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
        if authority_key is None or type(signature_hex) is not str or _SIGNATURE.fullmatch(signature_hex) is None:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(authority_key).verify(
            bytes.fromhex(signature_hex), _DOMAIN + _canonical_json(payload)
        )
        issued = _parse_time(payload["issued_at"])
        expires = _parse_time(payload["expires_at"])
        moment = _validate_now(datetime.now(timezone.utc) if now is None else now)
        _validate_window(issued, expires, now=moment)
        canonical = _canonical_json({**payload, "signature": signature_hex})
        return VerifiedVerifierHostTrustDecision(
            decision_id=payload["decision_id"],
            authority_key_id=payload["authority_key_id"],
            enrollment_digest=payload["enrollment_digest"],
            endpoint_url=payload["endpoint_url"],
            verifier_id=payload["verifier_id"],
            verifier_profile_digest=payload["verifier_profile_digest"],
            verifier_key_id=payload["verifier_key_id"],
            worker_host_id=payload["worker_host_id"],
            verifier_host_id=payload["verifier_host_id"],
            host_separation_evidence_digest=payload[
                "host_separation_evidence_digest"
            ],
            issued_at=payload["issued_at"],
            expires_at=payload["expires_at"],
            decision_digest=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
            _verification_token=_VERIFIED_DECISION_TOKEN,
        )
    except VerifierHostTrustDecisionError:
        raise
    except (InvalidSignature, TypeError, ValueError, KeyError, UnicodeError):
        raise VerifierHostTrustDecisionError(
            "verifier host trust decision: verification failed"
        ) from None
    except Exception:
        raise VerifierHostTrustDecisionError(
            "verifier host trust decision: verification failed"
        ) from None


def _validate_fields(value: object) -> dict[str, str]:
    if type(value) is not dict or set(value) != (_FIELDS - {"signature"}):
        raise ValueError
    if (
        value.get("schema") != DECISION_SCHEMA
        or value.get("outcome") != "approve_independent_host"
        or type(value.get("decision_id")) is not str
        or _ID.fullmatch(value["decision_id"]) is None
        or type(value.get("authority_key_id")) is not str
        or _ID.fullmatch(value["authority_key_id"]) is None
        or type(value.get("enrollment_digest")) is not str
        or _DIGEST.fullmatch(value["enrollment_digest"]) is None
        or type(value.get("endpoint_url")) is not str
        or not _valid_endpoint(value["endpoint_url"])
        or type(value.get("verifier_id")) is not str
        or not 1 <= len(value["verifier_id"]) <= 512
        or any(ord(char) < 0x20 for char in value["verifier_id"])
        or type(value.get("verifier_profile_digest")) is not str
        or _DIGEST.fullmatch(value["verifier_profile_digest"]) is None
        or type(value.get("verifier_key_id")) is not str
        or _ID.fullmatch(value["verifier_key_id"]) is None
        or type(value.get("worker_host_id")) is not str
        or _ID.fullmatch(value["worker_host_id"]) is None
        or type(value.get("verifier_host_id")) is not str
        or _ID.fullmatch(value["verifier_host_id"]) is None
        or value["worker_host_id"] == value["verifier_host_id"]
        or type(value.get("host_separation_evidence_digest")) is not str
        or _DIGEST.fullmatch(value["host_separation_evidence_digest"]) is None
        or type(value.get("issued_at")) is not str
        or type(value.get("expires_at")) is not str
    ):
        raise ValueError
    _parse_time(value["issued_at"])
    _parse_time(value["expires_at"])
    return dict(value)


def _valid_endpoint(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme != "https"
            or host is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/v1/verify"
            or parsed.query
            or parsed.fragment
            or parsed.port not in {None, 443}
            or host != host.lower()
            or host == "localhost"
            or host.endswith(".localhost")
            or _DNS_HOST.fullmatch(host) is None
            or value not in {f"https://{host}/v1/verify", f"https://{host}:443/v1/verify"}
        ):
            return False
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return True
        return False
    except Exception:
        return False


def _format_time(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond != 0
    ):
        raise ValueError
    return value.isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if _format_time(parsed) != value:
        raise ValueError
    return parsed


def _validate_now(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _validate_window(issued: datetime, expires: datetime, *, now: datetime) -> None:
    if (
        expires <= now
        or expires <= issued
        or expires - issued > MAX_DECISION_WINDOW
        or issued > now + MAX_CLOCK_SKEW
    ):
        raise ValueError


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError
