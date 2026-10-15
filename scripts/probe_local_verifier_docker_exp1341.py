#!/usr/bin/env python3
"""Read-only bounded probe of local Docker image-store metadata."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Callable, TextIO

from scripts import classify_local_verifier_image_id_exp1340 as classify
from scripts import stream_pinned_verifier_image as pinned


_MARKER_CODES = {
    "LOCAL_DOCKER_INFO_FAILED": 10,
    "LOCAL_DOCKER_INFO_INVALID": 11,
    "LOCAL_PINNED_IMAGE_ABSENT": 12,
    "LOCAL_PINNED_IMAGE_INSPECT_FAILED": 13,
    "LOCAL_PINNED_IMAGE_ID_MISMATCH": 14,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def run_probe(runner: Runner = subprocess.run, output: TextIO = sys.stdout) -> int:
    info_command = (
        "/usr/local/bin/docker",
        "info",
        "--format",
        "{{.Driver}}|{{json .DriverStatus}}",
    )
    try:
        info = runner(info_command, capture_output=True, timeout=15, check=False)
    except Exception:
        return _emit("LOCAL_DOCKER_INFO_FAILED", output)
    if info.returncode != 0:
        return _emit("LOCAL_DOCKER_INFO_FAILED", output)
    try:
        line = info.stdout.decode("utf-8")
        driver, status_json = line.rstrip("\n").split("|", 1)
        status = json.loads(status_json)
        if not driver or not isinstance(status, list):
            raise ValueError
        status_text = json.dumps(status, separators=(",", ":"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _emit("LOCAL_DOCKER_INFO_INVALID", output)
    containerd_snapshotter = "io.containerd.snapshotter.v1" in status_text

    inspect_command = (
        "/usr/local/bin/docker",
        "image",
        "inspect",
        "--format",
        "{{.Id}}|{{if .Descriptor}}{{.Descriptor.Digest}}{{else}}none{{end}}",
        pinned.IMAGE_ID,
    )
    try:
        inspected = runner(
            inspect_command, capture_output=True, timeout=15, check=False
        )
    except Exception:
        output.write(
            "LOCAL_DOCKER_STORE|driver_present=true|"
            f"containerd_snapshotter={str(containerd_snapshotter).lower()}\n"
        )
        return _emit("LOCAL_PINNED_IMAGE_INSPECT_FAILED", output)
    output.write(
        "LOCAL_DOCKER_STORE|driver_present=true|"
        f"containerd_snapshotter={str(containerd_snapshotter).lower()}\n"
    )
    if inspected.returncode != 0:
        error_text = b"\n".join((inspected.stdout or b"", inspected.stderr or b""))
        if b"No such image" in error_text:
            return _emit("LOCAL_PINNED_IMAGE_ABSENT", output)
        return _emit("LOCAL_PINNED_IMAGE_INSPECT_FAILED", output)
    identity = classify._parse_identity_line(inspected.stdout)
    if identity is None:
        return _emit("LOCAL_PINNED_IMAGE_INSPECT_FAILED", output)
    image_id, descriptor_digest = identity
    if image_id != pinned.IMAGE_ID:
        return _emit("LOCAL_PINNED_IMAGE_ID_MISMATCH", output)
    output.write(
        "LOCAL_PINNED_IMAGE|id_matches_pin=true|"
        f"descriptor_available={str(descriptor_digest != 'none').lower()}|"
        "id_equals_descriptor_digest="
        f"{str(image_id == descriptor_digest).lower()}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_probe())
