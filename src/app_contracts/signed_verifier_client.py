"""Single-attempt client for a future separately hosted signed verifier.

The transport is injected so this module does not choose HTTP, SSH, credentials
or deployment policy. A valid signature proves possession of the supplied key;
it does not establish independent-host trust, so returned receipts remain
audit-only until an external trust enrollment is governed separately.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .executor import VerifierInput
from .signed_verifier_service import VerifierProfile
from .signed_verifier_protocol import serialize_signed_verifier_invocation
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
