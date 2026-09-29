"""Typed provenance records for snapshots exported from a local Git commit.

These records describe local object-database evidence only. They do not attest
remote origin, authorship, host isolation, or the authenticity of the repository
identity supplied by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Literal

_REPOSITORY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
_FULL_COMMIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


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
