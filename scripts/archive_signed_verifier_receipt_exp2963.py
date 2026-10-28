#!/usr/bin/env python3
"""Archive the exact future EXP-2962 receipt as a detached stage candidate."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import archive_signed_verifier_receipt_exp2407 as core  # noqa: E402


EVIDENCE_DIR = Path("/Volumes/AlexDATA/Agent00X-local-evidence")
STAGE_DIGEST = "sha256:ac1c28ebeb908d971baad950a83ce60ed795435cedfc796c198a590522189a1b"
ARTIFACT_DIGEST = "sha256:146abcc35d054952a8ef941b9c40599e2ae1322a36b56294ec1753fe66d40e48"
PROCESS_ID = "process-exp-2915-local-001"
REQUEST_DIGEST = "sha256:86bdaebfcad6ed61bfaaa44fc69f5dcc6606d958f8c387b5bfeb8ff47d664613"
SOURCE_DATABASE = EVIDENCE_DIR / "EXP-2915-stage.sqlite3"
RECEIPT_PATH = EVIDENCE_DIR / "signed-verifier-evidence-exp2962.json"
KEY_SET_PATH = EVIDENCE_DIR / "control-plane-authority-keys-exp1977.json"
KEY_SET_DIGEST = "sha256:34b6a92168c02d8f37325b060545740d7e2061d991604daeac04b3b3df144ffc"
ARCHIVE_DATABASE = EVIDENCE_DIR / "EXP-2963-stage-archive.sqlite3"
ATTEMPT_PATH = EVIDENCE_DIR / "EXP-2963-stage-archive.attempted"
GATE = "RUN EXP-2963 ONCE"


def configure() -> None:
    core.STAGE_DIGEST = STAGE_DIGEST
    core.ARTIFACT_DIGEST = ARTIFACT_DIGEST
    core.PROCESS_ID = PROCESS_ID
    core.REQUEST_DIGEST = REQUEST_DIGEST
    core.SOURCE_DATABASE = SOURCE_DATABASE
    core.RECEIPT_PATH = RECEIPT_PATH
    core.KEY_SET_PATH = KEY_SET_PATH
    core.KEY_SET_DIGEST = KEY_SET_DIGEST
    core.ARCHIVE_DATABASE = ARCHIVE_DATABASE
    core.ATTEMPT_PATH = ATTEMPT_PATH
    core.GATE = GATE


def main() -> int:
    configure()
    result = core.main()
    if result == 0:
        print("EXP2963_EXP2915_RECEIPT_ARCHIVED")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
