#!/usr/bin/env python3
"""Check the exact local verifier image ID without revealing CLI output."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, TextIO

from scripts import stream_pinned_verifier_image as pinned


_MARKER_CODES = {
    "LOCAL_IMAGE_INSPECT_FAILED": 10,
    "LOCAL_IMAGE_ID_MISMATCH": 11,
    "LOCAL_IMAGE_NOT_FOUND": 12,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def check_local_image_id(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    command = (
        "/usr/local/bin/docker",
        "image",
        "inspect",
        "--format",
        "{{.Id}}",
        pinned.IMAGE_ID,
    )
    try:
        result = runner(command, capture_output=True, timeout=15, check=False)
    except Exception:
        return _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
    if result.returncode != 0:
        error_text = b"\n".join((result.stdout or b"", result.stderr or b""))
        if b"No such image" in error_text:
            return _emit("LOCAL_IMAGE_NOT_FOUND", output)
        return _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
    try:
        value = result.stdout.decode("ascii")
    except (AttributeError, UnicodeDecodeError):
        return _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
    if value != pinned.IMAGE_ID + "\n":
        return _emit("LOCAL_IMAGE_ID_MISMATCH", output)
    output.write("LOCAL_IMAGE_ID_CONFIRMED\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(check_local_image_id())
