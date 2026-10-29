#!/usr/bin/env python3
"""Run one fresh credential-free local Worker attempt for EXP-3087."""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    print("EXP3087_PYTHON_VERSION_REJECTED", file=sys.stderr)
    raise SystemExit(2)

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_pinned_deepseek_worker_exp1893 import run_profile  # noqa: E402


CARD_ID = "EXP-3087"
CONFIRMATION_PHRASE = "RUN EXP-3087 ONCE"
PROCESS_ID = "process-exp-3087-local-001"
TASK_ID = "task-exp-3087-local-001"
AUTHORIZATION_EXPIRES_AT = datetime(2026, 10, 29, 19, 59, tzinfo=timezone.utc)
EVIDENCE_DIR = Path("/Volumes/AlexDATA/Agent00X-local-evidence")
RUNTIME_METRICS_PATH = EVIDENCE_DIR / "EXP-3087-runtime.json"
STAGE_DATABASE = str(EVIDENCE_DIR / "EXP-3087-stage.sqlite3")
OBSERVATION_DATABASE = str(EVIDENCE_DIR / "EXP-3087-observer.sqlite3")
OBSERVER_ARTIFACT_DATABASE = str(EVIDENCE_DIR / "EXP-3087-artifacts.sqlite3")
PINNED_ARGUMENTS = [
    "--authorization-card-id", CARD_ID,
    "--model-backend", "local-ollama",
    "--verifier-backend", "pinned-docker",
    "--worker-backend", "restricted-container",
    "--credential-source", "not-applicable",
    "--observation-database", OBSERVATION_DATABASE,
    "--observer-artifact-database", OBSERVER_ARTIFACT_DATABASE,
    STAGE_DATABASE,
]


def main(
    argv: list[str] | None = None,
    *,
    now: datetime | None = None,
) -> int:
    requested = sys.argv[1:] if argv is None else argv
    if requested:
        print("EXP3087_ARGUMENTS_REJECTED", file=sys.stderr)
        return 2
    return run_profile(
        CARD_ID,
        CONFIRMATION_PHRASE,
        PROCESS_ID,
        TASK_ID,
        AUTHORIZATION_EXPIRES_AT,
        PINNED_ARGUMENTS,
        now=now,
        runtime_metrics_path=RUNTIME_METRICS_PATH,
    )


if __name__ == "__main__":
    raise SystemExit(main())
