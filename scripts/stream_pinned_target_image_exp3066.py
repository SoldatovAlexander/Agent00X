#!/usr/bin/env python3
"""One-shot transfer of the exact target image to testdev; inert on import."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Callable, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID  # noqa: E402
from scripts.transfer_pinned_verifier_host_bundle_exp1904 import (  # noqa: E402
    KNOWN_HOSTS_PATH,
    _check_known_host,
)

GATE = "RUN EXP-3066 ONCE"
TARGET_HOST = "alex@192.168.88.101"
# The pinned local object is an OCI manifest digest in the containerd-backed
# store. Docker-save serializes its config under a distinct content digest;
# classic Docker stores address the loaded image by that config ID.
TARGET_CONFIG_IMAGE_ID = "sha256:e56aa02407e6e149bd779d167d383a0eef47ba13ecc293ada6178ffca0a115d7"
IMAGE_SIZE = 48_796_358
STREAM_SIZE = 48_808_960
STREAM_SHA256 = "1a325a87f6c334c221172708784375a9497873b3e4a739cc7c57823e515c9722"
OS = "linux"
ARCH = "amd64"
DIFF_IDS = (
    "sha256:a6dc765193a52cbaede3c93a9ff48b9540948dd0774bbe7031fcb5847606f9ac",
    "sha256:a5c84380b3657bb723a1f71fa963f1e3a3f01e2c6bcba12e3b9a0d336158c7a9",
    "sha256:4a01ba3ac604812ef31dab0006efecd1d572676f7a68afa169a9d57883025006",
    "sha256:d190d09d7bd91836f809045799a7024a54026b3da5de1ccb811627fcf9878b92",
    "sha256:6fdb05443047d4f59586723590db290d1fdc46d9778c17946d484e75063c86a4",
    "sha256:186639581a0fc77c7a2817ad2fc2a305e22bb0bdf3735a5ce3790ea7a5c3a35a",
)
DIFF_JSON = json.dumps(DIFF_IDS, separators=(",", ":"))
LOCAL_INSPECT_FORMAT = (
    "{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|"
    "{{json .RootFS.Layers}}|{{json .RepoTags}}"
)
REMOTE_INSPECT_FORMAT = (
    "{{.Id}}|{{.Os}}|{{.Architecture}}|"
    "{{json .RootFS.Layers}}|{{json .RepoTags}}"
)
EXPECTED_LOCAL = (
    f"{TARGET_RUNTIME_IMAGE_ID}|{OS}|{ARCH}|{IMAGE_SIZE}|{DIFF_JSON}|[]"
)
EXPECTED_REMOTE = (
    f"{TARGET_CONFIG_IMAGE_ID}|{OS}|{ARCH}|{DIFF_JSON}|[]"
)
EVIDENCE_DIR = Path("/Volumes/AlexDATA/Agent00X-local-evidence")
ATTEMPT_MARKER = EVIDENCE_DIR / "exp3066-image-import.attempted"
AUTHORIZATION_EXPIRES_AT = "2026-10-29T20:00:00+00:00"
REMOTE_RECEIVER = r'''import hashlib,os,subprocess,sys
def fail(marker,code):
 sys.stdout.write(marker+"\n"); sys.stdout.flush(); raise SystemExit(code)
try:
 digest,size,expected_id,expected=sys.argv[1:]
 size=int(size)
 raw=sys.stdin.buffer.read(size+1)
 if size<=0 or size>200000000 or len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest:
  fail("REMOTE_ARCHIVE_REJECTED",41)
except SystemExit: raise
except Exception: fail("REMOTE_ARCHIVE_REJECTED",41)
env={"PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C","HOME":"/home/alex"}
try:
 loaded=subprocess.run(["/usr/bin/docker","image","load"],input=raw,capture_output=True,check=False,timeout=300,env=env)
except Exception: fail("REMOTE_IMAGE_LOAD_FAILED",42)
if loaded.returncode!=0: fail("REMOTE_IMAGE_LOAD_FAILED",42)
try:
 inspected=subprocess.run(["/usr/bin/docker","image","inspect",expected_id,"--format","{{.Id}}|{{.Os}}|{{.Architecture}}|{{json .RootFS.Layers}}|{{json .RepoTags}}"],capture_output=True,check=False,timeout=25,env=env)
except Exception: fail("REMOTE_IMAGE_IDENTITY_MISMATCH",43)
if inspected.returncode!=0 or inspected.stdout!=(expected+"\n").encode("ascii"):
 fail("REMOTE_IMAGE_IDENTITY_MISMATCH",43)
sys.stdout.write("EXP3066_IMAGE_IMPORT_CONFIRMED\n"); sys.stdout.flush()
'''
_SSH_OPTIONS = (
    "-T", "-F", "/dev/null", "-oBatchMode=yes",
    "-oStrictHostKeyChecking=yes", f"-oUserKnownHostsFile={KNOWN_HOSTS_PATH}",
    "-oGlobalKnownHostsFile=/dev/null", "-oHostKeyAlgorithms=ssh-ed25519",
    "-oConnectTimeout=8", "-oConnectionAttempts=1",
    "-oPreferredAuthentications=publickey", "-oPasswordAuthentication=no",
    "-oKbdInteractiveAuthentication=no", "-oNumberOfPasswordPrompts=0",
    "-oForwardAgent=no", "-oClearAllForwardings=yes",
)
Runner = Callable[..., subprocess.CompletedProcess[bytes]]
_CODES = {
    "HOST_KEY_PREFLIGHT_REJECTED": 10,
    "RUN_NOT_CONFIRMED": 11,
    "AUTHORIZATION_EXPIRED": 12,
    "ATTEMPT_MARKER_REJECTED": 13,
    "LOCAL_IMAGE_INSPECT_FAILED": 14,
    "LOCAL_IMAGE_IDENTITY_MISMATCH": 15,
    "LOCAL_IMAGE_SAVE_FAILED": 16,
    "LOCAL_ARCHIVE_PIN_MISMATCH": 17,
    "LOCAL_ARCHIVE_CONTENT_MISMATCH": 22,
    "SSH_FAILED": 18,
    "REMOTE_ARCHIVE_REJECTED": 19,
    "REMOTE_IMAGE_LOAD_FAILED": 20,
    "REMOTE_IMAGE_IDENTITY_MISMATCH": 21,
    "IMAGE_IMPORT_CONFIRMED": 0,
}
_REMOTE_MARKERS = {
    b"REMOTE_ARCHIVE_REJECTED\n": "REMOTE_ARCHIVE_REJECTED",
    b"REMOTE_IMAGE_LOAD_FAILED\n": "REMOTE_IMAGE_LOAD_FAILED",
    b"REMOTE_IMAGE_IDENTITY_MISMATCH\n": "REMOTE_IMAGE_IDENTITY_MISMATCH",
}


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    output.flush()
    return _CODES[marker]


def _env() -> dict[str, str]:
    env = {"HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"}
    if os.environ.get("SSH_AUTH_SOCK"):
        env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
    return env


def _reserve_attempt() -> None:
    fd = os.open(
        ATTEMPT_MARKER,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "wb") as marker:
        marker.write(b"EXP-3066_ATTEMPTED\n")
        marker.flush()
        os.fsync(marker.fileno())


def _exact_line(value: bytes) -> str | None:
    try:
        decoded = value.decode("ascii")
    except (AttributeError, UnicodeDecodeError):
        return None
    return decoded[:-1] if decoded.endswith("\n") and decoded.count("\n") == 1 else None


def _validate_archive_content(stream: bytes) -> bool:
    """Check pinned Docker-save manifest/config identity without extraction."""
    try:
        with tarfile.open(fileobj=io.BytesIO(stream), mode="r:") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if (
                len(names) != len(set(names))
                or any(not member.isfile() for member in members)
            ):
                return False
            manifest_file = archive.extractfile("manifest.json")
            if manifest_file is None:
                return False
            manifest = json.loads(manifest_file.read())
            if type(manifest) is not list or len(manifest) != 1:
                return False
            record = manifest[0]
            if (
                type(record) is not dict
                or set(record) != {"Config", "RepoTags", "Layers"}
                or record["RepoTags"] not in (None, [])
                or type(record["Layers"]) is not list
                or len(record["Layers"]) != len(DIFF_IDS)
            ):
                return False
            config_name = record["Config"]
            config_path = Path(config_name) if type(config_name) is str else None
            if (
                config_path is None
                or config_path.is_absolute()
                or ".." in config_path.parts
                or "\\" in config_name
            ):
                return False
            config_file = archive.extractfile(config_name)
            if config_file is None:
                return False
            config_bytes = config_file.read()
            if f"sha256:{hashlib.sha256(config_bytes).hexdigest()}" != TARGET_CONFIG_IMAGE_ID:
                return False
            config = json.loads(config_bytes)
            return config.get("rootfs", {}).get("diff_ids") == list(DIFF_IDS)
    except Exception:
        return False


def run_once(
    *, runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
    host_check: Callable[[], bool] = _check_known_host,
    archive_validator: Callable[[bytes], bool] = _validate_archive_content,
    now=None,
) -> int:
    from datetime import datetime, timezone

    moment = datetime.now(timezone.utc) if now is None else now
    if moment >= datetime.fromisoformat(AUTHORIZATION_EXPIRES_AT):
        return _emit("AUTHORIZATION_EXPIRED", output)
    try:
        if not host_check():
            return _emit("HOST_KEY_PREFLIGHT_REJECTED", output)
    except Exception:
        return _emit("HOST_KEY_PREFLIGHT_REJECTED", output)

    try:
        inspected = runner(
            ("/usr/local/bin/docker", "image", "inspect", "--format", LOCAL_INSPECT_FORMAT, TARGET_RUNTIME_IMAGE_ID),
            capture_output=True, timeout=15, check=False,
        )
    except Exception:
        return _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
    if inspected.returncode != 0:
        return _emit("LOCAL_IMAGE_INSPECT_FAILED", output)
    if _exact_line(inspected.stdout) != EXPECTED_LOCAL:
        return _emit("LOCAL_IMAGE_IDENTITY_MISMATCH", output)
    try:
        saved = runner(
            ("/usr/local/bin/docker", "image", "save", TARGET_RUNTIME_IMAGE_ID),
            capture_output=True, timeout=90, check=False,
        )
    except Exception:
        return _emit("LOCAL_IMAGE_SAVE_FAILED", output)
    if saved.returncode != 0 or type(saved.stdout) is not bytes:
        return _emit("LOCAL_IMAGE_SAVE_FAILED", output)
    stream = saved.stdout
    if len(stream) != STREAM_SIZE or hashlib.sha256(stream).hexdigest() != STREAM_SHA256:
        return _emit("LOCAL_ARCHIVE_PIN_MISMATCH", output)
    try:
        if archive_validator(stream) is not True:
            return _emit("LOCAL_ARCHIVE_CONTENT_MISMATCH", output)
    except Exception:
        return _emit("LOCAL_ARCHIVE_CONTENT_MISMATCH", output)
    try:
        _reserve_attempt()
    except Exception:
        return _emit("ATTEMPT_MARKER_REJECTED", output)
    remote_args = (STREAM_SHA256, str(STREAM_SIZE), TARGET_CONFIG_IMAGE_ID, EXPECTED_REMOTE)
    remote_command = "python3 -c " + shlex.quote(REMOTE_RECEIVER) + " " + " ".join(
        shlex.quote(value) for value in remote_args
    )
    command: Sequence[str] = (
        "/usr/bin/ssh", *_SSH_OPTIONS, TARGET_HOST, remote_command,
    )
    try:
        result = runner(
            command, input=stream, capture_output=True, timeout=420, check=False, env=_env()
        )
    except Exception:
        return _emit("SSH_FAILED", output)
    if result.returncode != 0:
        return _emit(_REMOTE_MARKERS.get(result.stdout, "SSH_FAILED"), output)
    if _exact_line(result.stdout) != "EXP3066_IMAGE_IMPORT_CONFIRMED":
        return _emit("SSH_FAILED", output)
    return _emit("IMAGE_IMPORT_CONFIRMED", output)


def main() -> int:
    sys.stderr.write(f"Type {GATE} to continue: ")
    sys.stderr.flush()
    if not sys.stdin.isatty() or sys.stdin.readline().rstrip("\r\n") != GATE:
        return _emit("RUN_NOT_CONFIRMED", sys.stdout)
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
