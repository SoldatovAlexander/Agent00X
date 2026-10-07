"""Digest-confirmed operator path to one fixed GitHub App PR publication.

The CLI is capable of an external write, but it never runs implicitly: it
requires a verified exact-stage approval and a fresh terminal phrase containing
that stage digest before reading provider configuration or opening the Broker.
The trust profile is still operator-supplied and is not an identity proof.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping

from .authority import DeterministicPolicy
from .controlled_publication import run_controlled_local_publication
from .digests import sha256_bytes, sha256_digest
from .durable_stage import StagedArtifact
from .gateway import enforce
from .github_app import (
    GitHubAppBrokerConfig,
    GitHubAppCredentialBroker,
    GitHubAppInstallationTokenMinter,
    GitHubAppPublicationChannel,
    GitHubPullRequest,
)
from .publication import PublicationJournal
from .publication_seed import (
    PublicationIntent,
    PublicationSeed,
    bind_publication_seed_to_target,
    derive_publication_intent,
)
from .repository_process import PublishableFile
from .runtime_store import ProcessNotFound, SQLiteProcessStore
from .signed_approval import (
    SignedApprovalError,
    VerifiedSignedApproval,
    load_verified_signed_approval,
)
from .stage_preview import render_stage_preview

TARGET_REPOSITORY = "SoldatovAlexander/brainbooster_full_v11"
ACTUATOR_ID = "github-app-actuator"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class SignedGitHubPublicationError(ValueError):
    """A fixed signed-stage GitHub publication could not safely complete."""


def _load_approval(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    signed_approval_path: str | Path,
    trust_profile_path: str | Path,
    *,
    now: datetime,
) -> VerifiedSignedApproval:
    try:
        verified = load_verified_signed_approval(
            database_path,
            staged_change_digest,
            request_path,
            signed_approval_path,
            trust_profile_path,
            now=now,
        )
    except SignedApprovalError:
        raise SignedGitHubPublicationError(
            "signed GitHub publication: approval verification failed"
        ) from None
    if (
        verified.result.get("decision") != "allow"
        or verified.binding.source_repository_id != TARGET_REPOSITORY
        or verified.result.get("identity_authenticated") is not False
    ):
        raise SignedGitHubPublicationError(
            "signed GitHub publication: approval or target is not allowed"
        )
    return verified


def _validated_inputs(
    verified: VerifiedSignedApproval, staged_change_digest: str
) -> tuple[PublicationSeed, PublicationIntent, dict, tuple[PublishableFile, ...]]:
    try:
        payload = verified.artifact.payload_copy()
        seed = PublicationSeed(**payload["seed"])
        seed = bind_publication_seed_to_target(seed, verified.binding)
        engine_intent = verified.request["intent"]
        intent = derive_publication_intent(
            seed, engine_intent["branch"], engine_intent["base_branch"]
        )
        staged_change = payload["staged_change"]
        raw_files = payload["verified_contents"]
        if (
            seed.staged_change_digest != staged_change_digest
            or seed.source_repository_id != TARGET_REPOSITORY
            or type(staged_change) is not dict
            or type(raw_files) is not list
            or not raw_files
        ):
            raise ValueError
        files = []
        for item in raw_files:
            if type(item) is not dict or set(item) != {"path", "content"}:
                raise ValueError
            path, content = item["path"], item["content"]
            if type(path) is not str or type(content) is not str:
                raise ValueError
            files.append(
                PublishableFile(path, content, sha256_bytes(content.encode("utf-8")))
            )
        return seed, intent, staged_change, tuple(files)
    except Exception:
        raise SignedGitHubPublicationError(
            "signed GitHub publication: stage binding is invalid"
        ) from None


def _require_new_journal_path(value: object) -> Path:
    try:
        path = Path(value)
        if (
            not path.is_absolute()
            or path.is_symlink()
            or path.exists()
            or not path.parent.is_dir()
        ):
            raise ValueError
        return path
    except Exception:
        raise SignedGitHubPublicationError(
            "signed GitHub publication: journal path must be a new absolute file"
        ) from None


def publish_signed_stage_github(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    signed_approval_path: str | Path,
    trust_profile_path: str | Path,
    journal_path: str | Path,
    operator_confirmation: str,
    *,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Publish one exact signed stage after a fresh digest-bound terminal phrase.

    Provider configuration and Broker construction happen only after the
    approval is reloaded, policy allows, the fixed repository matches, the
    exact stage is rebound and the operator phrase matches. This function does
    not retry or resume an existing journal; uncertain outcomes are left for a
    separate read-only reconciliation operation.
    """
    moment = datetime.now(timezone.utc) if now is None else now
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise SignedGitHubPublicationError("signed GitHub publication: clock is invalid")
    try:
        moment = moment.astimezone(timezone.utc)
    except Exception:
        raise SignedGitHubPublicationError("signed GitHub publication: clock is invalid") from None
    if type(staged_change_digest) is not str or _DIGEST_RE.fullmatch(staged_change_digest) is None:
        raise SignedGitHubPublicationError("signed GitHub publication: stage digest is invalid")
    verified = _load_approval(
        database_path,
        staged_change_digest,
        request_path,
        signed_approval_path,
        trust_profile_path,
        now=moment,
    )
    seed, intent, staged_change, verified_files = _validated_inputs(
        verified, staged_change_digest
    )
    if operator_confirmation != f"PUBLISH {staged_change_digest}":
        raise SignedGitHubPublicationError(
            "signed GitHub publication: exact digest confirmation is required"
        )
    new_journal = _require_new_journal_path(journal_path)

    # Only non-secret provider metadata is parsed here. The private key is
    # opened by the existing token minter after all publication gates pass.
    try:
        config = GitHubAppBrokerConfig.from_environment(environ)
        if (
            config.repository != TARGET_REPOSITORY
            or config.repository_target_binding != verified.binding
        ):
            raise ValueError
    except Exception:
        raise SignedGitHubPublicationError(
            "signed GitHub publication: provider target configuration is invalid"
        ) from None
    minter = GitHubAppInstallationTokenMinter(config)
    broker = GitHubAppCredentialBroker(config, minter)

    engine_intent = verified.request["intent"]
    actuator_request = {
        "operation": "publish_pull_request",
        "repository_id": intent.repository_id,
        "actuator_id": ACTUATOR_ID,
        "base_branch": intent.base_branch,
        "staged_change_digest": staged_change_digest,
        "branch_namespace": intent.branch.split("/", 1)[0],
        "idempotency_key": intent.idempotency_key,
    }
    grant = {
        "credential_grant_id": "signed-stage-" + staged_change_digest.removeprefix("sha256:")[:24],
        "actuator_id": ACTUATOR_ID,
        "repository_id": intent.repository_id,
        "operation": "publish_pull_request",
        "request_digest": sha256_digest(actuator_request),
        "single_use": True,
        "credential_class": "github-app-installation",
        "installation_id": config.installation_id,
        "permissions": ["contents:write", "pull_requests:write"],
        "expires_at": verified.approval["expires_at"],
    }
    envelope = {
        "intent": {"operation": "publish_pull_request"},
        "destination": {
            "port": "credential-operation",
            "repository_id": intent.repository_id,
            "base_branch": intent.base_branch,
        },
        "source": {"protocol": "internal", "principal_id": intent.process_id},
        "security": {"tainted": False, "sensitivity": "restricted"},
        "payload": {"content_digest": staged_change_digest},
        "correlation_id": intent.idempotency_key,
    }
    try:
        with PublicationJournal(new_journal) as journal, SQLiteProcessStore(new_journal) as runtime:
            try:
                runtime.get(intent.idempotency_key)
            except ProcessNotFound:
                # Gateway audit events are keyed by the envelope correlation
                # id, which is the idempotency key bound to this publication.
                runtime.create(intent.idempotency_key, now=moment)

            def gateway(gateway_envelope: dict, *, now: datetime):
                return enforce(
                    gateway_envelope,
                    policy_available=True,
                    audit_sink=runtime,
                    now=now,
                )

            def load_stage(candidate_seed: PublicationSeed) -> dict:
                if candidate_seed.staged_change_digest != staged_change_digest:
                    raise ValueError("stage digest mismatch")
                return staged_change

            receipt = run_controlled_local_publication(
                seed,
                intent,
                verified.approval,
                DeterministicPolicy(verified.policy_config),
                engine_intent,
                load_stage,
                "signed-stage-github-publication",
                gateway,
                envelope,
                broker,
                grant,
                journal,
                GitHubAppPublicationChannel,
                verified_files=verified_files,
                actuator_id=ACTUATOR_ID,
                now=moment,
            )
            record = journal.get(intent.process_id)
        if (
            type(receipt) is not GitHubPullRequest
            or record.status != "completed"
            or record.pull_request_id != receipt.pull_request_id
            or record.pull_request_url != receipt.pull_request_url
            or receipt.staged_change_digest != staged_change_digest
            or receipt.repository_id != intent.repository_id
            or receipt.branch != intent.branch
            or receipt.base_branch != intent.base_branch
            or receipt.idempotency_key != intent.idempotency_key
        ):
            raise ValueError
        return {
            "schema": "signed-stage-github-publication/v1",
            "status": "pull_request_confirmed",
            "staged_change_digest": staged_change_digest,
            "repository_id": receipt.repository_id,
            "branch": receipt.branch,
            "base_branch": receipt.base_branch,
            "pull_request_id": receipt.pull_request_id,
            "pull_request_url": receipt.pull_request_url,
            "identity_authenticated": False,
            "trust_profile_origin": verified.result.get("trust_profile_origin"),
            "automatic_write_retry": False,
        }
    except SignedGitHubPublicationError:
        raise
    except Exception:
        raise SignedGitHubPublicationError(
            "signed GitHub publication: controlled operation failed or needs reconciliation"
        ) from None


