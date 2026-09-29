"""Immutable digest-only seed binding verified execution to a publication input.

A seed carries bounded identifiers, digests, a verifier verdict and a snapshot
origin only. It never carries prompts, file contents, command output,
credentials, capabilities or approvals. :func:`build_publication_seed`
accepts a seed only from a matching pinned request and verified execution
result, failing closed before any downstream collaborator could use it.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from .executor import ExecutionRequest, ExecutionResult, ExecutionStatus, VerifierResult, VerifierVerdict
from .pinned_snapshot import PinnedSnapshot


class PublicationSeedError(ValueError):
    """A publication seed field is malformed."""


_VERDICTS = ("pass", "fail", "blocked")
_SNAPSHOT_ORIGINS = ("local_git_commit", "unverified_local_test")
_BRANCH_NAMESPACE = "agent/"
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


def build_publication_seed(
    request: ExecutionRequest, result: ExecutionResult
) -> PublicationSeed:
    """Build the single seed bound to one matching pinned verified execution.

    Only a pinned request paired with a verified result carrying the same
    process, repository, base commit, snapshot tree and verifier evidence
    produces a seed. Every other input fails closed with a stable,
    payload-free error before any downstream collaborator is involved; this
    function takes no collaborators and performs no effects.
    """

    if not isinstance(request, ExecutionRequest):
        raise PublicationSeedError("publication seed: execution request is invalid")
    if not isinstance(result, ExecutionResult):
        raise PublicationSeedError("publication seed: execution result is invalid")
    pin = request.pinned_snapshot
    if not isinstance(pin, PinnedSnapshot):
        raise PublicationSeedError("publication seed: pinned snapshot is required")
    if result.status is not ExecutionStatus.VERIFIED:
        raise PublicationSeedError("publication seed: execution status is not verified")
    verifier = result.verifier_result
    if not isinstance(verifier, VerifierResult):
        raise PublicationSeedError("publication seed: verifier evidence is missing")
    if verifier.verdict is not VerifierVerdict.PASS:
        raise PublicationSeedError("publication seed: verifier verdict is not pass")
    if result.staged_change_digest is None or result.verified_contents_digest is None:
        raise PublicationSeedError("publication seed: staged digest is missing")
    if result.snapshot_origin != "local_git_commit" or result.snapshot_tree_digest is None:
        raise PublicationSeedError("publication seed: snapshot origin is unverified")
    for value in (result.patch_digest, result.evidence_digest, result.verification_digest):
        _validate_digest(value)
    if verifier.evidence_origin != "local_test" or result.evidence_origin != "local_test":
        raise PublicationSeedError("publication seed: evidence origin is invalid")
    _validate_digest(verifier.replay_result_digest)
    try:
        bindings_match = (
            verifier.process_id == request.process_id
            and pin.repository_id == request.repository_id
            and pin.commit_oid == request.base_commit
            and verifier.base_commit == request.base_commit
            and pin.tree_digest == result.snapshot_tree_digest
            and verifier.snapshot_tree_digest == result.snapshot_tree_digest
            and verifier.patch_digest == result.patch_digest
            and verifier.evidence_digest == result.evidence_digest
            and verifier.verification_digest == result.verification_digest
            and verifier.verified_contents_digest == result.verified_contents_digest
        )
    except Exception:
        raise PublicationSeedError("publication seed: execution binding is invalid") from None
    if not bindings_match:
        raise PublicationSeedError("publication seed: execution binding mismatch")
    return PublicationSeed(
        process_id=request.process_id,
        repository_id=request.repository_id,
        base_commit=request.base_commit,
        staged_change_digest=result.staged_change_digest,
        verified_contents_digest=result.verified_contents_digest,
        verifier_id=verifier.verifier_id,
        verdict=verifier.verdict.value,
        replay_result_digest=verifier.replay_result_digest,
        snapshot_tree_digest=result.snapshot_tree_digest,
        snapshot_origin=result.snapshot_origin,
    )


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


@dataclass(frozen=True)
class PublicationIntent:
    """Minimal seed-bound publication input; carries no authority proof.

    The repository, base commit, process and staged digest are copied from one
    accepted seed, and the idempotency key is the canonical derivation of the
    explicit branch and staged digest. Any substitution is rejected at this
    boundary, before policy, gateway or broker code could observe the intent.
    """

    process_id: str
    repository_id: str
    base_commit: str
    branch: str
    staged_change_digest: str
    idempotency_key: str

    def __post_init__(self) -> None:
        for value in (self.process_id, self.repository_id, self.base_commit):
            _validate_identity(value)
        _validate_branch(self.branch)
        _validate_digest(self.staged_change_digest)
        if self.idempotency_key != _canonical_intent_key(self.branch, self.staged_change_digest):
            raise PublicationSeedError("publication intent: idempotency key mismatch")


def derive_publication_intent(seed: PublicationSeed, branch: str) -> PublicationIntent:
    """Derive the single canonical intent for one accepted seed and branch.

    The branch must explicitly satisfy the existing local agent-namespace
    constraints; the repository is never chosen here and always stays
    seed-bound. This function takes no collaborators and performs no effects.
    """

    if not isinstance(seed, PublicationSeed):
        raise PublicationSeedError("publication intent: seed is invalid")
    _validate_branch(branch)
    return PublicationIntent(
        process_id=seed.process_id,
        repository_id=seed.repository_id,
        base_commit=seed.base_commit,
        branch=branch,
        staged_change_digest=seed.staged_change_digest,
        idempotency_key=_canonical_intent_key(branch, seed.staged_change_digest),
    )


def _canonical_intent_key(branch: str, staged_change_digest: str) -> str:
    return f"publish/{branch.removeprefix(_BRANCH_NAMESPACE)}/{staged_change_digest}"


def _validate_branch(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
        or "\\" in value
        or not value.startswith(_BRANCH_NAMESPACE)
    ):
        raise PublicationSeedError("publication intent: branch is invalid")
    suffix = value.removeprefix(_BRANCH_NAMESPACE)
    if not suffix or any(part == "" for part in suffix.split("/")):
        raise PublicationSeedError("publication intent: branch is invalid")
