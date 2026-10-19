#!/usr/bin/env python3
"""Bounded read-only local Buildx builder listing (EXP-1611)."""

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
_STATUS = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_PLATFORM = re.compile(r"[a-z0-9]+/[a-z0-9]+(?:/[a-z0-9]+)?\Z")


def _facts(data: bytes) -> str | None:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    lines = text.splitlines()
    if len(lines) > 64:
        return None
    other_rows = 0
    default_found = False
    statuses: set[str] = set()
    platforms: set[str] = set()
    for line in lines:
        if not line:
            continue
        fields = line.split("|")
        if len(fields) != 3:
            return None
        name, status, platform_text = (field.strip() for field in fields)
        if name.endswith("*"):
            name = name[:-1]
        if _NAME.fullmatch(name) is None:
            return None
        if name != "default":
            other_rows += 1
            continue
        default_found = True
        if status:
            if _STATUS.fullmatch(status) is None:
                return None
            statuses.add(status)
        if platform_text:
            values = [part.strip().removesuffix("*") for part in platform_text.split(",")]
            if not values or any(_PLATFORM.fullmatch(value) is None for value in values):
                return None
            platforms.update(values)
    if not default_found:
        return f"BUILDX_LS|default=absent|other_rows={other_rows}"
    status_fact = ",".join(sorted(statuses)) or "unreported"
    platform_fact = ",".join(sorted(platforms)) or "unreported"
    return (
        f"BUILDX_LS|default=present|other_rows={other_rows}"
        f"|statuses={status_fact}|platforms={platform_fact}"
    )


def run_once(*, runner: Callable[..., subprocess.CompletedProcess[bytes]] = _bounded_process_output,
             output: TextIO = sys.stdout, temporary_directory=tempfile.TemporaryDirectory) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
    command = (
        DOCKER, "--host=" + DOCKER_HOST, "buildx", "ls", "--format",
        "{{.Name}}|{{.Status}}|{{.Platforms}}",
    )
    env = {
        "DOCKER_CONFIG": "",
        "DOCKER_HOST": DOCKER_HOST,
        "LANG": "C",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }
    try:
        with temporary_directory(prefix="agent00x-exp1611-docker-config-") as config_dir:
            env["DOCKER_CONFIG"] = str(config_dir)
            result = runner(command, max_bytes=MAX_OUTPUT_BYTES, timeout=TIMEOUT_SECONDS, env=env)
    except OutputLimitExceeded:
        output.write("BUILDX_LS_OUTPUT_LIMIT\n")
        return 11
    except subprocess.TimeoutExpired:
        output.write("BUILDX_LS_TIMEOUT\n")
        return 12
    except Exception:
        output.write("BUILDX_LS_INCONCLUSIVE\n")
        return 13
    if type(result.returncode) is not int or result.returncode != 0:
        output.write("BUILDX_LS_FAILED\n")
        return 14
    marker = _facts(result.stdout if type(result.stdout) is bytes else b"")
    if marker is None:
        output.write("BUILDX_LS_UNCLASSIFIED\n")
        return 15
    output.write(marker + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_once())
