"""Read-only cryptographic revalidation of persisted verifier-stage evidence.

This verifies the stored authority signatures and verifier response against a
caller-pinned authority-key mapping. It validates the signed request digest but
does not reconstruct the original full VerifierInput/snapshot bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import base64
import hashlib
import json

from .durable_stage import (
    DurableStageError,
    StagedArtifact,
    validate_verifier_request_binding,
)
from .publication_seed import PublicationSeed
from .verifier_attestation import (
    MAX_ATTESTATION_BYTES,
    VerifierAttestationError,
    verify_persisted_signed_verifier_response,
)
from .verifier_process import (
    MAX_VERIFIER_REQUEST_BYTES,
    VerifierProcessError,
    parse_verifier_request,
    serialize_verifier_request,
)
from .verifier_host_trust_decision import (
    MAX_DECISION_BYTES,
    VerifierHostTrustDecisionError,
    verify_verifier_host_trust_decision,
)
from .verifier_trust_enrollment import (
    MAX_ENROLLMENT_BYTES,
    VerifierTrustEnrollmentError,
    verify_verifier_trust_enrollment,
)


_VERIFIED_PROVENANCE_TOKEN = object()


class VerifierProvenanceError(ValueError):
    """Persisted verifier provenance could not be safely revalidated."""


@dataclass(frozen=True, repr=False)
class VerifiedStageVerifierProvenance:
    """Opaque proof that this exact stored stage's signatures were rechecked."""

    verifier_attestation_digest: str
    verifier_key_id: str
    verifier_profile_digest: str
    verifier_request_digest: str
    verifier_trust_enrollment_digest: str
    verifier_host_trust_decision_digest: str
    enrollment_authority_key_id: str
    decision_authority_key_id: str
    attestation_issued_at: str
    _verification_token: object = field(repr=False, compare=False)
    authority_signatures_valid: bool = True
    verifier_signature_valid: bool = True
    request_input_reconstructed: bool = False
    identity_authenticated: bool = False
    provider_write: bool = False

    def __repr__(self) -> str:
        return (
            "VerifiedStageVerifierProvenance("
            f"verifier_attestation_digest={self.verifier_attestation_digest!r}, "
            f"verifier_key_id={self.verifier_key_id!r}, "
            f"verifier_trust_enrollment_digest={self.verifier_trust_enrollment_digest!r}, "
            f"verifier_host_trust_decision_digest={self.verifier_host_trust_decision_digest!r}, "
            "authority_signatures_valid=True, verifier_signature_valid=True, "
            f"request_input_reconstructed={self.request_input_reconstructed!r}, "
            "identity_authenticated=False, "
            "provider_write=False)"
        )


def is_verified_stage_verifier_provenance(value: object) -> bool:
    return (
        type(value) is VerifiedStageVerifierProvenance
        and value._verification_token is _VERIFIED_PROVENANCE_TOKEN
    )


