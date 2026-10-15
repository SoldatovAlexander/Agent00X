#!/usr/bin/env python3
"""One-shot, read-only probe of testdev's Docker access for the pinned image.

Importing this module is inert. Running it requires the exact fresh gate and
performs at most one strict SSH invocation. Remote output is reduced to fixed
markers; Docker details and stderr are never emitted.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, TextIO

from scripts import stream_pinned_verifier_image as pinned


_RUN_GATE = "RUN EXP-1318 ONCE"

_REMOTE_SCRIPT = (
    "if ! command -v docker >/dev/null 2>&1; then "
    "printf '%s\\n' DOCKER_CLI_UNAVAILABLE; "
    "elif ! docker info >/dev/null 2>&1; then "
    "printf '%s\\n' DOCKER_DAEMON_UNAVAILABLE; "
    f"elif result=\"$(docker image inspect {pinned.IMAGE_ID} "
    f"--format '{pinned._INSPECT_FORMAT}' 2>/dev/null)\"; then "
    f"if [ \"$result\" = '{pinned._EXPECTED_REMOTE_INSPECT}' ]; then "
    "printf '%s\\n' REMOTE_IMAGE_CONFIRMED; "
    "else printf '%s\\n' REMOTE_IMAGE_IDENTITY_MISMATCH; fi; "
    "else printf '%s\\n' REMOTE_IMAGE_INSPECT_FAILED; fi"
)
_REMOTE_MARKERS = {
    "DOCKER_CLI_UNAVAILABLE",
    "DOCKER_DAEMON_UNAVAILABLE",
    "REMOTE_IMAGE_INSPECT_FAILED",
    "REMOTE_IMAGE_IDENTITY_MISMATCH",
    "REMOTE_IMAGE_CONFIRMED",
}
_MARKER_CODES = {
    "REMOTE_IMAGE_CONFIRMED": 0,
    "DOCKER_CLI_UNAVAILABLE": 10,
    "DOCKER_DAEMON_UNAVAILABLE": 11,
    "REMOTE_IMAGE_INSPECT_FAILED": 12,
    "REMOTE_IMAGE_IDENTITY_MISMATCH": 13,
    "REMOTE_PROBE_COMMAND_FAILED": 14,
    "SSH_CLIENT_LAUNCH_FAILED": 15,
    "SSH_CLIENT_TIMEOUT": 16,
    "SSH_CLIENT_EXIT_255": 17,
    "REMOTE_PROBE_UNEXPECTED": 18,
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


def probe_remote_host(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    """Run the bounded read-only probe once and emit one fixed marker."""
    command = (
        "/usr/bin/ssh",
        *pinned._SSH_OPTIONS,
        "alex@192.168.88.101",
        _REMOTE_SCRIPT,
    )
    try:
        result = runner(
            command,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _emit("SSH_CLIENT_TIMEOUT", output)
    except Exception:
        return _emit("SSH_CLIENT_LAUNCH_FAILED", output)

    if result.returncode == 255:
        return _emit("SSH_CLIENT_EXIT_255", output)
    if result.returncode != 0:
        return _emit("REMOTE_PROBE_COMMAND_FAILED", output)

    marker = _decode_exact_line(result.stdout)
    if marker not in _REMOTE_MARKERS:
        return _emit("REMOTE_PROBE_UNEXPECTED", output)
    return _emit(marker, output)


def main() -> int:
    sys.stderr.write(f"Type {_RUN_GATE} to continue: ")
    sys.stderr.flush()
    if sys.stdin.readline().rstrip("\r\n") != _RUN_GATE:
        return _emit("RUN_NOT_CONFIRMED", sys.stdout)
    return probe_remote_host()


if __name__ == "__main__":
    raise SystemExit(main())
