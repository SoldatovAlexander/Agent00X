"""Capture a public verifier bootstrap without exposing it to tool output.

This module is inert on import. Calling ``start_pinned_verifier_session`` is a
live SSH operation and requires a separate exact task card and user gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import selectors
import subprocess
import time
from typing import Callable, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.verifier_bootstrap_preflight import (  # noqa: E402
    MAX_BOOTSTRAP_BYTES,
    BoundPublicVerifierBootstrap,
    parse_pinned_public_verifier_bootstrap,
)


TARGET_HOST = "alex@192.168.88.101"
LOCAL_FORWARD = "127.0.0.1:49234:127.0.0.1:49231"
REMOTE_LAUNCHER = (
    "/home/alex/.local/share/agent00x/verifier-host/exp-1491/scripts/"
    "serve_ephemeral_signed_verifier_https.py"
)
REMOTE_COMMAND = f"python3 {REMOTE_LAUNCHER} --port 49231"
BOOTSTRAP_TIMEOUT_SECONDS = 30.0
SESSION_TIMEOUT_SECONDS = 910.0
STOP_TIMEOUT_SECONDS = 5.0
_ERROR = "BOOTSTRAP_CAPTURE_REJECTED"

Runner = Callable[..., subprocess.Popen[bytes]]


class VerifierBootstrapCaptureError(RuntimeError):
    """A fixed, redacted failure while starting or capturing the tunnel."""

    def __init__(self) -> None:
        super().__init__("verifier bootstrap capture: rejected")


def _ssh_command() -> tuple[str, ...]:
    return (
        "/usr/bin/ssh",
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
        "ExitOnForwardFailure=yes",
        "-o",
        "ClearAllForwardings=yes",
        "-L",
        LOCAL_FORWARD,
        TARGET_HOST,
        REMOTE_COMMAND,
    )


def _ssh_environment() -> dict[str, str]:
    env = {"HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"}
    agent = os.environ.get("SSH_AUTH_SOCK")
    if type(agent) is str and agent:
        env["SSH_AUTH_SOCK"] = agent
    return env


def _read_bootstrap_line(
    stream,
    process,
    *,
    timeout_seconds: float = BOOTSTRAP_TIMEOUT_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    selector_factory=selectors.DefaultSelector,
) -> bytes:
    if (
        type(timeout_seconds) not in (int, float)
        or timeout_seconds <= 0
        or timeout_seconds > BOOTSTRAP_TIMEOUT_SECONDS
    ):
        raise VerifierBootstrapCaptureError
    selector = selector_factory()
    raw = bytearray()
    try:
        selector.register(stream, selectors.EVENT_READ)
        deadline = monotonic() + timeout_seconds
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0 or process.poll() is not None:
                raise VerifierBootstrapCaptureError
            if not selector.select(remaining):
                raise VerifierBootstrapCaptureError
            chunk = os.read(stream.fileno(), min(4096, MAX_BOOTSTRAP_BYTES + 1 - len(raw)))
            if not chunk:
                raise VerifierBootstrapCaptureError
            raw.extend(chunk)
            if len(raw) > MAX_BOOTSTRAP_BYTES:
                raise VerifierBootstrapCaptureError
            if b"\n" in raw:
                if raw.count(b"\n") != 1 or not raw.endswith(b"\n"):
                    raise VerifierBootstrapCaptureError
                return bytes(raw)
    except VerifierBootstrapCaptureError:
        raise
    except Exception:
        raise VerifierBootstrapCaptureError from None
    finally:
        selector.close()


def _write_public_bootstrap(path_value: object, raw: bytes) -> None:
    descriptor = None
    created = None
    try:
        if type(path_value) is not str or not path_value:
            raise ValueError
        path = Path(path_value)
        if not path.is_absolute() or not path.parent.is_dir() or path.is_symlink():
            raise ValueError
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if type(nofollow) is not int:
            raise ValueError
        descriptor = os.open(path, flags | nofollow, 0o600)
        created = os.fstat(descriptor)
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OSError
            view = view[count:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        final = os.fstat(descriptor)
        if final.st_size != len(raw) or final.st_mode & 0o777 != 0o600:
            raise OSError
    except Exception:
        if descriptor is not None and created is not None:
            try:
                current = os.stat(path, follow_symlinks=False)
                if current.st_dev == created.st_dev and current.st_ino == created.st_ino:
                    os.unlink(path)
            except Exception:
                pass
        raise VerifierBootstrapCaptureError from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _stop_and_reap(process) -> None:
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
        else:
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except Exception:
        pass


@dataclass
class ActiveVerifierSession:
    """A held SSH forward plus its validated public bootstrap."""

    process: subprocess.Popen[bytes]
    bootstrap: bytes
    bound: BoundPublicVerifierBootstrap

    def wait(self, *, timeout_seconds: float = SESSION_TIMEOUT_SECONDS) -> int:
        if (
            type(timeout_seconds) not in (int, float)
            or timeout_seconds <= 0
            or timeout_seconds > SESSION_TIMEOUT_SECONDS
        ):
            raise VerifierBootstrapCaptureError
        try:
            code = self.process.wait(timeout=timeout_seconds)
        except Exception:
            raise VerifierBootstrapCaptureError from None
        if type(code) is not int or code not in (0, 2):
            raise VerifierBootstrapCaptureError
        return code

    def stop(self) -> None:
        _stop_and_reap(self.process)


def start_pinned_verifier_session(
    bootstrap_path: str,
    *,
    popen_factory: Runner | None = None,
    output: TextIO | None = None,
    line_reader: Callable[..., bytes] = _read_bootstrap_line,
    parser: Callable[..., BoundPublicVerifierBootstrap] = parse_pinned_public_verifier_bootstrap,
) -> ActiveVerifierSession:
    """Start one forward, validate/persist its bootstrap, and retain the SSH handle."""

    result = sys.stdout if output is None else output
    path = Path(bootstrap_path)
    if (
        not path.is_absolute()
        or not path.parent.is_dir()
        or path.exists()
        or path.is_symlink()
    ):
        result.write(_ERROR + "\n")
        raise VerifierBootstrapCaptureError

    process = None
    try:
        popen = subprocess.Popen if popen_factory is None else popen_factory
        process = popen(
            list(_ssh_command()),
            executable="/usr/bin/ssh",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            bufsize=0,
            env=_ssh_environment(),
        )
        if process.stdout is None:
            raise VerifierBootstrapCaptureError
        raw = line_reader(process.stdout, process)
        expected = "sha256:" + hashlib.sha256(raw).hexdigest()
        bound = parser(raw, expected_sha256=expected)
        if bound.connect_port != 49231 or bound.trust_established:
            raise VerifierBootstrapCaptureError
        _write_public_bootstrap(bootstrap_path, raw)
        result.write(
            f"BOOTSTRAP_CAPTURED|{expected}|port={bound.connect_port}|trust=unestablished\n"
        )
        result.flush()
        return ActiveVerifierSession(process=process, bootstrap=raw, bound=bound)
    except Exception:
        if process is not None:
            _stop_and_reap(process)
        result.write(_ERROR + "\n")
        result.flush()
        raise VerifierBootstrapCaptureError from None