def verify_staged_verifier_provenance(
    artifact: StagedArtifact,
    *,
    trusted_authority_keys: object,
    now: datetime | None = None,
) -> VerifiedStageVerifierProvenance:
    """Revalidate signed records from one reopened immutable stage.

    The caller supplies authority public keys from an independently pinned
    trust source. The signed request digest is verified as part of the
    attestation, but its original request bytes are intentionally not claimed
    to have been reconstructed.
    """
    try:
        if type(artifact) is not StagedArtifact:
            raise ValueError
        moment = _clock(datetime.now(timezone.utc) if now is None else now)
        if (
            type(trusted_authority_keys) is not dict
            or not 1 <= len(trusted_authority_keys) <= 32
            or any(
                type(key_id) is not str
                or not key_id
                or type(key_bytes) is not bytes
                or len(key_bytes) != 32
                for key_id, key_bytes in trusted_authority_keys.items()
            )
        ):
            raise ValueError
        payload = artifact.payload_copy()
        seed = PublicationSeed(**payload["seed"])
        evidence = payload.get("verifier_trust_evidence")
        if type(evidence) is not dict or evidence.get("schema") not in {
            "persisted-verifier-trust-evidence/v1",
            "persisted-verifier-trust-evidence/v2",
        }:
            raise ValueError
        enrollment_bytes = _decode(
            evidence.get("trust_enrollment_base64"), MAX_ENROLLMENT_BYTES
        )
        decision_bytes = _decode(
            evidence.get("host_trust_decision_base64"), MAX_DECISION_BYTES
        )
        attestation_bytes = _decode(
            evidence.get("signed_response_base64"), MAX_ATTESTATION_BYTES
        )
        enrollment_record = _canonical_record(enrollment_bytes, MAX_ENROLLMENT_BYTES)
        decision_record = _canonical_record(decision_bytes, MAX_DECISION_BYTES)
        if (
            _sha256(enrollment_bytes) != seed.verifier_trust_enrollment_digest
            or _sha256(decision_bytes) != seed.verifier_host_trust_decision_digest
            or _sha256(attestation_bytes) != seed.verifier_attestation_digest
            or enrollment_record.get("verifier_key_id")
            != seed.verifier_attestation_key_id
            or enrollment_record.get("verifier_profile_digest")
            != seed.verifier_attestation_profile_digest
        ):
            raise ValueError

        enrollment = verify_verifier_trust_enrollment(
            enrollment_bytes,
            trusted_authority_keys=trusted_authority_keys,
            expected_endpoint_url=enrollment_record.get("endpoint_url"),
            expected_verifier_id=enrollment_record.get("verifier_id"),
            expected_verifier_profile_digest=seed.verifier_attestation_profile_digest,
            now=moment,
        )
        if (
            enrollment.enrollment_digest != seed.verifier_trust_enrollment_digest
            or enrollment.verifier_key_id != seed.verifier_attestation_key_id
            or enrollment.verifier_profile_digest
            != seed.verifier_attestation_profile_digest
        ):
            raise ValueError
        decision = verify_verifier_host_trust_decision(
            decision_bytes,
            trusted_authority_keys=trusted_authority_keys,
            expected_enrollment_digest=enrollment.enrollment_digest,
            expected_endpoint_url=enrollment.endpoint_url,
            expected_verifier_id=enrollment.verifier_id,
            expected_verifier_profile_digest=enrollment.verifier_profile_digest,
            expected_verifier_key_id=enrollment.verifier_key_id,
            expected_worker_host_id=enrollment.worker_host_id,
            expected_verifier_host_id=enrollment.verifier_host_id,
            expected_host_separation_evidence_digest=(
                enrollment.host_separation_evidence_digest
            ),
            now=moment,
        )
        if decision.decision_digest != seed.verifier_host_trust_decision_digest:
            raise ValueError
        verifier_check = verify_persisted_signed_verifier_response(
            attestation_bytes,
            trusted_public_keys={enrollment.verifier_key_id: enrollment.verifier_public_key},
            expected_key_id=seed.verifier_attestation_key_id,
            expected_request_digest=evidence.get("request_digest"),
            expected_verifier_profile_digest=seed.verifier_attestation_profile_digest,
            expected_verifier_result=payload["verifier_result"],
            now=moment,
        )
        request_reconstructed = False
        if "verifier_request_base64" in evidence:
            request_bytes = _decode(
                evidence.get("verifier_request_base64"),
                MAX_VERIFIER_REQUEST_BYTES,
            )
            request = parse_verifier_request(request_bytes)
            if (
                serialize_verifier_request(request) != request_bytes
                or _sha256(request_bytes) != verifier_check["request_digest"]
            ):
                raise ValueError
            validate_verifier_request_binding(
                request,
                evidence.get("request_context"),
                seed,
                payload,
                verifier_check["request_digest"],
            )
            request_reconstructed = True
        elif evidence.get("schema") != "persisted-verifier-trust-evidence/v1":
            raise ValueError
        return VerifiedStageVerifierProvenance(
            verifier_attestation_digest=verifier_check["attestation_digest"],
            verifier_key_id=verifier_check["key_id"],
            verifier_profile_digest=verifier_check["verifier_profile_digest"],
            verifier_request_digest=verifier_check["request_digest"],
            verifier_trust_enrollment_digest=enrollment.enrollment_digest,
            verifier_host_trust_decision_digest=decision.decision_digest,
            enrollment_authority_key_id=enrollment.authority_key_id,
            decision_authority_key_id=decision.authority_key_id,
            attestation_issued_at=verifier_check["issued_at"],
            _verification_token=_VERIFIED_PROVENANCE_TOKEN,
            request_input_reconstructed=request_reconstructed,
        )
    except VerifierProvenanceError:
        raise
    except (
        DurableStageError,
        VerifierAttestationError,
        VerifierTrustEnrollmentError,
        VerifierHostTrustDecisionError,
        VerifierProcessError,
    ):
        raise VerifierProvenanceError(
            "verifier provenance: stage evidence verification failed"
        ) from None
    except Exception:
        raise VerifierProvenanceError(
            "verifier provenance: stage evidence verification failed"
        ) from None


def _decode(value: object, limit: int) -> bytes:
    try:
        if type(value) is not str or len(value) > ((limit + 2) // 3) * 4:
            raise ValueError
        decoded = base64.b64decode(value, validate=True)
        if not decoded or len(decoded) > limit:
            raise ValueError
        return decoded
    except Exception:
        raise VerifierProvenanceError(
            "verifier provenance: stage evidence verification failed"
        ) from None


def _canonical_record(raw: bytes, limit: int) -> dict:
    try:
        record = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        canonical = json.dumps(
            record, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if type(record) is not dict or len(raw) > limit or canonical != raw:
            raise ValueError
        return record
    except Exception:
        raise VerifierProvenanceError(
            "verifier provenance: stage evidence verification failed"
        ) from None


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError
    return value.astimezone(timezone.utc)
