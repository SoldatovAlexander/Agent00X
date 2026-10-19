"""Bounded caller-pinned public trust loading for fixed verifier CLIs.

This module reads public trust artifacts only. It never creates signatures,
loads credentials, or sends a verifier request while constructing the client.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import stat

from .authority_key_set import load_control_plane_authority_key_set
from .signed_verifier_client import SignedVerifierClient, SignedVerifierHTTPSTransport
from .signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE
from .verifier_host_trust_decision import MAX_DECISION_BYTES
from .verifier_trust_enrollment import MAX_ENROLLMENT_BYTES

PINNED_SIGNED_VERIFIER_ENDPOINT_URL = "https://testdev.local/v1/verify"
SHA256_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
VERIFIER_TRUST_ARTIFACT_ARGUMENTS = (
    "verifier_authority_key_set",
    "verifier_authority_key_set_sha256",
    "verifier_enrollment",
    "verifier_enrollment_sha256",
    "verifier_host_decision",
    "verifier_host_decision_sha256",
    "verifier_ca_bundle",
    "verifier_ca_bundle_sha256",
    "expected_worker_host_id",
    "expected_verifier_host_id",
)


def read_pinned_public_record(
    path_value: object,
    expected_digest: object,
    *,
    max_bytes: int,
) -> tuple[bytes, str]:
    """Read one absolute, regular, non-symlink public artifact and verify its pin."""

    descriptor: int | None = None
    try:
        if (
            type(path_value) is not str
            or not Path(path_value).is_absolute()
            or type(expected_digest) is not str
            or SHA256_DIGEST_PATTERN.fullmatch(expected_digest) is None
            or type(max_bytes) is not int
            or max_bytes < 1
        ):
            raise ValueError
        path = Path(path_value)
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError
        no_follow = getattr(os, "O_NOFOLLOW", None)
        no_block = getattr(os, "O_NONBLOCK", None)
        if type(no_follow) is not int or no_follow <= 0 or type(no_block) is not int:
            raise ValueError
        descriptor = os.open(
            path,
            os.O_RDONLY | no_follow | no_block | getattr(os, "O_CLOEXEC", 0),
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or opened.st_size != before.st_size
            or opened.st_size < 1
            or opened.st_size > max_bytes
        ):
            raise ValueError
        chunks: list[bytes] = []
        size = 0
        while size <= max_bytes:
            chunk = os.read(descriptor, min(65_536, max_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        raw = b"".join(chunks)
        if len(raw) != opened.st_size or len(raw) > max_bytes:
            raise ValueError
        actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise ValueError
        return raw, actual_digest
    except Exception:
        raise ValueError("pinned verifier CLI: public trust material unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def has_any_verifier_trust_artifact_args(args: object) -> bool:
    return any(
        getattr(args, name, None) is not None
        for name in VERIFIER_TRUST_ARTIFACT_ARGUMENTS
    )


def load_pinned_signed_verifier_client(
    args: object,
    *,
    expected_endpoint_url: str = PINNED_SIGNED_VERIFIER_ENDPOINT_URL,
    profile=BRAINBOOSTER_VERIFIER_PROFILE,
) -> tuple[SignedVerifierClient, str, str, dict[str, str]]:
    """Load and validate fixed public trust artifacts without making a request."""

    try:
        if any(
            getattr(args, name, None) is None
            for name in VERIFIER_TRUST_ARTIFACT_ARGUMENTS
        ):
            raise ValueError
        authority_path = Path(args.verifier_authority_key_set)
        if not authority_path.is_absolute() or authority_path.is_symlink():
            raise ValueError
        authority_keys, authority_digest = load_control_plane_authority_key_set(
            authority_path,
            expected_digest=args.verifier_authority_key_set_sha256,
        )
        enrollment_bytes, enrollment_digest = read_pinned_public_record(
            args.verifier_enrollment,
            args.verifier_enrollment_sha256,
            max_bytes=MAX_ENROLLMENT_BYTES,
        )
        decision_bytes, decision_digest = read_pinned_public_record(
            args.verifier_host_decision,
            args.verifier_host_decision_sha256,
            max_bytes=MAX_DECISION_BYTES,
        )
        _ca_bytes, ca_digest = read_pinned_public_record(
            args.verifier_ca_bundle,
            args.verifier_ca_bundle_sha256,
            max_bytes=SignedVerifierHTTPSTransport.MAX_CUSTOM_CA_BUNDLE_BYTES,
        )
        transport = SignedVerifierHTTPSTransport(
            expected_endpoint_url,
            custom_ca_bundle_path=args.verifier_ca_bundle,
            custom_ca_bundle_sha256=ca_digest.removeprefix("sha256:"),
            connect_address=getattr(args, "verifier_connect_address", None),
            connect_port=getattr(args, "verifier_connect_port", None),
        )
        transport.validate_configuration()
        worker_host_id = args.expected_worker_host_id
        verifier_host_id = args.expected_verifier_host_id
        client = SignedVerifierClient.from_trust_enrollment(
            profile,
            transport,
            enrollment_bytes,
            trusted_authority_keys=authority_keys,
            expected_endpoint_url=expected_endpoint_url,
            expected_worker_host_id=worker_host_id,
            expected_verifier_host_id=verifier_host_id,
            host_trust_decision_bytes=decision_bytes,
        )
        if client.has_current_independent_host_trust() is not True:
            raise ValueError
        return client, worker_host_id, verifier_host_id, {
            "authority_key_set_sha256": authority_digest,
            "enrollment_sha256": enrollment_digest,
            "host_decision_sha256": decision_digest,
            "ca_bundle_sha256": ca_digest,
        }
    except Exception:
        raise ValueError("pinned verifier CLI: verifier trust material unavailable") from None
