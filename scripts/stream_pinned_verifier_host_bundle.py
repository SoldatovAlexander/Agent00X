#!/usr/bin/env python3
"""One-shot, digest-pinned source-bundle transfer; inert on import."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from build_verifier_host_bundle import build_bundle  # noqa: E402
from app_contracts.verifier_process import (  # noqa: E402
    _collect_bounded_output,
    VerifierProcessError,
)


BUNDLE_SHA256 = "2ab1490ffa4cc69de131364eb39246180dc1dd948ae91d86b0ccc77ad37e33e9"
BUNDLE_MEMBER_COUNT = 34
BUNDLE_SOURCE_BYTES = 573_896
BUNDLE_ARCHIVE_BYTES = 614_400
TARGET_HOST = "alex@192.168.88.101"
TARGET_PATH = "/home/alex/.local/share/agent00x/verifier-host/exp-1491"
_SSH_OPTIONS = (
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
    "ClearAllForwardings=yes",
)
_REMOTE_RECEIVER = r'''import hashlib,io,json,os,pathlib,pwd,stat,sys,tarfile
def reject():
 sys.stdout.write("HOST_BUNDLE_REJECTED\n"); return 41
try:
 digest=sys.argv[1]; count=int(sys.argv[2]); source_size=int(sys.argv[3]); archive_size=int(sys.argv[4]); target=pathlib.Path(sys.argv[5])
 raw=sys.stdin.buffer.read(archive_size+1)
 if len(raw)!=archive_size or hashlib.sha256(raw).hexdigest()!=digest: raise ValueError
 with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as tar:
  items=tar.getmembers(); names=[x.name for x in items]
  if len(items)!=count+1 or len(names)!=len(set(names)) or any(not x.isfile() or x.mode!=0o644 or x.uid!=0 or x.gid!=0 or x.pax_headers for x in items): raise ValueError
  files={x.name:tar.extractfile(x).read() for x in items}
 manifest_raw=files["MANIFEST.json"]
 manifest=json.loads(manifest_raw.decode("ascii"))
 canonical=(json.dumps(manifest,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n").encode("ascii")
 if manifest_raw!=canonical or type(manifest)is not dict or set(manifest)!={"schema","files"} or manifest["schema"]!="agent00x-verifier-host-source-bundle/v1" or type(manifest["files"])is not list or len(manifest["files"])!=count: raise ValueError
 source_files={name:data for name,data in files.items() if name!="MANIFEST.json"}
 records=manifest["files"]; paths=[x.get("path") if type(x)is dict else None for x in records]
 if paths!=sorted(source_files) or len(paths)!=len(set(paths)) or sum(map(len,source_files.values()))!=source_size: raise ValueError
 for item in records:
  if type(item)is not dict or set(item)!={"path","size","sha256"}: raise ValueError
  name=item["path"]
  if type(name)is not str or name.startswith("/") or chr(92) in name or ".." in pathlib.PurePosixPath(name).parts or not (name in {"requirements-verifier-host.txt","schemas/checkpoint.schema.json","schemas/observation-event.schema.json","scripts/serve_ephemeral_signed_verifier_https.py"} or (name.startswith("src/app_contracts/") and name.endswith(".py"))): raise ValueError
  data=source_files[name]
  if type(item["size"])is not int or item["size"]!=len(data) or item["sha256"]!=hashlib.sha256(data).hexdigest(): raise ValueError
 home=pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)
 expected=home/".local/share/agent00x/verifier-host/exp-1491"
 if target!=expected: raise ValueError
 current=home
 for part in (".local","share","agent00x","verifier-host"):
  current=current/part
  try: current.mkdir(mode=0o700)
  except FileExistsError:
   st=current.lstat()
   if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_uid!=os.getuid(): raise ValueError
 if target.exists() or target.is_symlink(): raise ValueError
 target.mkdir(mode=0o700)
 for name,data in files.items():
  path=target/name; path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
  with os.fdopen(fd,"wb") as stream: stream.write(data)
except Exception:
 raise SystemExit(reject())
sys.stdout.write("HOST_BUNDLE_IMPORTED|sha256="+digest+"|members="+str(count)+"\n")
'''
_REMOTE_COMMAND = "python3 -c " + shlex.quote(_REMOTE_RECEIVER) + " " + " ".join(
    shlex.quote(value)
    for value in (
        BUNDLE_SHA256,
        str(BUNDLE_MEMBER_COUNT),
        str(BUNDLE_SOURCE_BYTES),
        str(BUNDLE_ARCHIVE_BYTES),
        TARGET_PATH,
    )
)
_EXPECTED_REMOTE = (
    f"HOST_BUNDLE_IMPORTED|sha256={BUNDLE_SHA256}|members={BUNDLE_MEMBER_COUNT}\n".encode(
        "ascii"
    )
)
_MARKER_CODES = {
    "BUNDLE_PIN_MISMATCH": 10,
    "SSH_OR_REMOTE_FAILED": 11,
    "HOST_BUNDLE_REJECTED": 12,
    "BUNDLE_TRANSFER_CONFIRMED": 0,
    "RUN_NOT_CONFIRMED": 19,
}
_REMOTE_FAILURE = b"HOST_BUNDLE_REJECTED\n"
Runner = Callable[..., subprocess.Popen]
Collector = Callable[..., tuple[bytes, bytes, int]]


def _ssh_environment() -> dict[str, str]:
    """Pass only standard SSH runtime values, never unrelated credentials."""

    environment = {
        "HOME": str(Path.home()),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
    }
    agent_socket = os.environ.get("SSH_AUTH_SOCK")
    if type(agent_socket) is str and agent_socket:
        environment["SSH_AUTH_SOCK"] = agent_socket
    return environment


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def run_transfer(
    *,
    popen_factory: Runner | None = None,
    collector: Collector | None = None,
    bundle_builder: Callable[..., tuple[bytes, str, int, int]] | None = None,
    output: TextIO | None = None,
) -> int:
    """Transfer exactly one reviewed bundle and emit a fixed result marker."""

    popen = subprocess.Popen if popen_factory is None else popen_factory
    collect = _collect_bounded_output if collector is None else collector
    build = build_bundle if bundle_builder is None else bundle_builder
    result = sys.stdout if output is None else output
    try:
        archive, digest, members, source_bytes = build()
    except Exception:
        return _emit("BUNDLE_PIN_MISMATCH", result)
    if (
        type(archive) is not bytes
        or digest != BUNDLE_SHA256
        or members != BUNDLE_MEMBER_COUNT
        or source_bytes != BUNDLE_SOURCE_BYTES
        or len(archive) != BUNDLE_ARCHIVE_BYTES
    ):
        return _emit("BUNDLE_PIN_MISMATCH", result)

    command: Sequence[str] = (
        "/usr/bin/ssh",
        *_SSH_OPTIONS,
        TARGET_HOST,
        _REMOTE_COMMAND,
    )
    try:
        process = popen(
            list(command),
            executable="/usr/bin/ssh",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=_ssh_environment(),
        )
        stdout, _stderr, returncode = collect(
            process,
            archive,
            stdout_cap=256,
            stderr_cap=4096,
            timeout_seconds=90,
        )
    except Exception:
        return _emit("SSH_OR_REMOTE_FAILED", result)
    if returncode != 0:
        if stdout == _REMOTE_FAILURE:
            return _emit("HOST_BUNDLE_REJECTED", result)
        return _emit("SSH_OR_REMOTE_FAILED", result)
    if stdout != _EXPECTED_REMOTE:
        return _emit("SSH_OR_REMOTE_FAILED", result)
    return _emit("BUNDLE_TRANSFER_CONFIRMED", result)


def main() -> int:
    sys.stderr.write("Type RUN EXP-1493 ONCE to continue: ")
    sys.stderr.flush()
    if sys.stdin.readline().rstrip("\r\n") != "RUN EXP-1493 ONCE":
        return _emit("RUN_NOT_CONFIRMED", sys.stdout)
    return run_transfer()


if __name__ == "__main__":
    raise SystemExit(main())
