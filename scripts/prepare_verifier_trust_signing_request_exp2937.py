#!/usr/bin/env python3
"""Prepare an in-memory enrollment request for the fresh EXP-2973 bootstrap."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import prepare_verifier_trust_signing_request_exp2271 as base  # noqa: E402


EVIDENCE_DIR = Path("/Volumes/AlexDATA/Agent00X-local-evidence")
BOOTSTRAP_PATH = EVIDENCE_DIR / "verifier-bootstrap-exp2973.json"
ENROLLMENT_ID = "agent00x-enrollment-exp2974"
DECISION_ID = "agent00x-host-decision-exp2975"


def build_enrollment_request(*, now=None) -> bytes:
    """Build a public request in memory; never sign or persist it."""

    original = {
        name: getattr(base, name)
        for name in ("BOOTSTRAP_PATH", "ENROLLMENT_ID", "DECISION_ID")
    }
    try:
        base.BOOTSTRAP_PATH = BOOTSTRAP_PATH
        base.ENROLLMENT_ID = ENROLLMENT_ID
        base.DECISION_ID = DECISION_ID
        return base.build_signing_request("enrollment", now=now)
    finally:
        for name, value in original.items():
            setattr(base, name, value)


if __name__ == "__main__":
    try:
        sys.stdout.buffer.write(build_enrollment_request())
    except Exception:
        print("EXP2937_SIGNING_INPUT_REJECTED", file=sys.stderr)
        raise SystemExit(2)
