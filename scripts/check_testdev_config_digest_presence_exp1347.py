#!/usr/bin/env python3
"""One-shot exact-ID-only read-only probe for EXP-1347."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, TextIO


CONFIG_IMAGE_ID = (
    "sha256:abead7559044e2f44369eed75ccfc56c5079cb5df08809e4c29f855d98bedfb3"
)
_RUN_GATE = "RUN EXP-1347 ONCE"
_REMOTE_COMMAND = (
    "if ! ids=\"$(docker image ls --all --no-trunc --format '{{.ID}}' "
    "2>/dev/null)\"; then printf '%s\\n' REMOTE_IMAGE_LIST_FAILED; exit 42; fi; "
    f"if printf '%s\\n' \"$ids\" | /usr/bin/grep -Fqx '{CONFIG_IMAGE_ID}'; then "
    "printf '%s\\n' REMOTE_CONFIG_IMAGE_ID_PRESENT; "
    "else printf '%s\\n' REMOTE_CONFIG_IMAGE_ID_ABSENT; fi"
)
_SSH_OPTIONS = (
    "-T",
    "-F",
    "/dev/null",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=8",
    "-o",
    "PreferredAuthentications=publickey",
    "-o",
    "PasswordAuthentication=no",
    "-o",
    "KbdInteractiveAuthentication=no",
    "-o",
    "ClearAllForwardings=yes",
)
_MARKER_CODES = {
    "REMOTE_CONFIG_IMAGE_ID_PRESENT": 0,
    "REMOTE_CONFIG_IMAGE_ID_ABSENT": 10,
    "REMOTE_IMAGE_LIST_FAILED": 11,
    "SSH_CLIENT_LAUNCH_FAILED": 12,
    "SSH_CLIENT_EXIT_255": 13,
    "REMOTE_PROBE_UNEXPECTED": 14,
    "RUN_NOT_CONFIRMED": 19,
}
_ALLOWED_REMOTE_MARKERS = frozenset(
    {
        "REMOTE_CONFIG_IMAGE_ID_PRESENT",
        "REMOTE_CONFIG_IMAGE_ID_ABSENT",
        "REMOTE_IMAGE_LIST_FAILED",
    }
)
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def check_once(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    command = (
        "/usr/bin/ssh",
        *_SSH_OPTIONS,
        "alex@192.168.88.101",
        _REMOTE_COMMAND,
    )
    try:
        result = runner(command, capture_output=True, timeout=15, check=False)
    except Exception:
        return _emit("SSH_CLIENT_LAUNCH_FAILED", output)
    if result.returncode == 255:
        return _emit("SSH_CLIENT_EXIT_255", output)
    if result.returncode == 42 and result.stdout == b"REMOTE_IMAGE_LIST_FAILED\n":
        return _emit("REMOTE_IMAGE_LIST_FAILED", output)
    if result.returncode != 0:
        return _emit("REMOTE_PROBE_UNEXPECTED", output)
    marker = result.stdout.decode("ascii", errors="ignore").removesuffix("\n")
    if marker not in _ALLOWED_REMOTE_MARKERS or result.stdout != (marker + "\n").encode():
        return _emit("REMOTE_PROBE_UNEXPECTED", output)
    return _emit(marker, output)


def main(
    stdin: TextIO = sys.stdin,
    output: TextIO = sys.stdout,
    runner: Runner = subprocess.run,
) -> int:
    output.write(f"Type {_RUN_GATE} to continue: ")
    output.flush()
    if stdin.readline().rstrip("\r\n") != _RUN_GATE:
        return _emit("RUN_NOT_CONFIRMED", output)
    return check_once(runner, output)


if __name__ == "__main__":
    raise SystemExit(main())
