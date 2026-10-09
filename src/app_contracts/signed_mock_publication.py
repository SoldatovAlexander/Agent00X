"""Local-only operator path from signed stage approval to an in-memory PR."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import tempfile
from pathlib import Path
import re
from typing import Any

from .authority import DeterministicPolicy
from .authority_key_set import (
    AuthorityKeySetError,
    AuthorityKeySetPinMismatch,
    MAX_AUTHORITY_KEY_SET_BYTES,
    load_control_plane_authority_key_set,
)
from .broker import InMemoryCredentialBroker
from .controlled_publication import (
    run_controlled_local_publication,
    run_enrolled_signed_approval_local_mock_publication,
)
from .durable_stage import SQLiteStagedArtifactStore
from .digests import sha256_digest
from .gateway import GatewayDecision, GatewayPath
from .mock_github import MockGitHubEndpoint
from .observer_runtime import (
    ControlledPublicationCallFailedError,
    ControlledPublicationJournalError,
    ControlledPublicationOutcomeUnknownError,
    JournaledProposalWorker,
    WorkerJournalError,
)
from .observation_store import SQLiteObservationStore
from .publication import PublicationJournal
from .publication_seed import (
    PublicationSeed,
    bind_publication_seed_to_target,
    derive_publication_intent,
)
from .signed_approval import (
    SignedApprovalError,
    load_verified_signed_approval,
)


class SignedMockPublicationError(ValueError):
    """A signed-stage mock publication could not safely complete."""


def _load_authority_key_set(
    path: str | Path, expected_digest: str
) -> tuple[dict[str, bytes], str]:
    try:
        return load_control_plane_authority_key_set(
            path,
            expected_digest=expected_digest,
        )
    except AuthorityKeySetPinMismatch:
        raise SignedMockPublicationError(
            "signed mock publication: authority key set pin mismatch"
        ) from None
    except (OSError, AuthorityKeySetError, ValueError):
        raise SignedMockPublicationError(
            "signed mock publication: authority key set unavailable"
        ) from None


def publish_signed_stage_mock(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    signed_approval_path: str | Path,
    trust_profile_path: str | Path,
    *,
    now: datetime | None = None,
    observer_store: SQLiteObservationStore | None = None,
    observer_run_id: str | None = None,
    approver_enrollment_path: str | Path | None = None,
    trusted_authority_keys: object | None = None,
    trusted_verifier_authority_keys: object | None = None,
    authority_key_set_digest: str | None = None,
) -> dict[str, Any]:
    """Verify exact inputs and run only the existing controlled local mock path.

    No provider endpoint is accepted or constructed. An operator-supplied
    trust profile remains unauthenticated and this function never authenticates
    a human or performs a real external write.
    """

    if (approver_enrollment_path is None) != (trusted_authority_keys is None):
        raise SignedMockPublicationError(
            "signed mock publication: enrollment trust is unavailable"
        )
    if (approver_enrollment_path is None) != (authority_key_set_digest is None):
        raise SignedMockPublicationError(
            "signed mock publication: authority key set unavailable"
        )
    if authority_key_set_digest is not None and (
        type(authority_key_set_digest) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", authority_key_set_digest) is None
    ):
        raise SignedMockPublicationError(
            "signed mock publication: authority key set unavailable"
        )
    if (observer_store is None) != (observer_run_id is None):
        raise SignedMockPublicationError("signed mock publication: observer configuration is invalid")
    observer = None
    process_id = None
    if observer_store is not None:
        if type(observer_store) is not SQLiteObservationStore:
            raise SignedMockPublicationError("signed mock publication: observer configuration is invalid")
        try:
            with SQLiteStagedArtifactStore(database_path, read_only=True) as stage_store:
                staged_artifact = stage_store.load(staged_change_digest)
            payload = staged_artifact.payload_copy()
            seed = PublicationSeed(**payload["seed"])
            process_id = seed.process_id
            observer = JournaledProposalWorker.resume_existing(
                _NoOpProposalWorker(),
                observer_store,
                process_id=process_id,
                run_id=observer_run_id,
            )
        except Exception:
            raise SignedMockPublicationError("signed mock publication: observer run rejected") from None

    def dispatch() -> dict[str, Any]:
        return _publish_signed_stage_mock_verified(
            database_path,
            staged_change_digest,
            request_path,
            signed_approval_path,
            trust_profile_path,
            now=now,
            observer=observer,
            process_id=process_id,
            approver_enrollment_path=approver_enrollment_path,
            trusted_authority_keys=trusted_authority_keys,
            trusted_verifier_authority_keys=trusted_verifier_authority_keys,
        )

    if observer is None:
        result = dispatch()
    else:
        try:
            result = observer.run_local_mock_publication(
                dispatch, process_id=process_id
            )
            result = dict(result)
            result["observer"] = observer.observer_reference()
        except (
            ControlledPublicationJournalError,
            ControlledPublicationCallFailedError,
            ControlledPublicationOutcomeUnknownError,
            WorkerJournalError,
        ):
            raise SignedMockPublicationError(
                "signed mock publication: observer run rejected"
            ) from None
    if authority_key_set_digest is not None:
        result["authority_key_set_digest"] = authority_key_set_digest
    return result


class _NoOpProposalWorker:
    def propose(self, _request: object) -> None:
        return None


def _publish_signed_stage_mock_verified(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    signed_approval_path: str | Path,
    trust_profile_path: str | Path,
    *,
    now: datetime | None = None,
    observer: JournaledProposalWorker | None = None,
    process_id: str | None = None,
    approver_enrollment_path: str | Path | None = None,
    trusted_authority_keys: object | None = None,
    trusted_verifier_authority_keys: object | None = None,
) -> dict[str, Any]:
    moment = datetime.now(timezone.utc) if now is None else now

    def verify_approval():
        return load_verified_signed_approval(
            database_path,
            staged_change_digest,
            request_path,
            signed_approval_path,
            trust_profile_path,
            approver_enrollment_path=approver_enrollment_path,
            trusted_authority_keys=trusted_authority_keys,
            trusted_verifier_authority_keys=trusted_verifier_authority_keys,
            now=moment,
        )

    try:
        if observer is None:
            verified = verify_approval()
        else:
            verified = observer.run_controlled_step(
                "SignedApproval.verify",
                verify_approval,
                process_id=process_id,
            )
    except SignedApprovalError as exc:
        raise SignedMockPublicationError(str(exc)) from None
    if verified.result.get("decision") != "allow":
        raise SignedMockPublicationError("signed mock publication: approval denied")

    try:
        payload = verified.artifact.payload_copy()
        source_seed = PublicationSeed(**payload["seed"])
        seed = bind_publication_seed_to_target(source_seed, verified.binding)
        engine_intent = verified.request["intent"]
        intent = derive_publication_intent(
            seed, engine_intent["branch"], engine_intent["base_branch"]
        )
        staged_change = payload["staged_change"]
        actuator_id = "github-app-actuator"
        actuator_request = {
            "operation": "publish_pull_request",
            "repository_id": intent.repository_id,
            "actuator_id": actuator_id,
            "base_branch": intent.base_branch,
            "staged_change_digest": intent.staged_change_digest,
            "branch_namespace": intent.branch.split("/", 1)[0],
            "idempotency_key": intent.idempotency_key,
        }
        grant = {
            "credential_grant_id": "local-mock-only-single-use-grant",
            "actuator_id": actuator_id,
            "repository_id": intent.repository_id,
            "operation": "publish_pull_request",
            "request_digest": sha256_digest(actuator_request),
            "single_use": True,
            "credential_class": "github-app-installation",
            "expires_at": verified.approval["expires_at"],
        }
        endpoint = MockGitHubEndpoint()
        broker = InMemoryCredentialBroker(lambda: endpoint)

        def load_stage(candidate_seed: PublicationSeed) -> dict:
            if candidate_seed.staged_change_digest != staged_change_digest:
                raise SignedMockPublicationError(
                    "signed mock publication: stage digest mismatch"
                )
            return staged_change

        def allow_slow_path(_envelope: dict, *, now: datetime) -> GatewayDecision:
            return GatewayDecision(
                GatewayPath.SLOW, True, ("local-mock-only",)
            )

        envelope = {
            "intent": {"operation": "publish_pull_request"},
            "destination": {
                "port": "local-mock",
                "repository_id": intent.repository_id,
                "base_branch": intent.base_branch,
            },
            "source": {"protocol": "internal", "principal_id": intent.process_id},
            "security": {"tainted": False, "sensitivity": "internal"},
            "payload": {"content_digest": intent.staged_change_digest},
            "correlation_id": intent.idempotency_key,
        }
        with tempfile.TemporaryDirectory(prefix="signed-stage-mock-") as temporary:
            journal_path = Path(temporary) / "publication.sqlite3"
            with PublicationJournal(journal_path) as journal:
                policy = DeterministicPolicy(verified.policy_config)
                publication_args = (
                    seed,
                    intent,
                    verified.approval,
                    policy,
                    engine_intent,
                    load_stage,
                    "signed-stage-mock-publication",
                    allow_slow_path,
                    envelope,
                    broker,
                    grant,
                    journal,
                    endpoint,
                )
                if approver_enrollment_path is None:
                    receipt = run_controlled_local_publication(
                        *publication_args,
                        actuator_id=actuator_id,
                        now=moment,
                        observer=observer,
                        trusted_verifier_authority_keys=trusted_verifier_authority_keys,
                    )
                else:
                    enrolled_publication_args = (
                        seed,
                        intent,
                        policy,
                        engine_intent,
                        load_stage,
                        "signed-stage-mock-publication",
                        allow_slow_path,
                        envelope,
                        broker,
                        grant,
                        journal,
                        endpoint,
                    )
                    receipt = run_enrolled_signed_approval_local_mock_publication(
                        database_path,
                        staged_change_digest,
                        request_path,
                        signed_approval_path,
                        trust_profile_path,
                        approver_enrollment_path,
                        trusted_authority_keys,
                        *enrolled_publication_args,
                        actuator_id=actuator_id,
                        now=moment,
                        observer=observer,
                        trusted_verifier_authority_keys=trusted_verifier_authority_keys,
                    )
                journal_record = journal.get(intent.process_id)
        if (
            receipt.staged_change_digest != staged_change_digest
            or receipt.repository_id != intent.repository_id
            or receipt.branch != intent.branch
            or receipt.base_branch != intent.base_branch
            or journal_record.status != "completed"
            or journal_record.pull_request_id != receipt.pull_request_id
            or endpoint.find_by_idempotency_key(intent.idempotency_key) is not receipt
            or len(broker.opened_grants) != 1
        ):
            raise SignedMockPublicationError(
                "signed mock publication: local receipt verification failed"
            )
        evidence = {
            "schema": "signed-stage-mock-publication/v1",
            "status": "mock_published",
            "staged_change_digest": staged_change_digest,
            "repository_id": receipt.repository_id,
            "branch": receipt.branch,
            "base_branch": receipt.base_branch,
            "mock_receipt_id": receipt.pull_request_id,
            "idempotency_key": receipt.idempotency_key,
            "destination": "in_memory_mock_only",
            "external_write": False,
            "identity_authenticated": False,
            "trust_profile_origin": verified.result["trust_profile_origin"],
        }
        if "approver_enrollment" in verified.result:
            evidence["approver_enrollment"] = verified.result["approver_enrollment"]
        return evidence
    except SignedMockPublicationError:
        raise
    except Exception:
        raise SignedMockPublicationError(
            "signed mock publication: controlled local path failed"
        ) from None


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description=(
            "Verify a signed approval for one exact stage and publish only to "
            "an in-memory local mock."
        )
    )
    parser.add_argument("database", help="existing verified SQLite stage database")
    parser.add_argument("staged_change_digest", help="exact sha256 staged digest")
    parser.add_argument("request", help="EXP-552 approval-request/v1 JSON")
    parser.add_argument("signed_approval", help="signed-approval/v1 JSON")
    parser.add_argument("trust_profile", help="operator-supplied public-key/policy JSON")
    parser.add_argument(
        "--observer-db",
        help="optional existing SQLite observer journal for exact-run continuation",
    )
    parser.add_argument(
        "--observer-run-id",
        help="resume this exact run from --observer-db",
    )
    parser.add_argument(
        "--approver-enrollment",
        help="authority-signed approver-key enrollment JSON",
    )
    parser.add_argument(
        "--authority-key-set",
        help="control-plane public-key set JSON (validated against the digest below)",
    )
    parser.add_argument(
        "--authority-key-set-digest",
        help="out-of-band pinned sha256 digest for --authority-key-set",
    )
    parser.add_argument(
        "--verifier-authority-key-set",
        help="caller-pinned public verifier-authority key set JSON",
    )
    parser.add_argument(
        "--verifier-authority-key-set-digest",
        help="out-of-band pinned sha256 digest for the verifier authority key set",
    )
    args = parser.parse_args(argv)
    observer_store = None
    try:
        enrollment_inputs = (
            args.approver_enrollment,
            args.authority_key_set,
            args.authority_key_set_digest,
        )
        if any(value is None for value in enrollment_inputs) and not all(
            value is None for value in enrollment_inputs
        ):
            raise SignedMockPublicationError(
                "signed mock publication: enrollment trust is unavailable"
            )
        authority_keys = None
        authority_key_set_digest = None
        if args.authority_key_set is not None:
            authority_keys, authority_key_set_digest = _load_authority_key_set(
                args.authority_key_set,
                args.authority_key_set_digest,
            )
            if (
                type(args.authority_key_set_digest) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", args.authority_key_set_digest)
                is None
                or args.authority_key_set_digest != authority_key_set_digest
            ):
                raise SignedMockPublicationError(
                    "signed mock publication: authority key set pin mismatch"
                )
        verifier_key_set_inputs = (
            args.verifier_authority_key_set,
            args.verifier_authority_key_set_digest,
        )
        if any(value is None for value in verifier_key_set_inputs) and not all(
            value is None for value in verifier_key_set_inputs
        ):
            raise SignedMockPublicationError(
                "signed mock publication: verifier authority key set unavailable"
            )
        verifier_authority_keys = None
        if args.verifier_authority_key_set is not None:
            verifier_authority_keys, _verifier_key_set_digest = (
                load_control_plane_authority_key_set(
                    args.verifier_authority_key_set,
                    expected_digest=args.verifier_authority_key_set_digest,
                )
            )
        if (args.observer_db is None) != (args.observer_run_id is None):
            raise SignedMockPublicationError(
                "signed mock publication: observer configuration is invalid"
            )
        if args.observer_db is not None:
            observer_path = Path(args.observer_db)
            try:
                if (
                    not observer_path.is_absolute()
                    or observer_path.is_symlink()
                    or not observer_path.is_file()
                ):
                    raise ValueError
                resolved_observer = observer_path.resolve(strict=True)
                input_paths = (
                    Path(args.database),
                    Path(args.request),
                    Path(args.signed_approval),
                    Path(args.trust_profile),
                    *(
                        (Path(args.approver_enrollment), Path(args.authority_key_set))
                        if args.approver_enrollment is not None
                        else ()
                    ),
                )
                if any(
                    resolved_observer == path.resolve(strict=True)
                    for path in input_paths
                ):
                    raise ValueError
            except Exception:
                raise SignedMockPublicationError(
                    "signed mock publication: observer database unavailable"
                ) from None
            observer_store = SQLiteObservationStore(observer_path)
        result = publish_signed_stage_mock(
            args.database,
            args.staged_change_digest,
            args.request,
            args.signed_approval,
            args.trust_profile,
            now=now,
            observer_store=observer_store,
            observer_run_id=args.observer_run_id,
            approver_enrollment_path=args.approver_enrollment,
            trusted_authority_keys=authority_keys,
            trusted_verifier_authority_keys=verifier_authority_keys,
            authority_key_set_digest=authority_key_set_digest,
        )
    except SignedMockPublicationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("signed mock publication: controlled local path failed", file=sys.stderr)
        return 2
    finally:
        if observer_store is not None:
            observer_store.close()
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
    return 0
