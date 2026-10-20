"""Fixed one-shot HTTP adapter for the signed verifier service.

Loopback is the default. An explicit private-LAN mode can bind to one RFC1918
address and admit one exact peer address, but source-IP filtering does not
authenticate callers or establish independent host trust.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import math
import os
import re
import ssl
import threading
from typing import Callable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .signed_verifier_protocol import (
    MAX_SIGNED_VERIFIER_INVOCATION_BYTES,
    parse_signed_verifier_invocation,
)
from .signed_verifier_service import (
    SignedVerifierServiceError,
    VerifierProfile,
    VerifierRunner,
    handle_signed_verifier_invocation,
)
from .signer_key_source import Ed25519SeedCredentialSource
from .verifier_attestation import MAX_ATTESTATION_BYTES


_PATH = "/v1/verify"
_MEDIA_TYPE = "application/json"
_USER_AGENT = "Agent00X-SignedVerifier/1"
_MAX_HEADER_COUNT = 32
_MAX_HEADER_BYTES = 8_192
_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}\Z")
_CONTENT_LENGTH = re.compile(r"(?:0|[1-9][0-9]{0,8})\Z")
_REJECTED_BODY = b'{"error":"request_rejected"}'
_UNAVAILABLE_BODY = b'{"error":"verifier_unavailable"}'
_EPHEMERAL_TLS_DNS_NAME = "testdev.local"
_MAX_EPHEMERAL_TLS_MATERIAL_BYTES = 65_536
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


@dataclass(frozen=True)
class SignedVerifierHTTPResponse:
    """Bounded sanitized response emitted by the one-shot HTTP adapter."""

    status: int
    body: bytes

    def __post_init__(self) -> None:
        if (
            type(self.status) is not int
            or not 100 <= self.status <= 599
            or type(self.body) is not bytes
            or not self.body
            or len(self.body) > MAX_ATTESTATION_BYTES
        ):
            raise SignedVerifierServiceError(
                "signed verifier HTTP service: response rejected"
            )

    @property
    def headers(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Content-Type", _MEDIA_TYPE),
            ("Content-Length", str(len(self.body))),
            ("Cache-Control", "no-store"),
            ("Connection", "close"),
        )


class SignedVerifierHTTPService:
    """Accept one exact bounded invocation and delegate to the fixed service."""

    def __init__(
        self,
        profile: object,
        verifier: object,
        signing_key: object,
        *,
        invocation_handler: Callable[..., bytes] | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            type(profile) is not VerifierProfile
            or not callable(getattr(verifier, "verify", None))
            or not (
                isinstance(signing_key, Ed25519PrivateKey)
                or type(signing_key) is Ed25519SeedCredentialSource
            )
            or (invocation_handler is not None and not callable(invocation_handler))
            or (now_factory is not None and not callable(now_factory))
        ):
            raise SignedVerifierServiceError(
                "signed verifier HTTP service: configuration rejected"
            )
        self._profile = profile
        self._verifier = verifier
        self._signing_key = signing_key
        self._invocation_handler = (
            handle_signed_verifier_invocation
            if invocation_handler is None
            else invocation_handler
        )
        self._now_factory = (
            (lambda: datetime.now(timezone.utc))
            if now_factory is None
            else now_factory
        )
        self._attempt_lock = threading.Lock()
        self._attempt_started = False

    @staticmethod
    def preflight(
        method: object, path: object, headers: object
    ) -> SignedVerifierHTTPResponse | None:
        """Validate request metadata before a server reads its bounded body."""

        if type(method) is not str or method != "POST":
            return _response(405)
        if type(path) is not str or path != _PATH:
            return _response(404)
        normalized = _normalize_headers(headers)
        if isinstance(normalized, SignedVerifierHTTPResponse):
            return normalized
        if (
            "transfer-encoding" in normalized
            or "content-encoding" in normalized
            or "authorization" in normalized
            or "cookie" in normalized
        ):
            return _response(400)
        if normalized.get("content-type") != _MEDIA_TYPE or normalized.get(
            "accept"
        ) != _MEDIA_TYPE:
            return _response(415)
        if normalized.get("accept-encoding") not in {None, "identity"}:
            return _response(400)
        if "host" not in normalized or not normalized["host"]:
            return _response(400)
        if normalized.get("user-agent") != _USER_AGENT:
            return _response(400)
        raw_length = normalized.get("content-length")
        if raw_length is None:
            return _response(411)
        if _CONTENT_LENGTH.fullmatch(raw_length) is None:
            return _response(400)
        length = int(raw_length)
        if length == 0:
            return _response(400)
        if length > MAX_SIGNED_VERIFIER_INVOCATION_BYTES:
            return _response(413)
        return None

    @staticmethod
    def _content_length(headers: object) -> int:
        normalized = _normalize_headers(headers)
        if isinstance(normalized, SignedVerifierHTTPResponse):
            raise SignedVerifierServiceError(
                "signed verifier HTTP service: request rejected"
            )
        return int(normalized["content-length"])

    def handle_request(
        self, method: object, path: object, headers: object, body: object
    ) -> SignedVerifierHTTPResponse:
        """Process at most one request; never expose verifier exceptions."""

        with self._attempt_lock:
            if self._attempt_started:
                return _response(429)
            self._attempt_started = True

        preflight = self.preflight(method, path, headers)
        if preflight is not None:
            return preflight
        try:
            expected_length = self._content_length(headers)
            if (
                type(body) is not bytes
                or len(body) != expected_length
                or len(body) > MAX_SIGNED_VERIFIER_INVOCATION_BYTES
            ):
                return _response(400)
            try:
                invocation = parse_signed_verifier_invocation(body)
                if (
                    invocation.verifier_profile_digest
                    != self._profile.profile_digest
                ):
                    return _response(400)
            except Exception:
                return _response(400)
            response_body = self._invocation_handler(
                body,
                profile=self._profile,
                verifier=self._verifier,
                signing_key=self._signing_key,
                issued_at=self._now_factory(),
            )
            if (
                type(response_body) is not bytes
                or not response_body
                or len(response_body) > MAX_ATTESTATION_BYTES
            ):
                return _response(500)
            return SignedVerifierHTTPResponse(200, response_body)
        except Exception:
            return _response(500, _UNAVAILABLE_BODY)


def _normalize_headers(
    headers: object,
) -> dict[str, str] | SignedVerifierHTTPResponse:
    if type(headers) not in {tuple, list} or len(headers) > _MAX_HEADER_COUNT:
        return _response(400)
    normalized: dict[str, str] = {}
    byte_count = 0
    allowed = {
        "host",
        "accept",
        "accept-encoding",
        "content-length",
        "content-type",
        "user-agent",
        "connection",
    }
    try:
        for item in headers:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not str
            ):
                raise ValueError
            name, value = item
            if (
                _HEADER_NAME.fullmatch(name) is None
                or not value
                or value != value.strip()
                or any(ord(char) < 32 and char != "\t" for char in value)
            ):
                raise ValueError
            lowered_name = name.lower()
            if lowered_name not in allowed or lowered_name in normalized:
                raise ValueError
            byte_count += len(name.encode("ascii")) + len(value.encode("utf-8"))
            if byte_count > _MAX_HEADER_BYTES:
                raise ValueError
            normalized[lowered_name] = value
    except Exception:
        return _response(400)
    return normalized


def _response(
    status: int, body: bytes = _REJECTED_BODY
) -> SignedVerifierHTTPResponse:
    return SignedVerifierHTTPResponse(status, body)


def create_loopback_http_server(
    service: SignedVerifierHTTPService,
    port: int,
    *,
    request_timeout_seconds: float = 30.0,
) -> HTTPServer:
    """Bind a single-request HTTP server only to IPv4 loopback."""
    return _create_single_request_http_server(
        service,
        port,
        bind_host="127.0.0.1",
        allowed_peer_address=None,
        request_timeout_seconds=request_timeout_seconds,
    )


def create_private_lan_http_server(
    service: SignedVerifierHTTPService,
    port: int,
    *,
    bind_address: str,
    allowed_peer_address: str,
    request_timeout_seconds: float = 30.0,
) -> HTTPServer:
    """Bind one request to an explicit RFC1918 IPv4 address/peer pair.

    Source-IP filtering is only an access-control boundary. It does not
    authenticate the peer or establish verifier-host trust.
    """
    if (
        _private_lan_ipv4(bind_address) is None
        or _private_lan_ipv4(allowed_peer_address) is None
        or bind_address == allowed_peer_address
    ):
        raise SignedVerifierServiceError(
            "signed verifier HTTP service: server configuration rejected"
        )
    return _create_single_request_http_server(
        service,
        port,
        bind_host=bind_address,
        allowed_peer_address=allowed_peer_address,
        request_timeout_seconds=request_timeout_seconds,
    )


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


def is_private_lan_ipv4(value: object) -> bool:
    """Return whether value is a canonical RFC1918 IPv4 literal."""
    return _private_lan_ipv4(value) is not None


def _create_single_request_http_server(
    service: SignedVerifierHTTPService,
    port: int,
    *,
    bind_host: str,
    allowed_peer_address: str | None,
    request_timeout_seconds: float,
) -> HTTPServer:
    try:
        timeout_valid = (
            type(request_timeout_seconds) in {int, float}
            and math.isfinite(float(request_timeout_seconds))
            and 0 < float(request_timeout_seconds) <= 30.0
        )
    except (OverflowError, TypeError, ValueError):
        timeout_valid = False
    if (
        type(service) is not SignedVerifierHTTPService
        or type(port) is not int
        or not 0 <= port <= 65_535
        or not timeout_valid
    ):
        raise SignedVerifierServiceError(
            "signed verifier HTTP service: server configuration rejected"
        )

    class Server(HTTPServer):
        allow_reuse_address = False

        def verify_request(self, _request, client_address):
            if allowed_peer_address is None:
                return True
            return (
                type(client_address) in {tuple, list}
                and len(client_address) >= 1
                and type(client_address[0]) is str
                and client_address[0] == allowed_peer_address
            )

        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(float(request_timeout_seconds))
            return connection, address

        def handle_error(self, _request, _client_address):
            return

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Agent00X"
        sys_version = ""

        def _dispatch(self):
            raw_headers = tuple(self.headers.raw_items())
            metadata_response = service.preflight(
                self.command, self.path, raw_headers
            )
            if metadata_response is None:
                try:
                    content_length = service._content_length(raw_headers)
                    body = self.rfile.read(content_length)
                except Exception:
                    body = None
            else:
                body = b""
            response = service.handle_request(
                self.command, self.path, raw_headers, body
            )
            self.server.last_response_status = response.status
            self.send_response(response.status)
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                try:
                    self.wfile.write(response.body)
                except Exception:
                    pass
            self.close_connection = True

        do_POST = _dispatch
        do_GET = _dispatch
        do_HEAD = _dispatch
        do_PUT = _dispatch
        do_PATCH = _dispatch
        do_DELETE = _dispatch
        do_OPTIONS = _dispatch

        def send_error(self, _code, message=None, explain=None):
            self._dispatch()

        def log_message(self, _format, *args):
            return

    try:
        server = Server((bind_host, port), Handler)
        server.timeout = float(request_timeout_seconds)
        server.last_response_status = None
        server.allowed_peer_address = allowed_peer_address
        return server
    except Exception:
        raise SignedVerifierServiceError(
            "signed verifier HTTP service: server unavailable"
        ) from None


def create_loopback_https_server(
    service: SignedVerifierHTTPService,
    port: int,
    tls_context: ssl.SSLContext,
    *,
    request_timeout_seconds: float = 30.0,
) -> HTTPServer:
    """Bind the same one-request service to loopback with server-side TLS."""

    if (
        type(tls_context) is not ssl.SSLContext
        or tls_context.protocol != ssl.PROTOCOL_TLS_SERVER
        or tls_context.minimum_version < ssl.TLSVersion.TLSv1_2
    ):
        raise SignedVerifierServiceError(
            "signed verifier HTTPS service: TLS configuration rejected"
        )

    server = create_loopback_http_server(
        service, port, request_timeout_seconds=request_timeout_seconds
    )
    try:
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
        server.tls_enabled = True
        return server
    except Exception:
        try:
            server.server_close()
        except Exception:
            pass
        raise SignedVerifierServiceError(
            "signed verifier HTTPS service: server unavailable"
        ) from None


def create_private_lan_https_server(
    service: SignedVerifierHTTPService,
    port: int,
    tls_context: ssl.SSLContext,
    *,
    bind_address: str,
    allowed_peer_address: str,
    request_timeout_seconds: float = 30.0,
) -> HTTPServer:
    """Serve one TLS request on an exact private-LAN address/peer pair."""
    if (
        type(tls_context) is not ssl.SSLContext
        or tls_context.protocol != ssl.PROTOCOL_TLS_SERVER
        or tls_context.minimum_version < ssl.TLSVersion.TLSv1_2
    ):
        raise SignedVerifierServiceError(
            "signed verifier HTTPS service: TLS configuration rejected"
        )
    server = create_private_lan_http_server(
        service,
        port,
        bind_address=bind_address,
        allowed_peer_address=allowed_peer_address,
        request_timeout_seconds=request_timeout_seconds,
    )
    try:
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
        server.tls_enabled = True
        return server
    except Exception:
        try:
            server.server_close()
        except Exception:
            pass
        raise SignedVerifierServiceError(
            "signed verifier HTTPS service: server unavailable"
        ) from None


def create_ephemeral_verifier_tls_context() -> tuple[ssl.SSLContext, bytes, str]:
    """Create a short-lived testdev.local TLS identity without key files.

    The public CA certificate and its SHA-256 digest are returned for explicit
    caller pinning. Private TLS material is loaded through sealed Linux memfds;
    this function intentionally has no disk/environment fallback.
    """

    certificate_fd = -1
    private_key_fd = -1
    private_key_pem = bytearray()
    try:
        memfd_create = getattr(os, "memfd_create", None)
        memfd_cloexec = getattr(os, "MFD_CLOEXEC", None)
        memfd_allow_sealing = getattr(os, "MFD_ALLOW_SEALING", None)
        if (
            not callable(memfd_create)
            or type(memfd_cloexec) is not int
            or type(memfd_allow_sealing) is not int
            or not os.path.isdir("/proc/self/fd")
        ):
            raise ValueError

        ca_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
        leaf_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        not_before = (now - timedelta(seconds=15)).replace(microsecond=0)
        not_after = not_before + timedelta(minutes=30)
        ca_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "Agent00X ephemeral verifier CA")]
        )
        leaf_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, _EPHEMERAL_TLS_DNS_NAME)]
        )
        ca_certificate = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=None,
                    decipher_only=None,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        leaf_certificate = (
            x509.CertificateBuilder()
            .subject_name(leaf_name)
            .issuer_name(ca_name)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName(_EPHEMERAL_TLS_DNS_NAME)]
                ),
                critical=False,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=None,
                    decipher_only=None,
                ),
                critical=True,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    ca_key.public_key()
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        ca_pem = ca_certificate.public_bytes(serialization.Encoding.PEM)
        chain_pem = (
            leaf_certificate.public_bytes(serialization.Encoding.PEM) + ca_pem
        )
        private_key_pem.extend(
            leaf_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        if (
            not ca_pem
            or len(ca_pem) > _MAX_EPHEMERAL_TLS_MATERIAL_BYTES
            or len(chain_pem) > _MAX_EPHEMERAL_TLS_MATERIAL_BYTES
            or not private_key_pem
            or len(private_key_pem) > _MAX_EPHEMERAL_TLS_MATERIAL_BYTES
        ):
            raise ValueError

        import fcntl

        flags = memfd_cloexec | memfd_allow_sealing
        certificate_fd = memfd_create("agent00x-verifier-chain", flags)
        private_key_fd = memfd_create("agent00x-verifier-key", flags)
        for descriptor, material in (
            (certificate_fd, chain_pem),
            (private_key_fd, private_key_pem),
        ):
            offset = 0
            while offset < len(material):
                written = os.write(descriptor, material[offset:])
                if written <= 0:
                    raise ValueError
                offset += written
            os.lseek(descriptor, 0, os.SEEK_SET)
            seals = (
                fcntl.F_SEAL_WRITE
                | fcntl.F_SEAL_GROW
                | fcntl.F_SEAL_SHRINK
                | fcntl.F_SEAL_SEAL
            )
            fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(
            certfile=f"/proc/self/fd/{certificate_fd}",
            keyfile=f"/proc/self/fd/{private_key_fd}",
        )
        return context, ca_pem, hashlib.sha256(ca_pem).hexdigest()
    except Exception:
        raise SignedVerifierServiceError(
            "signed verifier HTTPS service: ephemeral TLS identity unavailable"
        ) from None
    finally:
        for descriptor in (private_key_fd, certificate_fd):
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except Exception:
                    pass
        for index in range(len(private_key_pem)):
            private_key_pem[index] = 0
