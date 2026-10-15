#!/usr/bin/env python3
"""One-shot, read-only testdev inspect for the portable verifier config ID."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, TextIO

from scripts import stream_pinned_verifier_image as source_pin


CONFIG_IMAGE_ID = (
    "sha256:abead7559044e2f44369eed75ccfc56c5079cb5df08809e4c29f855d98bedfb3"
)
_RUN_GATE = "RUN EXP-1346 ONCE"
_INSPECT_FORMAT = (
    "{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|"
    "{{json .RootFS.Layers}}|{{json .RepoTags}}"
)
_EXPECTED = (
    f"{CONFIG_IMAGE_ID}|{source_pin.OS}|{source_pin.ARCH}|{source_pin.IMAGE_SIZE}|"
    f"{source_pin._DIFF_ID_LIST}|[]"
)
_REMOTE_COMMAND = (
    f"if ! result=\"$(docker image inspect {CONFIG_IMAGE_ID} "
    f"--format '{_INSPECT_FORMAT}' 2>/dev/null)\"; then "
    "printf '%s\\n' REMOTE_INSPECT_FAILED; exit 42; fi; "
    "printf '%s\\n' \"$result\""
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
    "REMOTE_CONFIG_IMAGE_CONFIRMED": 0,
    "REMOTE_INSPECT_FAILED": 10,
    "REMOTE_IMAGE_IDENTITY_MISMATCH": 11,
    "SSH_CLIENT_LAUNCH_FAILED": 12,
    "SSH_CLIENT_EXIT_255": 13,
    "RUN_NOT_CONFIRMED": 19,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def inspect_once(
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
    if result.returncode == 42 and result.stdout == b"REMOTE_INSPECT_FAILED\n":
        return _emit("REMOTE_INSPECT_FAILED", output)
    if result.returncode != 0:
        return _emit("REMOTE_IMAGE_IDENTITY_MISMATCH", output)
    if result.stdout != (_EXPECTED + "\n").encode("ascii"):
        return _emit("REMOTE_IMAGE_IDENTITY_MISMATCH", output)
    return _emit("REMOTE_CONFIG_IMAGE_CONFIRMED", output)


def main(
    stdin: TextIO = sys.stdin,
    output: TextIO = sys.stdout,
    runner: Runner = subprocess.run,
) -> int:
    output.write(f"Type {_RUN_GATE} to continue: ")
    output.flush()
    if stdin.readline().rstrip("\r\n") != _RUN_GATE:
        return _emit("RUN_NOT_CONFIRMED", output)
    return inspect_once(runner, output)


if __name__ == "__main__":
    raise SystemExit(main())
