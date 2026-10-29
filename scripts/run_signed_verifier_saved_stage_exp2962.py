#!/usr/bin/env python3
"""One-shot signed replay of the exact saved EXP-2915 stage (DRAFT)."""

from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import prepare_staged_verifier_request_exp2217 as prepared_stage  # noqa: E402
from scripts import run_signed_verifier_saved_stage_exp2253 as core  # noqa: E402
from scripts.record_verifier_trust_signature_exp2196 import (  # noqa: E402
    ENROLLMENT_ARTIFACT_EXP2955,
    HOST_DECISION_ARTIFACT_EXP2956,
)


EVIDENCE_DIR = Path("/Volumes/AlexDATA/Agent00X-local-evidence")
CARD_ID = "EXP-2962"
GATE = "RUN EXP-2962 ONCE"
STAGE_DIGEST = "sha256:ac1c28ebeb908d971baad950a83ce60ed795435cedfc796c198a590522189a1b"
ARTIFACT_DIGEST = "sha256:146abcc35d054952a8ef941b9c40599e2ae1322a36b56294ec1753fe66d40e48"
REQUEST_DIGEST = "sha256:86bdaebfcad6ed61bfaaa44fc69f5dcc6606d958f8c387b5bfeb8ff47d664613"
PROCESS_ID = "process-exp-2915-local-001"
STAGE_DATABASE = EVIDENCE_DIR / "EXP-2915-stage.sqlite3"
ARTIFACT_DATABASE = EVIDENCE_DIR / "EXP-2915-artifacts.sqlite3"
BOOTSTRAP_PATH = EVIDENCE_DIR / "verifier-bootstrap-exp2973.json"
OUTPUT_PATH = EVIDENCE_DIR / "signed-verifier-replay-exp2962.json"
ATTEMPT_PATH = EVIDENCE_DIR / "signed-verifier-replay-exp2962.attempted"
RECEIPT_PATH = EVIDENCE_DIR / "signed-verifier-evidence-exp2962.json"
AUTHORIZATION_EXPIRES_AT = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)


def configure() -> None:
    prepared_stage.STAGE_DATABASE = STAGE_DATABASE
    prepared_stage.ARTIFACT_DATABASE = ARTIFACT_DATABASE
    prepared_stage.STAGED_CHANGE_DIGEST = STAGE_DIGEST
    core.CARD_ID = CARD_ID
    core.GATE = GATE
    core.AUTHORIZATION_EXPIRES_AT = AUTHORIZATION_EXPIRES_AT
    core.STAGE_DATABASE = STAGE_DATABASE
    core.ARTIFACT_DATABASE = ARTIFACT_DATABASE
    core.BOOTSTRAP_PATH = BOOTSTRAP_PATH
    core.ENROLLMENT_ARTIFACT = ENROLLMENT_ARTIFACT_EXP2955
    core.HOST_DECISION_ARTIFACT = HOST_DECISION_ARTIFACT_EXP2956
    core.OUTPUT_PATH = OUTPUT_PATH
    core.ATTEMPT_PATH = ATTEMPT_PATH
    core.EVIDENCE_RECEIPT_PATH = RECEIPT_PATH
    core.EXPECTED_REQUEST_DIGEST = REQUEST_DIGEST
    core.STAGED_CHANGE_DIGEST = STAGE_DIGEST


def main() -> int:
    configure()
    try:
        outcome = core.replay_once()
        if (
            outcome.get("stage_digest") != STAGE_DIGEST
            or outcome.get("stage_artifact_digest") != ARTIFACT_DIGEST
            or outcome.get("process_id") != PROCESS_ID
            or outcome.get("request_digest") != REQUEST_DIGEST
        ):
            print("EXP2962_RESULT_PIN_MISMATCH", file=sys.stderr)
            return 2
        if not RECEIPT_PATH.is_file() or RECEIPT_PATH.is_symlink():
            print("EXP2962_EVIDENCE_RECEIPT_MISSING", file=sys.stderr)
            return 2
        print(
            "EXP2962_REPLAY_RECEIPT_CONFIRMED|verdict={}|signature=valid|host_decision=bound".format(
                outcome["verdict"]
            )
        )
        return 0 if outcome["status"] == "verified" else 2
    except core.ReplayError as exc:
        print("EXP2962_" + str(exc).removeprefix("EXP2253_"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
