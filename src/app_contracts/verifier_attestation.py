"""Verify a signed, challenge-bound response from a future remote verifier.

This module authenticates only a response against caller-supplied public keys.
It cannot establish where the private key lives or whether its host is
independent; key provisioning and the verifier runtime remain separate gates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .executor import VerifierInput, VerifierResult
from .verifier_process import (
    MAX_VERIFIER_REQUEST_BYTES,
    MAX_VERIFIER_RESPONSE_BYTES,
    VerifierProcessError,
    VerifierProcessRequest,
    VerifierProcessResponse,
    bind_verifier_response,
    parse_verifier_response,
    parse_verifier_request,
    serialize_verifier_request,
)

ATTESTATION_SCHEMA = "signed-verifier-response/v1"
MAX_ATTESTATION_BYTES = 2_100_000
MAX_TRUSTED_VERIFIER_KEYS = 32
MAX_ATTESTATION_AGE_SECONDS = 300
MAX_ATTESTATION_FUTURE_SKEW_SECONDS = 30
_NONCE_RE = re.compile(r"[0-9a-f]{64}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KEY_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SIGNATURE_RE = re.compile(r"[0-9a-f]{128}\Z")
_FIELDS = frozenset(
    {
        "schema",
        "key_id",
        "invocation_nonce",
        "request_digest",
        "verifier_profile_digest",
        "issued_at",
        "response",
        "signature",
    }
)
_SIGNED_FIELDS = _FIELDS - {"signature"}
_DOMAIN = b"agent00x-signed-verifier-response-ed25519-v1\0"


class VerifierAttestationError(ValueError):
    """A signed verifier response is malformed, stale or not bound to its call."""


@dataclass(frozen=True)
class VerifiedVerifierAttestation:
    """A cryptographically verified response without an independent-host claim."""

    verifier_result: VerifierResult
    key_id: str
    invocation_nonce: str
    request_digest: str
    verifier_profile_digest: str
    issued_at: str
    attestation_digest: str
    signature_valid: bool = True
    independent_host_trust_established: bool = False


def build_signed_verifier_response(
    request_bytes: object,
    response_bytes: object,
    *,
    invocation_nonce: object,
    verifier_profile_digest: object,
    key_id: object,
    signing_key: object,
    issued_at: datetime,
) -> bytes:
    """Sign one bounded typed verifier response without exporting its key.

    This is the verifier-side wire builder. It deliberately does not load a
    key, establish key custody, or assert that the signer runs on an
    independent host; those remain deployment and Control Plane trust gates.
    """

    try:
        if (
            type(request_bytes) is not bytes
            or not request_bytes
            or len(request_bytes) > MAX_VERIFIER_REQUEST_BYTES
            or type(response_bytes) is not bytes
            or not response_bytes
            or len(response_bytes) > MAX_VERIFIER_RESPONSE_BYTES
            or type(invocation_nonce) is not str
            or _NONCE_RE.fullmatch(invocation_nonce) is None
            or type(verifier_profile_digest) is not str
            or _DIGEST_RE.fullmatch(verifier_profile_digest) is None
            or type(key_id) is not str
            or _KEY_ID_RE.fullmatch(key_id) is None
            or not isinstance(signing_key, Ed25519PrivateKey)
        ):
            raise ValueError

        request = parse_verifier_request(request_bytes)
        if serialize_verifier_request(request) != request_bytes:
            raise ValueError
        response = parse_verifier_response(response_bytes)
        if _canonical_json(asdict(response)) != response_bytes:
            raise ValueError
        bound_result = bind_verifier_response(request, response)
        if bound_result.verifier_id != invocation_nonce:
            raise ValueError

        moment = _validate_now(issued_at)
        unsigned = {
            "schema": ATTESTATION_SCHEMA,
            "key_id": key_id,
            "invocation_nonce": invocation_nonce,
            "request_digest": _digest(request_bytes),
            "verifier_profile_digest": verifier_profile_digest,
            "issued_at": moment.isoformat().replace("+00:00", "Z"),
            "response": asdict(response),
        }
        signature = signing_key.sign(verifier_attestation_signing_bytes(unsigned))
        if type(signature) is not bytes or len(signature) != 64:
            raise ValueError
        envelope = {**unsigned, "signature": signature.hex()}
        encoded = _canonical_json(envelope)
        if len(encoded) > MAX_ATTESTATION_BYTES:
            raise ValueError
        return encoded
    except VerifierAttestationError:
        raise
    except Exception:
        raise VerifierAttestationError(
            "verifier attestation: response signing failed"
        ) from None


def verifier_attestation_signing_bytes(envelope: object) -> bytes:
    """Return domain-separated canonical bytes for a response without signature."""

    if type(envelope) is not dict or set(envelope) not in (
        _SIGNED_FIELDS,
        _FIELDS,
    ):
        raise VerifierAttestationError("verifier attestation: envelope is invalid")
    payload = {field: envelope[field] for field in _SIGNED_FIELDS}
    try:
        encoded = _canonical_json(payload)
    except Exception:
        raise VerifierAttestationError("verifier attestation: envelope is invalid") from None
    if len(encoded) > MAX_ATTESTATION_BYTES:
        raise VerifierAttestationError("verifier attestation: envelope exceeds limit")
    return _DOMAIN + encoded


def new_verifier_invocation_nonce() -> str:
    """Create one fresh 256-bit challenge for a single verifier invocation."""

    return secrets.token_hex(32)


def verify_signed_verifier_response(
    envelope_bytes: object,
    prepared: object,
    *,
    expected_invocation_nonce: object,
    expected_verifier_profile_digest: object,
    trusted_public_keys: object,
    now: datetime | None = None,
    max_age_seconds: int = MAX_ATTESTATION_AGE_SECONDS,
    max_future_skew_seconds: int = MAX_ATTESTATION_FUTURE_SKEW_SECONDS,
) -> VerifiedVerifierAttestation:
    """Verify one exact verifier response against a fresh caller challenge.

    ``trusted_public_keys`` must come from a separately governed trust source;
    passing an unverified key proves only signature possession, not verifier
    identity or host independence.
    """

    try:
        envelope = _parse_canonical_envelope(envelope_bytes)
        request = VerifierProcessRequest.from_verifier_input(prepared)
        if (
            request.verifier_input.snapshot_tree_digest is None
            or request.verifier_input.replay_result_digest is None
            or type(expected_invocation_nonce) is not str
            or _NONCE_RE.fullmatch(expected_invocation_nonce) is None
            or type(expected_verifier_profile_digest) is not str
            or _DIGEST_RE.fullmatch(expected_verifier_profile_digest) is None
            or type(max_age_seconds) is not int
            or not 1 <= max_age_seconds <= MAX_ATTESTATION_AGE_SECONDS
            or type(max_future_skew_seconds) is not int
            or not 0 <= max_future_skew_seconds <= MAX_ATTESTATION_FUTURE_SKEW_SECONDS
        ):
            raise ValueError
        if type(envelope) is not dict or set(envelope) != _FIELDS:
            raise ValueError
        if (
            envelope.get("schema") != ATTESTATION_SCHEMA
            or type(envelope.get("key_id")) is not str
            or _KEY_ID_RE.fullmatch(envelope["key_id"]) is None
            or envelope.get("invocation_nonce") != expected_invocation_nonce
            or envelope.get("verifier_profile_digest")
            != expected_verifier_profile_digest
            or type(envelope.get("request_digest")) is not str
            or _DIGEST_RE.fullmatch(envelope["request_digest"]) is None
            or type(envelope.get("issued_at")) is not str
            or type(envelope.get("signature")) is not str
            or _SIGNATURE_RE.fullmatch(envelope["signature"]) is None
        ):
            raise ValueError

        request_digest = _digest(serialize_verifier_request(request))
        if envelope["request_digest"] != request_digest:
            raise ValueError
        response_bytes = _canonical_json(envelope["response"])
        if len(response_bytes) > MAX_ATTESTATION_BYTES:
            raise ValueError
        response = parse_verifier_response(response_bytes)
        if type(response) is not VerifierProcessResponse:
            raise ValueError
        if response.request_digest != request_digest:
            raise ValueError
        verifier_result = bind_verifier_response(request, response)

        issued_at = _parse_utc(envelope["issued_at"])
        moment = _validate_now(datetime.now(timezone.utc) if now is None else now)
        if issued_at > moment + timedelta(seconds=max_future_skew_seconds):
            raise ValueError
        if issued_at < moment - timedelta(seconds=max_age_seconds):
            raise ValueError

        if (
            type(trusted_public_keys) is not dict
            or len(trusted_public_keys) > MAX_TRUSTED_VERIFIER_KEYS
            or any(
                type(key_id) is not str
                or _KEY_ID_RE.fullmatch(key_id) is None
                or type(key_bytes) is not bytes
                or len(key_bytes) != 32
                for key_id, key_bytes in trusted_public_keys.items()
            )
        ):
            raise ValueError
        public_key = trusted_public_keys.get(envelope["key_id"])
        if public_key is None:
            raise ValueError
        signing_bytes = verifier_attestation_signing_bytes(
            {key: value for key, value in envelope.items() if key != "signature"}
        )
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(envelope["signature"]), signing_bytes
        )
        full_bytes = _canonical_json(envelope)
        if len(full_bytes) > MAX_ATTESTATION_BYTES:
            raise ValueError
        return VerifiedVerifierAttestation(
            verifier_result=verifier_result,
            key_id=envelope["key_id"],
            invocation_nonce=envelope["invocation_nonce"],
            request_digest=request_digest,
            verifier_profile_digest=envelope["verifier_profile_digest"],
            issued_at=envelope["issued_at"],
            attestation_digest=f"sha256:{hashlib.sha256(full_bytes).hexdigest()}",
        )
    except VerifierAttestationError:
        raise
    except (InvalidSignature, VerifierProcessError, TypeError, ValueError, KeyError):
        raise VerifierAttestationError(
            "verifier attestation: response verification failed"
        ) from None
    except Exception:
        raise VerifierAttestationError(
            "verifier attestation: response verification failed"
        ) from None


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _parse_canonical_envelope(data: object) -> dict[str, object]:
    if type(data) is not bytes or not data or len(data) > MAX_ATTESTATION_BYTES:
        raise VerifierAttestationError("verifier attestation: envelope is invalid")
    try:
        parsed = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        if type(parsed) is not dict or _canonical_json(parsed) != data:
            raise ValueError
        return parsed
    except Exception:
        raise VerifierAttestationError("verifier attestation: envelope is invalid") from None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError


def _digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError
    if parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") != value:
        raise ValueError
    return parsed.astimezone(timezone.utc)


def _validate_now(value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError
    return value.astimezone(timezone.utc)
