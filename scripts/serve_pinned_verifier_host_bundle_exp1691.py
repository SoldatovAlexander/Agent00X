#!/usr/bin/env python3
"""Fresh one-shot LAN delivery gate for the current verifier source bundle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import shlex
import sys
from pathlib import Path
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import serve_pinned_verifier_image_exp1653 as delivery  # noqa: E402
from scripts import serve_pinned_verifier_host_bundle_exp1679 as previous_profile  # noqa: E402
from scripts.build_verifier_host_bundle import build_bundle  # noqa: E402
from scripts import stream_pinned_verifier_host_bundle as pinned  # noqa: E402


CONFIRMATION_PHRASE = "RUN EXP-1693 ONCE"
AUTHORIZATION_EXPIRES_AT = datetime(2026, 10, 20, 23, 0, 0, tzinfo=timezone.utc)
TARGET_ADDRESS = "192.168.88.101"
TARGET_PATH = "/home/alex/.local/share/agent00x/verifier-host/exp-1693"
REQUEST_PATH = "/exp-1693/verifier-host-bundle.tar"
TASK_PREFIX = "agent00x-exp1693"
TRANSFER_TIMEOUT_SECONDS = 180
_OLD_SUFFIX = "exp-1679"
_NEW_SUFFIX = "exp-1693"
if (
    pinned.TARGET_HOST != "alex@192.168.88.101"
    or previous_profile._REMOTE_RECEIVER.count(_OLD_SUFFIX) != 1
):
    raise RuntimeError("unexpected current host-bundle receiver pin")
_REMOTE_RECEIVER = previous_profile._REMOTE_RECEIVER.replace(_OLD_SUFFIX, _NEW_SUFFIX)

_MARKER_CODES = {
    "RUN_NOT_CONFIRMED": 10,
    "BIND_ADDRESS_INVALID": 11,
    "BUNDLE_PIN_MISMATCH": 12,
    "LISTENER_FAILED": 13,
    "TRANSFER_TIMEOUT": 14,
    "TRANSFER_REJECTED": 15,
    "AUTHORIZATION_EXPIRED": 16,
    "BUNDLE_SERVED": 0,
}


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def remote_bundle_command(bind_address: str, port: int) -> str:
    if (
        delivery.validate_bind_address(bind_address) != bind_address
        or type(port) is not int
        or not 1 <= port <= 65535
    ):
        raise ValueError("invalid pinned LAN endpoint")
    url = f"http://{bind_address}:{port}{REQUEST_PATH}"
    receiver = "python3 -c " + shlex.quote(_REMOTE_RECEIVER) + " " + " ".join(
        shlex.quote(value)
        for value in (
            pinned.BUNDLE_SHA256,
            str(pinned.BUNDLE_MEMBER_COUNT),
            str(pinned.BUNDLE_SOURCE_BYTES),
            str(pinned.BUNDLE_ARCHIVE_BYTES),
            TARGET_PATH,
        )
    )
    return (
        "umask 077; set -eu; "
        f"archive_file=$(mktemp /tmp/{TASK_PREFIX}.XXXXXX); "
        "trap 'rm -f \"$archive_file\"' EXIT; "
        f"if ! curl -fsS --max-time {TRANSFER_TIMEOUT_SECONDS} --output \"$archive_file\" '{url}' 2>/dev/null; then "
        "printf '%s\\n' BUNDLE_DOWNLOAD_FAILED; exit 1; fi; "
        "if ! hash_line=$(sha256sum \"$archive_file\" 2>/dev/null); then "
        "printf '%s\\n' BUNDLE_HASH_FAILED; exit 1; fi; "
        "actual_hash=${hash_line%% *}; "
        f"if [ \"$actual_hash\" != '{pinned.BUNDLE_SHA256}' ]; then "
        "printf '%s\\n' BUNDLE_DIGEST_MISMATCH; exit 1; fi; "
        f"if ! {receiver} < \"$archive_file\" >/dev/null 2>&1; then "
        "printf '%s\\n' BUNDLE_REJECTED; exit 1; fi; "
        f"if PYTHONDONTWRITEBYTECODE=1 python3 '{TARGET_PATH}/scripts/serve_ephemeral_signed_verifier_https.py' --help >/dev/null 2>&1; then "
        "printf '%s\\n' HOST_BUNDLE_IMPORT_SMOKE_CONFIRMED; else "
        "printf '%s\\n' HOST_BUNDLE_IMPORT_SMOKE_FAILED; exit 1; fi"
    )


def serve_once(
    archive: bytes,
    *,
    bind_address: str,
    port: int,
    output: TextIO,
    server_factory: Callable[..., object],
) -> int:
    if (
        type(archive) is not bytes
        or hashlib.sha256(archive).hexdigest() != pinned.BUNDLE_SHA256
        or len(archive) != pinned.BUNDLE_ARCHIVE_BYTES
    ):
        return _emit("BUNDLE_PIN_MISMATCH", output)
    try:
        server = server_factory((bind_address, port), archive, REQUEST_PATH)
    except Exception:
        return _emit("LISTENER_FAILED", output)
    with server:
        actual_port = server.server_address[1]
        output.write(
            f"BUNDLE_READY|url=http://{bind_address}:{actual_port}{REQUEST_PATH}|"
            f"bytes={len(archive)}|sha256={pinned.BUNDLE_SHA256}|"
            f"members={pinned.BUNDLE_MEMBER_COUNT}\n"
        )
        output.write("On the testdev console run exactly this one-shot command:\n")
        output.write(remote_bundle_command(bind_address, actual_port) + "\n")
        output.flush()
        server.timeout = 900
        try:
            server.handle_request()
        except Exception:
            return _emit("LISTENER_FAILED", output)
        if not server.request_consumed:
            return _emit("TRANSFER_TIMEOUT", output)
        if not server.archive_served:
            return _emit("TRANSFER_REJECTED", output)
    return _emit("BUNDLE_SERVED", output)


def run_once(
    *,
    bind_address: str,
    port: int,
    stdin=None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    bundle_builder: Callable[..., tuple[bytes, str, int, int]] = build_bundle,
    server_factory: Callable[..., object] = delivery._OneShotServer,
    now: datetime | None = None,
) -> int:
    try:
        is_tty = stdin is not None and stdin.isatty() is True
    except Exception:
        is_tty = False
    if not is_tty:
        return _emit("RUN_NOT_CONFIRMED", stdout)
    if (
        delivery.validate_bind_address(bind_address) is None
        or type(port) is not int
        or not 0 <= port <= 65535
    ):
        return _emit("BIND_ADDRESS_INVALID", stdout)
    stderr.write(f"Type {CONFIRMATION_PHRASE} to continue: ")
    stderr.flush()
    try:
        phrase = stdin.readline().rstrip("\r\n")
    except Exception:
        phrase = ""
    if phrase != CONFIRMATION_PHRASE:
        return _emit("RUN_NOT_CONFIRMED", stdout)
    moment = datetime.now(timezone.utc) if now is None else now
    if (
        not isinstance(moment, datetime)
        or moment.tzinfo is None
        or moment.utcoffset() is None
        or moment.astimezone(timezone.utc) >= AUTHORIZATION_EXPIRES_AT
    ):
        return _emit("AUTHORIZATION_EXPIRED", stdout)
    try:
        archive, digest, count, source_bytes = bundle_builder()
    except Exception:
        return _emit("BUNDLE_PIN_MISMATCH", stdout)
    if (
        type(archive) is not bytes
        or digest != pinned.BUNDLE_SHA256
        or count != pinned.BUNDLE_MEMBER_COUNT
        or source_bytes != pinned.BUNDLE_SOURCE_BYTES
        or len(archive) != pinned.BUNDLE_ARCHIVE_BYTES
        or hashlib.sha256(archive).hexdigest() != pinned.BUNDLE_SHA256
    ):
        return _emit("BUNDLE_PIN_MISMATCH", stdout)
    return serve_once(
        archive,
        bind_address=bind_address,
        port=port,
        output=stdout,
        server_factory=server_factory,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind-address", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    return run_once(bind_address=args.bind_address, port=args.port, stdin=sys.stdin)


if __name__ == "__main__":
    raise SystemExit(main())
