"""Trusted binding between a source repository slug and provider authority ID."""

from __future__ import annotations

from dataclasses import dataclass
import re


_SOURCE_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_PROVIDER_REPOSITORY_PATTERN = re.compile(
    r"github-installation/[1-9][0-9]*/repository/[1-9][0-9]*\Z"
)


@dataclass(frozen=True)
class RepositoryTargetBinding:
    """Immutable Control Plane mapping used only after the source is verified."""

    source_repository_id: str
    provider_repository_id: str

    def __post_init__(self) -> None:
        if (
            type(self.source_repository_id) is not str
            or _SOURCE_REPOSITORY_PATTERN.fullmatch(self.source_repository_id) is None
            or type(self.provider_repository_id) is not str
            or _PROVIDER_REPOSITORY_PATTERN.fullmatch(self.provider_repository_id) is None
        ):
            raise ValueError("repository binding: target identity is invalid")


def provider_repository_id(installation_id: int, repository_id: int) -> str:
    """Format a validated provider-scoped repository identity."""
    if (
        type(installation_id) is not int
        or installation_id < 1
        or type(repository_id) is not int
        or repository_id < 1
    ):
        raise ValueError("repository binding: target identity is invalid")
    return f"github-installation/{installation_id}/repository/{repository_id}"
