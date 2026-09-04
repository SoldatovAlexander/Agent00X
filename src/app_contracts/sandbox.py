"""Sandbox backend contract and a development-only local process backend.

The process backend proves workspace lifecycle and command allowlisting. It does
not claim network or kernel isolation and therefore cannot satisfy VP-02. A
Docker/Podman backend must replace it for the security milestone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from typing import Protocol, Sequence


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class SandboxSession(Protocol):
    security_profile: str
    network_isolated: bool
    workspace: Path

    def run(self, argv: Sequence[str], timeout_seconds: int = 30) -> CommandResult: ...
    def close(self) -> None: ...


class SandboxBackend(Protocol):
    def create(self, snapshot: Path, allowed_commands: set[str]) -> SandboxSession: ...


class LocalProcessSandbox:
    security_profile = "development-process-only"
    network_isolated = False

    def __init__(self, snapshot: Path, allowed_commands: set[str]) -> None:
        if not snapshot.is_dir():
            raise SandboxError("snapshot must be a directory")
        self._root = Path(tempfile.mkdtemp(prefix="app-sandbox-"))
        self.snapshot = self._root / "snapshot"
        self.workspace = self._root / "workspace"
        shutil.copytree(snapshot, self.snapshot, symlinks=False)
        shutil.copytree(snapshot, self.workspace, symlinks=False)
        _make_tree_read_only(self.snapshot)
        self._allowed_commands = frozenset(allowed_commands)
        self._closed = False

    def run(self, argv: Sequence[str], timeout_seconds: int = 30) -> CommandResult:
        if self._closed:
            raise SandboxError("sandbox is closed")
        if not argv:
            raise SandboxError("empty command")
        executable = Path(argv[0]).name
        if executable not in self._allowed_commands:
            raise SandboxError(f"command {executable!r} is not allowlisted")
        environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "C.UTF-8",
        }
        completed = subprocess.run(
            list(argv),
            cwd=self.workspace,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)

    def close(self) -> None:
        if self._closed:
            return
        _make_tree_owner_writable(self._root)
        shutil.rmtree(self._root)
        self._closed = True

    def __enter__(self) -> "LocalProcessSandbox":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class LocalProcessSandboxBackend:
    """Development fallback used only while a container daemon is unavailable."""

    def create(self, snapshot: Path, allowed_commands: set[str]) -> LocalProcessSandbox:
        return LocalProcessSandbox(snapshot, allowed_commands)


class DockerSandbox:
    security_profile = "container-network-none"
    network_isolated = True

    def __init__(self, root: Path, snapshot: Path, workspace: Path, container_id: str, allowed_commands: set[str]) -> None:
        self._root = root
        self.snapshot = snapshot
        self.workspace = workspace
        self._container_id = container_id
        self._allowed_commands = frozenset(allowed_commands)
        self._closed = False

    def run(self, argv: Sequence[str], timeout_seconds: int = 30) -> CommandResult:
        if self._closed:
            raise SandboxError("sandbox is closed")
        if not argv:
            raise SandboxError("empty command")
        executable = Path(argv[0]).name
        if executable not in self._allowed_commands:
            raise SandboxError(f"command {executable!r} is not allowlisted")
        completed = subprocess.run(
            [
                "docker", "exec", "--workdir", "/workspace",
                "--env", "PATH=/usr/bin:/bin",
                "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--env", "LANG=C.UTF-8",
                self._container_id, *argv,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)

    def close(self) -> None:
        if self._closed:
            return
        subprocess.run(["docker", "rm", "--force", self._container_id], capture_output=True, text=True, check=False)
        _make_tree_owner_writable(self._root)
        shutil.rmtree(self._root)
        self._closed = True

    def __enter__(self) -> "DockerSandbox":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class DockerSandboxBackend:
    """Container backend. It never pulls an image or silently falls back to host execution."""

    def __init__(self, image: str, *, memory: str = "512m", cpus: str = "1.0", pids_limit: int = 64) -> None:
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.pids_limit = pids_limit

    def create(self, snapshot: Path, allowed_commands: set[str]) -> DockerSandbox:
        if not snapshot.is_dir():
            raise SandboxError("snapshot must be a directory")
        self._assert_image_available()
        root = Path(tempfile.mkdtemp(prefix="app-docker-sandbox-"))
        copied_snapshot = root / "snapshot"
        workspace = root / "workspace"
        try:
            shutil.copytree(snapshot, copied_snapshot, symlinks=False)
            shutil.copytree(snapshot, workspace, symlinks=False)
            _make_tree_read_only(copied_snapshot)
            completed = subprocess.run(
                self.build_run_command(copied_snapshot, workspace),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if completed.returncode != 0:
                raise SandboxError(f"docker sandbox start failed: {completed.stderr.strip()}")
            container_id = completed.stdout.strip()
            if not container_id:
                raise SandboxError("docker sandbox returned no container id")
            return DockerSandbox(root, copied_snapshot, workspace, container_id, allowed_commands)
        except Exception:
            _make_tree_owner_writable(root)
            shutil.rmtree(root, ignore_errors=True)
            raise

    def build_run_command(self, snapshot: Path, workspace: Path) -> list[str]:
        return [
            "docker", "run", "--detach", "--rm",
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", str(self.pids_limit),
            "--memory", self.memory,
            "--cpus", self.cpus,
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--volume", f"{snapshot}:/snapshot:ro",
            "--volume", f"{workspace}:/workspace:rw",
            "--workdir", "/workspace",
            self.image,
            "sleep", "infinity",
        ]

    def _assert_image_available(self) -> None:
        completed = subprocess.run(
            ["docker", "image", "inspect", self.image],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise SandboxError(
                f"docker image {self.image!r} is unavailable or daemon is not running; image pull is not automatic"
            )


def _make_tree_read_only(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o500)
        else:
            path.chmod(0o400)
    root.chmod(0o500)


def _make_tree_owner_writable(root: Path) -> None:
    """Restore deletion rights only for files copied into our temporary root."""

    if not root.exists():
        return
    root.chmod(0o700)
    for path in root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
