"""Typed provenance records for snapshots exported from a local Git commit.

These records describe local object-database evidence only. They do not attest
remote origin, authorship, host isolation, or the authenticity of the repository
identity supplied by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import subprocess
import tempfile
from typing import Literal

_REPOSITORY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
_FULL_COMMIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
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


def _run_local_git_bytes(repository_path: Path, arguments: tuple[str, ...]) -> bytes:
    """Return raw local Git object data under the same command allowlist."""

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
            text=False,
            timeout=10,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError("pinned snapshot local Git object read failed") from None
    if completed.returncode != 0:
        raise ValueError("pinned snapshot local Git object read failed")
    return completed.stdout


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
) -> Path:
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
        )
        for record in listing.split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
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
            content = _run_local_git_bytes(repository.root_path, ("cat-file", "blob", object_oid))
            if len(content) != int(file_size_text):
                raise ValueError("pinned snapshot blob size changed")
            target = output_root.joinpath(*relative_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as snapshot_file:
                snapshot_file.write(content)
            target.chmod(0o755 if mode == "100755" else 0o644)
        return output_root
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise ValueError("pinned snapshot export failed") from None


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
