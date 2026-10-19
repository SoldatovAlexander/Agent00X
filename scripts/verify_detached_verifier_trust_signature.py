#!/usr/bin/env python3
"""Assemble and verify a detached authority signature without trusting deployment.

The CLI accepts a public signing message and detached signature, then checks
the resulting artifact against a caller-pinned authority key set and explicit
deployment bindings. It never signs, contacts a service, or establishes that
the claimed deployment or host separation is real.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import BinaryIO, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.authority_key_set import load_control_plane_authority_key_set
from app_contracts.verifier_host_trust_decision import (
    MAX_DECISION_BYTES,
    assemble_signed_verifier_host_trust_decision,
    verify_verifier_host_trust_decision,
)
from app_contracts.verifier_trust_enrollment import (
    MAX_ENROLLMENT_BYTES,
    assemble_signed_verifier_trust_enrollment,
    verify_verifier_trust_enrollment,
)


MAX_INPUT_BYTES = 131_072
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{128}\Z")
_RESPONSE_FIELDS = frozenset(
    {"schema", "kind", "message_base64", "message_sha256", "signature_hex"}
)
_RESPONSE_SCHEMA = "agent00x-detached-trust-signature-response/v1"


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


def _reject_constant(_value: str) -> object:
    raise ValueError


def _parse_response(raw: object, *, kind: str) -> tuple[bytes, bytes]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_INPUT_BYTES:
        raise ValueError
    response = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )
    if (
        type(response) is not dict
        or set(response) != _RESPONSE_FIELDS
        or response.get("schema") != _RESPONSE_SCHEMA
        or response.get("kind") != kind
        or type(response.get("message_base64")) is not str
        or type(response.get("message_sha256")) is not str
        or _DIGEST.fullmatch(response["message_sha256"]) is None
        or type(response.get("signature_hex")) is not str
        or _SIGNATURE.fullmatch(response["signature_hex"]) is None
    ):
        raise ValueError
    message = base64.b64decode(response["message_base64"], validate=True)
    max_message = (
        MAX_ENROLLMENT_BYTES
        if kind == "enrollment"
        else MAX_DECISION_BYTES
    ) + 128
    if (
        not message
        or len(message) > max_message
        or "sha256:" + hashlib.sha256(message).hexdigest()
        != response["message_sha256"]
    ):
        raise ValueError
    return message, bytes.fromhex(response["signature_hex"])


def _expected_bindings(args: argparse.Namespace) -> dict[str, str]:
    names = (
        "authority_key_id",
        "endpoint_url",
        "verifier_id",
        "verifier_profile_digest",
        "verifier_key_id",
        "worker_host_id",
        "verifier_host_id",
        "host_separation_evidence_digest",
    )
    expected = {
        name: getattr(args, "expected_" + name) for name in names
    }
    if any(type(value) is not str or not value for value in expected.values()):
        raise ValueError
    return expected


def verify_response(
    args: argparse.Namespace, raw: bytes
) -> bytes:
    message, signature = _parse_response(raw, kind=args.kind)
    trusted_keys, key_set_digest = load_control_plane_authority_key_set(
        args.authority_key_set,
        expected_digest=args.authority_key_set_digest,
    )
    expected = _expected_bindings(args)
    if args.kind == "enrollment":
        if (
            args.expected_enrollment_digest is not None
            or args.enrollment_artifact is not None
        ):
            raise ValueError
        artifact = assemble_signed_verifier_trust_enrollment(message, signature)
        verified = verify_verifier_trust_enrollment(
            artifact,
            trusted_authority_keys=trusted_keys,
            expected_endpoint_url=expected["endpoint_url"],
            expected_verifier_id=expected["verifier_id"],
            expected_verifier_profile_digest=expected[
                "verifier_profile_digest"
            ],
        )
        actual = {
            "authority_key_id": verified.authority_key_id,
            "endpoint_url": verified.endpoint_url,
            "verifier_id": verified.verifier_id,
            "verifier_profile_digest": verified.verifier_profile_digest,
            "verifier_key_id": verified.verifier_key_id,
            "worker_host_id": verified.worker_host_id,
            "verifier_host_id": verified.verifier_host_id,
            "host_separation_evidence_digest": (
                verified.host_separation_evidence_digest
            ),
        }
        artifact_digest = verified.enrollment_digest
        artifact_id = verified.enrollment_id
        issued_at = verified.issued_at
        expires_at = verified.expires_at
    else:
        if type(args.expected_enrollment_digest) is not str or _DIGEST.fullmatch(
            args.expected_enrollment_digest
        ) is None or type(args.enrollment_artifact) is not str:
            raise ValueError
        enrollment_path = Path(args.enrollment_artifact)
        if enrollment_path.is_symlink() or not enrollment_path.is_file():
            raise ValueError
        with enrollment_path.open("rb") as stream:
            enrollment_artifact = stream.read(MAX_ENROLLMENT_BYTES + 1)
        if not enrollment_artifact or len(enrollment_artifact) > MAX_ENROLLMENT_BYTES:
            raise ValueError
        verified_enrollment = verify_verifier_trust_enrollment(
            enrollment_artifact,
            trusted_authority_keys=trusted_keys,
            expected_endpoint_url=expected["endpoint_url"],
            expected_verifier_id=expected["verifier_id"],
            expected_verifier_profile_digest=expected[
                "verifier_profile_digest"
            ],
        )
        enrollment_bindings = {
            "authority_key_id": verified_enrollment.authority_key_id,
            "endpoint_url": verified_enrollment.endpoint_url,
            "verifier_id": verified_enrollment.verifier_id,
            "verifier_profile_digest": verified_enrollment.verifier_profile_digest,
            "verifier_key_id": verified_enrollment.verifier_key_id,
            "worker_host_id": verified_enrollment.worker_host_id,
            "verifier_host_id": verified_enrollment.verifier_host_id,
            "host_separation_evidence_digest": (
                verified_enrollment.host_separation_evidence_digest
            ),
        }
        if (
            enrollment_bindings != expected
            or verified_enrollment.enrollment_digest
            != args.expected_enrollment_digest
            or not verified_enrollment.authority_signature_valid
            or verified_enrollment.independent_host_trust_established
        ):
            raise ValueError
        artifact = assemble_signed_verifier_host_trust_decision(
            message, signature
        )
        verified = verify_verifier_host_trust_decision(
            artifact,
            trusted_authority_keys=trusted_keys,
            expected_enrollment_digest=verified_enrollment.enrollment_digest,
            expected_endpoint_url=expected["endpoint_url"],
            expected_verifier_id=expected["verifier_id"],
            expected_verifier_profile_digest=expected[
                "verifier_profile_digest"
            ],
            expected_verifier_key_id=expected["verifier_key_id"],
            expected_worker_host_id=expected["worker_host_id"],
            expected_verifier_host_id=expected["verifier_host_id"],
            expected_host_separation_evidence_digest=expected[
                "host_separation_evidence_digest"
            ],
        )
        actual = {
            "authority_key_id": verified.authority_key_id,
            "endpoint_url": verified.endpoint_url,
            "verifier_id": verified.verifier_id,
            "verifier_profile_digest": verified.verifier_profile_digest,
            "verifier_key_id": verified.verifier_key_id,
            "worker_host_id": verified.worker_host_id,
            "verifier_host_id": verified.verifier_host_id,
            "host_separation_evidence_digest": (
                verified.host_separation_evidence_digest
            ),
        }
        if verified.enrollment_digest != verified_enrollment.enrollment_digest:
            raise ValueError
        artifact_digest = verified.decision_digest
        artifact_id = verified.decision_id
        issued_at = verified.issued_at
        expires_at = verified.expires_at
    if actual != expected:
        raise ValueError
    result = {
        "artifact_base64": base64.b64encode(artifact).decode("ascii"),
        "artifact_digest": artifact_digest,
        "artifact_id": artifact_id,
        "authority_key_id": actual["authority_key_id"],
        "authority_key_set_digest": key_set_digest,
        "authority_signature_valid": True,
        "bound_enrollment_digest": (
            verified.enrollment_digest if args.kind == "host-decision" else None
        ),
        "independent_host_trust_established": False,
        "issued_at": issued_at,
        "kind": args.kind,
        "schema": "agent00x-detached-verifier-trust-verification/v1",
        "trust": "authority_claim_verified; deployment_and_host_separation_unestablished",
        "verified_bindings": actual,
        "expires_at": expires_at,
    }
    return (
        json.dumps(
            result,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")


def _add_binding_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--authority-key-set", required=True)
    parser.add_argument("--authority-key-set-digest", required=True)
    parser.add_argument("--expected-authority-key-id", required=True)
    parser.add_argument("--expected-endpoint-url", required=True)
    parser.add_argument("--expected-verifier-id", required=True)
    parser.add_argument("--expected-verifier-profile-digest", required=True)
    parser.add_argument("--expected-verifier-key-id", required=True)
    parser.add_argument("--expected-worker-host-id", required=True)
    parser.add_argument("--expected-verifier-host-id", required=True)
    parser.add_argument("--expected-host-separation-evidence-digest", required=True)
    parser.add_argument("--expected-enrollment-digest")
    parser.add_argument("--enrollment-artifact")


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
            "Assemble and verify a detached verifier-trust signature against a "
            "caller-pinned public authority key set. This does not establish "
            "deployment or independent host trust."
        )
    )
    parser.add_argument("--kind", choices=("enrollment", "host-decision"), required=True)
    _add_binding_arguments(parser)
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
        raw = input_stream.read(MAX_INPUT_BYTES + 1)
        response = verify_response(args, raw)
        output_stream.write(response.decode("ascii"))
        return 0
    except Exception:
        error_stream.write("DETACHED_TRUST_SIGNATURE_REJECTED\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
