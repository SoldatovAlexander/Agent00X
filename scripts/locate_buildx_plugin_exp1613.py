#!/usr/bin/env python3
"""Check only fixed Buildx plugin paths and version one unique executable."""

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


CANDIDATES = (
    "/Users/aleksandrsoldatov/.docker/cli-plugins/docker-buildx",
    "/usr/local/lib/docker/cli-plugins/docker-buildx",
    "/usr/local/libexec/docker/cli-plugins/docker-buildx",
    "/usr/lib/docker/cli-plugins/docker-buildx",
    "/usr/libexec/docker/cli-plugins/docker-buildx",
)
MAX_OUTPUT_BYTES = 4096
TIMEOUT_SECONDS = 10
_VERSION_LINE = re.compile(
    rb"\A(?:github\.com/docker/buildx\s+)?v([0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?)\s*\Z"
)


def _version(data: bytes) -> str | None:
    match = _VERSION_LINE.fullmatch(data.strip()) if len(data) <= MAX_OUTPUT_BYTES else None
    return match.group(1).decode("ascii") if match is not None else None


def _is_executable(path: str) -> bool:
    return Path(path).is_file() and os.access(path, os.X_OK)


def run_once(*, runner: Callable[..., subprocess.CompletedProcess[bytes]] = _bounded_process_output,
             output: TextIO = sys.stdout, is_executable: Callable[[str], bool] = _is_executable,
             temporary_directory=tempfile.TemporaryDirectory) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
    matches = [path for path in CANDIDATES if is_executable(path)]
    if len(matches) != 1:
        output.write(f"BUILDX_PLUGIN_CANDIDATES|executable_count={len(matches)}\n")
        return 11
    candidate = matches[0]
    try:
        with temporary_directory(prefix="agent00x-exp1613-config-") as config_dir:
            env = {
                "DOCKER_CONFIG": str(config_dir),
                "LANG": "C",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            }
            result = runner(
                (candidate, "version"),
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=TIMEOUT_SECONDS,
                env=env,
            )
    except OutputLimitExceeded:
        output.write("BUILDX_PLUGIN_VERSION_OUTPUT_LIMIT\n")
        return 12
    except subprocess.TimeoutExpired:
        output.write("BUILDX_PLUGIN_VERSION_TIMEOUT\n")
        return 13
    except Exception:
        output.write("BUILDX_PLUGIN_VERSION_INCONCLUSIVE\n")
        return 14
    if type(result.returncode) is not int or result.returncode != 0:
        output.write("BUILDX_PLUGIN_VERSION_FAILED\n")
        return 15
    version = _version(result.stdout if type(result.stdout) is bytes else b"")
    if version is None:
        output.write("BUILDX_PLUGIN_VERSION_UNCLASSIFIED\n")
        return 16
    output.write(f"BUILDX_PLUGIN|location=one-standard-path|version=v{version}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_once())
