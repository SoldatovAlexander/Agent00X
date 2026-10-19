"""Explicit typed-digest confirmation for a local mock-only publication run."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .approval_signature import approval_signature_payload
from .authority import DeterministicPolicy, PolicyConfig
from .broker import InMemoryCredentialBroker
from .controlled_publication import run_controlled_local_publication
from .digests import sha256_digest
from .durable_stage import (
    DurableStageStoreError,
    SQLiteStagedArtifactStore,
    StagedArtifact,
)
from .gateway import GatewayDecision, GatewayPath
from .mock_github import MockGitHubEndpoint, MockPullRequest
from .observer_runtime import (
    ControlledPublicationJournalError,
    ControlledPublicationOutcomeUnknownError,
    JournaledProposalWorker,
    WorkerJournalError,
)
from .observation_store import ObservationStoreError, SQLiteObservationStore
from .operator_confirmation import (
    OperatorConfirmationRecord,
    OperatorConfirmationStoreError,
    SQLiteOperatorConfirmationStore,
)
from .publication import PublicationJournal
from .publication_seed import (
    PublicationIntent,
    PublicationSeed,
    derive_publication_intent,
    verifier_trust_intent_binding,
)
from .stage_preview import StagePreviewError, render_stage_preview

MOCK_POLICY_VERSION = "local-mock-stage-approval-v1"
MOCK_ACTUATOR_ID = "local-mock-github-actuator"
APPROVAL_TTL_SECONDS = 300
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class StageApprovalError(ValueError):
    """A local exact-digest confirmation cannot be accepted."""


def run_local_mock_publication(
    artifact: StagedArtifact,
    confirmed_staged_digest: str,
    branch: str,
    base_branch: str,
    *,
    now: datetime,
    observer: JournaledProposalWorker | None = None,
) -> MockPullRequest:
    """Consume a typed digest once and run only the in-memory mock path.

    This helper deliberately accepts no policy, gateway, broker, journal, or
    endpoint injection. It is a local exercise, not authenticated approval or
    a path to a real provider.
    """
    if type(artifact) is not StagedArtifact:
        raise StageApprovalError("stage approval: artifact is invalid")
    if observer is not None and type(observer) is not JournaledProposalWorker:
        raise StageApprovalError("stage approval: observer is invalid")
    if (
        not isinstance(confirmed_staged_digest, str)
        or _DIGEST_PATTERN.fullmatch(confirmed_staged_digest) is None
        or confirmed_staged_digest != artifact.staged_change_digest
    ):
        raise StageApprovalError("stage approval: digest confirmation mismatch")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise StageApprovalError("stage approval: clock is invalid")
    if now.utcoffset() is None:
        raise StageApprovalError("stage approval: clock is invalid")
    artifact, payload, seed, intent = _validated_stage_intent(
        artifact, branch, base_branch
    )

    expires_at = (now + timedelta(seconds=APPROVAL_TTL_SECONDS)).astimezone(
        timezone.utc
    ).isoformat()
    approved_at = now.astimezone(timezone.utc).isoformat()
    mock_approver_key = Ed25519PrivateKey.generate()
    mock_approver_public_key = mock_approver_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    approval_id = "local-mock-approval-" + uuid4().hex
    engine_intent = _engine_intent(
        intent,
        approval_id,
        expires_at,
        verifier_trust_intent_binding(
            seed,
            signed_evidence_available=(
                type(payload.get("verifier_trust_evidence")) is dict
            ),
        ),
    )
    approval = {
        "schema_version": 1,
        "process_id": intent.process_id,
        "repository_id": intent.repository_id,
        "operation": "publish_pull_request",
        "approval_id": approval_id,
        "approver_id": "local-mock-operator",
        "policy_version": MOCK_POLICY_VERSION,
        "approved_at": approved_at,
        "expires_at": expires_at,
        "staged_change_digest": intent.staged_change_digest,
        "approved_intent_digest": sha256_digest(engine_intent),
    }
    approval["signature"] = mock_approver_key.sign(
        approval_signature_payload(approval)
    ).hex()
    staged_change = payload["staged_change"]
    endpoint = MockGitHubEndpoint()
    broker = InMemoryCredentialBroker(lambda: endpoint)
    policy = DeterministicPolicy(
        PolicyConfig(
            version=MOCK_POLICY_VERSION,
            allowed_repositories=frozenset({intent.repository_id}),
            allowed_actuators=frozenset({MOCK_ACTUATOR_ID}),
            allowed_approver_ids=frozenset({"local-mock-operator"}),
            trusted_approver_public_keys={
                "local-mock-operator": mock_approver_public_key
            },
            decision_ttl_seconds=APPROVAL_TTL_SECONDS,
        )
    )
    actuator_request = _actuator_request(intent)
    grant = {
        "credential_grant_id": "local-mock-grant-" + uuid4().hex,
        "actuator_id": MOCK_ACTUATOR_ID,
        "repository_id": intent.repository_id,
        "operation": "publish_pull_request",
        "request_digest": sha256_digest(actuator_request),
        "single_use": True,
        "credential_class": "github-app-installation",
        "expires_at": expires_at,
    }

    def gateway_envelope() -> dict:
        return {
            "intent": {"operation": "publish_pull_request"},
            "destination": {
                "port": "approval",
                "repository_id": intent.repository_id,
                "base_branch": intent.base_branch,
            },
            "source": {"protocol": "internal", "principal_id": intent.process_id},
            "security": {"tainted": False, "sensitivity": "internal"},
            "payload": {"content_digest": intent.staged_change_digest},
            "correlation_id": intent.idempotency_key,
        }

    class MockOnlyGateway:
        def __call__(self, _envelope: dict, *, now: datetime) -> GatewayDecision:
            return GatewayDecision(
                GatewayPath.SLOW, True, ("local-mock-only", "write-operation")
            )

    def load_stage(candidate_seed: PublicationSeed) -> dict:
        if candidate_seed.staged_change_digest != artifact.staged_change_digest:
            raise StageApprovalError("stage approval: stage binding mismatch")
        return staged_change

    try:
        with tempfile.TemporaryDirectory(prefix="agent00x-local-mock-approval-") as temporary:
            journal_path = Path(temporary) / "publication.sqlite3"
            with PublicationJournal(journal_path) as journal:
                def controlled_call() -> MockPullRequest:
                    return run_controlled_local_publication(
                        seed,
                        intent,
                        approval,
                        policy,
                        engine_intent,
                        load_stage,
                        "decision-" + uuid4().hex,
                        MockOnlyGateway(),
                        gateway_envelope(),
                        broker,
                        grant,
                        journal,
                        endpoint,
                        actuator_id=MOCK_ACTUATOR_ID,
                        now=now,
                        observer=observer,
                    )

                if observer is None:
                    receipt = controlled_call()
                else:
                    receipt = observer.run_local_mock_publication(
                        controlled_call, process_id=intent.process_id
                    )
                if (
                    receipt.staged_change_digest != artifact.staged_change_digest
                    or receipt.repository_id != seed.repository_id
                    or journal.get(intent.process_id).status != "completed"
                ):
                    raise StageApprovalError("stage approval: mock receipt mismatch")
        return receipt
    except (StageApprovalError, ControlledPublicationJournalError,
            ControlledPublicationOutcomeUnknownError):
        raise
    except Exception:
        raise StageApprovalError("stage approval: local mock path failed") from None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Review a saved stage and approve its digest for local mock gates only."
    )
    parser.add_argument("database", help="existing local SQLite stage database")
    parser.add_argument("staged_change_digest", help="exact sha256 stage digest")
    parser.add_argument("branch", help="explicit branch in the agent/ namespace")
    parser.add_argument("base_branch", help="explicit pull-request base branch")
    parser.add_argument(
        "--confirmation-db",
        required=True,
        help="separate SQLite database for local typed-digest confirmation evidence",
    )
    parser.add_argument(
        "--observer-db",
        help="optional absolute SQLite database for partial local observer evidence",
    )
    parser.add_argument(
        "--observer-run-id",
        help="resume this exact existing observer run from --observer-db",
    )
    args = parser.parse_args(argv)
    observer_store = None
    observer = None
    observer_locator = None
    try:
        if args.observer_run_id is not None and args.observer_db is None:
            raise StageApprovalError(
                "stage approval: observer run requires observer database"
            )
        if _paths_alias(args.database, args.confirmation_db):
            raise StageApprovalError(
                "stage approval: confirmation database must be separate"
            )
        if args.observer_db is not None and (
            not Path(args.observer_db).is_absolute()
            or _paths_alias(args.database, args.observer_db)
            or _paths_alias(args.confirmation_db, args.observer_db)
        ):
            raise StageApprovalError("stage approval: observer database path is invalid")
        if args.observer_run_id is not None and (
            Path(args.observer_db).is_symlink()
            or not Path(args.observer_db).is_file()
        ):
            raise StageApprovalError("stage approval: observer run database is unavailable")
        with SQLiteStagedArtifactStore(args.database, read_only=True) as store:
            artifact = store.load(args.staged_change_digest)
        artifact, _, _, intent = _validated_stage_intent(
            artifact, args.branch, args.base_branch
        )
        preview = json.loads(render_stage_preview(artifact))
        preview["requested_action"] = {
            "operation": "publish_pull_request",
            "branch": intent.branch,
            "base_branch": intent.base_branch,
            "intent_digest": sha256_digest(asdict(intent)),
            "destination": "in-memory MockGitHubEndpoint only",
            "approval_ttl_seconds": APPROVAL_TTL_SECONDS,
            "external_write": False,
        }
        print(json.dumps(preview, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2))
        try:
            confirmation = input(
                "Type the exact staged_change_digest to approve this local MOCK run: "
            )
        except (EOFError, KeyboardInterrupt):
            raise StageApprovalError("stage approval: confirmation cancelled") from None
        if confirmation != artifact.staged_change_digest:
            raise StageApprovalError("stage approval: digest confirmation mismatch")
        confirmed_at = datetime.now(timezone.utc)
        confirmation_id = "operator-confirmation-" + uuid4().hex
        confirmation_record = OperatorConfirmationRecord(
            confirmation_id=confirmation_id,
            staged_change_digest=artifact.staged_change_digest,
            intent_digest=sha256_digest(asdict(intent)),
            repository_id=intent.repository_id,
            branch=intent.branch,
            operation="publish_pull_request",
            confirmed_at=confirmed_at.isoformat(),
            expires_at=(confirmed_at + timedelta(seconds=APPROVAL_TTL_SECONDS)).isoformat(),
            status="confirmed",
        )
        with SQLiteOperatorConfirmationStore(args.confirmation_db) as confirmation_store:
            confirmation_store.save_confirmed(confirmation_record)
            if confirmation_store.load(confirmation_id) != confirmation_record:
                raise OperatorConfirmationStoreError(
                    "operator confirmation: exact readback failed"
                )
        if args.observer_db is not None:
            observer_store = SQLiteObservationStore(args.observer_db)
            observer_worker = SimpleNamespace(propose=lambda _request: None)
            if args.observer_run_id is None:
                observer = JournaledProposalWorker(
                    observer_worker,
                    observer_store,
                    process_id=intent.process_id,
                    task_id="task-" + uuid4().hex,
                )
            else:
                observer = JournaledProposalWorker.resume_existing(
                    observer_worker,
                    observer_store,
                    process_id=intent.process_id,
                    run_id=args.observer_run_id,
                )
        receipt = run_local_mock_publication(
            artifact,
            confirmation,
            args.branch,
            args.base_branch,
            now=confirmed_at,
            observer=observer,
        )
        if observer is not None:
            observer_locator = observer.observer_reference()
        with SQLiteOperatorConfirmationStore(args.confirmation_db) as confirmation_store:
            completed = confirmation_store.complete_mock(
                confirmation_id, receipt.pull_request_id
            )
            if (
                completed.status != "mock_completed"
                or completed.mock_receipt_id != receipt.pull_request_id
                or completed.staged_change_digest != artifact.staged_change_digest
                or completed.intent_digest != sha256_digest(asdict(intent))
            ):
                raise OperatorConfirmationStoreError(
                    "operator confirmation: completed readback mismatch"
                )
        if observer is not None:
            observer.finish_agent_invocation(status="ok")
            observer.finish_run(status="ok")
            observer_locator = observer.observer_reference()
    except (
        DurableStageStoreError,
        OperatorConfirmationStoreError,
        ObservationStoreError,
        StageApprovalError,
        StagePreviewError,
        ControlledPublicationJournalError,
        WorkerJournalError,
    ) as exc:
        if args.observer_db is None:
            print(str(exc), file=sys.stderr)
        else:
            if observer is not None:
                invocation_finished = False
                try:
                    observer.finish_agent_invocation(status="failed")
                    invocation_finished = True
                except Exception:
                    # Do not close an invocation with an unresolved outcome.
                    pass
                if invocation_finished:
                    try:
                        observer.finish_run(status="failed")
                    except Exception:
                        # An unsafe or incomplete run remains visibly partial.
                        pass
                try:
                    observer_locator = observer.observer_reference()
                except Exception:
                    observer_locator = None
            if isinstance(exc, ControlledPublicationOutcomeUnknownError):
                error_code = "publication-outcome-unknown"
            elif isinstance(exc, ControlledPublicationJournalError):
                error_code = "observer-gate-failed"
            elif isinstance(exc, ObservationStoreError):
                error_code = "observer-store-failed"
            elif isinstance(exc, WorkerJournalError):
                error_code = "observer-run-rejected"
            elif isinstance(exc, OperatorConfirmationStoreError):
                error_code = "confirmation-store-failed"
            elif isinstance(exc, DurableStageStoreError):
                error_code = "stage-read-failed"
            else:
                error_code = "stage-approval-failed"
            print(
                json.dumps(
                    {
                        "schema": "local-mock-confirmation-result/v1",
                        "status": "failed",
                        "error_code": error_code,
                        "observer": observer_locator,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
        return 2
    finally:
        if observer_store is not None:
            observer_store.close()
    output = {
                "schema": "local-mock-confirmation-receipt/v1",
                "staged_change_digest": receipt.staged_change_digest,
                "repository_id": receipt.repository_id,
                "branch": receipt.branch,
                "base_branch": intent.base_branch,
                "mock_pull_request_id": receipt.pull_request_id,
                "confirmation_record_id": confirmation_id,
                "confirmation_record_persisted": True,
                "authenticated": False,
                "external_write": False,
            }
    if observer_locator is not None:
        output["observer"] = observer_locator
    print(json.dumps(output, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0


def _paths_alias(first: str, second: str) -> bool:
    try:
        left = Path(first).resolve(strict=False)
        right = Path(second).resolve(strict=False)
        if left == right:
            return True
        return left.exists() and right.exists() and left.samefile(right)
    except Exception:
        raise StageApprovalError(
            "stage approval: database paths are invalid"
        ) from None


def _validated_stage_intent(
    artifact: StagedArtifact, branch: str, base_branch: str
) -> tuple[StagedArtifact, dict, PublicationSeed, PublicationIntent]:
    if type(artifact) is not StagedArtifact:
        raise StageApprovalError("stage approval: artifact is invalid")
    try:
        validated = StagedArtifact(
            staged_change_digest=artifact.staged_change_digest,
            verified_contents_digest=artifact.verified_contents_digest,
            artifact_digest=artifact.artifact_digest,
            canonical_payload=artifact.canonical_payload,
        )
        payload = validated.payload_copy()
        seed = PublicationSeed(**payload["seed"])
        intent = derive_publication_intent(seed, branch, base_branch)
        return validated, payload, seed, intent
    except Exception:
        raise StageApprovalError("stage approval: verified stage or intent is invalid") from None


def _engine_intent(
    intent: PublicationIntent,
    approval_id: str,
    expires_at: str,
    verifier_trust: dict[str, str | None],
) -> dict:
    return {
        "process_id": intent.process_id,
        "repository_id": intent.repository_id,
        "base_commit": intent.base_commit,
        "base_branch": intent.base_branch,
        "operation": "publish_pull_request",
        "approval_id": approval_id,
        "expires_at": expires_at,
        "branch_namespace": intent.branch.split("/", 1)[0],
        "idempotency_key": intent.idempotency_key,
        "staged_change_digest": intent.staged_change_digest,
        "verifier_trust": verifier_trust,
    }


def _actuator_request(intent: PublicationIntent) -> dict:
    return {
        "operation": "publish_pull_request",
        "repository_id": intent.repository_id,
        "actuator_id": MOCK_ACTUATOR_ID,
        "base_branch": intent.base_branch,
        "staged_change_digest": intent.staged_change_digest,
        "branch_namespace": intent.branch.split("/", 1)[0],
        "idempotency_key": intent.idempotency_key,
    }


if __name__ == "__main__":
    raise SystemExit(main())
