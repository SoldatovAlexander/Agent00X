"""Typed provenance records for snapshots exported from a local Git commit.

These records describe local object-database evidence only. They do not attest
remote origin, authorship, host isolation, or the authenticity of the repository
identity supplied by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class PinnedSnapshot:
    """A local snapshot bound to one exact commit and exported-tree digest."""

    repository_id: str
    commit_oid: str
    tree_digest: str
    snapshot_path: Path = field(repr=False)
    evidence_origin: Literal["local_git_commit"] = "local_git_commit"
