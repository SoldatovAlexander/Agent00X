"""Single-attempt client for a future separately hosted signed verifier.

The transport is injected so this module does not choose HTTP, SSH, credentials
or deployment policy. A valid signature proves possession of the supplied key;
it does not establish independent-host trust, so returned receipts remain
audit-only until an external trust enrollment is governed separately.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import tempfile
from typing import Protocol

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
from .verifier_process import (
    MAX_VERIFIER_REQUEST_BYTES,
    VerifierProcessRequest,
    serialize_verifier_request,
)


class SignedVerifierClientError(ValueError):
    """A remote verifier request or signed response was rejected."""


class SignedVerifierSubprocessTransportError(ValueError):
    """A bounded one-shot verifier process could not complete safely."""


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
        except Exception:
            raise SignedVerifierClientError(
                "signed verifier client: configuration rejected"
            ) from None

    @property
    def limitations(self) -> tuple[str, ...]:
        return (
            "signed_response_signature_validated",
            "independent_host_trust_not_established",
            "audit_only",
        )

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
            return attestation
        except SignedVerifierClientError:
            raise
        except Exception:
            raise SignedVerifierClientError(
                "signed verifier client: request or response rejected"
            ) from None
