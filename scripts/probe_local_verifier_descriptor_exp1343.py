#!/usr/bin/env python3
"""Probe only the exact local image Descriptor field, with redacted output."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Callable, TextIO

from scripts import stream_pinned_verifier_image as pinned


_MARKER_CODES = {
    "LOCAL_DESCRIPTOR_INSPECT_FAILED": 10,
    "LOCAL_DESCRIPTOR_OUTPUT_INVALID": 11,
    "LOCAL_DESCRIPTOR_ABSENT": 12,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def probe_descriptor(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    command = (
        "/usr/local/bin/docker",
        "image",
        "inspect",
        "--format",
        "{{json .Descriptor}}",
        pinned.IMAGE_ID,
    )
    try:
        result = runner(command, capture_output=True, timeout=15, check=False)
    except Exception:
        return _emit("LOCAL_DESCRIPTOR_INSPECT_FAILED", output)
    if result.returncode != 0:
        return _emit("LOCAL_DESCRIPTOR_INSPECT_FAILED", output)
    try:
        raw = result.stdout.decode("ascii")
        if not raw.endswith("\n") or raw.count("\n") != 1:
            raise ValueError
        descriptor = json.loads(raw[:-1])
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _emit("LOCAL_DESCRIPTOR_OUTPUT_INVALID", output)
    if descriptor is None:
        return _emit("LOCAL_DESCRIPTOR_ABSENT", output)
    if not isinstance(descriptor, dict):
        return _emit("LOCAL_DESCRIPTOR_OUTPUT_INVALID", output)
    digest = descriptor.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return _emit("LOCAL_DESCRIPTOR_OUTPUT_INVALID", output)
    output.write(
        "LOCAL_DESCRIPTOR|present=true|digest_matches_pinned_id="
        f"{str(digest == pinned.IMAGE_ID).lower()}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(probe_descriptor())
