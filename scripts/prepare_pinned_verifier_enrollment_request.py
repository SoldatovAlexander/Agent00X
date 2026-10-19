#!/usr/bin/env python3
"""Bind an untrusted verifier-enrollment signing request to a pinned bootstrap."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys
from typing import BinaryIO, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.verifier_bootstrap_preflight import (  # noqa: E402
    MAX_BOOTSTRAP_BYTES,
    parse_pinned_public_verifier_enrollment_bootstrap,
)
from app_contracts.verifier_image_pin import (  # noqa: E402
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from prepare_verifier_trust_signing_message import prepare_request  # noqa: E402


MAX_BINDINGS_BYTES = 4096
MAX_INPUT_BYTES = MAX_BOOTSTRAP_BYTES + MAX_BINDINGS_BYTES + 1
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BINDING_FIELDS = frozenset(
    {
        "enrollment_id",
        "authority_key_id",
        "worker_host_id",
        "verifier_host_id",
        "host_separation_evidence_digest",
        "issued_at",
        "expires_at",
    }
)
_ERROR_MARKER = "PINNED_ENROLLMENT_REQUEST_REJECTED\n"


class _SilentArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError


def _canonical_record(raw: bytes) -> dict[str, object]:
    value = json.loads(
        raw.decode("ascii", errors="strict"),
        object_pairs_hook=_unique_pairs,
        parse_constant=_reject_constant,
    )
    if (
        type(value) is not dict
        or json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        != raw
    ):
        raise ValueError
    return value


def prepare_pinned_enrollment_request(
    raw_input: object, *, expected_bootstrap_sha256: object
) -> bytes:
    """Return one signing request; the bootstrap digest never establishes trust."""

    try:
        if (
            type(raw_input) is not bytes
            or not 2 <= len(raw_input) <= MAX_INPUT_BYTES
            or type(expected_bootstrap_sha256) is not str
            or _DIGEST.fullmatch(expected_bootstrap_sha256) is None
        ):
            raise ValueError
        first, separator, remainder = raw_input.partition(b"\n")
        second, trailing_separator, extra = remainder.partition(b"\n")
        if (
            not separator
            or not trailing_separator
            or extra
            or not first
            or not second
            or len(first) + 1 > MAX_BOOTSTRAP_BYTES
            or len(second) + 1 > MAX_BINDINGS_BYTES
        ):
            raise ValueError
        bootstrap_raw = first + b"\n"
        bootstrap_digest = "sha256:" + hashlib.sha256(bootstrap_raw).hexdigest()
        if not hmac.compare_digest(bootstrap_digest, expected_bootstrap_sha256):
            raise ValueError
        bootstrap = parse_pinned_public_verifier_enrollment_bootstrap(
            bootstrap_raw, expected_sha256=expected_bootstrap_sha256
        )
        bindings = _canonical_record(second)
        if set(bindings) != _BINDING_FIELDS:
            raise ValueError
        signing_fields = {
            **bindings,
            "endpoint_url": bootstrap.endpoint_url,
            "verifier_id": (
                f"docker-image:{VERIFIER_RUNTIME_IMAGE_ID}"
                f"/code:{VERIFIER_RUNTIME_CODE_DIGEST}"
            ),
            "verifier_profile_digest": bootstrap.verifier_profile_digest,
            "verifier_key_id": bootstrap.verifier_key_id,
            "verifier_public_key": bootstrap.verifier_public_key.hex(),
        }
        return prepare_request(
            "enrollment",
            json.dumps(
                signing_fields,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii"),
        )
    except Exception:
        raise ValueError("pinned verifier enrollment request rejected") from None


def main(
    argv: object | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    input_stream = sys.stdin.buffer if stdin is None else stdin
    output_stream = sys.stdout if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr
    parser = _SilentArgumentParser(description=__doc__)
    parser.add_argument(
        "--expected-bootstrap-sha256",
        required=True,
        help="caller-supplied exact digest of the first stdin record",
    )
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
        raw = input_stream.read(MAX_INPUT_BYTES + 1)
        output = prepare_pinned_enrollment_request(
            raw, expected_bootstrap_sha256=args.expected_bootstrap_sha256
        )
        output_stream.write(output.decode("ascii"))
        return 0
    except Exception:
        error_stream.write(_ERROR_MARKER)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
