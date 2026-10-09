#!/usr/bin/env python3
"""Run the one fixed pinned BrainBooster Worker-to-stage experiment.

This operator entrypoint is intentionally not invoked by tests or setup. A
successful live run requires a separate fresh user authorization for EXP-634,
its exact prompt confirmation, and one temporary credential supplied through
hidden terminal input, process environment, or the explicitly selected native
credential manager. The native adapter does not provision or migrate credentials.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.brainbooster_target_profile import (  # noqa: E402
    PINNED_HTTP_DB_TEST_COMMAND,
    PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    TARGET_RUNTIME_IMAGE_ID,
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
    PINNED_COMMIT,
    PINNED_TREE,
    PINNED_CONTENT_DIGEST,
)
from app_contracts.credential_source import (  # noqa: E402
    NativeKeyringCredentialSource,
    ProcessEnvironmentCredentialSource,
    TerminalPromptCredentialSource,
)
from app_contracts.deepseek_http_channel import DeepSeekHTTPChannel  # noqa: E402
from app_contracts.deepseek_worker import DeepSeekProposalWorker  # noqa: E402
from app_contracts.github_http_transport import (  # noqa: E402
    GitHubAnonymousSnapshotTransport,
)
from app_contracts.observation_store import SQLiteObservationStore  # noqa: E402
from app_contracts.observer_runtime import JournaledProposalWorker  # noqa: E402
from app_contracts.verifier_container import (  # noqa: E402
    VerifierContainerConfig,
)
from app_contracts.worker_cli import (  # noqa: E402
    issue_remote_execution_permit,
    run_remote_snapshot_with_runtime,
)

CONFIRMATION_PHRASE = "RUN EXP-634 ONCE"
PROCESS_ID = "process-exp-634-live-001"
TASK_ID = "task-exp-634-live-001"
AUTHORIZATION_PROFILES = {
    "EXP-634": (CONFIRMATION_PHRASE, PROCESS_ID, TASK_ID),
    "EXP-726": (
        "RUN EXP-726 ONCE",
        "process-exp-726-live-001",
        "task-exp-726-live-001",
    ),
}
AUTHORIZATION_SNAPSHOT_ORIGINS = {
    "EXP-634": "github_rest_api_claim",
    "EXP-726": "github_rest_api_claim",
}
TASK_INSTRUCTION = (
    "In backend/routes.py, for /save-session validate each of level, correct, "
    "wrong, total, and time_ms before any database write. Reject booleans, "
    "malformed, non-finite, fractional, and integer values outside the signed "
    "64-bit range [-2^63, 2^63-1] with HTTP 422 and zero rows written. Preserve "
    "valid behavior (HTTP 200 and exactly one expected row). Change only this "
    "route file; do not add unrelated changes."
)
DECLARED_CHANGE_PATHS = ("backend/routes.py",)
ALLOWED_COMMANDS = frozenset({"python3"})


def _validate_new_stage_path(value: str | Path) -> Path:
    try:
        path = Path(value)
        parent = path.parent
        if (
            not path.is_absolute()
            or path == Path(path.anchor)
            or ".." in path.parts
            or path.is_symlink()
            or path.exists()
            or parent.is_symlink()
            or not parent.is_dir()
        ):
            raise ValueError
        return path
    except Exception:
        raise ValueError("pinned Worker CLI: stage path is unavailable") from None


def _validate_new_observation_path(value: str | Path) -> Path:
    try:
        path = Path(value)
        if (
            not path.is_absolute()
            or path == Path(path.anchor)
            or ".." in path.parts
            or path.is_symlink()
            or path.exists()
            or path.parent.is_symlink()
            or not path.parent.is_dir()
        ):
            raise ValueError
        return path
    except Exception:
        raise ValueError(
            "pinned Worker CLI: observation journal path is unavailable"
        ) from None


def _preflight_docker_images(
    docker_executable: str,
    *,
    run: Callable[..., object] = subprocess.run,
) -> None:
    for image in (TARGET_RUNTIME_IMAGE_ID, VERIFIER_RUNTIME_IMAGE_ID):
        try:
            result = run(
                [docker_executable, "image", "inspect", "--format={{.Id}}", image],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if getattr(result, "stdout", "").strip() != image:
                raise ValueError
        except Exception:
            raise ValueError("pinned Worker CLI: pinned Docker image unavailable") from None


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    input_fn: Callable[[str], str] | None = None,
    stdout=None,
    stderr=None,
    readiness_transport_factory: Callable[[], object] | None = None,
    runtime_runner: Callable[..., int] | None = None,
    docker_which: Callable[[str], str | None] | None = None,
    docker_inspect: Callable[..., None] | None = None,
    native_keyring_source_factory: Callable[[], object] | None = None,
) -> int:
    import sys as _sys

    output = _sys.stdout if stdout is None else stdout
    error_output = _sys.stderr if stderr is None else stderr
    read_input = input if input_fn is None else input_fn
    transport_factory = (
        GitHubAnonymousSnapshotTransport
        if readiness_transport_factory is None
        else readiness_transport_factory
    )
    run_runtime = run_remote_snapshot_with_runtime if runtime_runner is None else runtime_runner
    find_docker = shutil.which if docker_which is None else docker_which
    inspect_images = _preflight_docker_images if docker_inspect is None else docker_inspect
    keyring_source_factory = (
        NativeKeyringCredentialSource
        if native_keyring_source_factory is None
        else native_keyring_source_factory
    )

    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed pinned BrainBooster Worker pipeline once and persist "
            "verified stage evidence."
        )
    )
    parser.add_argument(
        "stage_database",
        nargs="?",
        help="new absolute SQLite stage path (not used for source-status checks)",
    )
    parser.add_argument(
        "--credential-source",
        choices=("hidden-terminal", "process-environment", "native-keyring"),
        default="hidden-terminal",
        help=(
            "use hidden input, an injected AI_PROCESS_API variable, or the "
            "current OS native credential manager"
        ),
    )
    parser.add_argument(
        "--authorization-card-id",
        choices=tuple(AUTHORIZATION_PROFILES),
        default="EXP-634",
        help="select one fixed, predeclared task identity and confirmation phrase",
    )
    parser.add_argument(
        "--observation-database",
        help="optional new absolute SQLite journal for bounded Worker-call evidence",
    )
    parser.add_argument(
        "--check-credential-source",
        action="store_true",
        help="report only whether AI_PROCESS_API is present; do not run the worker",
    )
    args = parser.parse_args(argv)
    authorization_card_id = args.authorization_card_id
    try:
        snapshot_evidence_origin = AUTHORIZATION_SNAPSHOT_ORIGINS[
            authorization_card_id
        ]
        if snapshot_evidence_origin not in {
            "github_rest_api_claim",
            "github_codeload_archive",
        }:
            raise ValueError
    except Exception:
        print(
            '{"status":"stopped","reason":"snapshot-source-not-authorized",'
            '"provider_attempts":0}',
            file=output,
        )
        return 2
    confirmation_phrase, process_id, task_id = AUTHORIZATION_PROFILES[
        authorization_card_id
    ]
    credential_environment = None
    if args.credential_source == "process-environment":
        credential_environment = os.environ if environ is None else environ
    if args.check_credential_source:
        if (
            args.stage_database is not None
            or args.observation_database is not None
            or args.credential_source == "hidden-terminal"
        ):
            print(
                '{"status":"unavailable","credential_source":"invalid-check",'
                '"value_read":false}',
                file=output,
            )
            return 2
        if args.credential_source == "native-keyring":
            source = keyring_source_factory()
            try:
                manager_available = source.manager_available()
            except Exception:
                manager_available = False
            result = {
                "status": "available" if manager_available else "unavailable",
                "credential_source": "native_keyring",
                "credential_item_checked": False,
                "value_read": False,
            }
        elif credential_environment is not None:
            try:
                manager_available = "AI_PROCESS_API" in credential_environment
            except Exception:
                manager_available = False
            result = {
                "status": "available" if manager_available else "unavailable",
                "credential_source": "process_environment",
                "value_read": False,
            }
        else:
            result = {
                "status": "unavailable",
                "credential_source": "process_environment",
                "value_read": False,
            }
        print(
            json.dumps(
                result,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=output,
        )
        return 0 if result["status"] == "available" else 3
    try:
        stage_path = _validate_new_stage_path(args.stage_database)
        observation_path = (
            _validate_new_observation_path(args.observation_database)
            if args.observation_database is not None
            else None
        )
        docker_executable = find_docker("docker")
        if type(docker_executable) is not str or not docker_executable:
            raise ValueError("pinned Worker CLI: Docker is unavailable")
        inspect_images(docker_executable)
    except ValueError as exc:
        print(str(exc), file=error_output)
        return 2

    print(
        json.dumps(
            {
                "operation": "one_deepseek_worker_call",
                "authorization_card_id": authorization_card_id,
                "process_id": process_id,
                "task_id": task_id,
                "repository": f"{PINNED_OWNER}/{PINNED_REPOSITORY}",
                "commit": PINNED_COMMIT,
                "tree": PINNED_TREE,
                "content_digest": PINNED_CONTENT_DIGEST,
                "snapshot_source": snapshot_evidence_origin,
                "change_path": DECLARED_CHANGE_PATHS[0],
                "model": "deepseek-flash",
                "endpoint": "https://api.deepseek.com/chat/completions",
                "max_provider_attempts": 1,
                "account_level_spend_cap": False,
                "credential_input": (
                    {
                        "hidden-terminal": "hidden_terminal_prompt",
                        "process-environment": "process_environment:AI_PROCESS_API",
                        "native-keyring": "native_keyring:Agent00X/AI_PROCESS_API",
                    }[args.credential_source]
                ),
                "stage_database": str(stage_path),
                "confirmation_phrase": confirmation_phrase,
                **(
                    {"observation_database": str(observation_path)}
                    if observation_path is not None
                    else {}
                ),
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=output,
        flush=True,
    )
    try:
        confirmation = read_input(f"Type {confirmation_phrase} to continue: ")
    except Exception:
        confirmation = ""
    if confirmation != confirmation_phrase:
        print('{"status":"cancelled","provider_attempts":0}', file=output)
        return 3

    if credential_environment is not None:
        try:
            credential_available = "AI_PROCESS_API" in credential_environment
        except Exception:
            credential_available = False
        if not credential_available:
            print(
                '{"status":"stopped","reason":"credential-source-unavailable",'
                '"provider_attempts":0}',
                file=output,
            )
            return 2

    native_keyring_source = None
    if args.credential_source == "native-keyring":
        try:
            native_keyring_source = keyring_source_factory()
            manager_available = native_keyring_source.manager_available()
        except Exception:
            manager_available = False
        if not manager_available:
            print(
                '{"status":"stopped","reason":"credential-source-unavailable",'
                '"provider_attempts":0}',
                file=output,
            )
            return 2

    if args.credential_source == "hidden-terminal":
        credential_source = TerminalPromptCredentialSource()
    elif args.credential_source == "process-environment":
        credential_source = ProcessEnvironmentCredentialSource(
            credential_environment, "AI_PROCESS_API"
        )
    else:
        credential_source = native_keyring_source

    observation_store = None
    execution_worker = None
    if observation_path is not None:
        try:
            observation_store = SQLiteObservationStore(observation_path)
            execution_worker = JournaledProposalWorker(
                DeepSeekProposalWorker(channel=DeepSeekHTTPChannel(credential_source)),
                observation_store,
                process_id=process_id,
                task_id=task_id,
            )
        except Exception:
            if observation_store is not None:
                observation_store.close()
            print(
                '{"status":"stopped","reason":"observation-journal-unavailable",'
                '"provider_attempts":0}',
                file=output,
            )
            return 2

    try:
        transport = transport_factory()

        def fetch_readiness():
            return transport.read_rate_limit()

        if execution_worker is None:
            readiness = fetch_readiness()
            permit = issue_remote_execution_permit(
                card_id=authorization_card_id,
                process_id=process_id,
                task_id=task_id,
                readiness=readiness,
                provider_call_approved=True,
                snapshot_evidence_origin=snapshot_evidence_origin,
            )
        else:
            readiness = execution_worker.run_controlled_step(
                "GitHubReadiness.fetch",
                fetch_readiness,
                process_id=PROCESS_ID,
            )
            permit = execution_worker.run_controlled_step(
                "RemoteExecutionPermit.issue",
                lambda: issue_remote_execution_permit(
                    card_id=authorization_card_id,
                    process_id=process_id,
                    task_id=task_id,
                    readiness=readiness,
                    provider_call_approved=True,
                    snapshot_evidence_origin=snapshot_evidence_origin,
                ),
                process_id=PROCESS_ID,
            )
        verifier_config = VerifierContainerConfig(
            docker_executable=docker_executable,
            runtime_image_id=VERIFIER_RUNTIME_IMAGE_ID,
            verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
            timeout_seconds=120,
        )
        runtime_options = dict(
            process_id=process_id,
            task_id=task_id,
            task_instruction=TASK_INSTRUCTION,
            declared_change_paths=DECLARED_CHANGE_PATHS,
            allowed_commands=ALLOWED_COMMANDS,
            test_command=PINNED_HTTP_DB_TEST_COMMAND,
            execution_image=TARGET_RUNTIME_IMAGE_ID,
            credential_source=credential_source,
            verifier_config=verifier_config,
            stage_database_path=stage_path,
            execution_permit=permit,
            snapshot_evidence_origin=snapshot_evidence_origin,
            test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
            stdout=output,
            stderr=error_output,
        )
        if observation_store is not None:
            runtime_options["observation_store"] = observation_store
            runtime_options["execution_worker"] = execution_worker
        result_code = run_runtime(**runtime_options)
        return result_code if type(result_code) is int else 2
    except Exception:
        failure = {
            "status": "failed",
            "failure_code": "pinned-worker-runtime-failed",
        }
        if execution_worker is not None:
            try:
                failure["observer"] = execution_worker.observer_reference()
            except Exception:
                pass
        print(
            json.dumps(failure, sort_keys=True, separators=(",", ":")),
            file=error_output,
        )
        return 2
    finally:
        if observation_store is not None:
            observation_store.close()


if __name__ == "__main__":
    raise SystemExit(main())
