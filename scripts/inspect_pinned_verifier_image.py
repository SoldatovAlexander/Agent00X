#!/usr/bin/env python3
"""One-shot read-only inspection of the pinned verifier image on testdev.

Importing this module is inert. Running it requires a fresh exact gate and then
performs at most one SSH invocation containing only `docker image inspect`.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, TextIO

from scripts import stream_pinned_verifier_image as pinned


_RUN_GATE = "RUN EXP-1315 ONCE"
_REMOTE_COMMAND = (
    f"docker image inspect {pinned.IMAGE_ID} "
    f"--format '{pinned._INSPECT_FORMAT}'"
)
_MARKER_CODES = {
    "REMOTE_IMAGE_CONFIRMED": 0,
    "REMOTE_IMAGE_IDENTITY_MISMATCH": 10,
    "REMOTE_INSPECT_FAILED": 11,
    "SSH_CLIENT_LAUNCH_FAILED": 12,
    "SSH_CLIENT_EXIT_255": 13,
    "RUN_NOT_CONFIRMED": 19,
}

Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _decode_exact_line(value: bytes) -> str | None:
    try:
        decoded = value.decode("ascii")
    except (AttributeError, UnicodeDecodeError):
        return None
    return decoded[:-1] if decoded.endswith("\n") else None


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def inspect_remote_image(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    """Inspect the exact image once and report only a fixed marker."""
    command = (
        "/usr/bin/ssh",
        *pinned._SSH_OPTIONS,
        "alex@192.168.88.101",
        _REMOTE_COMMAND,
    )
    try:
        result = runner(
            command,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return _emit("SSH_CLIENT_LAUNCH_FAILED", output)
    if result.returncode == 255:
        return _emit("SSH_CLIENT_EXIT_255", output)
    if result.returncode != 0:
        return _emit("REMOTE_INSPECT_FAILED", output)
    if _decode_exact_line(result.stdout) != pinned._EXPECTED_REMOTE_INSPECT:
        return _emit("REMOTE_IMAGE_IDENTITY_MISMATCH", output)
    return _emit("REMOTE_IMAGE_CONFIRMED", output)


def main() -> int:
    sys.stderr.write(f"Type {_RUN_GATE} to continue: ")
    sys.stderr.flush()
    if sys.stdin.readline().rstrip("\r\n") != _RUN_GATE:
        return _emit("RUN_NOT_CONFIRMED", sys.stdout)
    return inspect_remote_image()


if __name__ == "__main__":
    raise SystemExit(main())
