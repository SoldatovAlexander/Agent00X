"""Strict reader for caller-pinned Control Plane public authority keys."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


MAX_AUTHORITY_KEY_SET_BYTES = 32_768
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_PUBLIC_KEY = re.compile(r"[0-9a-f]{64}\Z")


class AuthorityKeySetError(ValueError):
    """A caller-pinned authority public-key set is unavailable or invalid."""


class AuthorityKeySetPinMismatch(AuthorityKeySetError):
    """The key-set bytes do not match the caller's out-of-band digest."""


def load_control_plane_authority_key_set(
    path: str | Path, *, expected_digest: str
) -> tuple[dict[str, bytes], str]:
    """Load a bounded strict-schema key set and check its out-of-band digest."""
    try:
        if type(expected_digest) is not str or _DIGEST.fullmatch(expected_digest) is None:
            raise ValueError
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise ValueError
        with source.open("rb") as stream:
            raw = stream.read(MAX_AUTHORITY_KEY_SET_BYTES + 1)
        if not raw or len(raw) > MAX_AUTHORITY_KEY_SET_BYTES:
            raise ValueError
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if digest != expected_digest:
            raise AuthorityKeySetPinMismatch

        def reject_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result

        record = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        if (
            type(record) is not dict
            or set(record) != {"schema", "keys"}
            or record.get("schema") != "control-plane-authority-key-set/v1"
            or type(record.get("keys")) is not dict
            or not 1 <= len(record["keys"]) <= 32
        ):
            raise ValueError
        keys = record["keys"]
        if any(
            type(key_id) is not str
            or _KEY_ID.fullmatch(key_id) is None
            or type(value) is not str
            or _PUBLIC_KEY.fullmatch(value) is None
            for key_id, value in keys.items()
        ):
            raise ValueError
        return {key_id: bytes.fromhex(value) for key_id, value in keys.items()}, digest
    except AuthorityKeySetPinMismatch:
        raise AuthorityKeySetPinMismatch(
            "authority key set: caller-pinned digest mismatch"
        ) from None
    except Exception:
        raise AuthorityKeySetError(
            "authority key set: caller-pinned public keys are unavailable"
        ) from None
