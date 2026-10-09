"""Bounded anonymous Git smart-HTTP source for one pinned commit object.

The Git command is used only as a temporary object transport/parser. No caller
configuration, credential helper, prompt, remote ref update, push or retry is
permitted. This verifies object bytes, not commit authorship or server identity.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .brainbooster_target_profile import (
    PINNED_COMMIT,
    PINNED_OWNER,
    PINNED_REPOSITORY,
)
from .github_snapshot import (
    GitHubCommitClaim,
    parse_git_commit_object,
)


_REMOTE_URL = (
    "https://github.com/"
    f"{PINNED_OWNER}/{PINNED_REPOSITORY}.git"
)
_MAX_FETCH_PACK_BYTES = 2 * 1024 * 1024
_MAX_FETCH_PACK_OBJECTS = 128
_MAX_GIT_TIMEOUT_SECONDS = 30.0
_ABSOLUTE_EXECUTABLE_PATTERN = re.compile(r"/.+")


class GitCommitObjectSourceError(ValueError):
    """The pinned raw commit object could not be acquired safely."""

    def __init__(self, reason: str, *, exit_code: int | None = None) -> None:
        stages = {
            "platform", "init", "fetch", "pack-validation", "object-count",
            "object-size", "object-read", "object-validation",
        }
        stage = reason.removesuffix(" failed") if reason.endswith(" failed") else None
        if stage not in stages and reason not in {"configuration is invalid", "claim is invalid"}:
            reason = "fetch failed"
            stage = "fetch"
        if exit_code is not None and (
            type(exit_code) is not int or not 0 <= exit_code <= 255
        ):
            exit_code = None
        if exit_code is not None and reason != f"{stage} failed":
            exit_code = None
        suffix = f" (exit {exit_code})" if exit_code is not None else ""
        super().__init__(f"github commit source: {reason}{suffix}")
        self.stage = stage
        self.exit_code = exit_code


class _GitProcessFailure(RuntimeError):
    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code


class GitHubRawCommitObjectSource:
    """Fetch only the pinned commit object using anonymous HTTPS Git transport."""

    __slots__ = ("_git_executable", "_timeout_seconds")

    def __init__(
        self,
        git_executable: str,
        *,
        timeout_seconds: float = 15.0,
    ) -> None:
        if (
            type(git_executable) is not str
            or _ABSOLUTE_EXECUTABLE_PATTERN.fullmatch(git_executable) is None
            or not Path(git_executable).is_file()
            or not os.access(git_executable, os.X_OK)
            or isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < float(timeout_seconds) <= _MAX_GIT_TIMEOUT_SECONDS
        ):
            raise GitCommitObjectSourceError("configuration is invalid")
        self._git_executable = git_executable
        self._timeout_seconds = float(timeout_seconds)

    def __repr__(self) -> str:
        return "GitHubRawCommitObjectSource(remote='pinned-public-repository')"

    __str__ = __repr__

    def __call__(self, claim: GitHubCommitClaim) -> bytes:
        if (
            type(claim) is not GitHubCommitClaim
            or claim.owner != PINNED_OWNER
            or claim.repository != PINNED_REPOSITORY
            or claim.commit_oid != PINNED_COMMIT
        ):
            raise GitCommitObjectSourceError("claim is invalid")
        failure_stage = "platform"
        try:
            import resource

            with tempfile.TemporaryDirectory(
                prefix="agent00x-git-commit-"
            ) as temporary_root:
                root = Path(temporary_root)
                home = root / "home"
                repository = root / "objects.git"
                home.mkdir(mode=0o700)
                environment = {
                    "HOME": str(home),
                    "XDG_CONFIG_HOME": str(home),
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_ASKPASS": os.devnull,
                    "SSH_ASKPASS": os.devnull,
                    "GIT_TRACE": "0",
                }
                deadline = time.monotonic() + self._timeout_seconds

                failure_stage = "init"
                self._run_git(
                    ["init", "--bare", "--quiet", "--template=", str(repository)],
                    cwd=root,
                    environment=environment,
                    resource_module=resource,
                    deadline=deadline,
                    capture_stdout=False,
                )
                failure_stage = "fetch"
                self._run_git(
                    [
                        "-C", str(repository),
                        "-c", "credential.helper=",
                        "-c", "credential.interactive=never",
                        "-c", "http.followRedirects=false",
                        "-c", "protocol.allow=never",
                        "-c", "protocol.https.allow=always",
                        "-c", "protocol.version=2",
                        "-c", "fetch.fsckObjects=true",
                        "fetch", "--no-tags", "--no-recurse-submodules",
                        "--depth=1",
                        _REMOTE_URL, PINNED_COMMIT,
                    ],
                    cwd=root,
                    environment=environment,
                    resource_module=resource,
                    deadline=deadline,
                    capture_stdout=False,
                )
                failure_stage = "pack-validation"
                self._validate_pack_sizes(repository)
                failure_stage = "object-count"
                object_counts = self._run_git(
                    ["-C", str(repository), "count-objects", "-v"],
                    cwd=root,
                    environment=environment,
                    resource_module=resource,
                    deadline=deadline,
                    capture_stdout=True,
                )
                self._validate_object_count(object_counts)
                failure_stage = "object-size"
                size_bytes = self._run_git(
                    [
                        "-C", str(repository), "-c", "protocol.allow=never",
                        "-c", "protocol.https.allow=always", "cat-file", "-s",
                        PINNED_COMMIT,
                    ],
                    cwd=root,
                    environment=environment,
                    resource_module=resource,
                    deadline=deadline,
                    capture_stdout=True,
                )
                size = self._parse_object_size(size_bytes)
                failure_stage = "object-read"
                raw_commit = self._run_git(
                    [
                        "-C", str(repository), "-c", "protocol.allow=never",
                        "-c", "protocol.https.allow=always", "cat-file", "commit",
                        PINNED_COMMIT,
                    ],
                    cwd=root,
                    environment=environment,
                    resource_module=resource,
                    deadline=deadline,
                    capture_stdout=True,
                )
                if len(raw_commit) != size:
                    raise ValueError
                failure_stage = "object-validation"
                parse_git_commit_object(claim, raw_commit)
                return raw_commit
        except GitCommitObjectSourceError:
            raise
        except _GitProcessFailure as error:
            raise GitCommitObjectSourceError(
                f"{failure_stage} failed", exit_code=error.exit_code
            ) from None
        except Exception:
            raise GitCommitObjectSourceError(f"{failure_stage} failed") from None

    @staticmethod
    def _parse_object_size(value: bytes) -> int:
        if type(value) is not bytes or re.fullmatch(rb"(?:0|[1-9][0-9]{0,6})\n", value) is None:
            raise ValueError
        size = int(value[:-1])
        from .github_snapshot import MAX_GIT_COMMIT_OBJECT_BYTES

        if not 1 <= size <= MAX_GIT_COMMIT_OBJECT_BYTES:
            raise ValueError
        return size

    @staticmethod
    def _validate_pack_sizes(repository: Path) -> None:
        pack_directory = repository / "objects" / "pack"
        if not pack_directory.is_dir():
            raise ValueError
        packs = tuple(pack_directory.glob("*.pack"))
        if (
            len(packs) != 1
            or any(not path.is_file() for path in packs)
            or sum(path.stat().st_size for path in packs) > _MAX_FETCH_PACK_BYTES
        ):
            raise ValueError

    @staticmethod
    def _validate_object_count(value: bytes) -> None:
        if type(value) is not bytes or len(value) > 4096:
            raise ValueError
        fields: dict[bytes, bytes] = {}
        for line in value.splitlines():
            name, separator, raw_value = line.partition(b": ")
            if separator and name in {b"count", b"in-pack", b"packs"}:
                if name in fields or re.fullmatch(rb"(?:0|[1-9][0-9]{0,5})", raw_value) is None:
                    raise ValueError
                fields[name] = raw_value
        try:
            in_pack = int(fields[b"in-pack"])
            pack_count = int(fields[b"packs"])
        except (KeyError, ValueError):
            raise ValueError from None
        if not 1 <= in_pack <= _MAX_FETCH_PACK_OBJECTS or pack_count != 1:
            raise ValueError

    def _run_git(
        self,
        arguments: list[str],
        *,
        cwd: Path,
        environment: dict[str, str],
        resource_module: object,
        deadline: float,
        capture_stdout: bool,
    ) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError

        def limit_file_size() -> None:
            resource_module.setrlimit(
                resource_module.RLIMIT_FSIZE,
                (_MAX_FETCH_PACK_BYTES, _MAX_FETCH_PACK_BYTES),
            )

        process = subprocess.Popen(
            [self._git_executable, *arguments],
            cwd=str(cwd),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            close_fds=True,
            preexec_fn=limit_file_size,
        )
        try:
            stdout, _ = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise TimeoutError from None
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
        if process.returncode != 0:
            raise _GitProcessFailure(process.returncode)
        return stdout or b""
