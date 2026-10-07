"""Local-only operator path from signed stage approval to an in-memory PR."""

from __future__ import annotations

from datetime import datetime, timezone
import tempfile
from pathlib import Path
from typing import Any

from .authority import DeterministicPolicy
from .broker import InMemoryCredentialBroker
from .controlled_publication import run_controlled_local_publication
from .digests import sha256_digest
from .gateway import GatewayDecision, GatewayPath
from .mock_github import MockGitHubEndpoint
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


def publish_signed_stage_mock(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    signed_approval_path: str | Path,
    trust_profile_path: str | Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify exact inputs and run only the existing controlled local mock path.

    No provider endpoint is accepted or constructed. An operator-supplied
    trust profile remains unauthenticated and this function never authenticates
    a human or performs a real external write.
    """

    moment = datetime.now(timezone.utc) if now is None else now
    try:
        verified = load_verified_signed_approval(
            database_path,
            staged_change_digest,
            request_path,
            signed_approval_path,
            trust_profile_path,
            now=moment,
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
                receipt = run_controlled_local_publication(
                    seed,
                    intent,
                    verified.approval,
                    DeterministicPolicy(verified.policy_config),
                    engine_intent,
                    load_stage,
                    "signed-stage-mock-publication",
                    allow_slow_path,
                    envelope,
                    broker,
                    grant,
                    journal,
                    endpoint,
                    actuator_id=actuator_id,
                    now=moment,
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
        return {
            "schema": "signed-stage-mock-publication/v1",
            "status": "mock_published",
            "staged_change_digest": staged_change_digest,
            "repository_id": receipt.repository_id,
            "branch": receipt.branch,
            "base_branch": receipt.base_branch,
            "mock_receipt_id": receipt.pull_request_id,
            "destination": "in_memory_mock_only",
            "external_write": False,
            "identity_authenticated": False,
            "trust_profile_origin": "operator_supplied_unverified",
        }
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
    args = parser.parse_args(argv)
    try:
        result = publish_signed_stage_mock(
            args.database,
            args.staged_change_digest,
            args.request,
            args.signed_approval,
            args.trust_profile,
            now=now,
        )
    except SignedMockPublicationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
    return 0
