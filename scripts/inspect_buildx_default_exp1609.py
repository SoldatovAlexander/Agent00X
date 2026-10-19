#!/usr/bin/env python3
"""Bounded read-only facts from the local default Buildx builder (EXP-1609)."""

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
DOCKER_HOST = "unix:///var/run/docker.sock"
MAX_OUTPUT_BYTES = 16_384
TIMEOUT_SECONDS = 25
_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_DRIVER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_STATUS = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_PLATFORM = re.compile(r"[a-z0-9]+/[a-z0-9]+(?:/[a-z0-9]+)?\Z")


def _env(config_dir: str) -> dict[str, str]:
    return {
        "DOCKER_CONFIG": config_dir,
        "DOCKER_HOST": DOCKER_HOST,
        "LANG": "C",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }


def _facts(output: bytes) -> str | None:
    try:
        lines = output.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError:
        return None
    if not lines or len(lines) > 512:
        return None
    nodes_index = next((i for i, line in enumerate(lines) if line.strip() == "Nodes:"), None)
    if nodes_index is None:
        return None

    top: dict[str, str] = {}
    for line in lines[:nodes_index]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        top[key.strip()] = value.strip()
    name = top.get("Name", "")
    driver = top.get("Driver", "")
    if name != "default" or _NAME.fullmatch(name) is None or _DRIVER.fullmatch(driver) is None:
        return None

    statuses: list[str] = []
    platforms: set[str] = set()
    for line in lines[nodes_index + 1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if key == "Status":
            if _STATUS.fullmatch(value) is None:
                return None
            statuses.append(value)
        elif key == "Platforms":
            values = [item.strip() for item in value.split(",") if item.strip()]
            if not values or any(_PLATFORM.fullmatch(item) is None for item in values):
                return None
            platforms.update(values)
    if not 1 <= len(statuses) <= 8 or not 1 <= len(platforms) <= 16:
        return None
    return (
        "BUILDX_INSPECT|name=default"
        f"|driver={driver}|nodes={len(statuses)}"
        f"|statuses={','.join(statuses)}"
        f"|platforms={','.join(sorted(platforms))}"
    )


def run_once(*, runner: Callable[..., subprocess.CompletedProcess[bytes]] = _bounded_process_output,
             output: TextIO = sys.stdout, temporary_directory=tempfile.TemporaryDirectory,
             builder_name: str | None = "default") -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
    command = (DOCKER, "--host=" + DOCKER_HOST, "buildx", "inspect")
    if builder_name is not None:
        if builder_name != "default":
            output.write("BUILDX_INSPECT_UNCLASSIFIED\n")
            return 15
        command += (builder_name,)
    try:
        with temporary_directory(prefix="agent00x-exp1609-docker-config-") as config_dir:
            result = runner(
                command,
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=TIMEOUT_SECONDS,
                env=_env(str(config_dir)),
            )
    except OutputLimitExceeded:
        output.write("BUILDX_INSPECT_OUTPUT_LIMIT\n")
        return 11
    except subprocess.TimeoutExpired:
        output.write("BUILDX_INSPECT_TIMEOUT\n")
        return 12
    except Exception:
        output.write("BUILDX_INSPECT_INCONCLUSIVE\n")
        return 13
    if type(result.returncode) is not int or result.returncode != 0:
        code = result.returncode if type(result.returncode) is int and 0 <= result.returncode <= 255 else "unknown"
        output.write(f"BUILDX_INSPECT_FAILED|exit={code}\n")
        return 14
    marker = _facts(result.stdout if type(result.stdout) is bytes else b"")
    if marker is None:
        output.write("BUILDX_INSPECT_UNCLASSIFIED\n")
        return 15
    output.write(marker + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_once())
