#!/usr/bin/env python3
"""One-shot, credential-free LAN delivery of the exact public verifier image.

This helper only serves a pinned image archive over a temporary, read-only
HTTP listener. A user operates the verifier host separately; this process does
not SSH, run Docker remotely, start a verifier, or claim remote import success.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.server
import ipaddress
import io
import subprocess
import sys
from pathlib import Path
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import audit_pinned_verifier_save_archive as archive_audit
from scripts import stream_pinned_verifier_image as pinned


CONFIRMATION_PHRASE = "RUN EXP-1654 ONCE"
AUTHORIZATION_EXPIRES_AT = datetime(2026, 10, 20, 16, 19, 21, tzinfo=timezone.utc)
TARGET_ADDRESS = "192.168.88.101"
REQUEST_PATH = "/exp-1654/verifier-image.tar"
IDLE_TIMEOUT_SECONDS = 900
TRANSFER_TIMEOUT_SECONDS = 180
_REMOTE_EXPECTED_TUPLE = pinned._EXPECTED_REMOTE_INSPECT

_MARKER_CODES = {
    "RUN_NOT_CONFIRMED": 10,
    "BIND_ADDRESS_INVALID": 11,
    "LOCAL_IMAGE_INSPECT_FAILED": 12,
    "LOCAL_IMAGE_IDENTITY_MISMATCH": 13,
    "LOCAL_IMAGE_SAVE_FAILED": 14,
    "LOCAL_ARCHIVE_INVALID": 15,
    "LISTENER_FAILED": 16,
    "TRANSFER_TIMEOUT": 17,
    "TRANSFER_REJECTED": 18,
    "PREPARED_INPUT_INVALID": 19,
    "AUTHORIZATION_EXPIRED": 20,
    "ARCHIVE_SERVED": 0,
}

Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def validate_bind_address(value: object) -> str | None:
    """Accept only an explicit private unicast IPv4 interface address."""
    if type(value) is not str:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if (
        type(address) is not ipaddress.IPv4Address
        or not address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
    ):
        return None
    return str(address)


def prepare_archive(
    runner: Runner = subprocess.run,
    *,
    output: TextIO = sys.stdout,
) -> bytes | None:
    """Inspect/save the exact local image and validate its full archive in RAM."""
    inspect_command = (
        "/usr/local/bin/docker",
        "image",
        "inspect",
        "--format",
        pinned._INSPECT_FORMAT,
        pinned.IMAGE_ID,
    )
    try:
        inspected = runner(
            inspect_command, capture_output=True, timeout=15, check=False
        )
    except Exception:
        _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
        return None
    if inspected.returncode != 0:
        _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
        return None
    try:
        local_tuple = inspected.stdout.decode("ascii").removesuffix("\n")
    except (AttributeError, UnicodeDecodeError):
        local_tuple = ""
    if local_tuple != pinned._EXPECTED_INSPECT:
        _emit("LOCAL_IMAGE_IDENTITY_MISMATCH", output)
        return None

    try:
        saved = runner(
            ("/usr/local/bin/docker", "image", "save", pinned.IMAGE_ID),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except Exception:
        _emit("LOCAL_IMAGE_SAVE_FAILED", output)
        return None
    if saved.returncode != 0 or type(saved.stdout) is not bytes:
        _emit("LOCAL_IMAGE_SAVE_FAILED", output)
        return None

    validation_output = io.StringIO()
    try:
        validation_code = archive_audit.inspect_archive(
            saved.stdout,
            image_id=pinned.REMOTE_CONFIG_IMAGE_ID,
            diff_ids=pinned.DIFF_IDS,
            stream_size=pinned.STREAM_SIZE,
            output=validation_output,
        )
    except Exception:
        _emit("LOCAL_ARCHIVE_INVALID", output)
        return None
    expected_marker = (
        f"ARCHIVE_CONFIRMED|{pinned.REMOTE_CONFIG_IMAGE_ID}|{pinned.STREAM_SIZE}|"
        f"{len(pinned.DIFF_IDS)}|"
    )
    if (
        validation_code != archive_audit._MARKER_CODES["ARCHIVE_CONFIRMED"]
        or not validation_output.getvalue().startswith(expected_marker)
    ):
        _emit("LOCAL_ARCHIVE_INVALID", output)
        return None
    return saved.stdout


def remote_import_command(bind_address: str, port: int, archive_sha256: str) -> str:
    """Return a shell command for the user to run on the target's open console."""
    url = f"http://{bind_address}:{port}{REQUEST_PATH}"
    expected = _REMOTE_EXPECTED_TUPLE
    fmt = pinned._REMOTE_INSPECT_FORMAT
    if (
        type(archive_sha256) is not str
        or len(archive_sha256) != 64
        or any(character not in "0123456789abcdef" for character in archive_sha256)
    ):
        raise ValueError("archive digest must be lowercase SHA-256 hex")
    return (
        "umask 077; set -eu; "
        "archive_file=$(mktemp /tmp/agent00x-exp1654.XXXXXX); "
        "trap 'rm -f \"$archive_file\"' EXIT; "
        f"if ! curl -fsS --max-time {TRANSFER_TIMEOUT_SECONDS} --output \"$archive_file\" '{url}' 2>/dev/null; then "
        "printf '%s\\n' IMAGE_DOWNLOAD_FAILED; exit 1; fi; "
        "if ! hash_line=$(sha256sum \"$archive_file\" 2>/dev/null); then "
        "printf '%s\\n' IMAGE_HASH_FAILED; exit 1; fi; "
        "actual_hash=${hash_line%% *}; "
        f"if [ \"$actual_hash\" != '{archive_sha256}' ]; then "
        "printf '%s\\n' ARCHIVE_DIGEST_MISMATCH; exit 1; fi; "
        "if ! docker image load --input \"$archive_file\" >/dev/null 2>&1; then "
        "printf '%s\\n' IMAGE_IMPORT_FAILED; exit 1; fi; "
        f"if actual=$(docker image inspect '{pinned.REMOTE_CONFIG_IMAGE_ID}' "
        f"--format '{fmt}' 2>/dev/null) && [ \"$actual\" = '{expected}' ]; then "
        "printf '%s\\n' IMAGE_IMPORT_CONFIRMED; else "
        "printf '%s\\n' IMAGE_IDENTITY_MISMATCH; exit 1; fi"
    )


