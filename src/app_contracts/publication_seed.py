"""Immutable digest-only seed binding verified execution to a publication input.

A seed carries bounded identifiers, digests, a verifier verdict and a snapshot
origin only. It never carries prompts, file contents, command output,
credentials, capabilities or approvals. Fail-closed construction from a pinned
execution request and result is added separately.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


class PublicationSeedError(ValueError):
    """A publication seed field is malformed."""


_VERDICTS = ("pass", "fail", "blocked")
_SNAPSHOT_ORIGINS = ("local_git_commit", "unverified_local_test")
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_VERIFIER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


@dataclass(frozen=True)
class PublicationSeed:
    """Digest-only binding for one verified local execution.

    Every field is reproducible from the originating execution request and
    result. Raw prompts, contents, outputs and credential material have no
    field here by construction.
    """

    process_id: str
    repository_id: str
    base_commit: str
    staged_change_digest: str
    verified_contents_digest: str
    verifier_id: str
    verdict: str
    replay_result_digest: str | None = None
    snapshot_tree_digest: str | None = None
    snapshot_origin: Literal[
        "local_git_commit", "unverified_local_test"
    ] = "unverified_local_test"

    def __post_init__(self) -> None:
        for value in (self.process_id, self.repository_id, self.base_commit):
            _validate_identity(value)
        for value in (self.staged_change_digest, self.verified_contents_digest):
            _validate_digest(value)
        _validate_verifier_id(self.verifier_id)
        if not isinstance(self.verdict, str) or self.verdict not in _VERDICTS:
            raise PublicationSeedError("publication seed: verifier verdict is invalid")
        for value in (self.replay_result_digest, self.snapshot_tree_digest):
            if value is not None:
                _validate_digest(value)
        if self.snapshot_origin not in _SNAPSHOT_ORIGINS:
            raise PublicationSeedError("publication seed: snapshot origin is invalid")


def _validate_identity(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise PublicationSeedError("publication seed: identity field is invalid")


def _validate_digest(value: object) -> None:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise PublicationSeedError("publication seed: digest is invalid")


def _validate_verifier_id(value: object) -> None:
    if not isinstance(value, str) or _VERIFIER_ID_PATTERN.fullmatch(value) is None:
        raise PublicationSeedError("publication seed: verifier identity is invalid")
