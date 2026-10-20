#!/usr/bin/env python3
"""Run one explicitly authorized pinned BrainBooster Worker-to-stage profile.

DeepSeek profiles require their own fresh confirmation and temporary
credential. EXP-842 selects one credential-free local Ollama call instead.
This operator entrypoint is intentionally not invoked by tests or setup.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
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
    PINNED_COMMIT,
    PINNED_TREE,
    PINNED_SNAPSHOT_TREE_DIGEST,
)
from app_contracts.verifier_image_pin import (  # noqa: E402
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.container_proposal_worker import ContainerProposalWorker  # noqa: E402
from app_contracts.docker_endpoint import LOCAL_DOCKER_HOST_ARGUMENT  # noqa: E402
from app_contracts.credential_source import (  # noqa: E402
    NativeKeyringCredentialSource,
    ProcessEnvironmentCredentialSource,
    TerminalPromptCredentialSource,
)
from app_contracts.deepseek_http_channel import DeepSeekHTTPChannel  # noqa: E402
from app_contracts.deepseek_worker import (  # noqa: E402
    MAX_LOCAL_MODEL_TIMEOUT_SECONDS,
    DeepSeekProposalWorker,
)
from app_contracts.local_ollama_channel import (  # noqa: E402
    LOCAL_OLLAMA_HOST,
    LOCAL_OLLAMA_MODEL,
    LOCAL_OLLAMA_MODEL_DIGEST,
    LOCAL_OLLAMA_PATH,
    LOCAL_OLLAMA_PORT,
    LocalOllamaChatCompletionsChannel,
)
from app_contracts.r5_local_model_preflight import (  # noqa: E402
    EXPECTED_OLLAMA_VERSION,
    R5LocalOllamaMetadataPreflight,
    R5LocalModelPreflightError,
)
from app_contracts.github_http_transport import (  # noqa: E402
    GITHUB_READINESS_FAILURE_CODES,
    GitHubAnonymousSnapshotTransport,
    GitHubHTTPTransportError,
)
from app_contracts.observation_store import SQLiteObservationStore  # noqa: E402
from app_contracts.observer_runtime import (  # noqa: E402
    JournaledModelChannel,
    JournaledProposalWorker,
)
from app_contracts.local_model_observer_gate import (  # noqa: E402
    journal_local_model_preflight,
)
from app_contracts.verifier_container import (  # noqa: E402
    VerifierContainerConfig,
)
from app_contracts.worker_cli import (  # noqa: E402
    PINNED_SIGNED_VERIFIER_ENDPOINT_URL,
    RemoteExecutionPermitError,
    issue_remote_execution_permit,
    run_remote_snapshot_with_runtime,
)
from app_contracts.signed_verifier_service import (  # noqa: E402
    BRAINBOOSTER_VERIFIER_PROFILE,
)
from app_contracts.pinned_verifier_cli import (  # noqa: E402
    VERIFIER_TRUST_ARTIFACT_ARGUMENTS as _VERIFIER_TRUST_ARTIFACT_ARGS,
    load_pinned_signed_verifier_client,
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
    "EXP-842": (
        "RUN EXP-842 ONCE",
        "process-exp-842-local-001",
        "task-exp-842-local-001",
    ),
    "EXP-843": (
        "RUN EXP-843 ONCE",
        "process-exp-843-local-001",
        "task-exp-843-local-001",
    ),
    "EXP-844": (
        "RUN EXP-844 ONCE",
        "process-exp-844-local-001",
        "task-exp-844-local-001",
    ),
    "EXP-846": (
        "RUN EXP-846 ONCE",
        "process-exp-846-local-001",
        "task-exp-846-local-001",
    ),
    "EXP-848": (
        "RUN EXP-848 ONCE",
        "process-exp-848-local-001",
        "task-exp-848-local-001",
    ),
    "EXP-849": (
        "RUN EXP-849 ONCE",
        "process-exp-849-local-001",
        "task-exp-849-local-001",
    ),
    "EXP-851": (
        "RUN EXP-851 ONCE",
        "process-exp-851-local-001",
        "task-exp-851-local-001",
    ),
    "EXP-964": (
        "RUN EXP-964 ONCE",
        "process-exp-964-local-001",
        "task-exp-964-local-001",
    ),
    "EXP-1200": (
        "RUN EXP-1200 ONCE",
        "process-exp-1200-local-001",
        "task-exp-1200-local-001",
    ),
    "EXP-1209": (
        "RUN EXP-1209 ONCE",
        "process-exp-1209-local-001",
        "task-exp-1209-local-001",
    ),
    "EXP-1218": (
        "RUN EXP-1218 ONCE",
        "process-exp-1218-local-001",
        "task-exp-1218-local-001",
    ),
    "EXP-1230": (
        "RUN EXP-1230 ONCE",
        "process-exp-1230-local-001",
        "task-exp-1230-local-001",
    ),
    "EXP-1233": (
        "RUN EXP-1233 ONCE",
        "process-exp-1233-local-001",
        "task-exp-1233-local-001",
    ),
    "EXP-1238": (
        "RUN EXP-1238 ONCE",
        "process-exp-1238-local-001",
        "task-exp-1238-local-001",
    ),
    "EXP-1246": (
        "RUN EXP-1246 ONCE",
        "process-exp-1246-local-001",
        "task-exp-1246-local-001",
    ),
    "EXP-1250": (
        "RUN EXP-1250 ONCE",
        "process-exp-1250-local-001",
        "task-exp-1250-local-001",
    ),
    "EXP-1253": (
        "RUN EXP-1253 ONCE",
        "process-exp-1253-local-001",
        "task-exp-1253-local-001",
    ),
    "EXP-1255": (
        "RUN EXP-1255 ONCE",
        "process-exp-1255-local-001",
        "task-exp-1255-local-001",
    ),
    "EXP-1257": (
        "RUN EXP-1257 ONCE",
        "process-exp-1257-local-001",
        "task-exp-1257-local-001",
    ),
    "EXP-1266": (
        "RUN EXP-1266 ONCE",
        "process-exp-1266-local-001",
        "task-exp-1266-local-001",
    ),
    "EXP-1268": (
        "RUN EXP-1268 ONCE",
        "process-exp-1268-local-001",
        "task-exp-1268-local-001",
    ),
    "EXP-1289": (
        "RUN EXP-1289 ONCE",
        "process-exp-1289-local-001",
        "task-exp-1289-local-001",
    ),
    "EXP-1293": (
        "RUN EXP-1293 ONCE",
        "process-exp-1293-local-001",
        "task-exp-1293-local-001",
    ),
    "EXP-1299": (
        "RUN EXP-1299 ONCE",
        "process-exp-1299-local-001",
        "task-exp-1299-local-001",
    ),
    "EXP-1303": (
        "RUN EXP-1303 ONCE",
        "process-exp-1303-local-001",
        "task-exp-1303-local-001",
    ),
    "EXP-1310": (
        "RUN EXP-1310 ONCE",
        "process-exp-1310-local-001",
        "task-exp-1310-local-001",
    ),
    "EXP-1312": (
        "RUN EXP-1312 ONCE",
        "process-exp-1312-local-001",
        "task-exp-1312-local-001",
    ),
    "EXP-1585": (
        "RUN EXP-1585 ONCE",
        "process-exp-1585-local-001",
        "task-exp-1585-local-001",
    ),
    "EXP-1643": (
        "RUN EXP-1643 ONCE",
        "process-exp-1643-local-001",
        "task-exp-1643-local-001",
    ),
    "EXP-1645": (
        "RUN EXP-1645 ONCE",
        "process-exp-1645-local-001",
        "task-exp-1645-local-001",
    ),
}
AUTHORIZATION_SNAPSHOT_ORIGINS = {
    "EXP-634": "github_rest_api_claim",
    "EXP-726": "github_rest_api_claim",
    "EXP-842": "github_rest_api_claim",
    "EXP-843": "github_rest_api_claim",
    "EXP-844": "github_rest_api_claim",
    "EXP-846": "github_rest_api_claim",
    "EXP-848": "github_rest_api_claim",
    "EXP-849": "github_rest_api_claim",
    "EXP-851": "github_rest_api_claim",
    "EXP-964": "github_rest_api_claim",
    "EXP-1200": "github_rest_api_claim",
    "EXP-1209": "github_rest_api_claim",
    "EXP-1218": "github_rest_api_claim",
    "EXP-1230": "github_rest_api_claim",
    "EXP-1233": "github_rest_api_claim",
    "EXP-1238": "github_rest_api_claim",
    "EXP-1246": "github_rest_api_claim",
    "EXP-1250": "github_rest_api_claim",
    "EXP-1253": "github_rest_api_claim",
    "EXP-1255": "github_rest_api_claim",
    "EXP-1257": "github_rest_api_claim",
    "EXP-1266": "github_rest_api_claim",
    "EXP-1268": "github_rest_api_claim",
    "EXP-1289": "github_rest_api_claim",
    "EXP-1293": "github_rest_api_claim",
    "EXP-1299": "github_rest_api_claim",
    "EXP-1303": "github_rest_api_claim",
    "EXP-1310": "github_rest_api_claim",
    "EXP-1312": "github_rest_api_claim",
    "EXP-1585": "github_rest_api_claim",
    "EXP-1643": "github_rest_api_claim",
    "EXP-1645": "github_rest_api_claim",
}
AUTHORIZATION_MODEL_BACKENDS = {
    "EXP-634": "deepseek",
    "EXP-726": "deepseek",
    "EXP-842": "local-ollama",
    "EXP-843": "local-ollama",
    "EXP-844": "local-ollama",
    "EXP-846": "local-ollama",
    "EXP-848": "local-ollama",
    "EXP-849": "local-ollama",
    "EXP-851": "local-ollama",
    "EXP-964": "local-ollama",
    "EXP-1200": "local-ollama",
    "EXP-1209": "local-ollama",
    "EXP-1218": "local-ollama",
    "EXP-1230": "local-ollama",
    "EXP-1233": "local-ollama",
    "EXP-1238": "local-ollama",
    "EXP-1246": "local-ollama",
    "EXP-1250": "local-ollama",
    "EXP-1253": "local-ollama",
    "EXP-1255": "local-ollama",
    "EXP-1257": "local-ollama",
    "EXP-1266": "local-ollama",
    "EXP-1268": "local-ollama",
    "EXP-1289": "local-ollama",
    "EXP-1293": "local-ollama",
    "EXP-1299": "local-ollama",
    "EXP-1303": "local-ollama",
    "EXP-1310": "local-ollama",
    "EXP-1312": "local-ollama",
    "EXP-1585": "local-ollama",
    "EXP-1643": "local-ollama",
    "EXP-1645": "local-ollama",
}
TASK_INSTRUCTION = (
    "In backend/routes.py change only /save-session. Preserve its existing "
    "defaults and valid insert/commit behavior. The pinned baseline currently "
    "uses int(data.get(...)) for all five fields; delete those five coercions. "
    "First read raw decoded values using exactly these defaults: "
    "raw_level = data.get('level', 1); raw_correct = data.get('correct', 0); "
    "raw_wrong = data.get('wrong', 0); raw_total = data.get('total', 10); "
    "raw_time_ms = data.get('time_ms', 0). Add/import HTTPException alongside "
    "APIRouter. Before any database/cursor access, validate those raw values. "
    "Implement and use this helper in exactly this order: if type(value) is not int, raise "
    "HTTPException(status_code=422); if value < -(2**63) or value > 2**63 - 1, "
    "raise HTTPException(status_code=422); otherwise return value unchanged. "
    "Use this literal implementation shape, adapting only the helper name if "
    "needed: def strict_sqlite_integer(value):\n"
    "    if type(value) is not int:\n"
    "        raise HTTPException(status_code=422, detail=\"invalid integer\")\n"
    "    if value < -(2**63) or value > 2**63 - 1:\n"
    "        raise HTTPException(status_code=422, detail=\"invalid integer\")\n"
    "    return value. Call it separately for raw_level, raw_correct, "
    "raw_wrong, raw_total, and raw_time_ms before any database/cursor call. "
    "Do not use isinstance for this check: type(True) is not int. "
    "Assign level/correct/wrong/total/time_ms only from helper results. "
    "Collect all five validated values before the first database call; "
    "perform no cursor access before validation. "
    "Do not retain any original int(data.get(...)) assignment or call int() "
    "anywhere in the changed path. Never coerce with int(). Never use "
    "isinstance(value, int) or "
    "insert/commit early. "
    "Acceptance oracle: every boolean, float (including non-finite), string, "
    "malformed value, and signed-64 overflow case for each field returns HTTP "
    "422 and writes zero rows; the valid fixture returns HTTP 200 and exactly "
    "one expected row. Python bool is a subclass of int, so reject True and "
    "False explicitly with type(value) is not int; isinstance(value, int) "
    "incorrectly accepts booleans. Latest diagnostic: "
    "target-test-malformed-status-level-bool; JSON true for level must return "
    "HTTP 422. Use FastAPI HTTPException. "
    "Do not change other routes, files, or acceptance criteria."
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
    _preflight_target_docker_image(docker_executable, run=run)
    _preflight_pinned_docker_image(
        docker_executable, VERIFIER_RUNTIME_IMAGE_ID, run=run
    )


def _preflight_target_docker_image(
    docker_executable: str,
    *,
    run: Callable[..., object] = subprocess.run,
) -> None:
    _preflight_pinned_docker_image(docker_executable, TARGET_RUNTIME_IMAGE_ID, run=run)


def _preflight_pinned_docker_image(
    docker_executable: str,
    image: str,
    *,
    run: Callable[..., object],
) -> None:
    try:
        result = run(
            [docker_executable, LOCAL_DOCKER_HOST_ARGUMENT, "image", "inspect", "--format={{.Id}}", image],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if getattr(result, "stdout", "").strip() != image:
            raise ValueError
    except Exception:
        raise ValueError("pinned Worker CLI: pinned Docker image unavailable") from None


def _has_any_verifier_trust_artifact_args(args: argparse.Namespace) -> bool:
    return any(getattr(args, name, None) is not None for name in _VERIFIER_TRUST_ARTIFACT_ARGS)


def _load_signed_verifier_client(args: argparse.Namespace):
    """Load only explicitly pinned public trust artifacts; never read a secret."""
    try:
        return load_pinned_signed_verifier_client(
            args,
            expected_endpoint_url=PINNED_SIGNED_VERIFIER_ENDPOINT_URL,
            profile=BRAINBOOSTER_VERIFIER_PROFILE,
        )
    except Exception:
        raise ValueError("pinned Worker CLI: verifier trust material unavailable") from None


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
    local_model_preflight_factory: Callable[[], object] | None = None,
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
    model_preflight_factory = (
        R5LocalOllamaMetadataPreflight
        if local_model_preflight_factory is None
        else local_model_preflight_factory
    )

    def readiness_failure_code(
        exc: Exception, *, observer_cursor_delta: int | None = None
    ) -> str:
        if observer_cursor_delta == 0:
            return "observer-readiness-pre-dispatch-failed"
        if observer_cursor_delta == 1:
            return "observer-readiness-outcome-unknown"
        try:
            candidate = exc.failure_code
        except Exception:
            candidate = None
        if (
            isinstance(exc, GitHubHTTPTransportError)
            and type(candidate) is str
            and candidate in GITHUB_READINESS_FAILURE_CODES
        ):
            return f"github-readiness-{candidate}"
        return "github-readiness-fetch-failed"

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
        choices=(
            "hidden-terminal",
            "process-environment",
            "native-keyring",
            "not-applicable",
        ),
        default="hidden-terminal",
        help=(
            "use hidden input, an injected AI_PROCESS_API variable, the current "
            "OS native credential manager, or not-applicable for local Ollama"
        ),
    )
    parser.add_argument(
        "--authorization-card-id",
        choices=tuple(AUTHORIZATION_PROFILES),
        default="EXP-634",
        help="select one fixed, predeclared task identity and confirmation phrase",
    )
    parser.add_argument(
        "--model-backend",
        choices=("deepseek", "local-ollama"),
        default="deepseek",
        help="use the authorized DeepSeek API or the fixed credential-free local Ollama model",
    )
    parser.add_argument(
        "--verifier-backend",
        choices=("pinned-docker", "trusted-https"),
        default="pinned-docker",
        help="use the pinned local Docker verifier or a caller-trusted HTTPS verifier",
    )
    parser.add_argument(
        "--worker-backend",
        choices=("restricted-container", "host-process"),
        default="restricted-container",
        help=(
            "run the proposal Worker in the pinned network-none container (default) "
            "or explicitly select the legacy host-process path"
        ),
    )
    parser.add_argument("--verifier-authority-key-set")
    parser.add_argument("--verifier-authority-key-set-sha256")
    parser.add_argument("--verifier-enrollment")
    parser.add_argument("--verifier-enrollment-sha256")
    parser.add_argument("--verifier-host-decision")
    parser.add_argument("--verifier-host-decision-sha256")
    parser.add_argument("--verifier-ca-bundle")
    parser.add_argument("--verifier-ca-bundle-sha256")
    parser.add_argument(
        "--verifier-connect-address",
        help=(
            "optional IP-literal TCP destination for trusted HTTPS; TLS still "
            "authenticates the pinned verifier hostname"
        ),
    )
    parser.add_argument(
        "--verifier-connect-port",
        type=int,
        help=(
            "optional unprivileged TCP destination port for trusted HTTPS; "
            "requires --verifier-connect-address and does not change TLS identity"
        ),
    )
    parser.add_argument("--expected-worker-host-id")
    parser.add_argument("--expected-verifier-host-id")
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
    local_model = args.model_backend == "local-ollama"
    model_timeout_seconds = (
        MAX_LOCAL_MODEL_TIMEOUT_SECONDS if local_model else 30.0
    )
    authorization_card_id = args.authorization_card_id
    if (
        args.model_backend != AUTHORIZATION_MODEL_BACKENDS[authorization_card_id]
        or (
            local_model
            and (
                args.worker_backend != "restricted-container"
                or args.credential_source != "not-applicable"
            )
        )
        or (not local_model and args.credential_source == "not-applicable")
    ):
        print(
            '{"status":"stopped","reason":"model-authorization-mismatch",'
            '"external_model_attempts":0}',
            file=output,
        )
        return 2
    if local_model and args.check_credential_source:
        print(
            '{"status":"unavailable","credential_source":"not-applicable",'
            '"value_read":false,"external_model_attempts":0}',
            file=output,
        )
        return 2
    if not args.check_credential_source:
        try:
            interactive_stdin = _sys.stdin.isatty() is True
        except Exception:
            interactive_stdin = False
        if not interactive_stdin:
            print(
                '{"status":"cancelled","reason":"interactive-terminal-required",'
                '"provider_attempts":0}',
                file=output,
            )
            return 3
    verifier_client = None
    expected_worker_host_id = None
    expected_verifier_host_id = None
    verifier_trust_digests = None
    try:
        if args.verifier_backend == "trusted-https":
            (
                verifier_client,
                expected_worker_host_id,
                expected_verifier_host_id,
                verifier_trust_digests,
            ) = _load_signed_verifier_client(args)
        elif (
            _has_any_verifier_trust_artifact_args(args)
            or args.verifier_connect_address is not None
            or args.verifier_connect_port is not None
        ):
            raise ValueError
    except Exception:
        print(
            '{"status":"stopped","reason":"verifier-trust-material-unavailable",'
            '"provider_attempts":0}',
            file=output,
        )
        return 2
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
        if args.verifier_backend == "pinned-docker":
            inspect_images(docker_executable)
        else:
            _preflight_target_docker_image(docker_executable)
    except ValueError as exc:
        print(str(exc), file=error_output)
        return 2

    native_keyring_source = None
    journaled_model_channel = None
    if local_model:
        credential_source = None
        model_channel = LocalOllamaChatCompletionsChannel()
    else:
        if args.credential_source == "hidden-terminal":
            credential_source = TerminalPromptCredentialSource()
        elif args.credential_source == "process-environment":
            credential_source = ProcessEnvironmentCredentialSource(
                credential_environment, "AI_PROCESS_API"
            )
        else:
            native_keyring_source = keyring_source_factory()
            credential_source = native_keyring_source
        model_channel = DeepSeekHTTPChannel(credential_source)
    if observation_path is not None:
        journaled_model_channel = JournaledModelChannel(model_channel)
        model_channel = journaled_model_channel
    try:
        if args.worker_backend == "restricted-container":
            proposal_worker = (
                ContainerProposalWorker(
                    model_channel,
                    docker_executable=docker_executable,
                    model_timeout_seconds=model_timeout_seconds,
                )
                if local_model
                else ContainerProposalWorker(
                    model_channel, docker_executable=docker_executable
                )
            )
        else:
            proposal_worker = (
                DeepSeekProposalWorker(
                    channel=model_channel, timeout_seconds=model_timeout_seconds
                )
                if local_model
                else DeepSeekProposalWorker(channel=model_channel)
            )
    except Exception:
        print(
            '{"status":"stopped","reason":"worker-runtime-unavailable",'
            '"provider_attempts":0}',
            file=output,
        )
        return 2

    print(
        json.dumps(
            {
                "operation": (
                    "one_local_worker_call" if local_model else "one_deepseek_worker_call"
                ),
                "authorization_card_id": authorization_card_id,
                "process_id": process_id,
                "task_id": task_id,
                "repository": f"{PINNED_OWNER}/{PINNED_REPOSITORY}",
                "commit": PINNED_COMMIT,
                "tree": PINNED_TREE,
                "content_digest": PINNED_SNAPSHOT_TREE_DIGEST,
                "snapshot_source": snapshot_evidence_origin,
                "verifier_backend": args.verifier_backend,
                "worker_backend": args.worker_backend,
                **(
                    {
                        "verifier_endpoint": PINNED_SIGNED_VERIFIER_ENDPOINT_URL,
                        "verifier_connect_address": verifier_client.connect_address,
                        "verifier_connect_port": verifier_client.connect_port,
                        "verifier_trust_digests": verifier_trust_digests,
                    }
                    if verifier_client is not None
                    else {}
                ),
                "change_path": DECLARED_CHANGE_PATHS[0],
                "model_backend": args.model_backend,
                "model": LOCAL_OLLAMA_MODEL if local_model else "deepseek-flash",
                "model_timeout_seconds": model_timeout_seconds,
                "endpoint": (
                    f"http://{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}{LOCAL_OLLAMA_PATH}"
                    if local_model
                    else "https://api.deepseek.com/chat/completions"
                ),
                "max_provider_attempts": 0 if local_model else 1,
                "external_model_attempts": 0,
                "account_level_spend_cap": False,
                "credential_input": (
                    "none"
                    if local_model
                    else {
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

    if native_keyring_source is not None:
        try:
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

    observation_store = None
    execution_worker = None
    if observation_path is not None:
        try:
            observation_store = SQLiteObservationStore(observation_path)
            execution_worker = JournaledProposalWorker(
                proposal_worker,
                observation_store,
                process_id=process_id,
                task_id=task_id,
            )
            if journaled_model_channel is not None:
                journaled_model_channel.bind(execution_worker)
        except Exception:
            if observation_store is not None:
                observation_store.close()
            print(
                '{"status":"stopped","reason":"observation-journal-unavailable",'
                '"provider_attempts":0}',
                file=output,
            )
            return 2

    def report_readiness_failure(payload):
        if execution_worker is not None:
            try:
                execution_worker.finish_agent_invocation(status="failed")
            except Exception:
                # Keep unresolved or unknown work visibly open.
                pass
            try:
                payload["observer"] = execution_worker.observer_reference()
            except Exception:
                pass
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=error_output)

    try:
        try:
            transport = transport_factory()
        except Exception as exc:
            report_readiness_failure(
                {
                    "status": "failed",
                    "failure_code": "github-readiness-transport-init-failed",
                }
            )
            return 2

        def fetch_readiness():
            return transport.read_rate_limit()

        readiness_cursor_before = None
        if execution_worker is not None:
            try:
                candidate_cursor = execution_worker.observer_reference().get(
                    "as_of_cursor"
                )
                if type(candidate_cursor) is int and candidate_cursor >= 0:
                    readiness_cursor_before = candidate_cursor
            except Exception:
                pass
        try:
            if execution_worker is None:
                readiness = fetch_readiness()
            else:
                readiness = execution_worker.run_controlled_step(
                    "GitHubReadiness.fetch",
                    fetch_readiness,
                    process_id=process_id,
                )
        except Exception as exc:
            cursor_delta = None
            if execution_worker is not None and readiness_cursor_before is not None:
                try:
                    candidate_cursor = execution_worker.observer_reference().get(
                        "as_of_cursor"
                    )
                    if type(candidate_cursor) is int and candidate_cursor >= 0:
                        cursor_delta = candidate_cursor - readiness_cursor_before
                except Exception:
                    pass
            report_readiness_failure(
                {
                    "status": "failed",
                    "failure_code": readiness_failure_code(
                        exc, observer_cursor_delta=cursor_delta
                    ),
                }
            )
            return 2

        try:
            if execution_worker is None:
                permit = issue_remote_execution_permit(
                    card_id=authorization_card_id,
                    process_id=process_id,
                    task_id=task_id,
                    readiness=readiness,
                    provider_call_approved=True,
                    snapshot_evidence_origin=snapshot_evidence_origin,
                )
            else:
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
                    process_id=process_id,
                )
        except RemoteExecutionPermitError:
            report_readiness_failure(
                {
                    "status": "stopped",
                    "reason": "github-readiness-ineligible",
                    "provider_attempts": 0,
                }
            )
            return 2
        except Exception:
            report_readiness_failure(
                {
                    "status": "failed",
                    "failure_code": "github-readiness-gate-failed",
                }
            )
            return 2
        if local_model:
            try:
                model_preflight = model_preflight_factory()
                inspect_model = getattr(model_preflight, "inspect", None)
                if not callable(inspect_model):
                    raise R5LocalModelPreflightError("configuration_rejected")
                def inspect_local_model_metadata():
                    return inspect_model(
                        expected_model_digest=LOCAL_OLLAMA_MODEL_DIGEST
                    )

                if execution_worker is None:
                    metadata = inspect_local_model_metadata()
                else:
                    metadata = journal_local_model_preflight(
                        execution_worker,
                        inspect_local_model_metadata,
                        process_id=process_id,
                    )
                if (
                    getattr(metadata, "version", None) != EXPECTED_OLLAMA_VERSION
                    or getattr(metadata, "model", None) != LOCAL_OLLAMA_MODEL
                    or getattr(metadata, "model_digest", None)
                    != LOCAL_OLLAMA_MODEL_DIGEST
                ):
                    raise R5LocalModelPreflightError("metadata_request_failed")
            except Exception:
                if execution_worker is not None:
                    try:
                        execution_worker.finish_agent_invocation(status="failed")
                    except Exception:
                        pass
                print(
                    '{"status":"stopped","reason":"local-model-preflight-failed",'
                    '"snapshot_attempts":0,"external_model_attempts":0,'
                    '"provider_attempts":0}',
                    file=error_output,
                )
                return 2
            print(
                json.dumps(
                    {
                        "status": "matched",
                        "local_model_preflight": "passed",
                        "model": metadata.model,
                        "model_digest": metadata.model_digest,
                        "ollama_version": metadata.version,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                file=output,
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
            stage_database_path=stage_path,
            execution_permit=permit,
            snapshot_evidence_origin=snapshot_evidence_origin,
            test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
            stdout=output,
            stderr=error_output,
            proposal_worker=proposal_worker,
        )
        if verifier_client is None:
            runtime_options["verifier_config"] = VerifierContainerConfig(
                docker_executable=docker_executable,
                runtime_image_id=VERIFIER_RUNTIME_IMAGE_ID,
                verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
                timeout_seconds=120,
            )
        else:
            runtime_options["verifier_client"] = verifier_client
            runtime_options["expected_worker_host_id"] = expected_worker_host_id
            runtime_options["expected_verifier_host_id"] = expected_verifier_host_id
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
                execution_worker.finish_agent_invocation(status="failed")
            except Exception:
                pass
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
