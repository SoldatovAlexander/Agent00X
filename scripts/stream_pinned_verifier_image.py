#!/usr/bin/env python3
"""Fail-closed, single-attempt transfer for the exact pinned verifier image.

This module is inert on import. Running it performs local Docker operations and
one SSH image import, so future use requires a separate, current task card.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, Sequence, TextIO


IMAGE_ID = "sha256:babefaa38e0e068f3af35b9f00d0ff0ea319a69e3a13697fe471b3e01a2cdf6a"
IMAGE_CODE_DIGEST = "sha256:f63ecc2359fe0c9dcd51893d55d831bacb33daa0b289a3b87d0b6a65de1d660f"
IMAGE_TAG = "agent00x-verifier-exp466:5865f817b97c4707857f50facce31a10"
IMAGE_SIZE = 48854834
STREAM_SIZE = 48868864
OS = "linux"
ARCH = "amd64"
DIFF_IDS = (
    "sha256:a6dc765193a52cbaede3c93a9ff48b9540948dd0774bbe7031fcb5847606f9ac",
    "sha256:a5c84380b3657bb723a1f71fa963f1e3a3f01e2c6bcba12e3b9a0d336158c7a9",
    "sha256:4a01ba3ac604812ef31dab0006efecd1d572676f7a68afa169a9d57883025006",
    "sha256:d190d09d7bd91836f809045799a7024a54026b3da5de1ccb811627fcf9878b92",
    "sha256:82fbc85959c7c97e6128123c0dcf2eb1430f74f4bf44ba52a48a120af0e4bfef",
    "sha256:09732bfeb389acc269d5251449c0156efe4d9a97bbfd0de62efc3b2b4a928307",
    "sha256:0a244a13dd659992bed00879b1f895d049647277cc4a5ff551afdf8fc9bd46a2",
    "sha256:7933242f7cd01d766983c0bdf67e33fd0ab8e75bc820f5a29d44dc8d30d10dc2",
    "sha256:adc78fa730d3fd4699887333f54b31c5cba046ee6b8b07d0922a399b760a31e0",
)
_DIFF_ID_LIST = "[" + ",".join(f'"{item}"' for item in DIFF_IDS) + "]"
# Local preflight keeps binding the exact image identity to its sole RepoTag, so a
# local image that lost the pinned tag is rejected before any save happens.
_EXPECTED_INSPECT = (
    f"{IMAGE_ID}|{OS}|{ARCH}|{IMAGE_SIZE}|{_DIFF_ID_LIST}|"
    f'["{IMAGE_TAG}"]'
)
# The archive is saved by immutable image ID, so Docker's archive manifest carries
# `RepoTags: null` and `docker image load` reports an untagged image. The remote
# acceptance tuple therefore requires the same ID/platform/size/ordered DiffIDs
# together with an empty RepoTags list; the previously observed conflicting
# remote tag `agent00x-verifier-exp466:8e26180bde4749438988170f85b395da` is never
# rewritten.
_EXPECTED_REMOTE_INSPECT = (
    f"{IMAGE_ID}|{OS}|{ARCH}|{IMAGE_SIZE}|{_DIFF_ID_LIST}|[]"
)
_INSPECT_FORMAT = (
    "{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|"
    "{{json .RootFS.Layers}}|{{json .RepoTags}}"
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
_REMOTE_COMMAND = (
    "docker image load >/dev/null 2>&1; load_status=$?; "
    "if [ \"$load_status\" -ne 0 ]; then "
    "printf '%s\\n' REMOTE_LOAD_FAILED; exit 41; fi; "
    f"if ! result=\"$(docker image inspect {IMAGE_ID} --format '{_INSPECT_FORMAT}' 2>/dev/null)\"; then "
    "printf '%s\\n' REMOTE_INSPECT_FAILED; exit 42; fi; "
    "printf '%s\\n' \"$result\""
)
_REMOTE_MARKERS = {
    b"REMOTE_LOAD_FAILED\n": "REMOTE_LOAD_FAILED",
    b"REMOTE_INSPECT_FAILED\n": "REMOTE_INSPECT_FAILED",
}
_MARKER_CODES = {
    "LOCAL_IMAGE_INSPECT_FAILED": 10,
    "LOCAL_IMAGE_IDENTITY_MISMATCH": 11,
    "LOCAL_IMAGE_SAVE_FAILED": 12,
    "LOCAL_IMAGE_STREAM_SIZE_MISMATCH": 13,
    "SSH_OR_REMOTE_COMMAND_FAILED": 14,
    "REMOTE_LOAD_FAILED": 15,
    "REMOTE_INSPECT_FAILED": 16,
    "REMOTE_IMAGE_IDENTITY_MISMATCH": 17,
    "IMAGE_IMPORT_CONFIRMED": 0,
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


def run_transfer(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    """Run the bounded transfer, using an injectable runner for offline tests."""
    inspect_command: Sequence[str] = (
        "/usr/local/bin/docker",
        "image",
        "inspect",
        "--format",
        _INSPECT_FORMAT,
        IMAGE_ID,
    )
    try:
        inspected = runner(
            inspect_command, capture_output=True, timeout=15, check=False
        )
    except Exception:
        return _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
    if inspected.returncode != 0:
        return _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
    if _decode_exact_line(inspected.stdout) != _EXPECTED_INSPECT:
        return _emit("LOCAL_IMAGE_IDENTITY_MISMATCH", output)

    try:
        saved = runner(
            ("/usr/local/bin/docker", "image", "save", IMAGE_ID),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except Exception:
        return _emit("LOCAL_IMAGE_SAVE_FAILED", output)
    if saved.returncode != 0:
        return _emit("LOCAL_IMAGE_SAVE_FAILED", output)
    stream = saved.stdout
    if not isinstance(stream, bytes) or len(stream) != STREAM_SIZE:
        return _emit("LOCAL_IMAGE_STREAM_SIZE_MISMATCH", output)

    ssh_command = (
        "/usr/bin/ssh",
        *_SSH_OPTIONS,
        "alex@192.168.88.101",
        _REMOTE_COMMAND,
    )
    try:
        imported = runner(
            ssh_command,
            input=stream,
            capture_output=True,
            timeout=90,
            check=False,
        )
    except Exception:
        return _emit("SSH_OR_REMOTE_COMMAND_FAILED", output)
    if imported.returncode != 0:
        marker = _REMOTE_MARKERS.get(imported.stdout)
        return _emit(marker or "SSH_OR_REMOTE_COMMAND_FAILED", output)
    if _decode_exact_line(imported.stdout) != _EXPECTED_REMOTE_INSPECT:
        return _emit("REMOTE_IMAGE_IDENTITY_MISMATCH", output)
    return _emit("IMAGE_IMPORT_CONFIRMED", output)


def main() -> int:
    sys.stderr.write("Type RUN EXP-1314 ONCE to continue: ")
    sys.stderr.flush()
    if sys.stdin.readline().rstrip("\r\n") != "RUN EXP-1314 ONCE":
        return _emit("RUN_NOT_CONFIRMED", sys.stdout)
    return run_transfer()


if __name__ == "__main__":
    raise SystemExit(main())
