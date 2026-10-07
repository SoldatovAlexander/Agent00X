"""Canonical bounded one-shot invocation envelope for the signed verifier."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json
import re

from .verifier_process import (
    MAX_VERIFIER_REQUEST_BYTES,
    VerifierProcessRequest,
    parse_verifier_request,
    serialize_verifier_request,
)


SIGNED_VERIFIER_INVOCATION_SCHEMA = "signed-verifier-invocation/v1"
MAX_SIGNED_VERIFIER_INVOCATION_BYTES = (
    ((MAX_VERIFIER_REQUEST_BYTES + 2) // 3) * 4 + 1_024
)
_NONCE_RE = re.compile(r"[0-9a-f]{64}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FIELDS = frozenset(
    {"schema", "request_base64", "invocation_nonce", "verifier_profile_digest"}
)


class SignedVerifierProtocolError(ValueError):
    """A wire invocation is malformed, noncanonical, or exceeds its bound."""


@dataclass(frozen=True)
class SignedVerifierInvocation:
    """Decoded one-shot request; request bytes stay out of repr/log output."""

    request_bytes: bytes = field(repr=False)
    invocation_nonce: str
    verifier_profile_digest: str

    def __post_init__(self) -> None:
        try:
            if (
                type(self.request_bytes) is not bytes
                or not self.request_bytes
                or len(self.request_bytes) > MAX_VERIFIER_REQUEST_BYTES
                or type(self.invocation_nonce) is not str
                or _NONCE_RE.fullmatch(self.invocation_nonce) is None
                or type(self.verifier_profile_digest) is not str
                or _DIGEST_RE.fullmatch(self.verifier_profile_digest) is None
            ):
                raise ValueError
            request = parse_verifier_request(self.request_bytes)
            if serialize_verifier_request(request) != self.request_bytes:
                raise ValueError
        except Exception:
            raise SignedVerifierProtocolError(
                "signed verifier protocol: invocation is invalid"
            ) from None


def serialize_signed_verifier_invocation(
    request_bytes: object,
    *,
    invocation_nonce: object,
    verifier_profile_digest: object,
) -> bytes:
    """Return one canonical JSON stdin record with a base64 request payload."""

    try:
        invocation = SignedVerifierInvocation(
            request_bytes=request_bytes,
            invocation_nonce=invocation_nonce,
            verifier_profile_digest=verifier_profile_digest,
        )
        value = {
            "schema": SIGNED_VERIFIER_INVOCATION_SCHEMA,
            "request_base64": base64.b64encode(invocation.request_bytes).decode("ascii"),
            "invocation_nonce": invocation.invocation_nonce,
            "verifier_profile_digest": invocation.verifier_profile_digest,
        }
        encoded = _canonical_json(value)
        if len(encoded) > MAX_SIGNED_VERIFIER_INVOCATION_BYTES:
            raise ValueError
        return encoded
    except SignedVerifierProtocolError:
        raise
    except Exception:
        raise SignedVerifierProtocolError(
            "signed verifier protocol: invocation is invalid"
        ) from None


def parse_signed_verifier_invocation(raw: object) -> SignedVerifierInvocation:
    """Parse exactly one canonical envelope and reject duplicate JSON keys."""

    try:
        if (
            type(raw) is not bytes
            or not raw
            or len(raw) > MAX_SIGNED_VERIFIER_INVOCATION_BYTES
        ):
            raise ValueError
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object)
        if type(value) is not dict or set(value) != _FIELDS:
            raise ValueError
        if (
            value.get("schema") != SIGNED_VERIFIER_INVOCATION_SCHEMA
            or type(value.get("request_base64")) is not str
            or len(value["request_base64"]) > ((MAX_VERIFIER_REQUEST_BYTES + 2) // 3) * 4
            or type(value.get("invocation_nonce")) is not str
            or type(value.get("verifier_profile_digest")) is not str
        ):
            raise ValueError
        request_bytes = base64.b64decode(value["request_base64"], validate=True)
        if base64.b64encode(request_bytes).decode("ascii") != value["request_base64"]:
            raise ValueError
        if _canonical_json(value) != raw:
            raise ValueError
        return SignedVerifierInvocation(
            request_bytes=request_bytes,
            invocation_nonce=value["invocation_nonce"],
            verifier_profile_digest=value["verifier_profile_digest"],
        )
    except SignedVerifierProtocolError:
        raise
    except Exception:
        raise SignedVerifierProtocolError(
            "signed verifier protocol: invocation is invalid"
        ) from None


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
