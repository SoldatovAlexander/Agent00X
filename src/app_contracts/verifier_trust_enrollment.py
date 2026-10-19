"""Out-of-band enrollment for one separately governed remote verifier.

An enrollment is an authority-signed claim, not proof that a host was deployed
or independently administered. The authority public key must be pinned outside
the verifier response/endpoint before this module can validate the claim.
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


ENROLLMENT_SCHEMA = "verifier-trust-enrollment/v1"
MAX_ENROLLMENT_BYTES = 65_536
MAX_ENROLLMENT_WINDOW = timedelta(days=30)
MAX_CLOCK_SKEW = timedelta(seconds=30)
_DOMAIN = b"agent00x-verifier-trust-enrollment-ed25519-v1\0"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HOST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KEY = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{128}\Z")
_DNS_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
_NUMERIC_DOTTED_HOST = re.compile(r"[0-9]+(?:\.[0-9]+){3}\Z")
_FIELDS = frozenset(
    {
        "schema",
        "enrollment_id",
        "authority_key_id",
        "endpoint_url",
        "verifier_id",
        "verifier_profile_digest",
        "verifier_key_id",
        "verifier_public_key",
        "worker_host_id",
        "verifier_host_id",
        "host_separation_evidence_digest",
        "issued_at",
        "expires_at",
        "signature",
    }
)


class VerifierTrustEnrollmentError(ValueError):
    """A verifier enrollment is invalid, untrusted or expired."""


@dataclass(frozen=True)
class VerifiedVerifierTrustEnrollment:
    """Validated authority claims; deployment evidence still needs OOB review."""

    enrollment_id: str
    authority_key_id: str
    endpoint_url: str
    verifier_id: str
    verifier_profile_digest: str
    verifier_key_id: str
    verifier_public_key: bytes = field(repr=False)
    worker_host_id: str = ""
    verifier_host_id: str = ""
    host_separation_evidence_digest: str = ""
    issued_at: str = ""
    expires_at: str = ""
    enrollment_digest: str = ""
    authority_signature_valid: bool = True
    independent_host_trust_established: bool = False

    def __repr__(self) -> str:
        return (
            "VerifiedVerifierTrustEnrollment("
            f"enrollment_id={self.enrollment_id!r}, "
            f"authority_key_id={self.authority_key_id!r}, "
            f"verifier_id={self.verifier_id!r}, "
            "authority_signature_valid=True, "
            "independent_host_trust_established=False)"
        )


def build_verifier_trust_enrollment_signing_message(
    *,
    enrollment_id: str,
    authority_key_id: str,
    endpoint_url: str,
    verifier_id: str,
    verifier_profile_digest: str,
    verifier_key_id: str,
    verifier_public_key: bytes,
    worker_host_id: str,
    verifier_host_id: str,
    host_separation_evidence_digest: str,
    issued_at: datetime,
    expires_at: datetime,
) -> bytes:
    """Return public canonical bytes for an external authority signer.

    The returned message contains no private key or signature. Its signature
    must be assembled and then verified against a separately pinned authority
    key set before the enrollment is trusted.
    """

    try:
        payload = _validate_fields(
            {
                "schema": ENROLLMENT_SCHEMA,
                "enrollment_id": enrollment_id,
                "authority_key_id": authority_key_id,
                "endpoint_url": endpoint_url,
                "verifier_id": verifier_id,
                "verifier_profile_digest": verifier_profile_digest,
                "verifier_key_id": verifier_key_id,
                "verifier_public_key": (
                    verifier_public_key.hex()
                    if type(verifier_public_key) is bytes
                    else None
                ),
                "worker_host_id": worker_host_id,
                "verifier_host_id": verifier_host_id,
                "host_separation_evidence_digest": host_separation_evidence_digest,
                "issued_at": _format_time(issued_at),
                "expires_at": _format_time(expires_at),
            }
        )
        _validate_window(
            _parse_time(payload["issued_at"]),
            _parse_time(payload["expires_at"]),
            now=_parse_time(payload["issued_at"]),
        )
        message = _DOMAIN + _canonical_json(payload)
        if len(message) > MAX_ENROLLMENT_BYTES + len(_DOMAIN):
            raise ValueError
        return message
    except Exception:
        raise VerifierTrustEnrollmentError(
            "verifier trust enrollment: signing request rejected"
        ) from None


def assemble_signed_verifier_trust_enrollment(
    signing_message: object, signature: object
) -> bytes:
    """Assemble an untrusted record from a canonical message and detached sig.

    This function does not verify who produced ``signature``. Call
    :func:`verify_verifier_trust_enrollment` with an independently pinned
    authority key set and expected deployment bindings before using the record.
    """

    try:
        if (
            type(signing_message) is not bytes
            or not signing_message.startswith(_DOMAIN)
            or len(signing_message) > MAX_ENROLLMENT_BYTES + len(_DOMAIN)
            or type(signature) is not bytes
            or len(signature) != 64
        ):
            raise ValueError
        payload_bytes = signing_message[len(_DOMAIN) :]
        payload = json.loads(
            payload_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        payload = _validate_fields(payload)
        if _canonical_json(payload) != payload_bytes:
            raise ValueError
        _validate_window(
            _parse_time(payload["issued_at"]),
            _parse_time(payload["expires_at"]),
            now=_parse_time(payload["issued_at"]),
        )
        encoded = _canonical_json({**payload, "signature": signature.hex()})
        if len(encoded) > MAX_ENROLLMENT_BYTES:
            raise ValueError
        return encoded
    except Exception:
        raise VerifierTrustEnrollmentError(
            "verifier trust enrollment: detached signature rejected"
        ) from None


def build_signed_verifier_trust_enrollment(
    *,
    enrollment_id: str,
    authority_key_id: str,
    endpoint_url: str,
    verifier_id: str,
    verifier_profile_digest: str,
    verifier_key_id: str,
    verifier_public_key: bytes,
    worker_host_id: str,
    verifier_host_id: str,
    host_separation_evidence_digest: str,
    signing_key: Ed25519PrivateKey,
    issued_at: datetime,
    expires_at: datetime,
) -> bytes:
    """Build one canonical signed record; does not store or enroll any key."""

    try:
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise ValueError
        message = build_verifier_trust_enrollment_signing_message(
            enrollment_id=enrollment_id,
            authority_key_id=authority_key_id,
            endpoint_url=endpoint_url,
            verifier_id=verifier_id,
            verifier_profile_digest=verifier_profile_digest,
            verifier_key_id=verifier_key_id,
            verifier_public_key=verifier_public_key,
            worker_host_id=worker_host_id,
            verifier_host_id=verifier_host_id,
            host_separation_evidence_digest=host_separation_evidence_digest,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return assemble_signed_verifier_trust_enrollment(
            message, signing_key.sign(message)
        )
    except Exception:
        raise VerifierTrustEnrollmentError(
            "verifier trust enrollment: record rejected"
        ) from None


def verify_verifier_trust_enrollment(
    enrollment_bytes: object,
    *,
    trusted_authority_keys: object,
    expected_endpoint_url: object,
    expected_verifier_id: object,
    expected_verifier_profile_digest: object,
    now: datetime | None = None,
) -> VerifiedVerifierTrustEnrollment:
    """Validate an enrollment only against an independently pinned authority."""

    try:
        if (
            type(enrollment_bytes) is not bytes
            or not enrollment_bytes
            or len(enrollment_bytes) > MAX_ENROLLMENT_BYTES
        ):
            raise ValueError
        record = json.loads(
            enrollment_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        if type(record) is not dict or set(record) != _FIELDS:
            raise ValueError
        signature_hex = record.pop("signature")
        payload = _validate_fields(record)
        if _canonical_json({**payload, "signature": signature_hex}) != enrollment_bytes:
            raise ValueError
        if (
            type(expected_endpoint_url) is not str
            or type(expected_verifier_id) is not str
            or type(expected_verifier_profile_digest) is not str
            or payload["endpoint_url"] != expected_endpoint_url
            or payload["verifier_id"] != expected_verifier_id
            or payload["verifier_profile_digest"]
            != expected_verifier_profile_digest
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
        authority_key_id = payload["authority_key_id"]
        authority_key = trusted_authority_keys.get(authority_key_id)
        if authority_key is None:
            raise ValueError
        if type(signature_hex) is not str or _SIGNATURE.fullmatch(signature_hex) is None:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(authority_key).verify(
            bytes.fromhex(signature_hex), _DOMAIN + _canonical_json(payload)
        )

        issued_at = _parse_time(payload["issued_at"])
        expires_at = _parse_time(payload["expires_at"])
        moment = _validate_now(datetime.now(timezone.utc) if now is None else now)
        _validate_window(issued_at, expires_at, now=moment)

        public_key = bytes.fromhex(payload["verifier_public_key"])
        canonical = _canonical_json({**payload, "signature": signature_hex})
        return VerifiedVerifierTrustEnrollment(
            enrollment_id=payload["enrollment_id"],
            authority_key_id=authority_key_id,
            endpoint_url=payload["endpoint_url"],
            verifier_id=payload["verifier_id"],
            verifier_profile_digest=payload["verifier_profile_digest"],
            verifier_key_id=payload["verifier_key_id"],
            verifier_public_key=public_key,
            worker_host_id=payload["worker_host_id"],
            verifier_host_id=payload["verifier_host_id"],
            host_separation_evidence_digest=(
                payload["host_separation_evidence_digest"]
            ),
            issued_at=payload["issued_at"],
            expires_at=payload["expires_at"],
            enrollment_digest=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        )
    except VerifierTrustEnrollmentError:
        raise
    except (InvalidSignature, TypeError, ValueError, KeyError, UnicodeError):
        raise VerifierTrustEnrollmentError(
            "verifier trust enrollment: verification failed"
        ) from None
    except Exception:
        raise VerifierTrustEnrollmentError(
            "verifier trust enrollment: verification failed"
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
        or type(value.get("endpoint_url")) is not str
        or not _valid_endpoint(value["endpoint_url"])
        or type(value.get("verifier_id")) is not str
        or not 1 <= len(value["verifier_id"]) <= 512
        or any(ord(char) < 0x20 for char in value["verifier_id"])
        or type(value.get("verifier_profile_digest")) is not str
        or _DIGEST.fullmatch(value["verifier_profile_digest"]) is None
        or type(value.get("verifier_key_id")) is not str
        or _ID.fullmatch(value["verifier_key_id"]) is None
        or type(value.get("verifier_public_key")) is not str
        or _KEY.fullmatch(value["verifier_public_key"]) is None
        or type(value.get("worker_host_id")) is not str
        or _HOST_ID.fullmatch(value["worker_host_id"]) is None
        or type(value.get("verifier_host_id")) is not str
        or _HOST_ID.fullmatch(value["verifier_host_id"]) is None
        or value["worker_host_id"] == value["verifier_host_id"]
        or type(value.get("host_separation_evidence_digest")) is not str
        or _DIGEST.fullmatch(value["host_separation_evidence_digest"]) is None
        or type(value.get("issued_at")) is not str
        or type(value.get("expires_at")) is not str
    ):
        raise ValueError
    _valid_endpoint(value["endpoint_url"], raise_on_invalid=True)
    _parse_time(value["issued_at"])
    _parse_time(value["expires_at"])
    return dict(value)


def _valid_endpoint(value: str, *, raise_on_invalid: bool = False) -> bool:
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
            or "?" in value
            or "#" in value
            or parsed.port not in {None, 443}
            or host != host.lower()
            or host == "localhost"
            or host.endswith(".localhost")
            or _DNS_HOST.fullmatch(host) is None
            or _NUMERIC_DOTTED_HOST.fullmatch(host) is not None
            or value
            not in {
                f"https://{host}/v1/verify",
                f"https://{host}:443/v1/verify",
            }
        ):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return True
    except Exception:
        pass
    if raise_on_invalid:
        raise ValueError
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


def _validate_window(issued_at: datetime, expires_at: datetime, *, now: datetime) -> None:
    if (
        expires_at <= now
        or expires_at <= issued_at
        or expires_at - issued_at > MAX_ENROLLMENT_WINDOW
        or issued_at > now + MAX_CLOCK_SKEW
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
