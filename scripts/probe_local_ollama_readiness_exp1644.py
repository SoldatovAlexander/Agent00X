#!/usr/bin/env python3
"""One TTY-gated, metadata-only readiness check for the pinned local Ollama."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.r5_local_model_preflight import (  # noqa: E402
    R5LocalModelPreflightError,
    R5LocalOllamaMetadataPreflight,
)


EXPECTED_MODEL_DIGEST = (
    "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364"
)
CONFIRMATION_PHRASE = "RUN EXP-1644 ONCE"
PreflightFactory = Callable[[], R5LocalOllamaMetadataPreflight]


def run_once(
    *,
    stdin=None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    preflight_factory: PreflightFactory = R5LocalOllamaMetadataPreflight,
) -> int:
    """Make one fixed two-GET metadata check; never call the model endpoint."""

    try:
        interactive = stdin is not None and stdin.isatty() is True
    except Exception:
        interactive = False
    if not interactive:
        stdout.write("OLLAMA_PROBE_REQUIRES_TTY\n")
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
    try:
        preflight = preflight_factory()
        metadata = preflight.inspect(expected_model_digest=EXPECTED_MODEL_DIGEST)
        if (
            type(metadata.version) is not str
            or type(metadata.model_digest) is not str
            or metadata.model_digest != EXPECTED_MODEL_DIGEST
        ):
            raise R5LocalModelPreflightError("model_digest_mismatch")
    except R5LocalModelPreflightError as exc:
        stdout.write(f"OLLAMA_PREFLIGHT_FAILED|reason={exc.reason_code}\n")
        return 10
    except Exception:
        stdout.write("OLLAMA_PREFLIGHT_FAILED|reason=metadata_request_failed\n")
        return 10
    stdout.write("OLLAMA_PREFLIGHT_MATCHED\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_once(stdin=sys.stdin))
