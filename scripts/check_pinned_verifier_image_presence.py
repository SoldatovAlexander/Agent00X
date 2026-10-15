#!/usr/bin/env python3
"""One-shot, read-only exact-ID presence check on the verifier host."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, TextIO

from scripts import stream_pinned_verifier_image as pinned


_RUN_GATE = "RUN EXP-1320 ONCE"
_REMOTE_SCRIPT = (
    "if ! command -v docker >/dev/null 2>&1; then "
    "printf '%s\\n' REMOTE_DOCKER_CLI_UNAVAILABLE; exit 0; fi; "
    "if ! ids=\"$(docker image ls --all --no-trunc "
    "--format '{{.ID}}' 2>/dev/null)\"; then "
    "printf '%s\\n' REMOTE_IMAGE_LIST_FAILED; exit 0; fi; "
    f"if printf '%s\\n' \"$ids\" | /usr/bin/grep -Fqx '{pinned.IMAGE_ID}'; then "
    "printf '%s\\n' REMOTE_IMAGE_ID_PRESENT; "
    "else printf '%s\\n' REMOTE_IMAGE_ID_ABSENT; fi"
)
_MARKER_CODES = {
    "REMOTE_IMAGE_ID_PRESENT": 0,
    "REMOTE_IMAGE_ID_ABSENT": 10,
    "REMOTE_DOCKER_CLI_UNAVAILABLE": 11,
    "REMOTE_IMAGE_LIST_FAILED": 12,
    "SSH_CLIENT_EXIT_255": 13,
    "SSH_CLIENT_LAUNCH_FAILED": 14,
    "REMOTE_COMMAND_FAILED": 15,
    "REMOTE_PROBE_UNEXPECTED": 16,
    "SSH_CLIENT_TIMEOUT": 17,
    "RUN_NOT_CONFIRMED": 19,
}
_ALLOWED_MARKERS = frozenset(
    {
        "REMOTE_IMAGE_ID_PRESENT",
        "REMOTE_IMAGE_ID_ABSENT",
        "REMOTE_DOCKER_CLI_UNAVAILABLE",
        "REMOTE_IMAGE_LIST_FAILED",
    }
)
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


def check_remote_image_presence(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    """Make one strict SSH request and reveal only a fixed marker."""
    command = (
        "/usr/bin/ssh",
        *pinned._SSH_OPTIONS,
        "alex@192.168.88.101",
        _REMOTE_SCRIPT,
    )
    try:
        result = runner(command, capture_output=True, timeout=20, check=False)
    except subprocess.TimeoutExpired:
        return _emit("SSH_CLIENT_TIMEOUT", output)
    except Exception:
        return _emit("SSH_CLIENT_LAUNCH_FAILED", output)
    if result.returncode == 255:
        return _emit("SSH_CLIENT_EXIT_255", output)
    if result.returncode != 0:
        return _emit("REMOTE_COMMAND_FAILED", output)
    marker = _decode_exact_line(result.stdout)
    if marker not in _ALLOWED_MARKERS:
        return _emit("REMOTE_PROBE_UNEXPECTED", output)
    return _emit(marker, output)


def main() -> int:
    sys.stderr.write(f"Type {_RUN_GATE} to continue: ")
    sys.stderr.flush()
    if sys.stdin.readline().rstrip("\r\n") != _RUN_GATE:
        return _emit("RUN_NOT_CONFIRMED", sys.stdout)
    return check_remote_image_presence()


if __name__ == "__main__":
    raise SystemExit(main())
