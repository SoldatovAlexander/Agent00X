"""Single-attempt client for a future separately hosted signed verifier.

The transport is injected so this module does not choose HTTP, SSH, credentials
or deployment policy. A valid signature proves possession of the supplied key;
it does not establish independent-host trust, so returned receipts remain
audit-only until an external trust enrollment is governed separately.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import http.client
import ipaddress
import math
import os
from pathlib import Path
import re
import socket
import ssl
import tempfile
import threading
import time
from typing import Protocol
from urllib.parse import urlsplit

import certifi

from .executor import VerifierInput
from .signed_verifier_service import VerifierProfile
from .signed_verifier_protocol import (
    MAX_SIGNED_VERIFIER_INVOCATION_BYTES,
    serialize_signed_verifier_invocation,
)
from .verifier_attestation import (
    MAX_ATTESTATION_BYTES,
    VerifiedVerifierAttestation,
    new_verifier_invocation_nonce,
    verify_signed_verifier_response,
)
from .verifier_trust_enrollment import (
    VerifiedVerifierTrustEnrollment,
    verify_verifier_trust_enrollment,
)
from .verifier_host_trust_decision import (
    VerifiedVerifierHostTrustDecision,
    is_verified_verifier_host_trust_decision,
    verify_verifier_host_trust_decision,
)
from .verifier_process import (
    MAX_VERIFIER_REQUEST_BYTES,
    VerifierProcessRequest,
    serialize_verifier_request,
)


class SignedVerifierClientError(ValueError):
    """A remote verifier request or signed response was rejected."""


class SignedVerifierSubprocessTransportError(ValueError):
    """A bounded one-shot verifier process could not complete safely."""


class SignedVerifierHTTPSTransportError(ValueError):
    """A one-shot signed-verifier HTTPS exchange was rejected safely."""


_VERIFIER_DNS_RESOLVER_SLOT = threading.BoundedSemaphore(1)
_MAX_VERIFIER_DNS_ADDRESSES = 32


def _check_verifier_deadline(deadline: float, expired: threading.Event) -> None:
    if expired.is_set() or time.monotonic() >= deadline:
        raise SignedVerifierHTTPSTransportError(
            "signed verifier HTTPS transport: request timed out"
        )


def _resolve_verifier_addresses(
    host: str, port: int, deadline: float, expired: threading.Event
) -> tuple[tuple[int, int, int, tuple[object, ...]], ...]:
    """Bound DNS wait and prevent accumulation of abandoned resolver threads."""

    if not _VERIFIER_DNS_RESOLVER_SLOT.acquire(blocking=False):
        raise SignedVerifierHTTPSTransportError(
            "signed verifier HTTPS transport: request timed out"
        )
    completed = threading.Event()
    results: list[object] = []
    failures: list[BaseException] = []

    def resolve() -> None:
        try:
            results.append(
                socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            )
        except BaseException as exc:
            failures.append(exc)
        finally:
            completed.set()
            _VERIFIER_DNS_RESOLVER_SLOT.release()

    resolver = threading.Thread(
        target=resolve, name="agent00x-signed-verifier-dns", daemon=True
    )
    try:
        resolver.start()
    except Exception:
        _VERIFIER_DNS_RESOLVER_SLOT.release()
        raise SignedVerifierHTTPSTransportError(
            "signed verifier HTTPS transport: request failed"
        ) from None

    remaining = deadline - time.monotonic()
    if remaining <= 0 or not completed.wait(remaining):
        expired.set()
        raise SignedVerifierHTTPSTransportError(
            "signed verifier HTTPS transport: request timed out"
        )
    _check_verifier_deadline(deadline, expired)
    if failures or len(results) != 1 or type(results[0]) is not list:
        raise SignedVerifierHTTPSTransportError(
            "signed verifier HTTPS transport: request failed"
        )

    addresses: list[tuple[int, int, int, tuple[object, ...]]] = []
    try:
        for item in results[0]:
            family, socktype, protocol, _canonical_name, sockaddr = item
            if (
                family not in {socket.AF_INET, socket.AF_INET6}
                or socktype != socket.SOCK_STREAM
                or type(sockaddr) is not tuple
                or not sockaddr
                or type(sockaddr[0]) is not str
                or "%" in sockaddr[0]
            ):
                continue
            ipaddress.ip_address(sockaddr[0])
            if family == socket.AF_INET and (
                len(sockaddr) != 2 or sockaddr[1] != port
            ):
                continue
            if family == socket.AF_INET6 and (
                len(sockaddr) != 4
                or sockaddr[1] != port
                or sockaddr[3] != 0
            ):
                continue
            address = (family, socktype, protocol, sockaddr)
            if address not in addresses:
                addresses.append(address)
            if len(addresses) > _MAX_VERIFIER_DNS_ADDRESSES:
                raise ValueError
    except Exception:
        raise SignedVerifierHTTPSTransportError(
            "signed verifier HTTPS transport: request failed"
        ) from None
    if not addresses:
        raise SignedVerifierHTTPSTransportError(
            "signed verifier HTTPS transport: request failed"
        )
    return tuple(addresses)


def _connect_verifier_address(
    addresses: tuple[tuple[int, int, int, tuple[object, ...]], ...],
    *,
    deadline: float,
    expired: threading.Event,
) -> socket.socket:
    last_error: OSError | None = None
    for family, socktype, protocol, sockaddr in addresses:
        _check_verifier_deadline(deadline, expired)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _check_verifier_deadline(deadline, expired)
        connection_socket = socket.socket(family, socktype, protocol)
        try:
            connection_socket.settimeout(remaining)
            connection_socket.connect(sockaddr)
            _check_verifier_deadline(deadline, expired)
            return connection_socket
        except SignedVerifierHTTPSTransportError:
            connection_socket.close()
            raise
        except OSError as exc:
            last_error = exc
            connection_socket.close()
    if last_error is not None:
        raise last_error
    raise OSError("connection failed")


class SignedVerifierHTTPSTransport:
    """One fixed-path, verified-TLS request to an explicitly configured host.

    HTTPS authenticates the configured DNS name according to the local CA
    bundle. Neither TLS nor the signed response proves that the verifier host
    is independently governed, so the client continues to return audit-only
    attestations.
    """

    MAX_TIMEOUT_SECONDS = 30.0
    _PATH = "/v1/verify"
    _MEDIA_TYPE = "application/json"
    _USER_AGENT = "Agent00X-SignedVerifier/1"
    _DNS_NAME = re.compile(
        r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
        r"(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+\Z"
    )

    def __init__(
        self,
        endpoint_url: object,
        *,
        timeout_seconds: float = 10.0,
        connection_factory: object = None,
    ) -> None:
        try:
            timeout_valid = (
                not isinstance(timeout_seconds, bool)
                and isinstance(timeout_seconds, (int, float))
                and math.isfinite(float(timeout_seconds))
                and 0 < float(timeout_seconds) <= self.MAX_TIMEOUT_SECONDS
            )
        except (OverflowError, TypeError, ValueError):
            timeout_valid = False
        endpoint = self._parse_endpoint(endpoint_url)
        if not timeout_valid or (
            connection_factory is not None and not callable(connection_factory)
        ):
            raise SignedVerifierHTTPSTransportError(
                "signed verifier HTTPS transport: configuration rejected"
            )
        self._host, self._port = endpoint
        self._endpoint_url = endpoint_url
        self._timeout_seconds = float(timeout_seconds)
        self._connection_factory = connection_factory
        self._attempt_lock = threading.Lock()
        self._attempt_started = False

    @property
    def endpoint_url(self) -> str:
        """Return the exact URL validated and bound to this transport."""

        return self._endpoint_url

    @classmethod
    def _parse_endpoint(cls, endpoint_url: object) -> tuple[str, int]:
        try:
            if type(endpoint_url) is not str or len(endpoint_url) > 2048:
                raise ValueError
            parsed = urlsplit(endpoint_url)
            host = parsed.hostname
            if (
                parsed.scheme != "https"
                or host is None
                or parsed.netloc.lower() not in {host, f"{host}:443"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or "?" in endpoint_url
                or "#" in endpoint_url
                or parsed.path != cls._PATH
                or parsed.port not in {None, 443}
                or not cls._DNS_NAME.fullmatch(host)
                or host == "localhost"
                or host.endswith(".localhost")
                or host.endswith(".local")
            ):
                raise ValueError
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError
            return host, 443
        except Exception:
            raise SignedVerifierHTTPSTransportError(
                "signed verifier HTTPS transport: configuration rejected"
            ) from None

    def __repr__(self) -> str:
        return "SignedVerifierHTTPSTransport(authentication='none', one_shot=True)"

    def request(self, invocation_bytes: object) -> bytes:
        """Send one bounded canonical invocation and return one bounded body."""

        if (
            type(invocation_bytes) is not bytes
            or not invocation_bytes
            or len(invocation_bytes) > MAX_SIGNED_VERIFIER_INVOCATION_BYTES
        ):
            raise SignedVerifierHTTPSTransportError(
                "signed verifier HTTPS transport: request rejected"
            )
        with self._attempt_lock:
            if self._attempt_started:
                raise SignedVerifierHTTPSTransportError(
                    "signed verifier HTTPS transport: attempt limit exceeded"
                )
            self._attempt_started = True

        connection = None
        response = None
        timer = None
        expired = threading.Event()
        deadline = time.monotonic() + self._timeout_seconds
        try:
            context = self._create_verified_ssl_context()
            factory = self._connection_factory or http.client.HTTPSConnection
            connection = factory(
                self._host,
                port=self._port,
                timeout=self._timeout_seconds,
                context=context,
            )
            if self._connection_factory is None:
                addresses = _resolve_verifier_addresses(
                    self._host, self._port, deadline, expired
                )

                def connect_to_resolved_addresses(
                    _address: tuple[str, int],
                    _connect_timeout: float,
                    source_address: tuple[str, int] | None = None,
                ) -> socket.socket:
                    if source_address is not None:
                        raise OSError("source address is not supported")
                    return _connect_verifier_address(
                        addresses, deadline=deadline, expired=expired
                    )

                connection._create_connection = connect_to_resolved_addresses

            def abort_connection() -> None:
                expired.set()
                active_socket = getattr(connection, "sock", None)
                shutdown = getattr(active_socket, "shutdown", None)
                if callable(shutdown):
                    try:
                        shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                close = getattr(connection, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass

            timer = threading.Timer(
                max(0.0, deadline - time.monotonic()), abort_connection
            )
            timer.daemon = True
            timer.start()
            _check_verifier_deadline(deadline, expired)
            connection.request(
                "POST",
                self._PATH,
                body=invocation_bytes,
                headers={
                    "Accept": self._MEDIA_TYPE,
                    "Content-Length": str(len(invocation_bytes)),
                    "Content-Type": self._MEDIA_TYPE,
                    "User-Agent": self._USER_AGENT,
                },
            )
            _check_verifier_deadline(deadline, expired)
            response = connection.getresponse()
            _check_verifier_deadline(deadline, expired)
            status = getattr(response, "status", None)
            content_type = response.getheader("Content-Type")
            if (
                type(status) is not int
                or status != 200
                or content_type != self._MEDIA_TYPE
            ):
                raise SignedVerifierHTTPSTransportError(
                    "signed verifier HTTPS transport: response rejected"
                )
            content_length = response.getheader("Content-Length")
            if content_length is not None and (
                type(content_length) is not str
                or not content_length.isascii()
                or not content_length.isdigit()
                or len(content_length) > 12
                or int(content_length) > MAX_ATTESTATION_BYTES
            ):
                raise SignedVerifierHTTPSTransportError(
                    "signed verifier HTTPS transport: response rejected"
                )
            body = response.read(MAX_ATTESTATION_BYTES + 1)
            _check_verifier_deadline(deadline, expired)
            if type(body) is not bytes or not body or len(body) > MAX_ATTESTATION_BYTES:
                raise SignedVerifierHTTPSTransportError(
                    "signed verifier HTTPS transport: response rejected"
                )
            return body
        except SignedVerifierHTTPSTransportError:
            raise
        except Exception:
            if expired.is_set() or time.monotonic() >= deadline:
                raise SignedVerifierHTTPSTransportError(
                    "signed verifier HTTPS transport: request timed out"
                ) from None
            raise SignedVerifierHTTPSTransportError(
                "signed verifier HTTPS transport: request failed"
            ) from None
        finally:
            if timer is not None:
                timer.cancel()
                timer.join()
            close_response = getattr(response, "close", None)
            if callable(close_response):
                try:
                    close_response()
                except Exception:
                    pass
            close_connection = getattr(connection, "close", None)
            if callable(close_connection):
                try:
                    close_connection()
                except Exception:
                    pass

    @staticmethod
    def _create_verified_ssl_context() -> ssl.SSLContext:
        try:
            context = ssl.create_default_context()
            ca_file = certifi.where()
            if type(ca_file) is not str or not ca_file:
                raise ValueError
            context.load_verify_locations(cafile=ca_file)
            if (
                not context.check_hostname
                or context.verify_mode != ssl.CERT_REQUIRED
                or context.cert_store_stats().get("x509_ca", 0) < 1
            ):
                raise ValueError
            return context
        except Exception:
            raise SignedVerifierHTTPSTransportError(
                "signed verifier HTTPS transport: TLS trust configuration rejected"
            ) from None


class SignedVerifierSubprocessTransport:
    """Run one explicitly configured local service command per invocation.

    This is a process boundary only. It does not sandbox the child, authenticate
    its host, provision signing keys, or establish independent verifier trust.
    """

    MAX_TIMEOUT_SECONDS = 300.0
    _OUTPUT_CHUNK_BYTES = 64 * 1024

    def __init__(
        self,
        command: object,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        try:
            if (
                type(command) is not tuple
                or not command
                or len(command) > 64
                or any(
                    type(argument) is not str
                    or not argument
                    or "\0" in argument
                    or len(argument.encode("utf-8")) > 16_384
                    for argument in command
                )
                or not Path(command[0]).is_absolute()
                or not Path(command[0]).is_file()
                or not os.access(command[0], os.X_OK)
                or isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or not 0 < float(timeout_seconds) <= self.MAX_TIMEOUT_SECONDS
            ):
                raise ValueError
            self._command = command
            self._timeout_seconds = float(timeout_seconds)
        except Exception:
            raise SignedVerifierSubprocessTransportError(
                "signed verifier transport: configuration rejected"
            ) from None

    def request(self, invocation_bytes: object) -> bytes:
        """Send one bounded wire record and return bounded child stdout bytes."""

        if (
            type(invocation_bytes) is not bytes
            or not invocation_bytes
            or len(invocation_bytes) > MAX_SIGNED_VERIFIER_INVOCATION_BYTES
        ):
            raise SignedVerifierSubprocessTransportError(
                "signed verifier transport: request rejected"
            )
        try:
            return asyncio.run(self._exchange(invocation_bytes))
        except SignedVerifierSubprocessTransportError:
            raise
        except Exception:
            raise SignedVerifierSubprocessTransportError(
                "signed verifier transport: process request failed"
            ) from None

    async def _exchange(self, invocation_bytes: bytes) -> bytes:
        try:
            with tempfile.TemporaryDirectory(
                prefix="agent00x-signed-verifier-"
            ) as working_directory:
                process = await asyncio.create_subprocess_exec(
                    *self._command,
                    cwd=working_directory,
                    env={
                        "PATH": os.defpath,
                        "LANG": "C.UTF-8",
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=self._OUTPUT_CHUNK_BYTES,
                )
                assert process.stdin is not None
                assert process.stdout is not None

                async def send_request() -> None:
                    process.stdin.write(invocation_bytes)
                    await process.stdin.drain()
                    process.stdin.close()
                    await process.stdin.wait_closed()

                async def read_response() -> bytes:
                    response = bytearray()
                    while True:
                        remaining = MAX_ATTESTATION_BYTES + 1 - len(response)
                        chunk = await process.stdout.read(
                            min(self._OUTPUT_CHUNK_BYTES, remaining)
                        )
                        if not chunk:
                            return bytes(response)
                        response.extend(chunk)
                        if len(response) > MAX_ATTESTATION_BYTES:
                            raise SignedVerifierSubprocessTransportError(
                                "signed verifier transport: response limit exceeded"
                            )

                try:
                    send_task = asyncio.create_task(send_request())
                    read_task = asyncio.create_task(read_response())
                    wait_task = asyncio.create_task(process.wait())
                    response, return_code, _ = await asyncio.wait_for(
                        asyncio.gather(read_task, wait_task, send_task),
                        timeout=self._timeout_seconds,
                    )
                except Exception:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
                    raise

                if return_code != 0 or type(response) is not bytes or not response:
                    raise SignedVerifierSubprocessTransportError(
                        "signed verifier transport: process request failed"
                    )
                return response
        except SignedVerifierSubprocessTransportError:
            raise
        except Exception:
            raise SignedVerifierSubprocessTransportError(
                "signed verifier transport: process request failed"
            ) from None


class SignedVerifierTransport(Protocol):
    def request(self, invocation_bytes: bytes) -> bytes: ...


class SignedVerifierClient:
    """Validate one fixed-profile request and verify one signed response."""

    def __init__(
        self,
        profile: object,
        transport: object,
        trusted_public_keys: object,
    ) -> None:
        try:
            if (
                type(profile) is not VerifierProfile
                or not callable(getattr(transport, "request", None))
                or type(trusted_public_keys) is not dict
                or set(trusted_public_keys) != {profile.signer_key_id}
                or any(
                    type(key_bytes) is not bytes or len(key_bytes) != 32
                    for key_bytes in trusted_public_keys.values()
                )
            ):
                raise ValueError
            self._profile = profile
            self._transport = transport
            # Copy the caller's mapping so later mutation cannot silently
            # replace the key trusted by this client instance.
            self._trusted_public_keys = dict(trusted_public_keys)
            self._trust_enrollment_digest: str | None = None
            self._host_trust_decision_digest: str | None = None
            self._host_trust_decision: VerifiedVerifierHostTrustDecision | None = None
            self._trust_enrollment_bytes: bytes | None = None
            self._host_trust_decision_bytes: bytes | None = None
        except Exception:
            raise SignedVerifierClientError(
                "signed verifier client: configuration rejected"
            ) from None

    @classmethod
    def from_trust_enrollment(
        cls,
        profile: object,
        transport: object,
        enrollment_bytes: object,
        *,
        trusted_authority_keys: object,
        expected_endpoint_url: object,
        expected_worker_host_id: object,
        expected_verifier_host_id: object,
        host_trust_decision_bytes: object = None,
        now: datetime | None = None,
    ) -> SignedVerifierClient:
        """Construct a client from an authority-pinned enrollment.

        Enrollment alone remains audit-only. A separate, exact authority-signed
        OOB review decision is required to promote host trust.
        """

        try:
            if (
                type(profile) is not VerifierProfile
                or type(expected_endpoint_url) is not str
                or type(expected_worker_host_id) is not str
                or type(expected_verifier_host_id) is not str
                or type(transport) is not SignedVerifierHTTPSTransport
                or getattr(transport, "endpoint_url", None) != expected_endpoint_url
            ):
                raise ValueError
            enrollment = verify_verifier_trust_enrollment(
                enrollment_bytes,
                trusted_authority_keys=trusted_authority_keys,
                expected_endpoint_url=expected_endpoint_url,
                expected_verifier_id=profile.expected_verifier_id,
                expected_verifier_profile_digest=profile.profile_digest,
                now=now,
            )
            if (
                type(enrollment) is not VerifiedVerifierTrustEnrollment
                or enrollment.verifier_key_id != profile.signer_key_id
                or enrollment.worker_host_id != expected_worker_host_id
                or enrollment.verifier_host_id != expected_verifier_host_id
                or enrollment.independent_host_trust_established is not False
            ):
                raise ValueError
            client = cls(
                profile,
                transport,
                {enrollment.verifier_key_id: enrollment.verifier_public_key},
            )
            client._trust_enrollment_digest = enrollment.enrollment_digest
            client._trust_enrollment_bytes = bytes(enrollment_bytes)
            if host_trust_decision_bytes is not None:
                decision = verify_verifier_host_trust_decision(
                    host_trust_decision_bytes,
                    trusted_authority_keys=trusted_authority_keys,
                    expected_enrollment_digest=enrollment.enrollment_digest,
                    expected_endpoint_url=expected_endpoint_url,
                    expected_verifier_id=profile.expected_verifier_id,
                    expected_verifier_profile_digest=profile.profile_digest,
                    expected_verifier_key_id=profile.signer_key_id,
                    expected_worker_host_id=expected_worker_host_id,
                    expected_verifier_host_id=expected_verifier_host_id,
                    expected_host_separation_evidence_digest=(
                        enrollment.host_separation_evidence_digest
                    ),
                    now=now,
                )
                if not is_verified_verifier_host_trust_decision(decision):
                    raise ValueError
                client._host_trust_decision_digest = decision.decision_digest
                client._host_trust_decision = decision
                client._host_trust_decision_bytes = bytes(host_trust_decision_bytes)
            return client
        except Exception:
            raise SignedVerifierClientError(
                "signed verifier client: configuration rejected"
            ) from None

    @property
    def limitations(self) -> tuple[str, ...]:
        enrollment_state = (
            "out_of_band_enrollment_validated"
            if self._trust_enrollment_digest is not None
            else "verifier_key_supplied_directly"
        )
        return (
            "signed_response_signature_validated",
            enrollment_state,
            (
                "independent_host_trust_authority_decision_validated"
                if self._host_trust_decision_digest is not None
                else "independent_host_trust_not_established"
            ),
            (
                "trusted_host_decision_bound"
                if self._host_trust_decision_digest is not None
                else "audit_only"
            ),
        )

    @property
    def trust_enrollment_digest(self) -> str | None:
        """Digest-only locator for the validated enrollment, when configured."""

        return self._trust_enrollment_digest

    def verify(self, prepared: object) -> VerifiedVerifierAttestation:
        """Make one transport call and validate the exact response binding."""

        try:
            if type(prepared) is not VerifierInput:
                raise ValueError
            self._profile.validate_request(prepared)
            request_bytes = serialize_verifier_request(
                VerifierProcessRequest.from_verifier_input(prepared)
            )
            if not request_bytes or len(request_bytes) > MAX_VERIFIER_REQUEST_BYTES:
                raise ValueError

            invocation_nonce = new_verifier_invocation_nonce()
            invocation_bytes = serialize_signed_verifier_invocation(
                request_bytes,
                invocation_nonce=invocation_nonce,
                verifier_profile_digest=self._profile.profile_digest,
            )
            response_bytes = self._transport.request(invocation_bytes)
            if (
                type(response_bytes) is not bytes
                or not response_bytes
                or len(response_bytes) > MAX_ATTESTATION_BYTES
            ):
                raise ValueError

            attestation = verify_signed_verifier_response(
                response_bytes,
                prepared,
                expected_invocation_nonce=invocation_nonce,
                expected_verifier_profile_digest=self._profile.profile_digest,
                trusted_public_keys=self._trusted_public_keys,
                now=datetime.now(timezone.utc),
            )
            if (
                type(attestation) is not VerifiedVerifierAttestation
                or attestation.signature_valid is not True
                or attestation.independent_host_trust_established is not False
                or attestation.key_id != self._profile.signer_key_id
                or attestation.verifier_profile_digest != self._profile.profile_digest
            ):
                raise ValueError
            if self._trust_enrollment_digest is not None:
                attestation = replace(
                    attestation,
                    trust_enrollment_digest=self._trust_enrollment_digest,
                )
            if self._host_trust_decision_digest is not None:
                attestation = replace(
                    attestation,
                    independent_host_trust_established=True,
                    host_trust_decision_digest=self._host_trust_decision_digest,
                    host_trust_decision=self._host_trust_decision,
                )
            attestation = replace(
                attestation,
                trust_enrollment_bytes=self._trust_enrollment_bytes,
                host_trust_decision_bytes=self._host_trust_decision_bytes,
            )
            return attestation
        except SignedVerifierClientError:
            raise
        except Exception:
            raise SignedVerifierClientError(
                "signed verifier client: request or response rejected"
            ) from None
