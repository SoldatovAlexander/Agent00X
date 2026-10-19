#!/usr/bin/env python3
"""Sanitized exact-pin inspect through the Worker CLI's ambient Docker context."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID  # noqa: E402
from app_contracts.verifier_image_pin import VERIFIER_RUNTIME_IMAGE_ID  # noqa: E402
from scripts.audit_portable_verifier_image_exp1350 import (  # noqa: E402
    _bounded_process_output,
)


MAX_OUTPUT_BYTES = 512
TIMEOUT_SECONDS = 10
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _classify(result: object, expected_id: str) -> str:
    if getattr(result, "returncode", None) != 0:
        return "UNAVAILABLE"
    stdout = getattr(result, "stdout", None)
    if type(stdout) is not bytes:
        return "UNCLASSIFIED"
    try:
        observed = stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        return "UNCLASSIFIED"
    if _IMAGE_ID.fullmatch(observed) is None:
        return "UNCLASSIFIED"
    return "MATCH" if observed == expected_id else "MISMATCH"


def run_once(
    *,
    runner: Callable[..., object] = _bounded_process_output,
    which: Callable[[str], str | None] = shutil.which,
    output: TextIO = sys.stdout,
) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
    docker = which("docker")
    if type(docker) is not str or not docker:
        output.write("EXP1596_IMAGES|CLI_UNAVAILABLE\n")
        return 11

    facts: list[str] = []
    for label, image_id in (
        ("TARGET", TARGET_RUNTIME_IMAGE_ID),
        ("VERIFIER", VERIFIER_RUNTIME_IMAGE_ID),
    ):
        command = (docker, "image", "inspect", "--format={{.Id}}", image_id)
        try:
            result = runner(
                command,
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=TIMEOUT_SECONDS,
            )
            status = _classify(result, image_id)
        except Exception:
            status = "UNAVAILABLE"
        facts.append(f"{label}_{status}")

    output.write("EXP1596_IMAGES|" + "|".join(facts) + "\n")
    return 0 if facts == ["TARGET_MATCH", "VERIFIER_MATCH"] else 12


if __name__ == "__main__":
    raise SystemExit(run_once())
