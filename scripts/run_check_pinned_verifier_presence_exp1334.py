#!/usr/bin/env python3
"""Fresh one-shot gate for EXP-1334's exact-ID-only presence query."""

from __future__ import annotations

import sys
from typing import Callable, TextIO

from scripts.check_pinned_verifier_image_presence import check_remote_image_presence


_RUN_GATE = "RUN EXP-1334 ONCE"


def main(
    check: Callable[[], int] = check_remote_image_presence,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    stderr.write(f"Type {_RUN_GATE} to continue: ")
    stderr.flush()
    if stdin.readline().rstrip("\r\n") != _RUN_GATE:
        stdout.write("RUN_NOT_CONFIRMED\n")
        return 19
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
