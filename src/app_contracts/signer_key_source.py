"""One-shot adapter from the opaque credential protocol to an Ed25519 signer.

This module does not implement storage, key enrollment, or memory erasure. A
trusted outer runtime must provide the credential source.
"""

from __future__ import annotations

import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .credential_source import CredentialSource


_SEED_RE = re.compile(r"[0-9a-f]{64}\Z")


class SignerKeySourceError(ValueError):
    """A signer seed is unavailable or not in the canonical test format."""


class Ed25519SeedCredentialSource:
    """Resolve one canonical Ed25519 seed from a credential source on demand."""

    __slots__ = ("_source",)

    def __init__(self, source: CredentialSource) -> None:
        if not isinstance(source, CredentialSource):
            raise SignerKeySourceError("signer key source: configuration is invalid")
        self._source = source

    def __repr__(self) -> str:
        return "Ed25519SeedCredentialSource(value='opaque')"

    __str__ = __repr__

    def __call__(self) -> Ed25519PrivateKey:
        try:
            seed = self._source()
            if type(seed) is not str or _SEED_RE.fullmatch(seed) is None:
                raise ValueError
            return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed))
        except Exception:
            raise SignerKeySourceError("signer key source: value is invalid") from None
