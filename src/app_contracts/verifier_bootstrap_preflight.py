"""Strictly inspect public one-shot verifier bootstrap without granting trust.

The caller must pin the exact input bytes independently. Matching this record
does not prove who operates the host, enroll its signer, or authorize a request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import ipaddress
import json
import re

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from .signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE


MAX_BOOTSTRAP_BYTES = 8193  # Launcher emits <=8192 canonical JSON bytes plus LF.
_ENDPOINT = "https://testdev.local/v1/verify"
_SCHEMA = "agent00x-ephemeral-verifier-bootstrap/v1"
_LAN_SCHEMA = "agent00x-private-lan-verifier-bootstrap/v2"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KEY = re.compile(r"[0-9a-f]{64}\Z")
_BASE_FIELDS = frozenset({
    "schema", "status", "endpoint_url", "listen_host", "connect_port",
    "tls_ca_certificate_pem", "tls_ca_sha256", "verifier_profile_digest",
    "verifier_key_id", "verifier_public_key", "verifier_public_key_sha256",
})
_LAN_FIELDS = _BASE_FIELDS | {"transport_mode", "allowed_peer_address"}
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class VerifierBootstrapPreflightError(ValueError):
    """The public bootstrap cannot be bound to the exact caller pin."""


@dataclass(frozen=True)
class BoundPublicVerifierBootstrap:
    """Bound public facts only; this object carries no host trust authority."""

    bootstrap_sha256: str
    connect_port: int
    tls_ca_sha256: str
    verifier_public_key_sha256: str
    listen_host: str = "127.0.0.1"
    allowed_peer_address: str | None = None
    transport_mode: str = "loopback"
    trust_established: bool = False


@dataclass(frozen=True)
class PinnedPublicVerifierEnrollmentBootstrap:
    """Exact-pinned public fields suitable for an untrusted signing request."""

    bootstrap_sha256: str
    endpoint_url: str
    verifier_profile_digest: str
    verifier_key_id: str
    verifier_public_key: bytes = field(repr=False)
    listen_host: str = "127.0.0.1"
    allowed_peer_address: str | None = None
    connect_port: int = 0
    tls_ca_certificate_pem: bytes = field(default=b"", repr=False)
    transport_mode: str = "loopback"
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
        if type(record) is not dict:
            raise ValueError
        schema = record.get("schema")
        expected_fields = (
            _BASE_FIELDS if schema == _SCHEMA
            else _LAN_FIELDS if schema == _LAN_SCHEMA
            else None
        )
        if (
            expected_fields is None
            or set(record) != expected_fields
            or json.dumps(
                record, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            ).encode("ascii") != payload
            or record["status"] != "ready"
            or record["endpoint_url"] != _ENDPOINT
            or type(record["connect_port"]) is not int
            or not 1024 <= record["connect_port"] <= 65535
            or record["verifier_profile_digest"]
            != BRAINBOOSTER_VERIFIER_PROFILE.profile_digest
            or record["verifier_key_id"]
            != BRAINBOOSTER_VERIFIER_PROFILE.signer_key_id
        ):
            raise ValueError
        if schema == _SCHEMA:
            if (
                record["listen_host"] != "127.0.0.1"
                or record.get("allowed_peer_address") is not None
            ):
                raise ValueError
            listen_host = "127.0.0.1"
            allowed_peer_address = None
            transport_mode = "loopback"
        else:
            listen_host = record["listen_host"]
            allowed_peer_address = record["allowed_peer_address"]
            if (
                record.get("transport_mode") != "private_lan"
                or _private_lan_ipv4(listen_host) is None
                or _private_lan_ipv4(allowed_peer_address) is None
                or listen_host == allowed_peer_address
            ):
                raise ValueError
            transport_mode = "private_lan"
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
            listen_host=listen_host,
            allowed_peer_address=allowed_peer_address,
            transport_mode=transport_mode,
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
            listen_host=bound.listen_host,
            allowed_peer_address=bound.allowed_peer_address,
            connect_port=bound.connect_port,
            tls_ca_certificate_pem=record["tls_ca_certificate_pem"].encode("ascii"),
            transport_mode=bound.transport_mode,
        )
    except Exception:
        raise VerifierBootstrapPreflightError(
            "verifier bootstrap preflight: public input rejected"
        ) from None


def _private_lan_ipv4(value: object) -> ipaddress.IPv4Address | None:
    if type(value) is not str:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if (
        type(address) is not ipaddress.IPv4Address
        or str(address) != value
        or not any(address in network for network in _RFC1918_NETWORKS)
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        return None
    return address
