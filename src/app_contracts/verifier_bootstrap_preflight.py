"""Strictly inspect public one-shot verifier bootstrap without granting trust.

The caller must pin the exact input bytes independently. Matching this record
does not prove who operates the host, enroll its signer, or authorize a request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from .signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE


MAX_BOOTSTRAP_BYTES = 8193  # Launcher emits <=8192 canonical JSON bytes plus LF.
_ENDPOINT = "https://testdev.local/v1/verify"
_SCHEMA = "agent00x-ephemeral-verifier-bootstrap/v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KEY = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema", "status", "endpoint_url", "listen_host", "connect_port",
    "tls_ca_certificate_pem", "tls_ca_sha256", "verifier_profile_digest",
    "verifier_key_id", "verifier_public_key", "verifier_public_key_sha256",
})


class VerifierBootstrapPreflightError(ValueError):
    """The public bootstrap cannot be bound to the exact caller pin."""


@dataclass(frozen=True)
class BoundPublicVerifierBootstrap:
    """Bound public facts only; this object carries no host trust authority."""

    bootstrap_sha256: str
    connect_port: int
    tls_ca_sha256: str
    verifier_public_key_sha256: str
    trust_established: bool = False


@dataclass(frozen=True)
class PinnedPublicVerifierEnrollmentBootstrap:
    """Exact-pinned public fields suitable for an untrusted signing request."""

    bootstrap_sha256: str
    endpoint_url: str
    verifier_profile_digest: str
    verifier_key_id: str
    verifier_public_key: bytes = field(repr=False)
    trust_established: bool = False


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    raise ValueError


def parse_pinned_public_verifier_bootstrap(
    raw: object, *, expected_sha256: object
) -> BoundPublicVerifierBootstrap:
    """Require the launcher's exact canonical public line and caller byte pin."""

    try:
        if (
            type(raw) is not bytes
            or not 1 <= len(raw) <= MAX_BOOTSTRAP_BYTES
            or type(expected_sha256) is not str
            or _DIGEST.fullmatch(expected_sha256) is None
        ):
            raise ValueError
        actual_sha256 = "sha256:" + hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(actual_sha256, expected_sha256):
            raise ValueError
        payload = raw[:-1] if raw.endswith(b"\n") else raw
        if not payload or len(payload) > MAX_BOOTSTRAP_BYTES - 1:
            raise ValueError
        record = json.loads(
            payload.decode("ascii", errors="strict"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
        if (
            type(record) is not dict
            or set(record) != _FIELDS
            or json.dumps(
                record, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            ).encode("ascii") != payload
            or record["schema"] != _SCHEMA
            or record["status"] != "ready"
            or record["endpoint_url"] != _ENDPOINT
            or record["listen_host"] != "127.0.0.1"
            or type(record["connect_port"]) is not int
            or not 1024 <= record["connect_port"] <= 65535
            or record["verifier_profile_digest"]
            != BRAINBOOSTER_VERIFIER_PROFILE.profile_digest
            or record["verifier_key_id"]
            != BRAINBOOSTER_VERIFIER_PROFILE.signer_key_id
        ):
            raise ValueError
        pem = record["tls_ca_certificate_pem"]
        if type(pem) is not str or not 1 <= len(pem) <= 4096:
            raise ValueError
        ca_bytes = pem.encode("ascii", errors="strict")
        certificate = x509.load_pem_x509_certificate(ca_bytes)
        if (
            certificate.public_bytes(serialization.Encoding.PEM) != ca_bytes
            or not certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value.ca
            or not certificate.extensions.get_extension_for_class(
                x509.KeyUsage
            ).value.key_cert_sign
        ):
            raise ValueError
        ca_digest = record["tls_ca_sha256"]
        if (
            type(ca_digest) is not str
            or _DIGEST.fullmatch(ca_digest) is None
            or ca_digest != "sha256:" + hashlib.sha256(ca_bytes).hexdigest()
        ):
            raise ValueError
        key_hex = record["verifier_public_key"]
        key_digest = record["verifier_public_key_sha256"]
        if (
            type(key_hex) is not str
            or _KEY.fullmatch(key_hex) is None
            or type(key_digest) is not str
            or _DIGEST.fullmatch(key_digest) is None
        ):
            raise ValueError
        public_key = bytes.fromhex(key_hex)
        Ed25519PublicKey.from_public_bytes(public_key)
        if key_digest != "sha256:" + hashlib.sha256(public_key).hexdigest():
            raise ValueError
        return BoundPublicVerifierBootstrap(
            bootstrap_sha256=actual_sha256,
            connect_port=record["connect_port"],
            tls_ca_sha256=ca_digest,
            verifier_public_key_sha256=key_digest,
        )
    except Exception:
        raise VerifierBootstrapPreflightError(
            "verifier bootstrap preflight: public input rejected"
        ) from None


def parse_pinned_public_verifier_enrollment_bootstrap(
    raw: object, *, expected_sha256: object
) -> PinnedPublicVerifierEnrollmentBootstrap:
    """Return enrollment inputs only after the same exact bootstrap validation.

    The result carries public signer bytes, but remains explicitly untrusted;
    matching a caller-provided digest is integrity checking, not OOB trust.
    """

    bound = parse_pinned_public_verifier_bootstrap(
        raw, expected_sha256=expected_sha256
    )
    try:
        payload = raw[:-1] if raw.endswith(b"\n") else raw
        record = json.loads(payload.decode("ascii", errors="strict"))
        return PinnedPublicVerifierEnrollmentBootstrap(
            bootstrap_sha256=bound.bootstrap_sha256,
            endpoint_url=record["endpoint_url"],
            verifier_profile_digest=record["verifier_profile_digest"],
            verifier_key_id=record["verifier_key_id"],
            verifier_public_key=bytes.fromhex(record["verifier_public_key"]),
        )
    except Exception:
        raise VerifierBootstrapPreflightError(
            "verifier bootstrap preflight: public input rejected"
        ) from None
