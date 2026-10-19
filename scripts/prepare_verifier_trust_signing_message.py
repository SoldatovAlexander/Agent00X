#!/usr/bin/env python3
"""Prepare public verifier-trust signing bytes for a detached signer.

This CLI never accepts a private key or signature. Its output is an
untrusted signing request; any later record must be verified against an
independently pinned authority key set and exact expected bindings.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import BinaryIO, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.verifier_host_trust_decision import (
    build_verifier_host_trust_decision_signing_message,
)
from app_contracts.verifier_trust_enrollment import (
    build_verifier_trust_enrollment_signing_message,
)


MAX_INPUT_BYTES = 65_536
_VERIFIER_PUBLIC_KEY = re.compile(r"[0-9a-f]{64}\Z")
_ENROLLMENT_FIELDS = frozenset(
    {
        "enrollment_id",
        "authority_key_id",
        "endpoint_url",
        "verifier_id",
        "verifier_profile_digest",
        "verifier_key_id",
        "verifier_public_key",
        "worker_host_id",
        "verifier_host_id",
        "host_separation_evidence_digest",
        "issued_at",
        "expires_at",
    }
)
_DECISION_FIELDS = frozenset(
    {
        "decision_id",
        "authority_key_id",
        "enrollment_digest",
        "endpoint_url",
        "verifier_id",
        "verifier_profile_digest",
        "verifier_key_id",
        "worker_host_id",
        "verifier_host_id",
        "host_separation_evidence_digest",
        "issued_at",
        "expires_at",
    }
)


class _SilentArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _parse_constant(_value: str) -> object:
    raise ValueError


def _parse_time(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError
    return parsed


def _prepare(kind: str, value: dict[str, object]) -> bytes:
    if kind == "enrollment":
        if set(value) != _ENROLLMENT_FIELDS:
            raise ValueError
        public_key = value["verifier_public_key"]
        if type(public_key) is not str or _VERIFIER_PUBLIC_KEY.fullmatch(public_key) is None:
            raise ValueError
        return build_verifier_trust_enrollment_signing_message(
            enrollment_id=value["enrollment_id"],
            authority_key_id=value["authority_key_id"],
            endpoint_url=value["endpoint_url"],
            verifier_id=value["verifier_id"],
            verifier_profile_digest=value["verifier_profile_digest"],
            verifier_key_id=value["verifier_key_id"],
            verifier_public_key=bytes.fromhex(public_key),
            worker_host_id=value["worker_host_id"],
            verifier_host_id=value["verifier_host_id"],
            host_separation_evidence_digest=value[
                "host_separation_evidence_digest"
            ],
            issued_at=_parse_time(value["issued_at"]),
            expires_at=_parse_time(value["expires_at"]),
        )
    if kind == "host-decision":
        if set(value) != _DECISION_FIELDS:
            raise ValueError
        return build_verifier_host_trust_decision_signing_message(
            decision_id=value["decision_id"],
            authority_key_id=value["authority_key_id"],
            enrollment_digest=value["enrollment_digest"],
            endpoint_url=value["endpoint_url"],
            verifier_id=value["verifier_id"],
            verifier_profile_digest=value["verifier_profile_digest"],
            verifier_key_id=value["verifier_key_id"],
            worker_host_id=value["worker_host_id"],
            verifier_host_id=value["verifier_host_id"],
            host_separation_evidence_digest=value[
                "host_separation_evidence_digest"
            ],
            issued_at=_parse_time(value["issued_at"]),
            expires_at=_parse_time(value["expires_at"]),
        )
    raise ValueError


def prepare_request(kind: object, raw: object) -> bytes:
    """Return one bounded public signing-request envelope."""

    try:
        if type(kind) is not str or kind not in {"enrollment", "host-decision"}:
            raise ValueError
        if type(raw) is not bytes or not raw or len(raw) > MAX_INPUT_BYTES:
            raise ValueError
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_parse_constant,
        )
        if type(value) is not dict:
            raise ValueError
        message = _prepare(kind, value)
        response = {
            "kind": kind,
            "message_base64": base64.b64encode(message).decode("ascii"),
            "message_sha256": "sha256:" + hashlib.sha256(message).hexdigest(),
            "schema": "agent00x-detached-trust-signing-request/v1",
            "trust": "unestablished",
        }
        return (
            json.dumps(
                response,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii")
    except Exception:
        raise ValueError("trust signing request rejected") from None


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
    parser = _SilentArgumentParser(
        description=(
            "Prepare public detached-signature bytes for a separately governed "
            "signer. This does not establish trust or read signing keys."
        )
    )
    parser.add_argument("--kind", choices=("enrollment", "host-decision"), required=True)
    parser.epilog = (
        "Verify any returned record with the existing validator, a caller-pinned "
        "authority key set and exact expected bindings."
    )
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
        raw = input_stream.read(MAX_INPUT_BYTES + 1)
        response = prepare_request(args.kind, raw)
        output_stream.write(response.decode("ascii"))
        return 0
    except Exception:
        error_stream.write("TRUST_SIGNING_REQUEST_REJECTED\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
