"""Immutable digest-only seed binding verified execution to a publication input.

A seed carries bounded identifiers, digests, a verifier verdict and a snapshot
origin only. It never carries prompts, file contents, command output,
credentials, capabilities or approvals. :func:`build_publication_seed`
accepts a seed only from a matching local Git pin or complete remote snapshot
and verified execution result, failing closed before downstream use.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal
from urllib.parse import quote

from .executor import ExecutionRequest, ExecutionResult, ExecutionStatus, VerifierResult, VerifierVerdict
from .github_snapshot import GitHubSnapshotClaim, GitHubSnapshotContents
from .pinned_snapshot import PinnedSnapshot
from .digests import sha256_digest
from .repository_binding import RepositoryTargetBinding


class PublicationSeedError(ValueError):
    """A publication seed field is malformed."""


_VERDICTS = ("pass", "fail", "blocked")
_SNAPSHOT_ORIGINS = (
    "local_git_commit",
    "github_rest_api_claim",
    "github_codeload_archive",
    "unverified_local_test",
)
_BRANCH_NAMESPACE = "agent/"
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_VERIFIER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_VERIFIER_KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DOCKER_VERIFIER_ID_PATTERN = re.compile(
    r"docker-image:sha256:[0-9a-f]{64}/code:sha256:[0-9a-f]{64}\Z"
)


@dataclass(frozen=True)
class PublicationSeed:
    """Digest-only binding for one verified local or remote execution.

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
        "local_git_commit", "github_rest_api_claim", "github_codeload_archive",
        "unverified_local_test"
    ] = "unverified_local_test"
    snapshot_claim_digest: str | None = None
    source_repository_id: str | None = None
    verifier_attestation_digest: str | None = None
    verifier_attestation_key_id: str | None = None
    verifier_attestation_profile_digest: str | None = None
    verifier_trust_enrollment_digest: str | None = None
    verifier_host_trust_decision_digest: str | None = None

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
        if (
            self.snapshot_origin
            in {
                "local_git_commit",
                "github_rest_api_claim",
                "github_codeload_archive",
            }
            and self.snapshot_tree_digest is None
        ):
            raise PublicationSeedError("publication seed: snapshot tree binding is invalid")
        if self.snapshot_claim_digest is not None:
            _validate_digest(self.snapshot_claim_digest)
        if (self.snapshot_origin in {"github_rest_api_claim", "github_codeload_archive"}) != (
            self.snapshot_claim_digest is not None
        ):
            raise PublicationSeedError("publication seed: snapshot claim binding is invalid")
        if self.source_repository_id is not None:
            try:
                RepositoryTargetBinding(
                    source_repository_id=self.source_repository_id,
                    provider_repository_id=self.repository_id,
                )
            except Exception:
                raise PublicationSeedError(
                    "publication seed: repository target binding is invalid"
                ) from None
        attestation_fields = (
            self.verifier_attestation_digest,
            self.verifier_attestation_key_id,
            self.verifier_attestation_profile_digest,
            self.verifier_trust_enrollment_digest,
            self.verifier_host_trust_decision_digest,
        )
        if all(value is None for value in attestation_fields):
            return
        if any(value is None for value in attestation_fields):
            raise PublicationSeedError(
                "publication seed: signed verifier trust is not established"
            )
        for value in (
            self.verifier_attestation_digest,
            self.verifier_attestation_profile_digest,
            self.verifier_trust_enrollment_digest,
            self.verifier_host_trust_decision_digest,
        ):
            _validate_digest(value)
        if (
            not isinstance(self.verifier_attestation_key_id, str)
            or _VERIFIER_KEY_ID_PATTERN.fullmatch(
                self.verifier_attestation_key_id
            )
            is None
        ):
            raise PublicationSeedError(
                "publication seed: verifier attestation key ID is invalid"
            )


