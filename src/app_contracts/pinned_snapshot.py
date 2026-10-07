"""Typed provenance records for snapshots exported from a local Git commit.

These records describe local object-database evidence only. They do not attest
remote origin, authorship, host isolation, or the authenticity of the repository
identity supplied by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Literal

from .digests import sha256_digest

_REPOSITORY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
_FULL_COMMIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
SNAPSHOT_DIGEST_CANONICALIZATION = "app-process-snapshot-tree/v1"
SNAPSHOT_CONTENT_DIGEST_CANONICALIZATION = "app-process-snapshot-content/v1"
MAX_SNAPSHOT_FILES = 10_000
MAX_SNAPSHOT_PATH_BYTES = 240
MAX_SNAPSHOT_FILE_BYTES = 262_144
MAX_SNAPSHOT_TOTAL_BYTES = 1_000_000
MAX_SNAPSHOT_TREE_LIST_BYTES = 8_000_000
_SNAPSHOT_OWNER_TOKEN = object()
_PREFLIGHT_GIT_ARGUMENTS = frozenset(
    {
        ("rev-parse", "--is-inside-work-tree"),
        ("rev-parse", "--is-bare-repository"),
        ("rev-parse", "--show-toplevel"),
        ("rev-parse", "--absolute-git-dir"),
        ("rev-parse", "--show-object-format"),
        ("rev-parse", "--verify", "--end-of-options"),
    }
)


@dataclass(frozen=True)
class LocalGitRepository:
    """A validated local Git repository handle; its host path stays private."""

    root_path: Path = field(repr=False)
    object_format: Literal["sha1", "sha256"]


class OwnedLocalSnapshot:
    """Explicit lease for one read-only temporary snapshot tree."""

    def __init__(self, root_path: Path, *, _owner_token: object) -> None:
        if _owner_token is not _SNAPSHOT_OWNER_TOKEN:
            raise ValueError("pinned snapshot ownership token is invalid")
        self._root_path = root_path
        self._closed = False

    @property
    def path(self) -> Path:
        if self._closed:
            raise ValueError("pinned snapshot lease is closed")
        return self._root_path

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        try:
            _make_snapshot_writable(self._root_path)
            shutil.rmtree(self._root_path)
        except FileNotFoundError:
            pass
        except OSError:
            raise ValueError("pinned snapshot cleanup failed") from None
        self._closed = True

    def __enter__(self) -> "OwnedLocalSnapshot":
        if self._closed:
            raise ValueError("pinned snapshot lease is closed")
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


@dataclass(frozen=True)
class PinnedSnapshot:
    """A local snapshot bound to one exact commit and exported-tree digest."""

    repository_id: str
    commit_oid: str
    tree_digest: str
    snapshot_path: Path = field(repr=False)
    evidence_origin: Literal["local_git_commit"] = "local_git_commit"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.repository_id, str)
            or not _REPOSITORY_ID.fullmatch(self.repository_id)
            or any(part in ("", ".", "..") for part in self.repository_id.split("/"))
        ):
            raise ValueError("pinned snapshot repository identity is invalid")
        if not isinstance(self.commit_oid, str) or not _FULL_COMMIT_OID.fullmatch(self.commit_oid):
            raise ValueError("pinned snapshot commit identity is invalid")
        if not isinstance(self.tree_digest, str) or not _SHA256_DIGEST.fullmatch(self.tree_digest):
            raise ValueError("pinned snapshot tree digest is invalid")
        if not isinstance(self.snapshot_path, Path):
            raise ValueError("pinned snapshot local path is invalid")
        if self.evidence_origin != "local_git_commit":
            raise ValueError("pinned snapshot evidence origin is invalid")


def open_local_repository(repository_path: Path) -> LocalGitRepository:
    """Validate a local repository using read-only Git metadata commands only."""

    if not isinstance(repository_path, Path):
        raise ValueError("pinned snapshot repository path is invalid")
    try:
        candidate = repository_path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("pinned snapshot repository path is invalid") from None
    if not candidate.is_dir():
        raise ValueError("pinned snapshot repository path is invalid")

    bare = _run_local_git(candidate, ("rev-parse", "--is-bare-repository")) == "true"
    if bare:
        root_path = Path(
            _run_local_git(candidate, ("rev-parse", "--absolute-git-dir"))
        ).resolve(strict=True)
    else:
        inside_work_tree = _run_local_git(
            candidate, ("rev-parse", "--is-inside-work-tree")
        )
        if inside_work_tree != "true":
            raise ValueError("pinned snapshot path is not a local Git repository")
        root_path = Path(
            _run_local_git(candidate, ("rev-parse", "--show-toplevel"))
        ).resolve(strict=True)

    object_format = _run_local_git(root_path, ("rev-parse", "--show-object-format"))
    if object_format not in ("sha1", "sha256"):
        raise ValueError("pinned snapshot repository object format is unsupported")
    return LocalGitRepository(root_path=root_path, object_format=object_format)


def _run_local_git(repository_path: Path, arguments: tuple[str, ...]) -> str:
    """Run one enumerated local read-only metadata query with sanitized failure."""

    if not _is_allowlisted_local_git_arguments(arguments):
        raise ValueError("pinned snapshot local Git operation is not allowlisted")
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_path), *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError("pinned snapshot local Git preflight failed") from None
    if completed.returncode != 0:
        raise ValueError("pinned snapshot local Git preflight failed")
    return completed.stdout.strip()


def _run_local_git_bytes(
    repository_path: Path,
    arguments: tuple[str, ...],
    *,
    max_output_bytes: int = MAX_SNAPSHOT_TOTAL_BYTES,
) -> bytes:
    """Return raw local Git object data under the same command allowlist."""

    if (
        not _is_allowlisted_local_git_arguments(arguments)
        or isinstance(max_output_bytes, bool)
        or not isinstance(max_output_bytes, int)
        or max_output_bytes < 0
    ):
        raise ValueError("pinned snapshot local Git operation is not allowlisted")
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            ["git", "-C", str(repository_path), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_git_environment(),
        )
        assert process.stdout is not None
        output = bytearray()
        deadline = time.monotonic() + 10
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    process.kill()
                    process.wait()
                    raise ValueError("pinned snapshot local Git object read failed")
                chunk = os.read(process.stdout.fileno(), 64 * 1024)
                if not chunk:
                    break
                if len(output) + len(chunk) > max_output_bytes:
                    process.kill()
                    process.wait()
                    raise ValueError("pinned snapshot Git output limit exceeded")
                output.extend(chunk)
        if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            raise ValueError("pinned snapshot local Git object read failed")
        return bytes(output)
    except (OSError, subprocess.SubprocessError):
        raise ValueError("pinned snapshot local Git object read failed") from None
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None and process.stdout is not None:
            process.stdout.close()


def _git_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }


def resolve_local_commit(repository: LocalGitRepository, commit_oid: str) -> str:
    """Resolve one full object id as a commit without symbolic or remote lookup."""

    if not isinstance(repository, LocalGitRepository):
        raise ValueError("pinned snapshot repository handle is invalid")
    expected_length = 40 if repository.object_format == "sha1" else 64
    if (
        not isinstance(commit_oid, str)
        or len(commit_oid) != expected_length
        or not _FULL_COMMIT_OID.fullmatch(commit_oid)
    ):
        raise ValueError("pinned snapshot commit identity is invalid")
    resolved = _run_local_git(
        repository.root_path,
        ("rev-parse", "--verify", "--end-of-options", f"{commit_oid}^{{commit}}"),
    )
    if resolved != commit_oid:
        raise ValueError("pinned snapshot commit identity did not resolve exactly")
    return resolved


def export_local_commit_tree(
    repository: LocalGitRepository,
    commit_oid: str,
    destination_parent: Path,
) -> OwnedLocalSnapshot:
    """Copy regular file blobs from one commit into an owned temporary tree."""

    resolved_commit = resolve_local_commit(repository, commit_oid)
    if not isinstance(destination_parent, Path):
        raise ValueError("pinned snapshot destination is invalid")
    try:
        parent = destination_parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("pinned snapshot destination is invalid") from None
    if not parent.is_dir():
        raise ValueError("pinned snapshot destination is invalid")
    output_root = Path(tempfile.mkdtemp(prefix="app-pinned-snapshot-", dir=parent))
    try:
        listing = _run_local_git_bytes(
            repository.root_path,
            ("ls-tree", "-r", "-z", "--full-tree", f"{resolved_commit}^{{tree}}"),
            max_output_bytes=MAX_SNAPSHOT_TREE_LIST_BYTES,
        )
        file_count = 0
        total_bytes = 0
        for record in listing.split(b"\0"):
            if not record:
                continue
            file_count += 1
            if file_count > MAX_SNAPSHOT_FILES:
                raise ValueError("pinned snapshot file count limit exceeded")
            metadata, raw_path = record.split(b"\t", 1)
            if not raw_path or len(raw_path) > MAX_SNAPSHOT_PATH_BYTES:
                raise ValueError("pinned snapshot path length limit exceeded")
            mode_raw, kind_raw, object_oid_raw = metadata.split(b" ", 2)
            mode = mode_raw.decode("ascii")
            kind = kind_raw.decode("ascii")
            object_oid = object_oid_raw.decode("ascii")
            if mode not in ("100644", "100755") or kind != "blob":
                raise ValueError("pinned snapshot tree contains an unsupported entry")
            expected_oid_length = 40 if repository.object_format == "sha1" else 64
            if len(object_oid) != expected_oid_length or not _FULL_COMMIT_OID.fullmatch(object_oid):
                raise ValueError("pinned snapshot tree object identity is invalid")
            try:
                path_text = raw_path.decode("utf-8")
            except UnicodeDecodeError:
                raise ValueError("pinned snapshot tree path is invalid") from None
            relative_path = _safe_snapshot_relative_path(path_text)
            file_size_text = _run_local_git(
                repository.root_path, ("cat-file", "-s", object_oid)
            )
            if not file_size_text.isdecimal():
                raise ValueError("pinned snapshot blob size is invalid")
            if len(file_size_text) > len(str(MAX_SNAPSHOT_FILE_BYTES)):
                raise ValueError("pinned snapshot file size limit exceeded")
            file_size = int(file_size_text)
            if file_size > MAX_SNAPSHOT_FILE_BYTES:
                raise ValueError("pinned snapshot file size limit exceeded")
            total_bytes += len(raw_path) + file_size
            if total_bytes > MAX_SNAPSHOT_TOTAL_BYTES:
                raise ValueError("pinned snapshot total size limit exceeded")
            content = _run_local_git_bytes(
                repository.root_path,
                ("cat-file", "blob", object_oid),
                max_output_bytes=MAX_SNAPSHOT_FILE_BYTES,
            )
            if len(content) != file_size:
                raise ValueError("pinned snapshot blob size changed")
            target = output_root.joinpath(*relative_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as snapshot_file:
                snapshot_file.write(content)
            target.chmod(0o755 if mode == "100755" else 0o644)
        _make_snapshot_read_only(output_root)
        return OwnedLocalSnapshot(output_root, _owner_token=_SNAPSHOT_OWNER_TOKEN)
    except Exception:
        _make_snapshot_writable(output_root)
        shutil.rmtree(output_root, ignore_errors=True)
        raise ValueError("pinned snapshot export failed") from None


def compute_snapshot_tree_digest(snapshot_path: Path, *, include_mode: bool = True) -> str:
    """Hash normalized relative paths and bytes, optionally binding executable mode."""

    if (
        not isinstance(snapshot_path, Path)
        or snapshot_path.is_symlink()
        or not isinstance(include_mode, bool)
    ):
        raise ValueError("pinned snapshot tree path is invalid")
    try:
        root = snapshot_path.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("pinned snapshot tree path is invalid")
        entries: list[dict[str, str]] = []
        file_count = 0
        total_bytes = 0
        for path in root.rglob("*"):
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("pinned snapshot tree contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("pinned snapshot tree contains an unsupported entry")
            relative = _safe_snapshot_relative_path(path.relative_to(root).as_posix())
            path_bytes = relative.as_posix().encode("utf-8")
            file_count += 1
            total_bytes += len(path_bytes) + metadata.st_size
            if (
                file_count > MAX_SNAPSHOT_FILES
                or len(path_bytes) > MAX_SNAPSHOT_PATH_BYTES
                or metadata.st_size > MAX_SNAPSHOT_FILE_BYTES
                or total_bytes > MAX_SNAPSHOT_TOTAL_BYTES
            ):
                raise ValueError("pinned snapshot tree limits exceeded")
            content_digest = _hash_file(path)
            entry = {"path": relative.as_posix(), "content_digest": content_digest}
            if include_mode:
                entry["mode"] = "100755" if metadata.st_mode & 0o111 else "100644"
            entries.append(entry)
        entries.sort(key=lambda entry: entry["path"])
    except ValueError:
        raise
    except (OSError, RuntimeError):
        raise ValueError("pinned snapshot tree could not be read") from None
    return sha256_digest(
        {
            "canonicalization": (
                SNAPSHOT_DIGEST_CANONICALIZATION
                if include_mode
                else SNAPSHOT_CONTENT_DIGEST_CANONICALIZATION
            ),
            "files": entries,
        }
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as snapshot_file:
        for chunk in iter(lambda: snapshot_file.read(64 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _make_snapshot_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            path.chmod(0o555)
        elif stat.S_ISREG(metadata.st_mode):
            path.chmod(0o555 if metadata.st_mode & 0o111 else 0o444)
        else:
            raise ValueError("pinned snapshot tree contains an unsupported entry")
    root.chmod(0o555)


def _make_snapshot_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            path.chmod(0o700)
        elif stat.S_ISREG(metadata.st_mode):
            path.chmod(0o600)
    root.chmod(0o700)


def _safe_snapshot_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    raw_parts = value.split("/")
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or "\x00" in value
        or ":" in raw_parts[0]
        or any(part in ("", ".", "..") for part in raw_parts)
        or any(part.casefold() == ".git" for part in raw_parts)
        or path.as_posix() != value
    ):
        raise ValueError("pinned snapshot tree path is invalid")
    return path


def _is_allowlisted_local_git_arguments(arguments: tuple[str, ...]) -> bool:
    if arguments in _PREFLIGHT_GIT_ARGUMENTS:
        return True
    if (
        len(arguments) == 4
        and arguments[:3] == ("rev-parse", "--verify", "--end-of-options")
        and isinstance(arguments[3], str)
        and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\^\{commit\}", arguments[3])
        is not None
    ):
        return True
    if (
        len(arguments) == 5
        and arguments[:4] == ("ls-tree", "-r", "-z", "--full-tree")
        and isinstance(arguments[4], str)
        and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\^\{tree\}", arguments[4])
        is not None
    ):
        return True
    return (
        len(arguments) == 3
        and arguments[0] == "cat-file"
        and arguments[1] in ("-s", "blob")
        and isinstance(arguments[2], str)
        and _FULL_COMMIT_OID.fullmatch(arguments[2]) is not None
    )
