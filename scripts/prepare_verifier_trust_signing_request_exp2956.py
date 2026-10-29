#!/usr/bin/env python3
"""Prepare the EXP-2975 decision request bound to recorded EXP-2974 enrollment."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import prepare_verifier_trust_signing_request_exp2271 as base  # noqa: E402
from scripts import record_verifier_trust_signature_exp2196 as recorder  # noqa: E402


EVIDENCE_DIR = Path("/Volumes/AlexDATA/Agent00X-local-evidence")
BOOTSTRAP_PATH = EVIDENCE_DIR / "verifier-bootstrap-exp2973.json"
ENROLLMENT_ID = "agent00x-enrollment-exp2974"
DECISION_ID = "agent00x-host-decision-exp2975"


def build_host_decision_request(*, now=None) -> bytes:
    """Build public request bytes in memory; never sign, save or send them."""

    names = (
        "BOOTSTRAP_PATH",
        "ENROLLMENT_ID",
        "DECISION_ID",
        "ENROLLMENT_REPORT_EXP2271",
        "ENROLLMENT_ARTIFACT_EXP2271",
    )
    original = {name: getattr(base, name) for name in names}
    try:
        base.BOOTSTRAP_PATH = BOOTSTRAP_PATH
        base.ENROLLMENT_ID = ENROLLMENT_ID
        base.DECISION_ID = DECISION_ID
        base.ENROLLMENT_REPORT_EXP2271 = recorder.ENROLLMENT_REPORT_EXP2955
        base.ENROLLMENT_ARTIFACT_EXP2271 = recorder.ENROLLMENT_ARTIFACT_EXP2955
        return base.build_signing_request("host-decision", now=now)
    finally:
        for name, value in original.items():
            setattr(base, name, value)


if __name__ == "__main__":
    try:
        sys.stdout.buffer.write(build_host_decision_request())
    except Exception:
        print("EXP2956_SIGNING_INPUT_REJECTED", file=sys.stderr)
        raise SystemExit(2)