def verifier_trust_intent_binding(
    seed: PublicationSeed,
    *,
    signed_evidence_available: bool = False,
    verified_provenance: object | None = None,
) -> dict[str, str | None | bool]:
    """Return bounded provenance metadata suitable for review and intent binding.

    A reopened stage preserves only these digests and identifiers; it does not
    revalidate the signed enrollment, host-trust decision, or OOB evidence.
    The status wording intentionally avoids implying that it does.
    """
    if (
        type(seed) is not PublicationSeed
        or type(signed_evidence_available) is not bool
    ):
        raise PublicationSeedError("publication seed: verifier trust binding is invalid")
    values = (
        seed.verifier_attestation_digest,
        seed.verifier_attestation_key_id,
        seed.verifier_attestation_profile_digest,
        seed.verifier_trust_enrollment_digest,
        seed.verifier_host_trust_decision_digest,
    )
    binding: dict[str, str | None | bool] = {
        "status": (
            "recorded_digest_only_not_revalidated"
            if any(value is not None for value in values)
            else "not_recorded"
        ),
        "attestation_digest": seed.verifier_attestation_digest,
        "attestation_key_id": seed.verifier_attestation_key_id,
        "profile_digest": seed.verifier_attestation_profile_digest,
        "enrollment_digest": seed.verifier_trust_enrollment_digest,
        "host_trust_decision_digest": seed.verifier_host_trust_decision_digest,
        "signed_evidence_available": signed_evidence_available,
        "signed_evidence_status": (
            "not_applicable"
            if seed.verifier_attestation_digest is None
            else (
                "stored_not_revalidated"
                if signed_evidence_available
                else "not_available"
            )
        ),
    }
    if verified_provenance is not None:
        try:
            from .verifier_provenance import (
                is_verified_stage_verifier_provenance,
            )

            if (
                not is_verified_stage_verifier_provenance(verified_provenance)
                or verified_provenance.verifier_attestation_digest
                != seed.verifier_attestation_digest
                or verified_provenance.verifier_key_id
                != seed.verifier_attestation_key_id
                or verified_provenance.verifier_profile_digest
                != seed.verifier_attestation_profile_digest
                or verified_provenance.verifier_trust_enrollment_digest
                != seed.verifier_trust_enrollment_digest
                or verified_provenance.verifier_host_trust_decision_digest
                != seed.verifier_host_trust_decision_digest
                or verified_provenance.request_input_reconstructed is not True
                or signed_evidence_available is not True
            ):
                raise ValueError
            binding.update(
                {
                    "status": "cryptographically_revalidated_request_reconstructed",
                    "signed_evidence_status": "revalidated",
                    "request_input_reconstructed": True,
                    "authority_signatures_valid": True,
                    "verifier_signature_valid": True,
                    "identity_authenticated": False,
                    "provider_write": False,
                    "request_digest": verified_provenance.verifier_request_digest,
                    "enrollment_authority_key_id": (
                        verified_provenance.enrollment_authority_key_id
                    ),
                    "decision_authority_key_id": (
                        verified_provenance.decision_authority_key_id
                    ),
                }
            )
        except Exception:
            raise PublicationSeedError(
                "publication seed: verifier provenance is unavailable"
            ) from None
    return binding


def bind_publication_seed_to_target(
    seed: PublicationSeed, binding: RepositoryTargetBinding
) -> PublicationSeed:
    """Bind the source seed to a trusted provider identity without losing its slug."""
    if (
        type(seed) is not PublicationSeed
        or seed.verdict != "pass"
        or type(binding) is not RepositoryTargetBinding
    ):
        raise PublicationSeedError("publication seed: repository target binding is invalid")
    if seed.source_repository_id is not None or seed.repository_id != binding.source_repository_id:
        raise PublicationSeedError("publication seed: repository target does not match source")
    return PublicationSeed(
        process_id=seed.process_id,
        repository_id=binding.provider_repository_id,
        source_repository_id=seed.repository_id,
        base_commit=seed.base_commit,
        staged_change_digest=seed.staged_change_digest,
        verified_contents_digest=seed.verified_contents_digest,
        verifier_id=seed.verifier_id,
        verdict=seed.verdict,
        replay_result_digest=seed.replay_result_digest,
        snapshot_tree_digest=seed.snapshot_tree_digest,
        snapshot_origin=seed.snapshot_origin,
        snapshot_claim_digest=seed.snapshot_claim_digest,
        verifier_attestation_digest=seed.verifier_attestation_digest,
        verifier_attestation_key_id=seed.verifier_attestation_key_id,
        verifier_attestation_profile_digest=seed.verifier_attestation_profile_digest,
        verifier_trust_enrollment_digest=seed.verifier_trust_enrollment_digest,
        verifier_host_trust_decision_digest=seed.verifier_host_trust_decision_digest,
    )


