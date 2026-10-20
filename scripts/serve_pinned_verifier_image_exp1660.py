#!/usr/bin/env python3
"""Prepare a fresh, one-shot gate for the current pinned verifier image."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import sys
from pathlib import Path
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import serve_pinned_verifier_image_exp1653 as delivery  # noqa: E402


CONFIRMATION_PHRASE = "RUN EXP-1661 ONCE"
AUTHORIZATION_EXPIRES_AT = datetime(2026, 10, 21, 15, 0, 0, tzinfo=timezone.utc)
REQUEST_PATH = "/exp-1661/verifier-image.tar"


def run_once(
    *,
    bind_address: str,
    port: int,
    stdin=None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    runner: Callable[..., object] = delivery.subprocess.run,
    server_factory: Callable[..., object] = delivery._OneShotServer,
    now: datetime | None = None,
) -> int:
    try:
        is_tty = stdin is not None and stdin.isatty() is True
    except Exception:
        is_tty = False
    if not is_tty:
        return delivery._emit("RUN_NOT_CONFIRMED", stdout)
    if (
        delivery.validate_bind_address(bind_address) is None
        or type(port) is not int
        or not 0 <= port <= 65535
    ):
        return delivery._emit("BIND_ADDRESS_INVALID", stdout)
    stderr.write(f"Type {CONFIRMATION_PHRASE} to continue: ")
    stderr.flush()
    try:
        phrase = stdin.readline().rstrip("\r\n")
    except Exception:
        phrase = ""
    if phrase != CONFIRMATION_PHRASE:
        return delivery._emit("RUN_NOT_CONFIRMED", stdout)

    moment = datetime.now(timezone.utc) if now is None else now
    if (
        not isinstance(moment, datetime)
        or moment.tzinfo is None
        or moment.utcoffset() is None
        or moment.astimezone(timezone.utc) >= AUTHORIZATION_EXPIRES_AT
    ):
        return delivery._emit("AUTHORIZATION_EXPIRED", stdout)

    preparation_output = io.StringIO()
    archive = delivery.prepare_archive(runner, output=preparation_output)
    if archive is None:
        marker = preparation_output.getvalue().strip()
        if marker not in delivery._MARKER_CODES:
            marker = "LOCAL_ARCHIVE_INVALID"
        return delivery._emit(marker, stdout)
    return delivery.serve_once(
        archive,
        bind_address=bind_address,
        port=port,
        output=stdout,
        server_factory=server_factory,
        request_path=REQUEST_PATH,
        task_prefix="agent00x-exp1661",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind-address", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    return run_once(bind_address=args.bind_address, port=args.port, stdin=sys.stdin)


if __name__ == "__main__":
    raise SystemExit(main())
