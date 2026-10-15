#!/usr/bin/env python3
"""Review and sign one exact-stage approval using an injected seed."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Mapping, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.approval_request import repository_target_binding_from_metadata
from app_contracts.approval_signer import (
    ApprovalSigningError,
    load_verifier_authority_keys,
    sign_approval_request,
)
from app_contracts.credential_source import ProcessEnvironmentCredentialSource
from app_contracts.signer_key_source import Ed25519SeedCredentialSource


APPROVER_SEED_ENV_NAME = "AGENT_APPROVER_SIGNING_SEED"


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    input_fn=input,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    now: datetime | None = None,
) -> int:
    import sys

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    parser = argparse.ArgumentParser(
        description=(
            "Review and sign one exact saved-stage approval; no provider effect. "
            "The seed must be injected into this process by a trusted manager."
        )
    )
    parser.add_argument("database", help="existing quiescent SQLite stage database")
    parser.add_argument("staged_change_digest", help="exact sha256 staged digest")
    parser.add_argument("request", help="approval-request/v1 JSON")
    parser.add_argument("--verifier-authority-key-set")
    parser.add_argument("--verifier-authority-key-set-digest")
    args = parser.parse_args(argv)
    metadata = os.environ if environ is None else environ
    try:
        binding = repository_target_binding_from_metadata(metadata)
        verifier_keys = load_verifier_authority_keys(
            args.verifier_authority_key_set,
            args.verifier_authority_key_set_digest,
        )
        source = Ed25519SeedCredentialSource(
            ProcessEnvironmentCredentialSource(metadata, APPROVER_SEED_ENV_NAME)
        )

        def confirm(review: dict, phrase: str) -> str:
            errors.write("Review this exact staged action before signing:\n")
            errors.write(
                json.dumps(
                    review,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    indent=2,
                )
            )
            errors.write("\n")
            errors.write(f"Type {phrase} to continue: ")
            errors.flush()
            return input_fn()

        signed = sign_approval_request(
            args.database,
            args.staged_change_digest,
            args.request,
            binding,
            source,
            confirm,
            clock=(lambda: now) if now is not None else (lambda: datetime.now(timezone.utc)),
            trusted_verifier_authority_keys=verifier_keys,
        )
    except (ApprovalSigningError, ValueError) as exc:
        errors.write(f"{exc}\n")
        return 2
    except Exception:
        errors.write("approval signer: operation unavailable\n")
        return 2
    output.write(
        json.dumps(signed, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
