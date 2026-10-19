#!/usr/bin/env python3
"""One read-only, redacted Docker image-store backend probe (EXP-1626)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_portable_verifier_image_exp1350 import _bounded_process_output  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
MAX_OUTPUT_BYTES = 4096
TIMEOUT_SECONDS = 20
_CLASSIC_DRIVERS = frozenset({
    "aufs", "btrfs", "devicemapper", "overlay2", "fuse-overlayfs",
    "vfs", "windowsfilter", "zfs",
})


def _classify(stdout: bytes) -> str:
    try:
        driver_raw, status_raw = stdout.decode("utf-8").split("\n", 1)
        driver = driver_raw.strip()
        statuses = json.loads(status_raw)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return "unclassified"
    if not isinstance(statuses, list):
        return "unclassified"
    if any(
        isinstance(pair, list)
        and len(pair) == 2
        and pair[0] == "driver-type"
        and isinstance(pair[1], str)
        and pair[1].startswith("io.containerd.snapshotter.v1")
        for pair in statuses
    ):
        return "containerd"
    if driver in _CLASSIC_DRIVERS:
        return "classic"
    return "unclassified"


def run_once(*, runner: Callable = _bounded_process_output,
             temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory,
             output: TextIO = sys.stdout) -> int:
    with temporary_directory(prefix="agent00x-exp1626-docker-config-") as config_dir:
        env = {
            "DOCKER_CONFIG": str(config_dir),
            "DOCKER_HOST": DOCKER_HOST,
            "LANG": "C",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
        }
        command = (
            DOCKER, "--host=" + DOCKER_HOST, "info", "--format",
            "{{.Driver}}\n{{json .DriverStatus}}",
        )
        try:
            result = runner(
                command, max_bytes=MAX_OUTPUT_BYTES, timeout=TIMEOUT_SECONDS, env=env
            )
        except Exception:
            output.write("IMAGE_STORE_BACKEND|classification=unavailable\n")
            return 11
    if result.returncode != 0 or type(result.stdout) is not bytes:
        output.write("IMAGE_STORE_BACKEND|classification=unavailable\n")
        return 11
    classification = _classify(result.stdout)
    if classification == "unclassified":
        output.write("IMAGE_STORE_BACKEND|classification=unclassified\n")
        return 12
    output.write(f"IMAGE_STORE_BACKEND|classification={classification}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_once())
