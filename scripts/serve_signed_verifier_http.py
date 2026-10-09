#!/usr/bin/env python3
"""Serve one fixed signed-verifier request on IPv4 loopback only.

Remote use requires a separately governed TLS/access-control proxy. This
operator entrypoint is intentionally not invoked by tests or setup.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import shutil
import sys
from typing import Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "src"))

from app_contracts.credential_source import ProcessEnvironmentCredentialSource  # noqa: E402
from app_contracts.signed_verifier_http_service import (  # noqa: E402
    SignedVerifierHTTPService,
    create_loopback_http_server,
)
from app_contracts.signed_verifier_service import (  # noqa: E402
    BRAINBOOSTER_VERIFIER_PROFILE,
    SignedVerifierServiceError,
    create_brainbooster_verifier_runner,
)
from app_contracts.signer_key_source import Ed25519SeedCredentialSource  # noqa: E402


_SIGNING_SEED_ENV_NAME = "AGENT_VERIFIER_SIGNING_SEED"
_ERROR_MARKER = "signed verifier HTTP service: startup or request failed\n"
_MIN_PORT = 1024
_MAX_PORT = 65_535


def _default_service_factory() -> SignedVerifierHTTPService:
    docker_executable = shutil.which("docker")
    if docker_executable is None:
        raise SignedVerifierServiceError(
            "signed verifier HTTP service: service unavailable"
        )
    verifier = create_brainbooster_verifier_runner(docker_executable)
    credential_source = ProcessEnvironmentCredentialSource(
        os.environ, _SIGNING_SEED_ENV_NAME
    )
    signing_key = Ed25519SeedCredentialSource(credential_source)
    return SignedVerifierHTTPService(
        BRAINBOOSTER_VERIFIER_PROFILE,
        verifier,
        signing_key,
        now_factory=lambda: datetime.now(timezone.utc),
    )


def main(
    argv: object | None = None,
    *,
    service_factory: Callable[[], SignedVerifierHTTPService] | None = None,
    server_factory: Callable[..., object] | None = None,
    stderr=None,
) -> int:
    """Serve one request, using only loopback and an explicit unprivileged port."""

    error_stream = sys.stderr if stderr is None else stderr
    server = None
    try:
        parser = argparse.ArgumentParser(add_help=True)
        parser.add_argument("--port", type=int, required=True)
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
        if type(args.port) is not int or not _MIN_PORT <= args.port <= _MAX_PORT:
            raise ValueError
        service = (service_factory or _default_service_factory)()
        server = (server_factory or create_loopback_http_server)(
            service, args.port, request_timeout_seconds=30.0
        )
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
