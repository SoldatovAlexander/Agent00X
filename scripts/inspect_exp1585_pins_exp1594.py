#!/usr/bin/env python3
"""Classify only the two immutable image pins required by EXP-1585."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_portable_verifier_image_exp1350 import (  # noqa: E402
    _bounded_process_output,
)


DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
TARGET_IMAGE_ID = "sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187"
VERIFIER_IMAGE_ID = "sha256:59468457bb9a2ec5e6857e3a413df1e480481d832280027ecfd1f227517bdaa2"
MAX_OUTPUT_BYTES = 512
TIMEOUT_SECONDS = 15
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PLATFORM = re.compile(r"[a-z0-9_./-]{1,64}\Z")


def _env(config_dir: str) -> dict[str, str]:
    return {
        "DOCKER_CONFIG": config_dir,
        "DOCKER_HOST": DOCKER_HOST,
        "LANG": "C",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }


def _classify(result, expected_id: str) -> str:
    if getattr(result, "returncode", None) != 0:
        return "UNAVAILABLE"
    data = getattr(result, "stdout", None)
    if type(data) is not bytes:
        return "UNCLASSIFIED"
    try:
        image_id, os_name, architecture = data.decode("ascii").rstrip("\n").split("|")
    except (UnicodeDecodeError, ValueError):
        return "UNCLASSIFIED"
    if (
        _IMAGE_ID.fullmatch(image_id) is None
        or _PLATFORM.fullmatch(os_name) is None
        or _PLATFORM.fullmatch(architecture) is None
    ):
        return "UNCLASSIFIED"
    if image_id == expected_id and os_name == "linux" and architecture == "amd64":
        return "MATCH"
    return "MISMATCH"


def run_once(*, runner=_bounded_process_output, output: TextIO = sys.stdout,
             temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
    with temporary_directory(prefix="agent00x-exp1594-docker-config-") as config_dir:
        env = _env(config_dir)
        facts: list[str] = []
        for label, image_id in (
            ("TARGET", TARGET_IMAGE_ID),
            ("VERIFIER", VERIFIER_IMAGE_ID),
        ):
            command = (
                DOCKER,
                "--host=" + DOCKER_HOST,
                "image",
                "inspect",
                "--format",
                "{{.Id}}|{{.Os}}|{{.Architecture}}",
                image_id,
            )
            try:
                result = runner(
                    command,
                    max_bytes=MAX_OUTPUT_BYTES,
                    timeout=TIMEOUT_SECONDS,
                    env=env,
                )
                status = _classify(result, image_id)
            except Exception:
                status = "UNAVAILABLE"
            facts.append(f"{label}_{status}")
    output.write("EXP1594_IMAGES|" + "|".join(facts) + "\n")
    return 0 if facts == ["TARGET_MATCH", "VERIFIER_MATCH"] else 11


if __name__ == "__main__":
    raise SystemExit(run_once())
