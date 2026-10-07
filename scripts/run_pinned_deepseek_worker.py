#!/usr/bin/env python3
"""Run the one fixed pinned BrainBooster Worker-to-stage experiment.

This operator entrypoint is intentionally not invoked by tests or setup. A
successful live run requires a separate fresh user authorization for EXP-566,
its exact prompt confirmation, and one temporary credential supplied through
hidden terminal input (or an explicitly injected manager in an embedding host).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
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
    ProcessEnvironmentCredentialSource,
    TerminalPromptCredentialSource,
)
from app_contracts.github_http_transport import (  # noqa: E402
    GitHubAnonymousSnapshotTransport,
)
from app_contracts.verifier_container import (  # noqa: E402
    VerifierContainerConfig,
)
from app_contracts.worker_cli import (  # noqa: E402
    issue_remote_execution_permit,
    run_remote_snapshot_with_runtime,
)

CONFIRMATION_PHRASE = "RUN EXP-566 ONCE"
PROCESS_ID = "process-exp-566-live-001"
TASK_ID = "task-exp-566-live-001"
TASK_INSTRUCTION = (
    "In backend/routes.py, reject malformed or non-finite numeric fields in "
    "/save-session with HTTP 422 before any database write. Preserve valid "
    "behavior (HTTP 200 and exactly one expected row). Change only this route "
    "file; do not add unrelated changes."
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

    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed pinned BrainBooster Worker pipeline once and persist "
            "verified stage evidence."
        )
    )
    parser.add_argument("stage_database", help="new absolute SQLite stage path")
    args = parser.parse_args(argv)
    try:
        stage_path = _validate_new_stage_path(args.stage_database)
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
                "repository": f"{PINNED_OWNER}/{PINNED_REPOSITORY}",
                "commit": PINNED_COMMIT,
                "tree": PINNED_TREE,
                "content_digest": PINNED_CONTENT_DIGEST,
                "change_path": DECLARED_CHANGE_PATHS[0],
                "model": "deepseek-flash",
                "endpoint": "https://api.deepseek.com/chat/completions",
                "max_provider_attempts": 1,
                "account_level_spend_cap": False,
                "credential_input": (
                    "hidden_terminal_prompt"
                    if environ is None
                    else "explicit_process_mapping"
                ),
                "stage_database": str(stage_path),
                "confirmation_phrase": CONFIRMATION_PHRASE,
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
        confirmation = read_input(f"Type {CONFIRMATION_PHRASE} to continue: ")
    except Exception:
        confirmation = ""
    if confirmation != CONFIRMATION_PHRASE:
        print('{"status":"cancelled","provider_attempts":0}', file=output)
        return 3

    try:
        transport = transport_factory()
        readiness = transport.read_rate_limit()
        permit = issue_remote_execution_permit(
            card_id="EXP-566",
            process_id=PROCESS_ID,
            task_id=TASK_ID,
            readiness=readiness,
            provider_call_approved=True,
        )
        if environ is None:
            credential_source = TerminalPromptCredentialSource()
        else:
            credential_source = ProcessEnvironmentCredentialSource(
                environ, "AI_PROCESS_API"
            )
        verifier_config = VerifierContainerConfig(
            docker_executable=docker_executable,
            runtime_image_id=VERIFIER_RUNTIME_IMAGE_ID,
            verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
            timeout_seconds=120,
        )
        result_code = run_runtime(
            process_id=PROCESS_ID,
            task_id=TASK_ID,
            task_instruction=TASK_INSTRUCTION,
            declared_change_paths=DECLARED_CHANGE_PATHS,
            allowed_commands=ALLOWED_COMMANDS,
            test_command=PINNED_HTTP_DB_TEST_COMMAND,
            execution_image=TARGET_RUNTIME_IMAGE_ID,
            credential_source=credential_source,
            verifier_config=verifier_config,
            stage_database_path=stage_path,
            execution_permit=permit,
            test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
            stdout=output,
            stderr=error_output,
        )
        return result_code if type(result_code) is int else 2
    except Exception:
        print('{"status":"failed","failure_code":"pinned-worker-runtime-failed"}', file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