def build_publication_seed(
    request: ExecutionRequest, result: ExecutionResult
) -> PublicationSeed:
    """Build the single seed bound to one matching pinned verified execution.

    Only a local Git pin or a complete remote snapshot request paired with a
    verified result carrying the same process, repository, base commit,
    snapshot tree/claim and verifier evidence produces a seed. Every other
    input fails closed with a stable,
    payload-free error before any downstream collaborator is involved; this
    function takes no collaborators and performs no effects.
    """

    if not isinstance(request, ExecutionRequest):
        raise PublicationSeedError("publication seed: execution request is invalid")
    if not isinstance(result, ExecutionResult):
        raise PublicationSeedError("publication seed: execution result is invalid")
    if result.verifier_independent_host_trust_established is not None:
        try:
            from .verifier_host_trust_decision import (
                is_verified_verifier_host_trust_decision,
            )

            decision = result.verifier_host_trust_decision
            if (
                result.verifier_signature_valid is not True
                or result.verifier_independent_host_trust_established is not True
                or not is_verified_verifier_host_trust_decision(decision)
                or decision.decision_digest
                != result.verifier_host_trust_decision_digest
                or decision.enrollment_digest
                != result.verifier_trust_enrollment_digest
                or decision.verifier_key_id != result.verifier_attestation_key_id
                or decision.verifier_profile_digest
                != result.verifier_attestation_profile_digest
            ):
                raise ValueError
        except Exception:
            raise PublicationSeedError(
                "publication seed: signed verifier trust is not established"
            ) from None
    pin = request.pinned_snapshot
    remote_snapshot = request.remote_snapshot
    if pin is None and remote_snapshot is None:
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
    if (
        result.snapshot_origin
        not in {
            "local_git_commit",
            "github_rest_api_claim",
            "github_codeload_archive",
        }
        or result.snapshot_tree_digest is None
    ):
        raise PublicationSeedError("publication seed: snapshot origin is unverified")
    for value in (result.patch_digest, result.evidence_digest, result.verification_digest):
        _validate_digest(value)
    if verifier.evidence_origin != "local_test" or result.evidence_origin != "local_test":
        raise PublicationSeedError("publication seed: evidence origin is invalid")
    if verifier.replay_result_digest is not None or pin is not None:
        _validate_digest(verifier.replay_result_digest)
    if pin is not None:
        if not isinstance(pin, PinnedSnapshot):
            raise PublicationSeedError("publication seed: execution binding is invalid")
        expected_repository = pin.repository_id
        expected_commit = pin.commit_oid
        expected_tree_digest = pin.tree_digest
        expected_origin = "local_git_commit"
        expected_claim_digest = None
    else:
        if (
            type(remote_snapshot) is not GitHubSnapshotContents
            or type(remote_snapshot.claim) is not GitHubSnapshotClaim
        ):
            raise PublicationSeedError("publication seed: remote snapshot is invalid")
        claim = remote_snapshot.claim
        if not claim.full_snapshot:
            raise PublicationSeedError("publication seed: remote snapshot is incomplete")
        expected_repository = f"{claim.owner}/{claim.repository}"
        expected_commit = claim.commit_oid
        expected_tree_digest = claim.content_digest
        expected_origin = claim.evidence_origin
        expected_claim_digest = _github_claim_digest(claim)
        if result.snapshot_claim_digest != expected_claim_digest:
            raise PublicationSeedError("publication seed: remote claim binding mismatch")

    try:
        bindings_match = (
            request.repository_id == expected_repository
            and request.base_commit == expected_commit
            and result.snapshot_origin == expected_origin
            and result.snapshot_tree_digest == expected_tree_digest
            and result.snapshot_claim_digest == expected_claim_digest
            and verifier.process_id == request.process_id
            and verifier.base_commit == request.base_commit
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
        snapshot_claim_digest=expected_claim_digest,
        verifier_attestation_digest=result.verifier_attestation_digest,
        verifier_attestation_key_id=result.verifier_attestation_key_id,
        verifier_attestation_profile_digest=(
            result.verifier_attestation_profile_digest
        ),
        verifier_trust_enrollment_digest=result.verifier_trust_enrollment_digest,
        verifier_host_trust_decision_digest=(
            result.verifier_host_trust_decision_digest
        ),
    )


