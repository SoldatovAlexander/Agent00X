#!/usr/bin/env python3
"""Fresh one-shot gate for EXP-1330's exact pinned verifier image transfer."""

from __future__ import annotations

import sys
from typing import Callable, TextIO

from scripts.stream_pinned_verifier_image import run_transfer


_RUN_GATE = "RUN EXP-1330 ONCE"


def main(
    transfer: Callable[[], int] = run_transfer,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    stderr.write(f"Type {_RUN_GATE} to continue: ")
    stderr.flush()
    if stdin.readline().rstrip("\r\n") != _RUN_GATE:
        stdout.write("RUN_NOT_CONFIRMED\n")
        return 19
    return transfer()


if __name__ == "__main__":
    raise SystemExit(main())
