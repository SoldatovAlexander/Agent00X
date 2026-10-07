"""One-request fixed-profile verifier execution and signed receipt composition.

This transport-neutral service core does not load signing keys or establish
host trust. A remote launcher must provide an already-held signer and a
verifier configured from the same immutable profile before it can be trusted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
import json
import posixpath
import re
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .digests import sha256_digest
from .executor import (
    MAX_VERIFIER_SNAPSHOT_FILES,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    validate_verifier_result,
    verifier_snapshot_tree_digest,
)
from .verifier_attestation import build_signed_verifier_response
from .brainbooster_target_profile import (
    PINNED_COMMIT,
    PINNED_CONTENT_DIGEST,
    PINNED_FILE_COUNT,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_HTTP_DB_TEST_COMMAND,
    PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
    PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from .verifier_container import DockerContainerVerifier, VerifierContainerConfig
from .verifier_process import (
    VerifierProcessRequest,
    VerifierProcessResponse,
    digest_verifier_request,
    parse_verifier_request,
    serialize_verifier_request,
)


_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{64}\Z")
_KEY_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_IMAGE_ID_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class SignedVerifierServiceError(ValueError):
    """A fixed-profile verifier request could not be safely processed."""


@dataclass(frozen=True)
class VerifierProfile:
    """Immutable target/test/runtime contract used by one verifier service."""

    repository_id: str
    base_commit: str
    snapshot_tree_digest: str
    snapshot_file_count: int
    allowed_change_paths: tuple[str, ...]
    test_command: tuple[str, ...]
    test_timeout_seconds: int
    verifier_image_id: str
    verifier_code_digest: str
    signer_key_id: str

    def __post_init__(self) -> None:
        if (
            type(self.repository_id) is not str
            or not self.repository_id
            or len(self.repository_id) > 256
            or type(self.base_commit) is not str
            or re.fullmatch(r"[0-9a-f]{40,64}", self.base_commit) is None
            or type(self.snapshot_tree_digest) is not str
            or _DIGEST_RE.fullmatch(self.snapshot_tree_digest) is None
            or type(self.snapshot_file_count) is not int
            or not 1 <= self.snapshot_file_count <= MAX_VERIFIER_SNAPSHOT_FILES
            or type(self.allowed_change_paths) is not tuple
            or not self.allowed_change_paths
            or any(
                type(path) is not str
                or not path
                or path.startswith("/")
                or "\\" in path
                or posixpath.normpath(path) != path
                or any(part in {"", ".", ".."} for part in path.split("/"))
                for path in self.allowed_change_paths
            )
            or tuple(sorted(set(self.allowed_change_paths))) != self.allowed_change_paths
            or type(self.test_command) is not tuple
            or not self.test_command
            or any(type(arg) is not str or not arg for arg in self.test_command)
            or type(self.test_timeout_seconds) is not int
            or not 1 <= self.test_timeout_seconds <= 86_400
            or type(self.verifier_image_id) is not str
            or _IMAGE_ID_RE.fullmatch(self.verifier_image_id) is None
            or type(self.verifier_code_digest) is not str
            or _IMAGE_ID_RE.fullmatch(self.verifier_code_digest) is None
            or type(self.signer_key_id) is not str
            or _KEY_ID_RE.fullmatch(self.signer_key_id) is None
        ):
            raise SignedVerifierServiceError("signed verifier service: profile is invalid")

    @property
    def expected_verifier_id(self) -> str:
        return f"docker-image:{self.verifier_image_id}/code:{self.verifier_code_digest}"

    @property
    def profile_digest(self) -> str:
        return sha256_digest(
            {
                "schema": "agent00x-verifier-profile/v1",
                "repository_id": self.repository_id,
                "base_commit": self.base_commit,
                "snapshot_tree_digest": self.snapshot_tree_digest,
                "snapshot_file_count": self.snapshot_file_count,
                "allowed_change_paths": self.allowed_change_paths,
                "test_command": self.test_command,
                "test_timeout_seconds": self.test_timeout_seconds,
                "verifier_image_id": self.verifier_image_id,
                "verifier_code_digest": self.verifier_code_digest,
                "signer_key_id": self.signer_key_id,
            }
        )

    def validate_request(self, prepared: VerifierInput) -> None:
        """Reject caller-selected target/test inputs before verifier execution."""

        if type(prepared) is not VerifierInput:
            raise SignedVerifierServiceError("signed verifier service: request rejected")
        try:
            snapshot_digest = verifier_snapshot_tree_digest(prepared.snapshot_files)
            changed_paths = tuple(path for path, _content in prepared.verified_contents)
            if (
                prepared.repository_id != self.repository_id
                or prepared.base_commit != self.base_commit
                or prepared.snapshot_tree_digest != self.snapshot_tree_digest
                or prepared.snapshot_tree_digest != snapshot_digest
                or type(prepared.snapshot_claim_digest) is not str
                or _DIGEST_RE.fullmatch(prepared.snapshot_claim_digest) is None
                or len(prepared.snapshot_files) != self.snapshot_file_count
                or prepared.declared_change_paths != self.allowed_change_paths
                or changed_paths != self.allowed_change_paths
                or prepared.test_command != self.test_command
                or prepared.test_timeout_seconds != self.test_timeout_seconds
                or prepared.replay_result_digest is None
            ):
                raise ValueError
        except Exception:
            raise SignedVerifierServiceError(
                "signed verifier service: request rejected"
            ) from None


BRAINBOOSTER_VERIFIER_PROFILE = VerifierProfile(
    repository_id=f"{PINNED_OWNER}/{PINNED_REPOSITORY}",
    base_commit=PINNED_COMMIT,
    snapshot_tree_digest=PINNED_CONTENT_DIGEST,
    snapshot_file_count=PINNED_FILE_COUNT,
    allowed_change_paths=("backend/routes.py",),
    test_command=PINNED_HTTP_DB_TEST_COMMAND,
    test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
    verifier_image_id=VERIFIER_RUNTIME_IMAGE_ID,
    verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
    signer_key_id="brainbooster-verifier-v1",
)


def create_brainbooster_verifier_runner(
    docker_executable: str,
) -> DockerContainerVerifier:
    """Construct the pinned runner without invoking Docker or a subprocess."""

    config = VerifierContainerConfig(
        docker_executable=docker_executable,
        runtime_image_id=BRAINBOOSTER_VERIFIER_PROFILE.verifier_image_id,
        verifier_code_digest=BRAINBOOSTER_VERIFIER_PROFILE.verifier_code_digest,
        timeout_seconds=PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
    )
    return DockerContainerVerifier(config)


class VerifierRunner(Protocol):
    def verify(self, prepared: VerifierInput) -> VerifierResult: ...


def run_signed_verifier_request(
    request_bytes: object,
    *,
    invocation_nonce: object,
    profile: VerifierProfile,
    verifier: VerifierRunner,
    signing_key: object,
    issued_at: datetime,
) -> bytes:
    """Validate one fixed-profile request, run it once, and sign its result."""

    try:
        if (
            type(request_bytes) is not bytes
            or type(profile) is not VerifierProfile
            or type(invocation_nonce) is not str
            or _NONCE_RE.fullmatch(invocation_nonce) is None
            or not callable(getattr(verifier, "verify", None))
            or not isinstance(signing_key, Ed25519PrivateKey)
            or not isinstance(issued_at, datetime)
            or issued_at.tzinfo is None
            or issued_at.utcoffset() != timedelta(0)
        ):
            raise ValueError
        request = parse_verifier_request(request_bytes)
        if serialize_verifier_request(request) != request_bytes:
            raise ValueError
        prepared = request.verifier_input
        profile.validate_request(prepared)

        raw_result = verifier.verify(prepared)
        result = validate_verifier_result(raw_result, prepared)
        if (
            result.verifier_id != profile.expected_verifier_id
            or result.verdict not in {VerifierVerdict.PASS, VerifierVerdict.FAIL, VerifierVerdict.BLOCKED}
        ):
            raise ValueError

        # The nonce is a replay marker. The independently configured verifier
        # identity and runtime remain bound by the signed profile digest.
        response_result = replace(result, verifier_id=invocation_nonce)
        response = VerifierProcessResponse.from_verifier_result(
            response_result, digest_verifier_request(request)
        )
        response_bytes = _canonical_response_bytes(response)
        return build_signed_verifier_response(
            request_bytes,
            response_bytes,
            invocation_nonce=invocation_nonce,
            verifier_profile_digest=profile.profile_digest,
            key_id=profile.signer_key_id,
            signing_key=signing_key,
            issued_at=issued_at,
        )
    except SignedVerifierServiceError:
        raise
    except Exception:
        raise SignedVerifierServiceError(
            "signed verifier service: request rejected"
        ) from None


def _canonical_response_bytes(response: VerifierProcessResponse) -> bytes:
    return json.dumps(
        asdict(response),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
