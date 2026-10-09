"""Fixed one-shot stdin/stdout entrypoint for a future verifier host.

This process wrapper does not itself establish independent-host trust. It fixes
the BrainBooster verifier profile, accepts one bounded canonical invocation,
and emits only a signed response through a caller-provided transport.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import shutil
import sys
from typing import Callable

from .credential_source import ProcessEnvironmentCredentialSource
from .signed_verifier_service import (
    BRAINBOOSTER_VERIFIER_PROFILE,
    SignedVerifierServiceError,
    VerifierRunner,
    create_brainbooster_verifier_runner,
    handle_signed_verifier_invocation,
)
from .signed_verifier_protocol import MAX_SIGNED_VERIFIER_INVOCATION_BYTES
from .signer_key_source import Ed25519SeedCredentialSource
from .verifier_attestation import MAX_ATTESTATION_BYTES


_SIGNING_SEED_ENV_NAME = "AGENT_VERIFIER_SIGNING_SEED"
_ERROR_MARKER = "signed verifier service: request or execution rejected\n"


def _default_verifier_factory() -> VerifierRunner:
    docker_executable = shutil.which("docker")
    if docker_executable is None:
        raise SignedVerifierServiceError(
            "signed verifier service: request or execution rejected"
        )
    return create_brainbooster_verifier_runner(docker_executable)


def _default_credential_source_factory() -> ProcessEnvironmentCredentialSource:
    # Construction stores the mapping; the value is not read until the service
    # reaches its final signing boundary after request and verifier validation.
    return ProcessEnvironmentCredentialSource(os.environ, _SIGNING_SEED_ENV_NAME)


def main(
    argv: object | None = None,
    *,
    stdin=None,
    stdout=None,
    stderr=None,
    verifier_factory: Callable[[], VerifierRunner] | None = None,
    credential_source_factory: Callable[[], object] | None = None,
    handler: Callable[..., bytes] | None = None,
    now_factory: Callable[[], datetime] | None = None,
) -> int:
    """Process exactly one request, returning only a signed response on stdout."""

    args = sys.argv[1:] if argv is None else argv
    input_stream = sys.stdin.buffer if stdin is None else stdin
    output_stream = sys.stdout.buffer if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr
    try:
        if type(args) is not list or args:
            raise ValueError
        isatty = getattr(input_stream, "isatty", None)
        if callable(isatty) and isatty():
            raise ValueError
        request_bytes = input_stream.read(MAX_SIGNED_VERIFIER_INVOCATION_BYTES + 1)
        if (
            type(request_bytes) is not bytes
            or not request_bytes
            or len(request_bytes) > MAX_SIGNED_VERIFIER_INVOCATION_BYTES
        ):
            raise ValueError

        verifier = (verifier_factory or _default_verifier_factory)()
        credential_source = (
            credential_source_factory or _default_credential_source_factory
        )()
        signing_key = Ed25519SeedCredentialSource(credential_source)
        response = (handler or handle_signed_verifier_invocation)(
            request_bytes,
            profile=BRAINBOOSTER_VERIFIER_PROFILE,
            verifier=verifier,
            signing_key=signing_key,
            issued_at=(now_factory or (lambda: datetime.now(timezone.utc)))(),
        )
        if (
            type(response) is not bytes
            or not response
            or len(response) > MAX_ATTESTATION_BYTES
        ):
            raise ValueError
        output_stream.write(response)
        output_stream.flush()
        return 0
    except Exception:
        try:
            error_stream.write(_ERROR_MARKER)
            error_stream.flush()
        except Exception:
            pass
        return 2
