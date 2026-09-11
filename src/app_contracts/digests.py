"""Canonical digest helpers used to bind approvals and actions to artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> bytes:
    """Return the MVP canonical JSON representation.

    M0 uses sorted UTF-8 JSON without insignificant whitespace. A standards-based
    canonicalization profile can replace this function only through a versioned
    contract change. Unencodable values fail with a deterministic error that
    carries no key or value representation.
    """

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical JSON is not encodable") from exc


def sha256_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()

