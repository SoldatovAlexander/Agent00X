"""Read-only recovery for one existing signed-stage GitHub journal entry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping
from urllib.parse import quote, unquote

from .controlled_publication import reconcile_controlled_attempt_after_restart
from .digests import sha256_bytes, sha256_digest
from .durable_stage import SQLiteStagedArtifactStore
from .github_app import (
    GitHubAppBrokerConfig,
    GitHubAppInstallationTokenMinter,
    GitHubAppReadOnlyReconciliationBroker,
)
from .publication import PublicationJournal, validate_publication_base_branch
from .publication_seed import (
    PublicationIntent,
    PublicationSeed,
    bind_publication_seed_to_target,
    derive_publication_intent,
)
from .repository_binding import RepositoryTargetBinding
from .repository_process import PublishableFile

TARGET_REPOSITORY = "SoldatovAlexander/brainbooster_full_v11"
ACTUATOR_ID = "github-app-readonly-reconciliation"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class SignedGitHubReconciliationError(ValueError):
    """A signed-stage publication journal could not be safely reconciled."""


def _parse_intent_from_record(
    seed: PublicationSeed, record: Any, staged_change_digest: str
) -> PublicationIntent:
    try:
        parts = record.idempotency_key.split("/")
        if (
            len(parts) != 4
            or parts[0] != "publish"
            or not parts[1]
            or not parts[2]
            or parts[3] != staged_change_digest
        ):
            raise ValueError
        branch_suffix = unquote(parts[1])
        base_branch = unquote(parts[2])
        if (
            quote(branch_suffix, safe="") != parts[1]
            or quote(base_branch, safe="") != parts[2]
            or not branch_suffix.startswith("process-")
        ):
            raise ValueError
        branch = "agent/" + branch_suffix
        validate_publication_base_branch(base_branch)
        intent = derive_publication_intent(seed, branch, base_branch)
        if (
            intent.process_id != record.process_id
            or intent.repository_id != record.repository_id
            or intent.idempotency_key != record.idempotency_key
            or record.base_branch != base_branch
            or record.verified_files_digest != seed.verified_contents_digest
        ):
            raise ValueError
        return intent
    except Exception:
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: journal binding is invalid"
        ) from None


def _load_recovery_inputs(
    database_path: str | Path,
    staged_change_digest: str,
    journal_path: str | Path,
) -> tuple[PublicationSeed, PublicationIntent, tuple[PublishableFile, ...], Any]:
    if type(staged_change_digest) is not str or _DIGEST_RE.fullmatch(
        staged_change_digest
    ) is None:
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: stage digest is invalid"
        )
    try:
        with SQLiteStagedArtifactStore(database_path, read_only=True) as stage_store:
            artifact = stage_store.load(staged_change_digest)
            payload = artifact.payload_copy()
        seed = PublicationSeed(**payload["seed"])
        if (
            seed.staged_change_digest != staged_change_digest
            or seed.source_repository_id is not None
            or seed.repository_id != TARGET_REPOSITORY
            or type(payload.get("verified_contents")) is not list
        ):
            raise ValueError
        files: list[PublishableFile] = []
        for item in payload["verified_contents"]:
            if type(item) is not dict or set(item) != {"path", "content"}:
                raise ValueError
            path, content = item["path"], item["content"]
            if type(path) is not str or type(content) is not str:
                raise ValueError
            files.append(
                PublishableFile(path, content, sha256_bytes(content.encode("utf-8")))
            )
        manifest = tuple(files)
        if (
            not manifest
            or sha256_digest(tuple((item.path, item.content) for item in manifest))
            != seed.verified_contents_digest
        ):
            raise ValueError
    except SignedGitHubReconciliationError:
        raise
    except Exception:
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: stage is unavailable or invalid"
        ) from None

    try:
        with PublicationJournal(Path(journal_path), create_if_missing=False) as journal:
            record = journal.get(seed.process_id)
            binding = RepositoryTargetBinding(TARGET_REPOSITORY, record.repository_id)
            seed = bind_publication_seed_to_target(seed, binding)
            intent = _parse_intent_from_record(seed, record, staged_change_digest)
            if record.status not in {
                "prepared", "attempting", "completed", "reconciliation_required"
            }:
                raise ValueError
            if record.status == "completed" and (
                not isinstance(record.pull_request_id, int)
                or isinstance(record.pull_request_id, bool)
                or record.pull_request_id < 1
                or record.pull_request_url
                != f"https://github.com/{TARGET_REPOSITORY}/pull/{record.pull_request_id}"
            ):
                raise ValueError
            if record.status in {"attempting", "reconciliation_required"} and (
                record.verified_files_outcome not in {None, "verified", "unverified"}
            ):
                raise ValueError
            return seed, intent, manifest, record
    except SignedGitHubReconciliationError:
        raise
    except Exception:
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: journal is unavailable or mismatched"
        ) from None


def _render_record_result(record: Any, staged_change_digest: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "signed-stage-github-reconciliation/v1",
        "status": record.status,
        "staged_change_digest": staged_change_digest,
        "repository_id": record.repository_id,
        "base_branch": record.base_branch,
        "identity_authenticated": False,
        "provider_write": False,
    }
    if record.pull_request_id is not None:
        result["pull_request_id"] = record.pull_request_id
        result["pull_request_url"] = record.pull_request_url
    if record.verified_files_digest is not None:
        result["verified_files_digest"] = record.verified_files_digest
        result["verified_files_outcome"] = record.verified_files_outcome
        result["verified_branch_commit_sha"] = record.verified_branch_commit_sha
        result["verified_files_observed_at"] = record.verified_files_observed_at
    return result


def reconcile_signed_stage_github(
    database_path: str | Path,
    staged_change_digest: str,
    journal_path: str | Path,
    operator_confirmation: str,
    *,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
    get_json: Callable[[str, Mapping[str, str]], object] | None = None,
) -> dict[str, Any]:
    """Reconcile an existing attempt using GET-only provider capability."""
    moment = datetime.now(timezone.utc) if now is None else now
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: clock is invalid"
        )
    moment = moment.astimezone(timezone.utc)
    seed, intent, files, record = _load_recovery_inputs(
        database_path, staged_change_digest, journal_path
    )
    if record.status == "prepared":
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: no uncertain provider attempt exists"
        )
    if record.status == "completed":
        return _render_record_result(record, staged_change_digest)
    if operator_confirmation != f"RECONCILE {staged_change_digest}":
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: exact digest confirmation is required"
        )

    try:
        config = GitHubAppBrokerConfig.from_environment(environ)
        if (
            config.repository != TARGET_REPOSITORY
            or config.repository_target_binding
            != RepositoryTargetBinding(TARGET_REPOSITORY, record.repository_id)
        ):
            raise ValueError
    except Exception:
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: provider target configuration is invalid"
        ) from None

    request = {
        "operation": "reconcile_publication",
        "repository_id": intent.repository_id,
        "actuator_id": ACTUATOR_ID,
        "base_branch": intent.base_branch,
        "staged_change_digest": staged_change_digest,
        "branch_namespace": intent.branch.split("/", 1)[0],
        "idempotency_key": intent.idempotency_key,
    }
    grant = {
        "credential_grant_id": "reconcile-" + staged_change_digest.removeprefix("sha256:")[:24],
        "actuator_id": ACTUATOR_ID,
        "repository_id": intent.repository_id,
        "operation": "reconcile_publication",
        "request_digest": sha256_digest(request),
        "single_use": True,
        "credential_class": "github-app-installation",
        "installation_id": config.installation_id,
        "permissions": ["contents:read", "pull_requests:read"],
        "expires_at": (moment + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    }
    broker = GitHubAppReadOnlyReconciliationBroker(
        config, GitHubAppInstallationTokenMinter(config), get_json=get_json
    )
    try:
        with PublicationJournal(Path(journal_path), create_if_missing=False) as journal:
            if journal.get(seed.process_id) != record:
                raise SignedGitHubReconciliationError(
                    "signed GitHub reconciliation: journal changed before recovery"
                )
            channel = broker.open_read_only_reconciliation_channel(
                grant, request, now=moment
            )
            record = reconcile_controlled_attempt_after_restart(
                seed,
                intent,
                files,
                journal,
                channel,
                now=moment,
            )
        return _render_record_result(record, staged_change_digest)
    except SignedGitHubReconciliationError:
        raise
    except Exception:
        raise SignedGitHubReconciliationError(
            "signed GitHub reconciliation: read-only recovery is inconclusive"
        ) from None


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
        description="Read-only reconciliation of one existing fixed-target GitHub publication journal."
    )
    parser.add_argument("database")
    parser.add_argument("staged_change_digest")
    parser.add_argument("journal")
    args = parser.parse_args(argv)
    moment = datetime.now(timezone.utc) if now is None else now
    try:
        _seed, intent, _files, record = _load_recovery_inputs(
            args.database, args.staged_change_digest, args.journal
        )
        output.write(
            json.dumps(
                {
                    "target": TARGET_REPOSITORY,
                    "branch": intent.branch,
                    "base_branch": intent.base_branch,
                    "status": record.status,
                    "staged_change_digest": args.staged_change_digest,
                    "identity_authenticated": False,
                    "provider_write": False,
                },
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
            )
            + "\n"
        )
        if record.status == "completed":
            output.write(
                json.dumps(
                    _render_record_result(record, args.staged_change_digest),
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                )
                + "\n"
            )
            return 0
        if record.status == "prepared":
            raise SignedGitHubReconciliationError(
                "signed GitHub reconciliation: no uncertain provider attempt exists"
            )
        if not getattr(sys.stdin if input_reader is None else None, "isatty", lambda: True)():
            raise SignedGitHubReconciliationError(
                "signed GitHub reconciliation: interactive confirmation is required"
            )
        confirmation = reader(
            f"Type RECONCILE {args.staged_change_digest} for read-only GitHub recovery: "
        )
        result = reconcile_signed_stage_github(
            args.database,
            args.staged_change_digest,
            args.journal,
            confirmation,
            now=moment,
            environ=environ,
        )
    except (SignedGitHubReconciliationError, KeyboardInterrupt, EOFError):
        errors.write("signed GitHub reconciliation: cancelled or safely refused\n")
        return 2
    except Exception:
        errors.write("signed GitHub reconciliation: recovery failed safely\n")
        return 2
    output.write(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n")
    return 0
