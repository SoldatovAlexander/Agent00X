#!/usr/bin/env python3
"""One exact read-only Docker image-tag presence query (EXP-1581)."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from typing import TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_portable_verifier_image_exp1350 import (  # noqa: E402
    OutputLimitExceeded,
    _bounded_process_output,
)


DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
IMAGE_TAG = "agent00x-verifier:exp-1580"
EXPECTED_LINE = (IMAGE_TAG + "\n").encode("ascii")


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def run_once(*, runner=_bounded_process_output, output: TextIO = sys.stdout) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        return _emit(output, "OPT_IN_REQUIRED", 10)
    try:
        with tempfile.TemporaryDirectory(prefix="agent00x-exp1581-docker-config-") as config:
            result = runner(
                (
                    DOCKER,
                    "--host=" + DOCKER_HOST,
                    "image",
                    "ls",
                    "--filter",
                    "reference=" + IMAGE_TAG,
                    "--format",
                    "{{.Repository}}:{{.Tag}}",
                ),
                max_bytes=256,
                timeout=15,
                env={
                    "DOCKER_CONFIG": config,
                    "DOCKER_HOST": DOCKER_HOST,
                    "LANG": "C",
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                },
            )
    except (OSError, OutputLimitExceeded, TimeoutError):
        return _emit(output, "EXP1580_TAG_UNCLASSIFIED", 11)
    except Exception:
        return _emit(output, "EXP1580_TAG_UNCLASSIFIED", 11)
    if result.returncode != 0:
        return _emit(output, "EXP1580_TAG_UNCLASSIFIED", 11)
    if result.stdout == b"":
        return _emit(output, "EXP1580_TAG_ABSENT", 0)
    if result.stdout == EXPECTED_LINE:
        return _emit(output, "EXP1580_TAG_PRESENT", 0)
    return _emit(output, "EXP1580_TAG_UNCLASSIFIED", 11)


if __name__ == "__main__":
    raise SystemExit(run_once())