def _load_preview(
    database_path: str | Path,
    staged_change_digest: str,
    request_path: str | Path,
    signed_approval_path: str | Path,
    trust_profile_path: str | Path,
    *,
    now: datetime,
) -> tuple[VerifiedSignedApproval, str]:
    verified = _load_approval(
        database_path,
        staged_change_digest,
        request_path,
        signed_approval_path,
        trust_profile_path,
        now=now,
    )
    _validated_inputs(verified, staged_change_digest)
    return verified, render_stage_preview(verified.artifact)


def main(
    argv: list[str] | None = None,
    *,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
    input_reader: Callable[[str], str] | None = None,
    stdout=None,
    stderr=None,
) -> int:
    import argparse

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    reader = input if input_reader is None else input_reader
    parser = argparse.ArgumentParser(
        description="Publish one signed stage to the fixed GitHub App target after exact-digest confirmation."
    )
    parser.add_argument("database")
    parser.add_argument("staged_change_digest")
    parser.add_argument("request")
    parser.add_argument("signed_approval")
    parser.add_argument("trust_profile")
    parser.add_argument("journal", help="new absolute persistent SQLite publication journal")
    args = parser.parse_args(argv)
    moment = datetime.now(timezone.utc) if now is None else now
    try:
        verified, preview = _load_preview(
            args.database,
            args.staged_change_digest,
            args.request,
            args.signed_approval,
            args.trust_profile,
            now=moment,
        )
        request_intent = verified.request["intent"]
        output.write(
            json.dumps(
                {
                    "target": TARGET_REPOSITORY,
                    "branch": request_intent["branch"],
                    "base_branch": request_intent["base_branch"],
                    "staged_change_digest": args.staged_change_digest,
                    "identity_authenticated": False,
                    "preview": json.loads(preview),
                },
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
            )
            + "\n"
        )
        if not getattr(sys.stdin if input_reader is None else None, "isatty", lambda: True)():
            raise SignedGitHubPublicationError(
                "signed GitHub publication: interactive confirmation is required"
            )
        confirmation = reader(
            f"Type PUBLISH {args.staged_change_digest} to create/update the PR: "
        )
        result = publish_signed_stage_github(
            args.database,
            args.staged_change_digest,
            args.request,
            args.signed_approval,
            args.trust_profile,
            args.journal,
            confirmation,
            now=moment,
            environ=environ,
        )
    except (SignedGitHubPublicationError, KeyboardInterrupt, EOFError):
        errors.write(
            "signed GitHub publication: cancelled or safely refused\n"
        )
        return 2
    except Exception:
        errors.write("signed GitHub publication: controlled operation failed\n")
        return 2
    output.write(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n")
    return 0
