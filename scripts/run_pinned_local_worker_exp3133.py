#!/usr/bin/env python3
"""Run one credential-free local Worker slice with a phase-duration sidecar."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sqlite3
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_pinned_local_worker_exp3124 as base  # noqa: E402
from app_contracts.execution_metrics import (  # noqa: E402
    read_runtime_metrics,
    validate_metrics_destination,
    write_runtime_metrics,
)
from app_contracts.github_http_transport import (  # noqa: E402
    GitHubAnonymousSnapshotTransport,
)


CARD_ID = "EXP-3133"
GATE = "RUN EXP-3133 ONCE"
PROCESS_ID = "process-exp-3133-local-001"
TASK_ID = "task-exp-3133-local-001"
EXPIRES_AT = datetime(2026, 10, 29, 19, 59, tzinfo=timezone.utc)
EVIDENCE_DIR = Path("/Volumes/AlexDATA/Agent00X-local-evidence")
STAGE_DATABASE = EVIDENCE_DIR / "EXP-3133-stage.sqlite3"
OBSERVER_DATABASE = EVIDENCE_DIR / "EXP-3133-observer.sqlite3"
ARTIFACT_DATABASE = EVIDENCE_DIR / "EXP-3133-artifacts.sqlite3"
METRICS_PATH = EVIDENCE_DIR / "EXP-3133-runtime-metrics.json"
ATTEMPT_DIRECTORY = (
    Path.home() / "Library" / "Application Support" / "Agent00X" / "worker-attempts"
)
WRAPPER_ATTEMPT = ATTEMPT_DIRECTORY / "exp-3133-launch.attempted"
CLI_ATTEMPT = ATTEMPT_DIRECTORY / "exp-3133.attempted"


def _port_is_open(timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", base.OLLAMA_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def _pin_profile() -> None:
    base.CARD_ID = CARD_ID
    base.GATE = GATE
    base.PROCESS_ID = PROCESS_ID
    base.TASK_ID = TASK_ID
    base.AUTHORIZATION_EXPIRES_AT = EXPIRES_AT
    base.EVIDENCE_DIR = EVIDENCE_DIR
    base.STAGE_DATABASE = STAGE_DATABASE
    base.OBSERVER_DATABASE = OBSERVER_DATABASE
    base.ARTIFACT_DATABASE = ARTIFACT_DATABASE
    base.WRAPPER_ATTEMPT = WRAPPER_ATTEMPT
    base.CLI_ATTEMPT = CLI_ATTEMPT
    base.PINNED_ARGUMENTS = [
        "--authorization-card-id", CARD_ID,
        "--model-backend", "local-ollama",
        "--verifier-backend", "pinned-docker",
        "--worker-backend", "restricted-container",
        "--credential-source", "not-applicable",
        "--observation-database", str(OBSERVER_DATABASE),
        "--observer-artifact-database", str(ARTIFACT_DATABASE),
        str(STAGE_DATABASE),
    ]


def _observer_run_id() -> str:
    if OBSERVER_DATABASE.is_symlink() or not OBSERVER_DATABASE.is_file():
        raise ValueError
    connection = sqlite3.connect(
        OBSERVER_DATABASE.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1
    )
    try:
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError
        rows = connection.execute(
            "SELECT event_json FROM observation_events ORDER BY cursor"
        ).fetchall()
        run_ids = set()
        for (raw,) in rows:
            event = json.loads(raw)
            if type(event) is not dict or event.get("process_id") != PROCESS_ID:
                raise ValueError
            run_id = event.get("run_id")
            if type(run_id) is not str:
                raise ValueError
            run_ids.add(run_id)
        if len(run_ids) != 1:
            raise ValueError
        return next(iter(run_ids))
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    if (sys.argv[1:] if argv is None else argv):
        print("EXP3133_ARGUMENTS_REJECTED")
        return 2
    if datetime.now(timezone.utc) >= EXPIRES_AT:
        print("EXP3133_AUTHORIZATION_EXPIRED")
        return 2
    if _port_is_open():
        print("EXP3133_OLLAMA_ALREADY_ACTIVE")
        return 2
    if any(path.exists() or path.is_symlink() for path in (
        STAGE_DATABASE, OBSERVER_DATABASE, ARTIFACT_DATABASE, METRICS_PATH,
        WRAPPER_ATTEMPT, CLI_ATTEMPT,
    )):
        print("EXP3133_EVIDENCE_OR_ATTEMPT_CONFLICT")
        return 2
    if not EVIDENCE_DIR.is_dir() or EVIDENCE_DIR.is_symlink():
        print("EXP3133_EVIDENCE_DIRECTORY_UNAVAILABLE")
        return 2
    try:
        validate_metrics_destination(METRICS_PATH)
    except Exception:
        print("EXP3133_METRICS_DESTINATION_REJECTED")
        return 2
    if not sys.stdin.isatty() or input(f"Type {GATE} to continue: ") != GATE:
        print("EXP3133_RUN_NOT_CONFIRMED")
        return 3
    try:
        readiness = GitHubAnonymousSnapshotTransport().read_rate_limit()
    except Exception:
        print("EXP3133_GITHUB_QUOTA_PREFLIGHT_FAILED")
        return 2
    if readiness.status != 200 or readiness.remaining < 36:
        print("EXP3133_GITHUB_QUOTA_INSUFFICIENT")
        return 2

    _pin_profile()
    worker_cli = base.worker_cli
    original_main = worker_cli.main
    metrics_written: list[bool] = []

    def measured_runtime_runner(**runtime_options):
        started = time.monotonic_ns()
        outcome = "returned"
        try:
            return worker_cli.run_remote_snapshot_with_runtime(**runtime_options)
        except BaseException:
            outcome = "raised"
            raise
        finally:
            finished = time.monotonic_ns()
            elapsed = (finished - started) // 1_000_000 if finished >= started else -1
            execution_worker = runtime_options.get("execution_worker")
            try:
                reference = execution_worker.observer_reference()
                write_runtime_metrics(
                    METRICS_PATH,
                    {
                        "schema": "agent00x-runtime-metrics/v1",
                        "scope": "run_remote_snapshot_with_runtime",
                        "process_id": runtime_options.get("process_id"),
                        "run_id": reference.get("run_id"),
                        "duration_ms": elapsed,
                        "outcome": outcome,
                        "trust": "local_unattested",
                    },
                )
                metrics_written.append(True)
            except Exception:
                metrics_written.append(False)

    def measured_cli_main(arguments, *, input_fn):
        return original_main(
            arguments,
            input_fn=input_fn,
            runtime_runner=measured_runtime_runner,
        )

    worker_cli.main = measured_cli_main
    try:
        result = base.main([])
    finally:
        worker_cli.main = original_main

    if not metrics_written or metrics_written[-1] is not True:
        print("EXP3133_METRICS_WRITE_UNAVAILABLE")
        return 2
    try:
        if stat.S_IMODE(METRICS_PATH.stat().st_mode) != 0o600:
            raise ValueError
        run_id = _observer_run_id()
        summary = read_runtime_metrics(
            METRICS_PATH,
            expected_process_id=PROCESS_ID,
            expected_run_id=run_id,
        )
        if summary["runtime_phase_status"] != "available":
            raise ValueError
    except Exception:
        print("EXP3133_METRICS_BINDING_REJECTED")
        return 2
    print(
        "EXP3133_RUNTIME_METRICS_CONFIRMED"
        f"|duration_ms={summary['runtime_phase_duration_ms']}"
        "|scope=run_remote_snapshot_with_runtime"
        f"|outcome={summary['runtime_phase_outcome']}|trust=local_unattested"
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
