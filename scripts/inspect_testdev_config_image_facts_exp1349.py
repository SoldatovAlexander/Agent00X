#!/usr/bin/env python3
"""One-shot, boolean-only verifier image facts probe for EXP-1349."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, TextIO

from scripts import stream_pinned_verifier_image as source_pin

CONFIG_IMAGE_ID = "sha256:abead7559044e2f44369eed75ccfc56c5079cb5df08809e4c29f855d98bedfb3"
_RUN_GATE = "RUN EXP-1349 ONCE"
_FORMAT = "{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|{{json .RootFS.Layers}}"
_REMOTE_COMMAND = (
    f"if ! result=\"$(docker image inspect {CONFIG_IMAGE_ID} --format '{_FORMAT}' "
    "2>/dev/null)\"; then printf '%s\\n' REMOTE_INSPECT_FAILED; exit 42; fi; "
    "printf '%s\\n' \"$result\""
)
_SSH_OPTIONS = (
    "-T", "-F", "/dev/null", "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
    "-o", "PreferredAuthentications=publickey", "-o", "PasswordAuthentication=no",
    "-o", "KbdInteractiveAuthentication=no", "-o", "ClearAllForwardings=yes",
)
_EXIT_CODES = {
    "REMOTE_CONFIG_IMAGE_FACTS": 0,
    "REMOTE_INSPECT_FAILED": 10,
    "REMOTE_CONFIG_IMAGE_FACTS_MISMATCH": 11,
    "REMOTE_CONFIG_IMAGE_FACTS_UNEXPECTED": 12,
    "SSH_CLIENT_LAUNCH_FAILED": 13,
    "SSH_CLIENT_EXIT_255": 14,
    "RUN_NOT_CONFIRMED": 19,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _classify(stdout: bytes) -> tuple[str, int]:
    if not stdout.endswith(b"\n") or stdout.count(b"\n") != 1:
        marker = "REMOTE_CONFIG_IMAGE_FACTS_UNEXPECTED"
        return marker, _EXIT_CODES[marker]
    try:
        fields = stdout[:-1].decode("ascii").split("|", 4)
    except UnicodeDecodeError:
        marker = "REMOTE_CONFIG_IMAGE_FACTS_UNEXPECTED"
        return marker, _EXIT_CODES[marker]
    if len(fields) != 5:
        marker = "REMOTE_CONFIG_IMAGE_FACTS_UNEXPECTED"
        return marker, _EXIT_CODES[marker]
    matches = (
        fields[0] == CONFIG_IMAGE_ID,
        fields[1] == source_pin.OS and fields[2] == source_pin.ARCH,
        fields[3] == str(source_pin.IMAGE_SIZE),
        fields[4] == source_pin._DIFF_ID_LIST,
    )
    marker = "REMOTE_CONFIG_IMAGE_FACTS|" + "|".join(
        f"{name}={'match' if match else 'mismatch'}"
        for name, match in zip(("id", "platform", "size", "layers"), matches)
    )
    status = "REMOTE_CONFIG_IMAGE_FACTS" if all(matches) else "REMOTE_CONFIG_IMAGE_FACTS_MISMATCH"
    return marker, _EXIT_CODES[status]


def inspect_once(runner: Runner = subprocess.run, output: TextIO = sys.stdout) -> int:
    command = ("/usr/bin/ssh", *_SSH_OPTIONS, "alex@192.168.88.101", _REMOTE_COMMAND)
    try:
        result = runner(command, capture_output=True, timeout=15, check=False)
    except Exception:
        marker = "SSH_CLIENT_LAUNCH_FAILED"
        output.write(marker + "\n")
        return _EXIT_CODES[marker]
    if result.returncode == 255:
        marker = "SSH_CLIENT_EXIT_255"
        output.write(marker + "\n")
        return _EXIT_CODES[marker]
    if result.returncode == 42 and result.stdout == b"REMOTE_INSPECT_FAILED\n":
        marker = "REMOTE_INSPECT_FAILED"
        output.write(marker + "\n")
        return _EXIT_CODES[marker]
    if result.returncode != 0:
        marker = "REMOTE_CONFIG_IMAGE_FACTS_UNEXPECTED"
        output.write(marker + "\n")
        return _EXIT_CODES[marker]
    marker, code = _classify(result.stdout)
    output.write(marker + "\n")
    return code


def main(stdin: TextIO = sys.stdin, output: TextIO = sys.stdout,
         runner: Runner = subprocess.run) -> int:
    output.write(f"Type {_RUN_GATE} to continue: ")
    output.flush()
    if stdin.readline().rstrip("\r\n") != _RUN_GATE:
        marker = "RUN_NOT_CONFIRMED"
        output.write(marker + "\n")
        return _EXIT_CODES[marker]
    return inspect_once(runner, output)


if __name__ == "__main__":
    raise SystemExit(main())
