#!/usr/bin/env python3
"""Serve one locally tunneled verifier request with process-ephemeral keys.

Only public TLS/trust bootstrap data is written to stdout. Private signing and
TLS keys are generated inside this process, never loaded from or written to a
file, environment variable, or command argument. This is an experimental
one-shot host service, not a durable key store or authenticated enrollment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from typing import Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "src"))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app_contracts.signed_verifier_http_service import (  # noqa: E402
    SignedVerifierHTTPService,
    create_ephemeral_verifier_tls_context,
    create_loopback_https_server,
)
from app_contracts.signed_verifier_service import (  # noqa: E402
    BRAINBOOSTER_VERIFIER_PROFILE,
    SignedVerifierServiceError,
    VerifierRunner,
    create_brainbooster_verifier_runner,
)


_ERROR_MARKER = "signed verifier HTTPS service: startup or request failed\n"
_BOOTSTRAP_SCHEMA = "agent00x-ephemeral-verifier-bootstrap/v1"
_ENDPOINT_URL = "https://testdev.local/v1/verify"
_MAX_BOOTSTRAP_BYTES = 8192
_MAX_IDLE_WAIT_SECONDS = 900
_MIN_PORT = 1024
_MAX_PORT = 65_535


def _default_verifier_factory() -> VerifierRunner:
    docker_executable = shutil.which("docker")
    if docker_executable is None:
        raise SignedVerifierServiceError(
            "signed verifier HTTPS service: verifier unavailable"
        )
    return create_brainbooster_verifier_runner(docker_executable)


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError


def _serialize_public_bootstrap(
    *, port: int, ca_certificate_pem: bytes, ca_sha256: str, signing_key: Ed25519PrivateKey
) -> bytes:
    try:
        if (
            type(port) is not int
            or not _MIN_PORT <= port <= _MAX_PORT
            or type(ca_certificate_pem) is not bytes
            or not ca_certificate_pem
            or len(ca_certificate_pem) > 4096
            or type(ca_sha256) is not str
            or len(ca_sha256) != 64
            or any(character not in "0123456789abcdef" for character in ca_sha256)
            or not isinstance(signing_key, Ed25519PrivateKey)
        ):
            raise ValueError
        if hashlib.sha256(ca_certificate_pem).hexdigest() != ca_sha256:
            raise ValueError
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        record = {
            "schema": _BOOTSTRAP_SCHEMA,
            "status": "ready",
            "endpoint_url": _ENDPOINT_URL,
            "listen_host": "127.0.0.1",
            "connect_port": port,
            "tls_ca_certificate_pem": ca_certificate_pem.decode("ascii"),
            "tls_ca_sha256": "sha256:" + ca_sha256,
            "verifier_profile_digest": BRAINBOOSTER_VERIFIER_PROFILE.profile_digest,
            "verifier_key_id": BRAINBOOSTER_VERIFIER_PROFILE.signer_key_id,
            "verifier_public_key": public_key.hex(),
            "verifier_public_key_sha256": "sha256:" + hashlib.sha256(public_key).hexdigest(),
        }
        encoded = json.dumps(
            record, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("ascii")
        if not encoded or len(encoded) > _MAX_BOOTSTRAP_BYTES:
            raise ValueError
        return encoded
    except Exception:
        raise SignedVerifierServiceError(
            "signed verifier HTTPS service: bootstrap unavailable"
        ) from None


def main(
    argv: object | None = None,
    *,
    verifier_factory: Callable[[], VerifierRunner] | None = None,
    tls_identity_factory: Callable[[], tuple[object, bytes, str]] | None = None,
    signer_factory: Callable[[], Ed25519PrivateKey] | None = None,
    server_factory: Callable[..., object] | None = None,
    stdout=None,
    stderr=None,
) -> int:
    """Serve exactly one request on IPv4 loopback with no persisted key."""

    output = sys.stdout if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr
    server = None
    try:
        parser = _SanitizedArgumentParser(add_help=True)
        parser.add_argument("--port", type=int, required=True)
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
        if type(args.port) is not int or (
            args.port != 0 and not _MIN_PORT <= args.port <= _MAX_PORT
        ):
            raise ValueError

        signing_key = (signer_factory or Ed25519PrivateKey.generate)()
        verifier = (verifier_factory or _default_verifier_factory)()
        service = SignedVerifierHTTPService(
            BRAINBOOSTER_VERIFIER_PROFILE,
            verifier,
            signing_key,
        )
        tls_context, ca_certificate_pem, ca_sha256 = (
            tls_identity_factory or create_ephemeral_verifier_tls_context
        )()
        server = (server_factory or create_loopback_https_server)(
            service,
            args.port,
            tls_context,
            request_timeout_seconds=30.0,
        )
        address = getattr(server, "server_address", None)
        bound_port = (
            address[1]
            if type(address) is tuple and len(address) >= 2
            else None
        )
        if (
            type(address) is not tuple
            or len(address) < 2
            or address[0] != "127.0.0.1"
            or type(bound_port) is not int
            or not _MIN_PORT <= bound_port <= _MAX_PORT
            or (args.port != 0 and bound_port != args.port)
            or getattr(server, "tls_enabled", None) is not True
        ):
            raise ValueError
        server.timeout = _MAX_IDLE_WAIT_SECONDS

        bootstrap = _serialize_public_bootstrap(
            port=bound_port,
            ca_certificate_pem=ca_certificate_pem,
            ca_sha256=ca_sha256,
            signing_key=signing_key,
        )
        output.write(bootstrap.decode("ascii") + "\n")
        output.flush()
        server.handle_request()
        return 0 if getattr(server, "last_response_status", None) == 200 else 2
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        try:
            error_stream.write(_ERROR_MARKER)
            error_stream.flush()
        except Exception:
            pass
        return 2
    finally:
        close = getattr(server, "server_close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
