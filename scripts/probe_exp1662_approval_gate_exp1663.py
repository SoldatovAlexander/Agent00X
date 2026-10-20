#!/usr/bin/env python3
"""TTY-gated, redacted approval-eligibility check for the EXP-1662 stage."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.approval_request import main as approval_request_main  # noqa: E402

CONFIRMATION_PHRASE = "RUN EXP-1663 ONCE"
STAGE_PATH = ROOT / "EXP-1662-stage.sqlite3"
STAGED_CHANGE_DIGEST = (
    "sha256:b0b71bdfe8eff7df1e721cceabcc86c4c4e4a833d859e70ab0499197184cc008"
)
FIXED_ENVIRONMENT = {
    "AGENT_GITHUB_TEST_REPOSITORY": "SoldatovAlexander/brainbooster_full_v11",
    "AGENT_GITHUB_INSTALLATION_ID": "1",
    "AGENT_GITHUB_REPOSITORY_ID": "1",
}
REFUSAL_MARKERS = {
    "approval request: verifier provenance trust is unavailable":
        "APPROVAL_REFUSED|reason=verifier-provenance-trust-unavailable",
    "approval request: stage database is unavailable":
        "APPROVAL_REFUSED|reason=stage-database-unavailable",
    "approval request: stage database is not quiescent":
        "APPROVAL_REFUSED|reason=stage-database-not-quiescent",
    "approval request: verified stage or target is invalid":
        "APPROVAL_REFUSED|reason=verified-stage-or-target-invalid",
    "approval request: target metadata is invalid":
        "APPROVAL_REFUSED|reason=target-metadata-invalid",
}
CliMain = Callable[..., int]


def _argv() -> list[str]:
    return [
        str(STAGE_PATH),
        STAGED_CHANGE_DIGEST,
        "agent/exp-1663",
        "master",
        "approval-exp-1663",
        "owner-local-test",
        "policy-exp-1663",
    ]


def _classify(code: int, captured_stdout: str, captured_stderr: str) -> str:
    if code == 2 and captured_stdout == "":
        marker = REFUSAL_MARKERS.get(captured_stderr.strip())
        return marker if marker is not None else "APPROVAL_RESULT_UNCLASSIFIED"
    if code == 0 and captured_stdout:
        try:
            request = json.loads(captured_stdout)
        except Exception:
            return "APPROVAL_RESULT_UNCLASSIFIED"
        if (
            type(request) is dict
            and request.get("schema") == "approval-request/v1"
            and request.get("status") == "unsigned"
            and request.get("approval") == "not_created"
            and request.get("provider_write") is False
            and type(request.get("stage")) is dict
            and request["stage"].get("staged_change_digest")
            == STAGED_CHANGE_DIGEST
        ):
            return "UNSIGNED_REQUEST_IN_MEMORY"
        return "APPROVAL_RESULT_UNCLASSIFIED"
    if code == 0 and captured_stdout == "":
        return "CLI_EXIT_ZERO_WITH_EMPTY_OUTPUT"
    return "APPROVAL_RESULT_UNCLASSIFIED"


def run_once(
    *,
    stdin=None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    cli_main: CliMain = approval_request_main,
) -> int:
    """Run the approval CLI once, retaining only fixed status markers."""
    try:
        is_tty = stdin is not None and stdin.isatty() is True
    except Exception:
        is_tty = False
    if not is_tty:
        stdout.write("APPROVAL_PROBE_REQUIRES_TTY\n")
        return 2
    stderr.write(f"Type {CONFIRMATION_PHRASE} to continue: ")
    stderr.flush()
    try:
        phrase = stdin.readline().rstrip("\r\n")
    except Exception:
        phrase = ""
    if phrase != CONFIRMATION_PHRASE:
        stdout.write("RUN_NOT_CONFIRMED\n")
        return 3

    captured_stdout, captured_stderr = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
            code = cli_main(
                _argv(),
                environ=FIXED_ENVIRONMENT,
                now=datetime(2026, 10, 20, tzinfo=timezone.utc),
            )
        marker = _classify(code, captured_stdout.getvalue(), captured_stderr.getvalue())
    except Exception:
        marker = "APPROVAL_RESULT_UNCLASSIFIED"
    stdout.write(marker + "\n")
    return 0 if marker != "APPROVAL_RESULT_UNCLASSIFIED" else 10


if __name__ == "__main__":
    raise SystemExit(run_once(stdin=sys.stdin))