def _github_claim_digest(claim: GitHubSnapshotClaim) -> str:
    canonicalization = (
        "github-codeload-snapshot-claim/v1"
        if claim.evidence_origin == "github_codeload_archive"
        else "github-rest-snapshot-claim/v1"
    )
    return sha256_digest(
        {
            "canonicalization": canonicalization,
            "owner": claim.owner,
            "repository": claim.repository,
            "commit_oid": claim.commit_oid,
            "tree_oid": claim.tree_oid,
            "content_digest": claim.content_digest,
            "full_snapshot": claim.full_snapshot,
            "selected_paths": claim.selected_paths,
            "evidence_origin": claim.evidence_origin,
        }
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
    if not isinstance(value, str) or (
        _VERIFIER_ID_PATTERN.fullmatch(value) is None
        and _DOCKER_VERIFIER_ID_PATTERN.fullmatch(value) is None
    ):
        raise PublicationSeedError("publication seed: verifier identity is invalid")


@dataclass(frozen=True)
class PublicationIntent:
    """Minimal seed-bound publication input; carries no authority proof.

    The repository, base commit, process and staged digest are copied from one
    accepted seed, and the idempotency key is the canonical derivation of the
    explicit base branch, head branch and staged digest. Any substitution is rejected at this
    boundary, before policy, gateway or broker code could observe the intent.
    """

    process_id: str
    repository_id: str
    base_commit: str
    base_branch: str
    branch: str
    staged_change_digest: str
    idempotency_key: str
    source_repository_id: str | None = None

    def __post_init__(self) -> None:
        for value in (self.process_id, self.repository_id, self.base_commit):
            _validate_identity(value)
        if self.source_repository_id is not None:
            try:
                RepositoryTargetBinding(
                    source_repository_id=self.source_repository_id,
                    provider_repository_id=self.repository_id,
                )
            except Exception:
                raise PublicationSeedError(
                    "publication intent: repository target binding is invalid"
                ) from None
        validate_publication_base_branch(self.base_branch)
        _validate_branch(self.branch)
        _validate_digest(self.staged_change_digest)
        if self.idempotency_key != publication_idempotency_key(
            self.branch, self.base_branch, self.staged_change_digest
        ):
            raise PublicationSeedError("publication intent: idempotency key mismatch")
        if self.source_repository_id is not None:
            try:
                RepositoryTargetBinding(
                    source_repository_id=self.source_repository_id,
                    provider_repository_id=self.repository_id,
                )
            except Exception:
                raise PublicationSeedError(
                    "publication intent: repository target binding is invalid"
                ) from None


def derive_publication_intent(
    seed: PublicationSeed, branch: str, base_branch: str
) -> PublicationIntent:
    """Derive the single canonical intent for one accepted seed and branch.

    The branch must explicitly satisfy the existing local agent-namespace
    constraints; the repository is never chosen here and always stays
    seed-bound. This function takes no collaborators and performs no effects.
    """

    if not isinstance(seed, PublicationSeed):
        raise PublicationSeedError("publication intent: seed is invalid")
    _validate_branch(branch)
    validate_publication_base_branch(base_branch)
    return PublicationIntent(
        process_id=seed.process_id,
        repository_id=seed.repository_id,
        base_commit=seed.base_commit,
        base_branch=base_branch,
        branch=branch,
        staged_change_digest=seed.staged_change_digest,
        idempotency_key=publication_idempotency_key(
            branch, base_branch, seed.staged_change_digest
        ),
        source_repository_id=seed.source_repository_id,
    )


def publication_idempotency_key(
    branch: str, base_branch: str, staged_change_digest: str
) -> str:
    head = quote(branch.removeprefix(_BRANCH_NAMESPACE), safe="")
    base = quote(base_branch, safe="")
    return f"publish/{head}/{base}/{staged_change_digest}"


def validate_publication_base_branch(value: object) -> None:
    try:
        size = len(value.encode("utf-8", errors="strict")) if type(value) is str else 0
    except UnicodeEncodeError:
        size = 256
    if (
        type(value) is not str
        or not value
        or size > 255
        or value != value.strip()
        or value.startswith("-")
        or value.endswith(("/", "."))
        or "//" in value
        or ".." in value
        or "@{" in value
        or any(
            character.isspace()
            or ord(character) < 32
            or ord(character) == 127
            or character in "~^:?*[\\"
            for character in value
        )
        or any(
            part in {"", ".", ".."} or part.endswith(".lock")
            for part in value.split("/")
        )
    ):
        raise PublicationSeedError("publication intent: base branch is invalid")


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
