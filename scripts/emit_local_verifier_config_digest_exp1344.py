#!/usr/bin/env python3
"""Emit one exact local verifier config digest with bounded archive facts."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, TextIO

from scripts import audit_pinned_verifier_save_archive as audit
from scripts import stream_pinned_verifier_image as pinned


_MARKER_CODES = {
    "LOCAL_IMAGE_SAVE_FAILED": 10,
    "LOCAL_IMAGE_SAVE_TIMEOUT": 11,
    "LOCAL_IMAGE_SAVE_LAUNCH_FAILED": 12,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def emit_config_digest(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    try:
        saved = runner(
            ("/usr/local/bin/docker", "image", "save", pinned.IMAGE_ID),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _emit("LOCAL_IMAGE_SAVE_TIMEOUT", output)
    except Exception:
        return _emit("LOCAL_IMAGE_SAVE_LAUNCH_FAILED", output)
    if saved.returncode != 0:
        return _emit("LOCAL_IMAGE_SAVE_FAILED", output)
    return audit.inspect_archive(
        saved.stdout,
        descriptor_digest=pinned.IMAGE_ID,
        emit_config_digest=True,
        output=output,
    )


if __name__ == "__main__":
    raise SystemExit(emit_config_digest())
