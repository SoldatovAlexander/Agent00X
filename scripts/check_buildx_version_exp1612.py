#!/usr/bin/env python3
"""Bounded read-only Buildx CLI version check under isolated config (EXP-1612)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_portable_verifier_image_exp1350 import (  # noqa: E402
    OutputLimitExceeded,
    _bounded_process_output,
)


DOCKER = "/usr/local/bin/docker"
MAX_OUTPUT_BYTES = 4096
TIMEOUT_SECONDS = 10
_VERSION_LINE = re.compile(
    rb"\A(?:github\.com/docker/buildx\s+)?v([0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?)\s*\Z"
)


def _version(data: bytes) -> str | None:
    if len(data) > MAX_OUTPUT_BYTES:
        return None
    match = _VERSION_LINE.fullmatch(data.strip())
    if match is None:
        return None
    return match.group(1).decode("ascii")


def run_once(*, runner: Callable[..., subprocess.CompletedProcess[bytes]] = _bounded_process_output,
             output: TextIO = sys.stdout, temporary_directory=tempfile.TemporaryDirectory) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
    command = (DOCKER, "buildx", "version")
    try:
        with temporary_directory(prefix="agent00x-exp1612-docker-config-") as config_dir:
            env = {
                "DOCKER_CONFIG": str(config_dir),
                "LANG": "C",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            }
            result = runner(
                command,
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=TIMEOUT_SECONDS,
                env=env,
            )
    except OutputLimitExceeded:
        output.write("BUILDX_VERSION_OUTPUT_LIMIT\n")
        return 11
    except subprocess.TimeoutExpired:
        output.write("BUILDX_VERSION_TIMEOUT\n")
        return 12
    except Exception:
        output.write("BUILDX_VERSION_INCONCLUSIVE\n")
        return 13
    if type(result.returncode) is not int or result.returncode != 0:
        output.write("BUILDX_VERSION_FAILED\n")
        return 14
    version = _version(result.stdout if type(result.stdout) is bytes else b"")
    if version is None:
        output.write("BUILDX_VERSION_UNCLASSIFIED\n")
        return 15
    output.write(f"BUILDX_VERSION|version=v{version}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_once())
