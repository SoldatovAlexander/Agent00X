#!/usr/bin/env python3
"""Capture one public testdev bootstrap over strict SSH without TTY pasting."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import import_testdev_verifier_bootstrap as importer  # noqa: E402
from scripts.transfer_pinned_verifier_host_bundle_exp1904 import (  # noqa: E402
    KNOWN_HOSTS_PATH,
    _check_known_host,
)


CARD_ID = "EXP-2973"
GATE = "RUN EXP-2973 ONCE"
EXPIRES_AT = datetime(2026, 10, 29, 20, 0, tzinfo=timezone.utc)
OUTPUT = Path("/Volumes/AlexDATA/Agent00X-local-evidence/verifier-bootstrap-exp2973.json")
ATTEMPT = Path("/Volumes/AlexDATA/Agent00X-local-evidence/verifier-bootstrap-exp2973.attempted")
TARGET_HOST = "alex@192.168.88.101"
REMOTE_SCRIPT = "/home/alex/.local/share/agent00x/verifier-host/exp-2927/scripts/serve_ephemeral_signed_verifier_https.py"
REMOTE_COMMAND = (
    "PYTHONDONTWRITEBYTECODE=1 python3 "
    + REMOTE_SCRIPT
    + " --bind-address 192.168.88.101 --allowed-peer-address 192.168.88.5 --port 0"
)


def ssh_command() -> tuple[str, ...]:
    return (
        "/usr/bin/ssh", "-F", "/dev/null", "-T",
        "-oBatchMode=yes", "-oStrictHostKeyChecking=yes",
        f"-oUserKnownHostsFile={KNOWN_HOSTS_PATH}",
        "-oGlobalKnownHostsFile=/dev/null", "-oHostKeyAlgorithms=ssh-ed25519",
        "-oPreferredAuthentications=publickey", "-oPasswordAuthentication=no",
        "-oKbdInteractiveAuthentication=no", "-oNumberOfPasswordPrompts=0",
        "-oForwardAgent=no", "-oClearAllForwardings=yes",
        "-oConnectTimeout=10", "-oConnectionAttempts=1",
        TARGET_HOST, REMOTE_COMMAND,
    )


def _environment() -> dict[str, str]:
    env = {"HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"}
    agent_socket = os.environ.get("SSH_AUTH_SOCK")
    if agent_socket:
        env["SSH_AUTH_SOCK"] = agent_socket
    return env


class _LazySSHBootstrapLine:
    """Start SSH only when the base importer has accepted its TTY gate."""

    def __init__(self, *, runner=subprocess.Popen):
        self.runner = runner
        self.process = None
        self.capture = None

    def readline(self, limit: int = -1) -> bytes:
        try:
            self.capture = tempfile.TemporaryFile(mode="w+b")
            self.process = self.runner(
                ssh_command(),
                executable="/usr/bin/ssh",
                stdin=subprocess.DEVNULL,
                stdout=self.capture,
                stderr=subprocess.DEVNULL,
                shell=False,
                env=_environment(),
                start_new_session=True,
            )
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                self.capture.flush()
                if os.fstat(self.capture.fileno()).st_size:
                    self.capture.seek(0)
                    raw = self.capture.readline(8193)
                    if raw.endswith(b"\n") and len(raw) <= 8192:
                        return raw
                    raise ValueError
                if self.process.poll() is not None:
                    raise ValueError
                time.sleep(0.05)
            raise TimeoutError
        except Exception:
            self.stop()
            return b""

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


def main(argv: list[str] | None = None, **kwargs: Any) -> int:
    if not _check_known_host():
        print("EXP2973_HOST_KEY_PREFLIGHT_REJECTED")
        return 2
    names = (
        "AUTHORIZATION_PROFILES", "AUTHORIZATION_EXPIRES_AT",
        "BOOTSTRAP_OUTPUTS", "ATTEMPT_MARKERS",
    )
    original = {name: getattr(importer, name) for name in names}
    stream = _LazySSHBootstrapLine()
    try:
        importer.AUTHORIZATION_PROFILES = {
            **importer.AUTHORIZATION_PROFILES, CARD_ID: GATE,
        }
        importer.AUTHORIZATION_EXPIRES_AT = {
            **importer.AUTHORIZATION_EXPIRES_AT, CARD_ID: EXPIRES_AT,
        }
        importer.BOOTSTRAP_OUTPUTS = {
            **importer.BOOTSTRAP_OUTPUTS, CARD_ID: str(OUTPUT),
        }
        importer.ATTEMPT_MARKERS = {
            **importer.ATTEMPT_MARKERS, CARD_ID: str(ATTEMPT),
        }
        code = importer.main(
            ["--authorization-card-id", CARD_ID, "--bootstrap-output", str(OUTPUT)]
            if argv is None else argv,
            stdin=stream,
            **kwargs,
        )
        if code != 0:
            stream.stop()
            return code
        if stream.process is None or stream.process.poll() is not None:
            print("EXP2973_LISTENER_EXITED")
            return 2
        print("EXP2973_LISTENER_ACTIVE")
        return 0
    finally:
        for name, value in original.items():
            setattr(importer, name, value)


if __name__ == "__main__":
    raise SystemExit(main())
