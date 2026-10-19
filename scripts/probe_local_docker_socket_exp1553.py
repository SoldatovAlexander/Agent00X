#!/usr/bin/env python3
"""Filesystem-only probe of the adapter's fixed local Docker socket path."""

from __future__ import annotations

import os
import stat
import sys
from typing import TextIO


DOCKER_SOCKET = "/var/run/docker.sock"
_CODES = {
    "DOCKER_SOCKET_READY": 0,
    "DOCKER_SOCKET_MISSING": 1,
    "DOCKER_SOCKET_NOT_SOCKET": 2,
    "DOCKER_SOCKET_NOT_READY": 3,
}


def run_once(*, output: TextIO = sys.stdout, path: str = DOCKER_SOCKET) -> int:
    try:
        metadata = os.stat(path)
    except FileNotFoundError:
        marker = "DOCKER_SOCKET_MISSING"
    except OSError:
        marker = "DOCKER_SOCKET_NOT_READY"
    else:
        if not stat.S_ISSOCK(metadata.st_mode):
            marker = "DOCKER_SOCKET_NOT_SOCKET"
        elif not (os.access(path, os.R_OK) and os.access(path, os.W_OK)):
            marker = "DOCKER_SOCKET_NOT_READY"
        else:
            marker = "DOCKER_SOCKET_READY"
    output.write(marker + "\n")
    return _CODES[marker]


if __name__ == "__main__":
    raise SystemExit(run_once())
