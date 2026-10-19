#!/usr/bin/env python3
"""One read-only, bounded Buildx capability probe (EXP-1575)."""

from __future__ import annotations

import os
from pathlib import Path
import re
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
MAX_OUTPUT_BYTES = 8192
VERSION_RE = re.compile(r"github\.com/docker/buildx\s+(v?[A-Za-z0-9.+_-]+)")
DRIVER_RE = re.compile(r"^Driver:\s+([a-z][a-z0-9_-]{0,31})\s*$", re.MULTILINE)
BUILDKIT_RE = re.compile(r"^BuildKit version:\s+(v?[A-Za-z0-9.+_-]+)\s*$", re.MULTILINE)


def _env(config_dir: str) -> dict[str, str]:
    return {
        "DOCKER_CONFIG": config_dir,
        "DOCKER_HOST": DOCKER_HOST,
        "LANG": "C",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }


def parse_version(data: bytes) -> str | None:
    try:
        text = data.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return None
    match = VERSION_RE.search(text)
    return match.group(1) if match else None


def parse_builder(data: bytes) -> tuple[str, str] | None:
    try:
        text = data.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return None
    driver = DRIVER_RE.search(text)
    buildkit = BUILDKIT_RE.search(text)
    if driver is None or buildkit is None:
        return None
    return driver.group(1), buildkit.group(1)


def run_once(*, runner=_bounded_process_output, output: TextIO = sys.stdout) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
    try:
        with tempfile.TemporaryDirectory(prefix="agent00x-exp1575-docker-config-") as config:
            env = _env(config)
            version = runner(
                (DOCKER, "buildx", "version"),
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=10,
                env=env,
            )
            builder = runner(
                (DOCKER, "--host=" + DOCKER_HOST, "buildx", "inspect", "default"),
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=15,
                env=env,
            )
    except (OSError, OutputLimitExceeded, TimeoutError):
        output.write("PROBE_UNAVAILABLE\n")
        return 11
    except Exception:
        output.write("PROBE_UNAVAILABLE\n")
        return 11

    version_value = parse_version(version.stdout) if version.returncode == 0 else None
    builder_value = parse_builder(builder.stdout) if builder.returncode == 0 else None
    version_fact = version_value or "unclassified"
    builder_fact = "unclassified"
    if builder_value is not None:
        driver, buildkit = builder_value
        builder_fact = f"{driver},{buildkit}"
    output.write(
        f"BUILDX_PROBE|version={version_fact}|builder={builder_fact}\n"
    )
    return 0 if version_value is not None and builder_value is not None else 12


if __name__ == "__main__":
    raise SystemExit(run_once())
