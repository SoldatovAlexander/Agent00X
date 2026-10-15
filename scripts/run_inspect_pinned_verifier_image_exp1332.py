#!/usr/bin/env python3
"""Fresh one-shot gate for the read-only EXP-1332 image inspection."""

from __future__ import annotations

import sys
from typing import Callable, TextIO

from scripts.inspect_pinned_verifier_image import inspect_remote_image


_RUN_GATE = "RUN EXP-1332 ONCE"


def main(
    inspect: Callable[[], int] = inspect_remote_image,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    stderr.write(f"Type {_RUN_GATE} to continue: ")
    stderr.flush()
    if stdin.readline().rstrip("\r\n") != _RUN_GATE:
        stdout.write("RUN_NOT_CONFIRMED\n")
        return 19
    return inspect()


if __name__ == "__main__":
    raise SystemExit(main())