class _OneShotServer(http.server.HTTPServer):
    allow_reuse_address = False
    request_queue_size = 1

    def __init__(self, address: tuple[str, int], archive: bytes):
        self.archive = archive
        self.request_consumed = False
        self.archive_served = False
        super().__init__(address, _ArchiveHandler, bind_and_activate=True)
        self.timeout = IDLE_TIMEOUT_SECONDS

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(TRANSFER_TIMEOUT_SECONDS + 10)
        return request, client_address

    def handle_error(self, _request, _client_address) -> None:
        return


class _ArchiveHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _reply(self, status: int, body: bytes = b"") -> bool:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 200:
            self.send_header("Content-Type", "application/vnd.docker.image.tar")
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return False
        return True

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        server = self.server
        if server.request_consumed:
            self._reply(410)
            return
        server.request_consumed = True
        if self.client_address[0] != TARGET_ADDRESS:
            self._reply(403)
            return
        if self.path != REQUEST_PATH:
            self._reply(404)
            return
        server.archive_served = self._reply(200, server.archive)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler contract
        self._reply(405)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        self._reply(405)


def serve_once(
    archive: bytes,
    *,
    bind_address: str,
    port: int,
    output: TextIO = sys.stdout,
    server_factory: Callable[..., _OneShotServer] = _OneShotServer,
) -> int:
    if (
        validate_bind_address(bind_address) != bind_address
        or type(port) is not int
        or not 0 <= port <= 65535
        or type(archive) is not bytes
        or len(archive) != pinned.STREAM_SIZE
    ):
        return _emit("PREPARED_INPUT_INVALID", output)
    try:
        server = server_factory((bind_address, port), archive)
    except Exception:
        return _emit("LISTENER_FAILED", output)
    with server:
        actual_port = server.server_address[1]
        archive_digest = hashlib.sha256(archive).hexdigest()
        output.write(
            f"IMAGE_READY|url=http://{bind_address}:{actual_port}{REQUEST_PATH}|"
            f"bytes={len(archive)}|archive_sha256={archive_digest}\n"
        )
        output.write("On the testdev console run exactly this one-shot command:\n")
        output.write(
            remote_import_command(bind_address, actual_port, archive_digest) + "\n"
        )
        output.flush()
        try:
            server.handle_request()
        except Exception:
            return _emit("LISTENER_FAILED", output)
        if not server.request_consumed:
            return _emit("TRANSFER_TIMEOUT", output)
        if not server.archive_served:
            return _emit("TRANSFER_REJECTED", output)
    return _emit("ARCHIVE_SERVED", output)


def run_once(
    *,
    bind_address: str,
    port: int,
    stdin=None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    runner: Runner = subprocess.run,
    server_factory: Callable[..., _OneShotServer] = _OneShotServer,
    now: datetime | None = None,
) -> int:
    try:
        is_tty = stdin is not None and stdin.isatty() is True
    except Exception:
        is_tty = False
    if not is_tty:
        return _emit("RUN_NOT_CONFIRMED", stdout)
    if validate_bind_address(bind_address) is None or type(port) is not int or not 0 <= port <= 65535:
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

    preparation_output = io.StringIO()
    archive = prepare_archive(runner, output=preparation_output)
    if archive is None:
        marker = preparation_output.getvalue().strip()
        if marker not in _MARKER_CODES:
            marker = "LOCAL_ARCHIVE_INVALID"
        return _emit(marker, stdout)
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
    return run_once(
        bind_address=args.bind_address,
        port=args.port,
        stdin=sys.stdin,
    )


if __name__ == "__main__":
    raise SystemExit(main())
