"""Typed provenance records for snapshots exported from a local Git commit.

These records describe local object-database evidence only. They do not attest
remote origin, authorship, host isolation, or the authenticity of the repository
identity supplied by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
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


def _is_allowlisted_local_git_arguments(arguments: tuple[str, ...]) -> bool:
    if arguments in _PREFLIGHT_GIT_ARGUMENTS:
        return True
    return (
        len(arguments) == 4
        and arguments[:3] == ("rev-parse", "--verify", "--end-of-options")
        and isinstance(arguments[3], str)
        and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\^\{commit\}", arguments[3])
        is not None
    )
