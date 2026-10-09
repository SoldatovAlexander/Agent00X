from __future__ import annotations

import hashlib
import base64
from dataclasses import replace
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import patch
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

from app_contracts.digests import canonical_json, sha256_bytes, sha256_digest
from app_contracts.authority import DeterministicPolicy, PolicyConfig
from app_contracts.broker import InMemoryCredentialBroker
from app_contracts.controlled_publication import (
    run_controlled_local_publication,
)
from app_contracts.executor import (
    ExecutionRequest,
    ExecutionStatus,
    VerifierResult,
    VerifierVerdict,
    WorkerProposal,
    run_local_execution,
)
from app_contracts.deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
    DeepSeekProposalWorker,
)
from app_contracts.approval_request import main as approval_request_main
from app_contracts.approver_trust_enrollment import build_signed_approver_trust_enrollment
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts.signed_mock_publication import main as signed_mock_publication_main
import app_contracts.executor as executor_module
from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitCommitObject,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
    GitHubSnapshotRequest,
    read_github_snapshot_contents,
)
from app_contracts.github_http_transport import (
    GitHubAnonymousSnapshotTransport,
    GitHubRateLimitEvidence,
)
from app_contracts.github_git_commit_source import GitHubRawCommitObjectSource
from app_contracts.gateway import GatewayDecision, GatewayPath
from app_contracts.mock_github import MockGitHubEndpoint
from approval_test_support import (
    TEST_APPROVER_ID,
    TEST_APPROVER_PUBLIC_KEY,
    TEST_APPROVER_PUBLIC_KEYS,
    sign_test_approval,
)
from app_contracts.openai_worker import OpenAIProposalWorker, ResponsesModelResult
from app_contracts.pinned_snapshot import SNAPSHOT_DIGEST_CANONICALIZATION
from app_contracts.publication_seed import (
    build_publication_seed,
    derive_publication_intent,
)
from app_contracts.publication import PublicationJournal
from app_contracts.durable_stage import (
    DurableStageError,
    SQLiteStagedArtifactStore,
    StagedArtifact,
)
from app_contracts.secret_scan import assert_canary_absent
from app_contracts.observation_store import ObservationStore, SQLiteObservationStore
from app_contracts.observer_report import report_from_sqlite
from app_contracts.observer_runtime import JournaledProposalWorker
from app_contracts.brainbooster_target_profile import (
    PINNED_COMMIT,
    PINNED_CONTENT_DIGEST,
    PINNED_FILE_COUNT,
    PINNED_HTTP_DB_TEST_COMMAND,
    PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
    TARGET_RUNTIME_IMAGE_ID,
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.remote_snapshot_workspace import materialize_github_snapshot
from app_contracts.sandbox import CommandResult, DockerSandboxBackend, LocalProcessSandboxBackend
from app_contracts.stage_approval import run_local_mock_publication
from app_contracts.stage_preview import render_stage_preview
from app_contracts.verifier_process import SubprocessVerifier, VerifierProcessConfig
from app_contracts.verifier_container import (
    DockerContainerVerifier,
    VerifierContainerConfig,
)
from app_contracts.validator import ContractValidationError
from app_contracts.worker_cli import run_remote_snapshot_execution
import app_contracts.worker_cli as worker_cli
import run_pinned_deepseek_worker as pinned_worker_cli


def _strict_signed_range_routes_candidate(source: str) -> str:
    """Build one deterministic synthetic patch for the pinned target route."""
    if type(source) is not str:
        raise AssertionError("synthetic Worker context is invalid")
    replacements = (
        (
            "from fastapi import APIRouter\n",
            "from fastapi import APIRouter, HTTPException\n",
        ),
        (
            "def save_session(data: dict):",
            "def save_session(data: dict):\n"
            "    numeric_defaults = {\n"
            "        'level': 1, 'correct': 0, 'wrong': 0, 'total': 10, 'time_ms': 0,\n"
            "    }\n"
            "    for field, default in numeric_defaults.items():\n"
            "        value = data.get(field, default)\n"
            "        if type(value) is not int or not -(2**63) <= value <= (2**63 - 1):\n"
            "            raise HTTPException(status_code=422, detail='invalid numeric field')",
        ),
    )
    candidate = source
    for before, after in replacements:
        if candidate.count(before) != 1:
            raise AssertionError("synthetic Worker target shape mismatch")
        candidate = candidate.replace(before, after, 1)
    if candidate == source:
        raise AssertionError("synthetic Worker produced no change")
    return candidate


_SAFE_PINNED_CLI_FAILURE_CODES = frozenset(
    {
        "remote-execution-runtime-unavailable",
        "remote-execution-profile-invalid",
        "remote-execution-authorization-unavailable",
        "remote-snapshot-fetch-failed",
        "remote-snapshot-execution-failed",
        "remote-fixture-preview-failed",
        "deepseek-fixture-preview-failed",
        "cli-execution-failed",
        "pinned-worker-runtime-failed",
        "worker-failed",
        "observation-gate-failed",
        "worker-outcome-unknown",
        "sandbox-observation-gate-failed",
        "sandbox-outcome-unknown",
        "sandbox-command-failed",
        "stage-observation-gate-failed",
        "stage-outcome-unknown",
        "stage-operation-failed",
        "verification-replay-failed",
        "verifier-failed",
        "verifier-observation-gate-failed",
        "verifier-outcome-unknown",
        "verifier-not-pass",
        "verifier-trust-unestablished",
        "verifier-attestation-invalid",
        "stage-persistence-failed",
    }
)


def _safe_pinned_cli_failure_code(output: object) -> str:
    """Project only a fixed failure category from JSON output, never its payload."""
    if type(output) is not str:
        return "unavailable"
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        if type(record) is not dict or record.get("status") not in {"failed", "error"}:
            continue
        code = record.get("failure_code")
        if type(code) is str and code in _SAFE_PINNED_CLI_FAILURE_CODES:
            return code
        if (
            type(code) is str
            and re.fullmatch(r"remote-snapshot-http-[1-5][0-9]{2}", code)
            is not None
        ):
            return "remote-snapshot-http-status"
    return "unavailable"


_SAFE_OBSERVER_EVENT_TYPES = frozenset(
    {
        "decision_proposed",
        "decision_applied",
        "tool_requested",
        "tool_completed",
        "tool_failed",
        "tool_denied",
        "outcome_unknown",
        "agent_started",
        "agent_completed",
    }
)
_SAFE_OBSERVER_ACTIONS = frozenset(
    {
        "GitHubReadiness.fetch",
        "RemoteExecutionPermit.issue",
        "RemoteExecutionPermit.consume",
        "GitHubSnapshot.GET.commit",
        "GitHubSnapshot.GET.tree",
        "GitHubSnapshot.GET.blob",
        "GitHubRawCommitObjectSource.read",
        "PinnedSnapshot.validate-fixed-pin",
        "ProposalWorker.propose",
        "SandboxBackend.create.target-execution",
        "SandboxBackend.create.verifier-replay",
        "SandboxSession.run.target-tests",
        "SandboxSession.run.verifier-replay",
        "SandboxSession.close.target-execution",
        "SandboxSession.close.verifier-replay",
        "IndependentVerifier.verify",
        "StagedArtifactStore.save",
        "StagedArtifactStore.load",
    }
)
_SAFE_OBSERVER_FAILURE_CODES = frozenset(
    {
        "sandbox-command-nonzero",
        "sandbox-call-failed",
        "sandbox-close-failed",
    }
)
_SAFE_TARGET_PROBE_FAILURES = frozenset(
    {
        "readiness-exit",
        "readiness-timeout",
        "malformed-status",
        "malformed-no-write",
        "overflow-status",
        "overflow-no-write",
        "sqlite-range-status",
        "sqlite-range-no-write",
        "valid-status",
        "valid-body",
        "valid-row",
    }
)


def _safe_target_probe_failure_marker(result: object) -> str:
    """Project one fixed target-probe category; never return command output."""
    if type(result) is not CommandResult:
        return "unavailable"
    if type(result.returncode) is not int or result.returncode == 0:
        return "unavailable"
    if type(result.stdout) is not str or len(result.stdout) > 4096:
        return "unavailable"
    lines = [line for line in result.stdout.splitlines() if line]
    if len(lines) != 1 or not lines[0].startswith("agent00x:test-failure:"):
        return "unavailable"
    category = lines[0].removeprefix("agent00x:test-failure:")
    if category not in _SAFE_TARGET_PROBE_FAILURES:
        return "unavailable"
    return "target-test-failure:" + category


_PINNED_HTTP_DB_OVERFLOW_DIAGNOSTIC = r'''import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import socket

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
base = f"http://127.0.0.1:{port}"
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    deadline = time.monotonic() + 5
    while True:
        if server.poll() is not None:
            print("agent00x:overflow-diagnostic:readiness-exit", flush=True)
            raise SystemExit(2)
        try:
            with urllib.request.urlopen(base + "/openapi.json", timeout=1) as response:
                if response.status != 200:
                    print("agent00x:overflow-diagnostic:readiness-status", flush=True)
                    raise SystemExit(2)
            break
        except (OSError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                print("agent00x:overflow-diagnostic:readiness-timeout", flush=True)
                raise SystemExit(2)
            time.sleep(0.05)

    request = urllib.request.Request(
        base + "/save-session",
        data=b'{"telegram_id":"synthetic-probe","level":1e309,"correct":1,"wrong":0,"total":1,"time_ms":250}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    with sqlite3.connect("brainbooster.db", timeout=2) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if type(status) is not int or not 100 <= status <= 599 or type(rows) is not int or rows < 0:
        print("agent00x:overflow-diagnostic:invalid-result", flush=True)
        raise SystemExit(2)
    print(f"agent00x:overflow-diagnostic:status={status}:rows={rows}", flush=True)
finally:
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=2)
'''


def _safe_overflow_diagnostic_marker(result: object) -> str:
    """Return only validated status/count evidence from the synthetic probe."""
    if type(result) is not CommandResult or type(result.returncode) is not int:
        return "unavailable"
    if result.returncode != 0 or type(result.stdout) is not str or len(result.stdout) > 256:
        return "unavailable"
    lines = [line for line in result.stdout.splitlines() if line]
    if len(lines) != 1:
        return "unavailable"
    match = re.fullmatch(
        r"agent00x:overflow-diagnostic:status=([1-5][0-9]{2}):rows=(0|[1-9][0-9]{0,8})",
        lines[0],
    )
    if match is None:
        return "unavailable"
    status, rows = (int(value) for value in match.groups())
    if not 100 <= status <= 599 or rows < 0:
        return "unavailable"
    return f"overflow-diagnostic:status={status}:rows={rows}"


def _safe_overflow_exception_category_marker(result: object) -> str:
    """Return one allowlisted category; never project arbitrary command output."""
    if type(result) is not CommandResult or type(result.returncode) is not int:
        return "unavailable"
    if result.returncode != 0 or type(result.stdout) is not str or len(result.stdout) > 128:
        return "unavailable"
    lines = [line for line in result.stdout.splitlines() if line]
    if len(lines) != 1:
        return "unavailable"
    match = re.fullmatch(
        r"agent00x:overflow-exception:category=(overflow|type|value|sqlite|attribute|key|other|none)",
        lines[0],
    )
    if match is None:
        return "unavailable"
    return "overflow-exception:category=" + match.group(1)


def _safe_candidate_numeric_contract_marker(result: object) -> str:
    """Project only the fixed result or one enumerated candidate-test failure."""
    if type(result) is not CommandResult or type(result.returncode) is not int:
        return "unavailable"
    if type(result.stdout) is not str or len(result.stdout) > 160:
        return "unavailable"
    lines = [line for line in result.stdout.splitlines() if line]
    if len(lines) != 1:
        return "unavailable"
    if result.returncode == 0 and lines[0] == "agent00x:numeric-contract:PASS":
        return "candidate-numeric-contract:PASS"
    if result.returncode != 0:
        match = re.fullmatch(
            r"agent00x:numeric-contract:FAIL:(readiness-exit|readiness-timeout|"
            r"invalid-status|invalid-no-write|overflow-status|overflow-no-write|"
            r"valid-status|valid-no-write|valid-row)",
            lines[0],
        )
        if match is not None:
            return "candidate-numeric-contract:FAIL:" + match.group(1)
    return "unavailable"


class _ProbeDiagnosticSession:
    def __init__(self, session: object, evidence: dict) -> None:
        self._session = session
        self._evidence = evidence

    def __getattr__(self, name: str):
        return getattr(self._session, name)

    def run(self, argv, timeout_seconds=30):
        result = self._session.run(argv, timeout_seconds=timeout_seconds)
        marker = _safe_target_probe_failure_marker(result)
        if marker != "unavailable":
            self._evidence["target_probe_failure_marker"] = marker
        return result


class _ProbeDiagnosticBackend:
    def __init__(self, backend: object, evidence: dict) -> None:
        self._backend = backend
        self._evidence = evidence

    def create(self, snapshot, allowed_commands):
        session = self._backend.create(snapshot, allowed_commands)
        return _ProbeDiagnosticSession(session, self._evidence)


def _safe_last_observer_marker(events: object) -> str:
    """Return only a recognized event/action label from an observer sequence."""
    if type(events) not in {tuple, list}:
        return "unavailable"
    for event in reversed(events):
        if type(event) is not dict:
            continue
        event_type = event.get("event_type")
        action = event.get("decision_or_tool")
        error_code = event.get("error_code")
        if (
            event_type == "tool_failed"
            and event.get("status") == "failed"
            and type(action) is str
            and action in _SAFE_OBSERVER_ACTIONS
            and type(error_code) is str
            and error_code in _SAFE_OBSERVER_FAILURE_CODES
        ):
            return event_type + ":" + action + ":" + error_code
    for event in reversed(events):
        if type(event) is not dict:
            continue
        event_type = event.get("event_type")
        action = event.get("decision_or_tool")
        if (
            type(event_type) is str
            and event_type in _SAFE_OBSERVER_EVENT_TYPES
            and type(action) is str
            and action in _SAFE_OBSERVER_ACTIONS
        ):
            return event_type + ":" + action
    return "unavailable"


def _safe_readiness_marker(evidence: object) -> str:
    """Project only bounded HTTP status and quota count from readiness."""
    if type(evidence) is not GitHubRateLimitEvidence:
        return "unavailable"
    status = evidence.status
    remaining = evidence.remaining
    if (
        type(status) is not int
        or not 100 <= status <= 599
        or type(remaining) is not int
        or not 0 <= remaining <= 1_000_000
    ):
        return "unavailable"
    return f"http-{status}:remaining-{remaining}"


def _safe_rate_reset_marker(evidence: object) -> str:
    """Project only a bounded, strict Unix-seconds reset epoch."""
    if type(evidence) is not GitHubRateLimitEvidence:
        return "reset-unavailable"
    reset_unix = evidence.reset_unix
    if type(reset_unix) is not int or not 0 <= reset_unix <= 9_999_999_999:
        return "reset-unavailable"
    return f"reset-unix={reset_unix}"


def _safe_public_attempt_counts(
    readiness_gets: object,
    snapshot_rest_gets: object,
    raw_commit_fetches: object,
    runtime_invocations: object,
) -> str:
    """Project only strict, bounded public-attempt counters into diagnostics."""
    counts = (
        readiness_gets,
        snapshot_rest_gets,
        raw_commit_fetches,
        runtime_invocations,
    )
    limits = (1, 25, 1, 1)
    if any(
        type(value) is not int or value < 0 or value > limit
        for value, limit in zip(counts, limits)
    ):
        return "unavailable"
    return (
        f"readiness_gets={readiness_gets};"
        f"snapshot_rest_gets={snapshot_rest_gets};"
        f"raw_commit_fetches={raw_commit_fetches};"
        f"runtime_invocations={runtime_invocations}"
    )


def _synthetic_rest_snapshot_source(content: bytes, owner: str, repository: str):
    """Build a valid one-file Git object/API chain without network access."""
    blob_oid = hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()
    tree_payload = b"100644 calculator.py\0" + bytes.fromhex(blob_oid)
    tree_oid = hashlib.sha1(
        b"tree "
        + str(len(tree_payload)).encode("ascii")
        + b"\0"
        + tree_payload
    ).hexdigest()
    raw_commit = (
        f"tree {tree_oid}\n"
        "author Synthetic Fixture <fixture@example.invalid> 1 +0000\n"
        "committer Synthetic Fixture <fixture@example.invalid> 1 +0000\n"
        "\nsynthetic observer snapshot\n"
    ).encode("ascii")
    commit_oid = hashlib.sha1(
        b"commit " + str(len(raw_commit)).encode("ascii") + b"\0" + raw_commit
    ).hexdigest()
    content_digest = sha256_digest(
        {
            "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
            "files": [
                {
                    "path": "calculator.py",
                    "content_digest": sha256_bytes(content),
                    "mode": "100644",
                }
            ],
        }
    )
    expected_snapshot = GitHubSnapshotContents(
        claim=GitHubSnapshotClaim(
            owner=owner,
            repository=repository,
            commit_oid=commit_oid,
            tree_oid=tree_oid,
            content_digest=content_digest,
        ),
        files=(
            GitHubBlobClaim(
                path="calculator.py",
                mode="100644",
                sha=blob_oid,
                size=len(content),
                content=content,
                content_digest=sha256_bytes(content),
            ),
        ),
        verified_commit_object=GitCommitObject(commit_oid, tree_oid),
    )
    paths = (
        f"/repos/{owner}/{repository}/commits/{commit_oid}",
        f"/repos/{owner}/{repository}/git/trees/{tree_oid}?recursive=1",
        f"/repos/{owner}/{repository}/git/blobs/{blob_oid}",
    )
    payloads = {
        paths[0]: {"sha": commit_oid, "commit": {"tree": {"sha": tree_oid}}},
        paths[1]: {
            "sha": tree_oid,
            "truncated": False,
            "tree": [
                {
                    "path": "calculator.py",
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_oid,
                    "size": len(content),
                }
            ],
        },
        paths[2]: {
            "sha": blob_oid,
            "encoding": "base64",
            "size": len(content),
            "content": base64.b64encode(content).decode("ascii"),
        },
    }

    class SyntheticTransport:
        def __init__(self):
            self.paths = []

        def __call__(self, method, url, headers, max_bytes, *, allow_redirects):
            parsed = urlsplit(url)
            if (
                method != "GET"
                or parsed.scheme != "https"
                or parsed.netloc != "api.github.com"
                or headers
                != {
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                }
                or type(max_bytes) is not int
                or allow_redirects is not False
            ):
                raise AssertionError("synthetic REST request contract mismatch")
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            if path not in payloads or len(self.paths) >= len(paths):
                raise AssertionError("synthetic REST endpoint/count mismatch")
            self.paths.append(path)
            return {
                "status": 200,
                "body": json.dumps(payloads[path], separators=(",", ":")).encode(
                    "ascii"
                ),
            }

    class SyntheticCommitSource:
        def __init__(self):
            self.claims = []

        def __call__(self, claim):
            self.claims.append((claim.commit_oid, claim.tree_oid))
            if (claim.commit_oid, claim.tree_oid) != (commit_oid, tree_oid):
                raise AssertionError("synthetic commit pin mismatch")
            return raw_commit

    return expected_snapshot, SyntheticTransport(), SyntheticCommitSource(), paths


class FixedResponsesChannel:
    def __init__(self, proposed_content: str) -> None:
        self.proposed_content = proposed_content
        self.calls = 0

    def create_response(self, payload: dict, *, timeout_seconds: float) -> ResponsesModelResult:
        self.calls += 1
        changes = [{"path": "calculator.py", "content": self.proposed_content}]
        return ResponsesModelResult(
            status="completed",
            output_text=json.dumps({"changes": changes}, separators=(",", ":")),
        )


class FixedChatCompletionsChannel:
    def __init__(self, proposed_content: str) -> None:
        self.proposed_content = proposed_content
        self.calls = 0
        self.payloads: list[dict] = []

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        self.calls += 1
        self.payloads.append(payload)
        output = json.dumps(
            {"changes": [{"path": "calculator.py", "content": self.proposed_content}]},
            separators=(",", ":"),
        )
        return ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=output,
                        reasoning_content="must not enter proposal or evidence",
                    ),
                ),
            )
        )


def make_full_snapshot() -> tuple[GitHubSnapshotContents, str]:
    fixture = ROOT / "fixtures" / "repository" / "project" / "calculator.py"
    content = fixture.read_bytes()
    content_text = content.decode("utf-8")
    blob = GitHubBlobClaim(
        path="calculator.py",
        mode="100644",
        sha=hashlib.sha1(
            b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        ).hexdigest(),
        size=len(content),
        content=content,
        content_digest=sha256_bytes(content),
    )
    content_digest = sha256_digest(
        {
            "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
            "files": [
                {
                    "path": blob.path,
                    "content_digest": blob.content_digest,
                    "mode": blob.mode,
                }
            ],
        }
    )
    snapshot = GitHubSnapshotContents(
        claim=GitHubSnapshotClaim(
            owner="FixtureOwner",
            repository="calculator-fixture",
            commit_oid="a" * 40,
            tree_oid="b" * 40,
            content_digest=content_digest,
        ),
        files=(blob,),
    )
    return snapshot, content_text


_PUBLIC_SNAPSHOT_EVIDENCE_PREFIX = "AGENT00X_PUBLIC_SNAPSHOT_EVIDENCE="


def _emit_public_snapshot_evidence(
    stream,
    *,
    enabled: bool,
    snapshot_metadata: dict[str, object],
    staged_change_digest: str,
    observer_run_id: str,
    request_counts: dict[str, int],
    receipt: dict[str, object],
) -> None:
    """Emit one strict, content-free public integration success record."""

    if not enabled:
        return
    digest_pattern = re.compile(r"sha256:[0-9a-f]{64}\Z")
    oid_pattern = re.compile(r"[0-9a-f]{40}\Z")
    if (
        type(snapshot_metadata) is not dict
        or set(snapshot_metadata)
        != {"commit_oid", "tree_oid", "content_digest", "file_count"}
        or snapshot_metadata.get("commit_oid") != PINNED_COMMIT
        or snapshot_metadata.get("tree_oid") != PINNED_TREE
        or snapshot_metadata.get("content_digest") != PINNED_CONTENT_DIGEST
        or type(snapshot_metadata.get("file_count")) is not int
        or snapshot_metadata.get("file_count") != PINNED_FILE_COUNT
        or oid_pattern.fullmatch(snapshot_metadata["commit_oid"]) is None
        or oid_pattern.fullmatch(snapshot_metadata["tree_oid"]) is None
        or digest_pattern.fullmatch(snapshot_metadata["content_digest"]) is None
        or type(staged_change_digest) is not str
        or digest_pattern.fullmatch(staged_change_digest) is None
        or type(observer_run_id) is not str
        or re.fullmatch(r"run-[a-z0-9-]{8,64}", observer_run_id) is None
        or type(request_counts) is not dict
        or any(type(value) is not int for value in request_counts.values())
        or set(request_counts)
        != {
            "readiness_gets",
            "commit_gets",
            "tree_gets",
            "blob_gets",
            "raw_commit_fetches",
            "runtime_invocations",
        }
        or request_counts
        != {
            "readiness_gets": 1,
            "commit_gets": 1,
            "tree_gets": 1,
            "blob_gets": PINNED_FILE_COUNT,
            "raw_commit_fetches": 1,
            "runtime_invocations": 1,
        }
        or type(receipt) is not dict
        or receipt.get("status") != "mock_published"
        or receipt.get("staged_change_digest") != staged_change_digest
        or receipt.get("identity_authenticated") is not False
        or receipt.get("external_write") is not False
        or receipt.get("observer_completeness") != "partial"
    ):
        raise ValueError("public snapshot success evidence is invalid")
    record = {
        "schema": "public-snapshot-observer-mock-evidence/v1",
        "snapshot": dict(snapshot_metadata),
        "staged_change_digest": staged_change_digest,
        "observer_run_id": observer_run_id,
        "request_counts": dict(request_counts),
        "receipt": {
            "status": "mock_published",
            "staged_change_digest": staged_change_digest,
            "identity_authenticated": False,
            "external_write": False,
            "observer_completeness": "partial",
        },
    }
    line = (
        _PUBLIC_SNAPSHOT_EVIDENCE_PREFIX
        + json.dumps(record, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    if len(line) > 4096:
        raise ValueError("public snapshot success evidence is invalid")
    stream.write(line)


class RemoteSnapshotPipelineTests(unittest.TestCase):
    def test_safe_readiness_marker_projection(self):
        valid = GitHubRateLimitEvidence(
            status=200,
            remaining=10,
            reset_unix=1_799_000_000,
            observed_monotonic=1.0,
        )
        self.assertEqual(_safe_readiness_marker(valid), "http-200:remaining-10")
        for malformed in (
            None,
            RuntimeError("CANARY-EXP701"),
            {"status": 200, "remaining": 10, "body": "CANARY-EXP701"},
            SimpleNamespace(status=200, remaining=True),
            SimpleNamespace(status=200, remaining=-1),
            SimpleNamespace(status=700, remaining=10),
            SimpleNamespace(status=200, remaining="10 CANARY-EXP701"),
        ):
            with self.subTest(evidence_type=type(malformed).__name__):
                marker = _safe_readiness_marker(malformed)
                self.assertEqual(marker, "unavailable")
                self.assertNotIn("CANARY-EXP701", marker)

    def test_safe_rate_reset_marker_projection(self):
        valid = GitHubRateLimitEvidence(
            status=200,
            remaining=10,
            reset_unix=1_799_000_000,
            observed_monotonic=1.0,
        )
        self.assertEqual(
            _safe_rate_reset_marker(valid), "reset-unix=1799000000"
        )
        absent = GitHubRateLimitEvidence(
            status=200,
            remaining=10,
            reset_unix=None,
            observed_monotonic=1.0,
        )
        self.assertEqual(_safe_rate_reset_marker(absent), "reset-unavailable")

        malformed = []
        for value in (True, -1, 10_000_000_000, "CANARY-EXP709"):
            item = GitHubRateLimitEvidence(
                status=200,
                remaining=10,
                reset_unix=1_799_000_000,
                observed_monotonic=1.0,
            )
            object.__setattr__(item, "reset_unix", value)
            malformed.append(item)
        malformed.extend(
            (None, SimpleNamespace(reset_unix=1_799_000_000))
        )
        for evidence in malformed:
            with self.subTest(evidence_type=type(evidence).__name__):
                marker = _safe_rate_reset_marker(evidence)
                self.assertEqual(marker, "reset-unavailable")
                self.assertNotIn("CANARY-EXP709", marker)

    def test_safe_public_attempt_count_projection(self):
        self.assertEqual(
            _safe_public_attempt_counts(1, 0, 0, 0),
            "readiness_gets=1;snapshot_rest_gets=0;raw_commit_fetches=0;"
            "runtime_invocations=0",
        )
        for malformed in (
            (True, 0, 0, 0),
            (1, -1, 0, 0),
            (1, 26, 0, 0),
            (1, 0, "0 CANARY-EXP705", 0),
            (1, 0, 0, 2),
        ):
            with self.subTest(counts=type(malformed[2]).__name__):
                marker = _safe_public_attempt_counts(*malformed)
                self.assertEqual(marker, "unavailable")
                self.assertNotIn("CANARY-EXP705", marker)

    def test_real_snapshot_reader_is_journaled_with_worker_and_stage_offline(self):
        self._run_real_snapshot_reader_with_verifier(signed_attestation=False)

    def test_real_snapshot_reader_fails_closed_on_untrusted_verifier_host(self):
        self._run_real_snapshot_reader_with_verifier(signed_attestation=True)

    def test_real_snapshot_reader_stages_with_explicit_synthetic_host_decision(self):
        self._run_real_snapshot_reader_with_verifier(
            signed_attestation=True, explicit_host_decision=True
        )

    def _run_real_snapshot_reader_with_verifier(
        self, *, signed_attestation: bool, explicit_host_decision: bool = False
    ):
        content = (ROOT / "fixtures/repository/project/calculator.py").read_bytes()
        blob_oid = hashlib.sha1(
            b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        ).hexdigest()
        tree_payload = (
            b"100644 calculator.py\0" + bytes.fromhex(blob_oid)
        )
        tree_oid = hashlib.sha1(
            b"tree "
            + str(len(tree_payload)).encode("ascii")
            + b"\0"
            + tree_payload
        ).hexdigest()
        raw_commit = (
            f"tree {tree_oid}\n"
            "author Synthetic Fixture <fixture@example.invalid> 1 +0000\n"
            "committer Synthetic Fixture <fixture@example.invalid> 1 +0000\n"
            "\nsynthetic observer snapshot\n"
        ).encode("ascii")
        commit_oid = hashlib.sha1(
            b"commit " + str(len(raw_commit)).encode("ascii") + b"\0" + raw_commit
        ).hexdigest()
        owner, repository = "FixtureOwner", "observer-fixture"
        expected_paths = (
            f"/repos/{owner}/{repository}/commits/{commit_oid}",
            f"/repos/{owner}/{repository}/git/trees/{tree_oid}?recursive=1",
            f"/repos/{owner}/{repository}/git/blobs/{blob_oid}",
        )
        response_bodies = {
            expected_paths[0]: {
                "sha": commit_oid,
                "commit": {"tree": {"sha": tree_oid}},
            },
            expected_paths[1]: {
                "sha": tree_oid,
                "truncated": False,
                "tree": [
                    {
                        "path": "calculator.py",
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_oid,
                        "size": len(content),
                    }
                ],
            },
            expected_paths[2]: {
                "sha": blob_oid,
                "encoding": "base64",
                "size": len(content),
                "content": base64.b64encode(content).decode("ascii"),
            },
        }

        class SyntheticTransport:
            def __init__(self):
                self.paths = []

            def __call__(self, method, url, headers, max_bytes, *, allow_redirects):
                parsed = urlsplit(url)
                if (
                    method != "GET"
                    or parsed.scheme != "https"
                    or parsed.netloc != "api.github.com"
                    or headers
                    != {
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2026-03-10",
                    }
                    or type(max_bytes) is not int
                    or allow_redirects is not False
                ):
                    raise AssertionError("synthetic request contract mismatch")
                path = parsed.path + ("?" + parsed.query if parsed.query else "")
                if path not in response_bodies or len(self.paths) >= 3:
                    raise AssertionError("synthetic endpoint/count mismatch")
                self.paths.append(path)
                return {
                    "status": 200,
                    "body": json.dumps(
                        response_bodies[path], separators=(",", ":")
                    ).encode("ascii"),
                }

        transport = SyntheticTransport()
        commit_source_calls = []

        def synthetic_commit_source(claim):
            commit_source_calls.append((claim.commit_oid, claim.tree_oid))
            return raw_commit

        class FixedWorker:
            def propose(self, worker_input):
                source = dict(worker_input.context_files)["calculator.py"]
                self_test.assertEqual(source.encode("utf-8"), content)
                return WorkerProposal(
                    (("calculator.py", source + "\n# observer-linked candidate\n"),)
                )

        authority_public_key_for_test = None

        class AcceptingVerifier:
            def verify(self, prepared):
                nonlocal authority_public_key_for_test
                result = VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="synthetic-exp699-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )
                if not signed_attestation:
                    return result

                from app_contracts.signed_verifier_client import SignedVerifierClient
                from app_contracts.signed_verifier_service import (
                    VerifierProfile,
                    handle_signed_verifier_invocation,
                )

                signing_key = Ed25519PrivateKey.generate()
                profile = VerifierProfile(
                    repository_id=prepared.repository_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    snapshot_file_count=len(prepared.snapshot_files),
                    allowed_change_paths=prepared.declared_change_paths,
                    test_command=prepared.test_command,
                    test_timeout_seconds=prepared.test_timeout_seconds,
                    verifier_image_id=VERIFIER_RUNTIME_IMAGE_ID,
                    verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
                    signer_key_id="exp728-synthetic-verifier-key",
                )

                class SyntheticPassVerifier:
                    def verify(self, verifier_input):
                        return VerifierResult(
                            process_id=verifier_input.process_id,
                            base_commit=verifier_input.base_commit,
                            snapshot_tree_digest=verifier_input.snapshot_tree_digest,
                            replay_result_digest=verifier_input.replay_result_digest,
                            verifier_id=profile.expected_verifier_id,
                            patch_digest=verifier_input.patch_digest,
                            evidence_digest=verifier_input.evidence_digest,
                            verification_digest=verifier_input.verification_digest,
                            verified_contents_digest=verifier_input.verified_contents_digest,
                            verdict=VerifierVerdict.PASS,
                            evidence_origin="local_test",
                        )

                class InProcessSignedTransport:
                    def request(self, invocation_bytes):
                        return handle_signed_verifier_invocation(
                            invocation_bytes,
                            profile=profile,
                            verifier=SyntheticPassVerifier(),
                            signing_key=signing_key,
                            issued_at=datetime.now(timezone.utc),
                        )

                from app_contracts.verifier_trust_enrollment import (
                    build_signed_verifier_trust_enrollment,
                )
                from app_contracts.verifier_host_trust_decision import (
                    build_signed_verifier_host_trust_decision,
                )

                authority_key = Ed25519PrivateKey.generate()
                authority_public_key = authority_key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
                authority_public_key_for_test = authority_public_key
                verifier_public_key = signing_key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
                verifier_endpoint = "https://verifier.example.test/v1/verify"
                worker_host_id = "synthetic-worker-host-exp732"
                verifier_host_id = "synthetic-verifier-host-exp732"
                now = datetime.now(timezone.utc).replace(microsecond=0)
                evidence_digest = "sha256:" + "4" * 64
                enrollment_bytes = build_signed_verifier_trust_enrollment(
                    enrollment_id="synthetic-enrollment-exp732",
                    authority_key_id="synthetic-authority-exp732",
                    endpoint_url=verifier_endpoint,
                    verifier_id=profile.expected_verifier_id,
                    verifier_profile_digest=profile.profile_digest,
                    verifier_key_id=profile.signer_key_id,
                    verifier_public_key=verifier_public_key,
                    worker_host_id=worker_host_id,
                    verifier_host_id=verifier_host_id,
                    host_separation_evidence_digest=evidence_digest,
                    signing_key=authority_key,
                    issued_at=now,
                    expires_at=now + timedelta(hours=1),
                )
                decision_bytes = None
                if explicit_host_decision:
                    decision_bytes = build_signed_verifier_host_trust_decision(
                        decision_id="synthetic-review-exp732",
                        authority_key_id="synthetic-authority-exp732",
                        enrollment_digest=sha256_bytes(enrollment_bytes),
                        endpoint_url=verifier_endpoint,
                        verifier_id=profile.expected_verifier_id,
                        verifier_profile_digest=profile.profile_digest,
                        verifier_key_id=profile.signer_key_id,
                        worker_host_id=worker_host_id,
                        verifier_host_id=verifier_host_id,
                        host_separation_evidence_digest=evidence_digest,
                        signing_key=authority_key,
                        issued_at=now,
                        expires_at=now + timedelta(minutes=30),
                    )

                class FakeVerifierHTTPSResponse:
                    status = 200

                    def __init__(self, body):
                        self.body = body

                    def getheader(self, name):
                        return "application/json" if name == "Content-Type" else None

                    def read(self, limit):
                        return self.body[:limit]

                    def close(self):
                        return None

                class FakeVerifierHTTPSConnection:
                    def configure(self, _host, *, port, timeout, context):
                        self.port = port
                        self.timeout = timeout
                        self.context = context
                        return self

                    def request(self, method, path, *, body, headers):
                        if (method, path) != ("POST", "/v1/verify"):
                            raise AssertionError("unexpected verifier route")
                        if headers.get("Authorization") is not None:
                            raise AssertionError("verifier request must be unauthenticated")
                        self.response = FakeVerifierHTTPSResponse(
                            InProcessSignedTransport().request(body)
                        )

                    def getresponse(self):
                        return self.response

                    def close(self):
                        return None

                from app_contracts.signed_verifier_client import (
                    SignedVerifierHTTPSTransport,
                )

                verifier_connection = FakeVerifierHTTPSConnection()
                verifier_transport = SignedVerifierHTTPSTransport(
                    verifier_endpoint,
                    connection_factory=lambda host, *, port, timeout, context: verifier_connection.configure(
                        host, port=port, timeout=timeout, context=context
                    ),
                )
                client = SignedVerifierClient.from_trust_enrollment(
                    profile,
                    verifier_transport,
                    enrollment_bytes,
                    trusted_authority_keys={
                        "synthetic-authority-exp732": authority_public_key
                    },
                    expected_endpoint_url=verifier_endpoint,
                    expected_worker_host_id=worker_host_id,
                    expected_verifier_host_id=verifier_host_id,
                    host_trust_decision_bytes=decision_bytes,
                    now=now,
                )
                attestation = client.verify(prepared)
                from app_contracts.verifier_process import (
                    VerifierProcessRequest,
                    serialize_verifier_request,
                )

                self_test.assertIs(attestation.signature_valid, True)
                self_test.assertIs(
                    attestation.independent_host_trust_established,
                    explicit_host_decision,
                )
                if explicit_host_decision:
                    self_test.assertIsNotNone(
                        attestation.host_trust_decision_digest
                    )
                    self_test.assertEqual(
                        attestation.request_digest,
                        sha256_bytes(
                            serialize_verifier_request(
                                VerifierProcessRequest.from_verifier_input(prepared)
                            )
                        ),
                    )
                    self_test.assertTrue(
                        attestation.trust_enrollment_digest.startswith("sha256:")
                    )
                    self_test.assertTrue(
                        attestation.host_trust_decision_digest.startswith("sha256:")
                    )
                else:
                    self_test.assertIn("audit_only", client.limitations)
                return attestation

        class CountingStageSink:
            def __init__(self, wrapped):
                self.wrapped = wrapped
                self.save_calls = 0
                self.load_calls = 0
                self.saved_artifact = None
                self.loaded_artifact = None

            def save(self, artifact):
                self.save_calls += 1
                self.saved_artifact = artifact
                return self.wrapped.save(artifact)

            def load(self, digest):
                self.load_calls += 1
                self.loaded_artifact = self.wrapped.load(digest)
                return self.loaded_artifact

        self_test = self
        content_digest = sha256_digest(
            {
                "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
                "files": [
                    {
                        "path": "calculator.py",
                        "content_digest": sha256_bytes(content),
                        "mode": "100644",
                    }
                ],
            }
        )
        process_id = "process-exp699-synthetic"
        task_id = "task-exp699-synthetic"
        observer_temporary = tempfile.TemporaryDirectory(
            prefix="exp738-same-run-observer-"
        )
        self.addCleanup(observer_temporary.cleanup)
        observer_database = Path(observer_temporary.name) / "observer.sqlite3"
        observer_store = SQLiteObservationStore(observer_database)
        self.addCleanup(observer_store.close)
        worker = JournaledProposalWorker(
            FixedWorker(),
            observer_store,
            process_id=process_id,
            task_id=task_id,
            id_factory=iter(f"exp699-{index:04d}" for index in range(1, 1000)).__next__,
            clock=lambda: datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
        )

        with tempfile.TemporaryDirectory(prefix="exp699-synthetic-snapshot-") as directory:
            stage_path = Path(directory) / "stage.sqlite3"
            with SQLiteStagedArtifactStore(stage_path) as stage_store:
                counting_stage = CountingStageSink(stage_store)
                profile = worker_cli.RemoteSnapshotExecutionProfile(
                    process_id=process_id,
                    task_id=task_id,
                    task_instruction="Add one harmless comment to calculator.py.",
                    declared_change_paths=("calculator.py",),
                    allowed_commands=frozenset({Path(sys.executable).name}),
                    test_command=(sys.executable, "-c", "pass"),
                    worker=FixedWorker(),
                    verifier=AcceptingVerifier(),
                    sandbox_backend=LocalProcessSandboxBackend(),
                    stage_sink=counting_stage,
                    stage_database_path=stage_path,
                    observation_store=observer_store,
                )
                with patch.multiple(
                    worker_cli,
                    REMOTE_REPOSITORY_OWNER=owner,
                    REMOTE_REPOSITORY_NAME=repository,
                    REMOTE_REPOSITORY_COMMIT=commit_oid,
                    REMOTE_REPOSITORY_TREE=tree_oid,
                    REMOTE_REPOSITORY_CONTENT_DIGEST=content_digest,
                    REMOTE_REPOSITORY_FILE_COUNT=1,
                ), patch.object(
                    worker_cli,
                    "GitHubAnonymousSnapshotTransport",
                    return_value=transport,
                ), patch.object(
                    worker_cli,
                    "GitHubRawCommitObjectSource",
                    return_value=synthetic_commit_source,
                ):
                    evidence = worker_cli._run_pinned_remote_execution(
                        profile,
                        execution_worker=worker,
                    )

        events = observer_store.events()
        run_ids = {event["run_id"] for event in events}
        self.assertEqual(len(run_ids), 1)
        run_id = next(iter(run_ids))
        labels = [
            event["decision_or_tool"]
            for event in events
            if event.get("event_type") in {"tool_requested", "decision_proposed"}
        ]
        if signed_attestation:
            if explicit_host_decision:
                self.assertEqual(
                    evidence["status"],
                    "verified",
                    evidence.get("failure_code"),
                )
                self.assertTrue(
                    evidence["verifier_attestation"][
                        "independent_host_trust_established"
                    ]
                )
                self.assertTrue(
                    evidence["verifier_attestation"][
                        "host_trust_decision_digest"
                    ].startswith("sha256:")
                )
                self.assertEqual((counting_stage.save_calls, counting_stage.load_calls), (1, 1))
                self.assertEqual(counting_stage.loaded_artifact, counting_stage.saved_artifact)
                persisted_proof = counting_stage.saved_artifact.payload_copy()[
                    "verifier_trust_evidence"
                ]
                self.assertEqual(
                    persisted_proof["schema"],
                    "persisted-verifier-trust-evidence/v2",
                )
                self.assertEqual(
                    persisted_proof["request_digest"],
                    json.loads(
                        base64.b64decode(
                            persisted_proof["signed_response_base64"], validate=True
                        )
                    )["request_digest"],
                )
                self.assertIsNotNone(persisted_proof["signed_response_base64"])
                self.assertIsNotNone(persisted_proof["trust_enrollment_base64"])
                self.assertIsNotNone(persisted_proof["host_trust_decision_base64"])
                from app_contracts.verifier_process import (
                    parse_verifier_request,
                    serialize_verifier_request,
                )

                persisted_request = base64.b64decode(
                    persisted_proof["verifier_request_base64"], validate=True
                )
                typed_request = parse_verifier_request(persisted_request)
                self.assertEqual(serialize_verifier_request(typed_request), persisted_request)
                self.assertEqual(
                    sha256_bytes(persisted_request), persisted_proof["request_digest"]
                )
                from app_contracts.verifier_provenance import (
                    VerifierProvenanceError,
                    is_verified_stage_verifier_provenance,
                    verify_staged_verifier_provenance,
                )

                revalidated = verify_staged_verifier_provenance(
                    counting_stage.loaded_artifact,
                    trusted_authority_keys={
                        "synthetic-authority-exp732": authority_public_key_for_test
                    },
                    now=datetime.now(timezone.utc),
                )
                self.assertTrue(is_verified_stage_verifier_provenance(revalidated))
                self.assertTrue(revalidated.request_input_reconstructed)
                self.assertFalse(revalidated.provider_write)
                self.assertFalse(revalidated.identity_authenticated)
                self.assertTrue(revalidated.authority_signatures_valid)
                self.assertTrue(revalidated.verifier_signature_valid)
                self.assertEqual(
                    revalidated.verifier_attestation_digest,
                    counting_stage.loaded_artifact.payload_copy()["seed"][
                        "verifier_attestation_digest"
                    ],
                )
                self.assertEqual(
                    revalidated.verifier_request_digest,
                    persisted_proof["request_digest"],
                )
                self.assertNotIn(
                    persisted_proof["signed_response_base64"], repr(revalidated)
                )
                self.assertNotIn(persisted_proof["verifier_request_base64"], repr(revalidated))

                # Remote approval intent and its later consumption must each
                # independently revalidate the staged verifier proof against
                # caller-pinned authority keys.
                from app_contracts.approval_request import build_approval_request
                from app_contracts.signed_approval import (
                    SignedApprovalError,
                    load_verified_signed_approval,
                )

                stage_payload = counting_stage.loaded_artifact.payload_copy()
                target_binding = RepositoryTargetBinding(
                    f"{owner}/{repository}", "github-installation/456/repository/1001"
                )
                approval_now = datetime.now(timezone.utc).replace(microsecond=0)
                trusted_verifier_keys = {
                    "synthetic-authority-exp732": authority_public_key_for_test
                }
                request = build_approval_request(
                    counting_stage.loaded_artifact,
                    target_binding,
                    branch="agent/exp737-remote-approval",
                    base_branch="main",
                    approval_id="approval-exp737-remote-positive",
                    approver_id=TEST_APPROVER_ID,
                    policy_version="synthetic-policy-exp737",
                    now=approval_now,
                    trusted_verifier_authority_keys=trusted_verifier_keys,
                )
                self.assertEqual(
                    request["intent"]["verifier_trust"]["status"],
                    "cryptographically_revalidated_request_reconstructed",
                )
                self.assertTrue(
                    request["intent"]["verifier_trust"]["request_input_reconstructed"]
                )
                approval_temporary = tempfile.TemporaryDirectory(
                    prefix="exp737-approval-"
                )
                self.addCleanup(approval_temporary.cleanup)
                approval_root = Path(approval_temporary.name)
                approval_database = approval_root / "stage.sqlite3"
                with SQLiteStagedArtifactStore(approval_database) as approval_store:
                    approval_store.save(counting_stage.loaded_artifact)
                request_path = approval_root / "request.json"
                signed_path = approval_root / "signed.json"
                profile_path = approval_root / "trust.json"
                request_path.write_text(json.dumps(request), encoding="utf-8")
                signed_path.write_text(
                    json.dumps(
                        {
                            "schema": "signed-approval/v1",
                            "approval": sign_test_approval(request["unsigned_approval"]),
                        }
                    ),
                    encoding="utf-8",
                )
                profile_path.write_text(
                    json.dumps(
                        {
                            "schema": "approval-trust-profile/v1",
                            "policy_version": "synthetic-policy-exp737",
                            "target": {
                                "source_repository_id": target_binding.source_repository_id,
                                "provider_repository_id": target_binding.provider_repository_id,
                            },
                            "allowed_repositories": [target_binding.provider_repository_id],
                            "allowed_actuators": ["github-app-actuator"],
                            "allowed_approver_ids": [TEST_APPROVER_ID],
                            "trusted_approver_public_keys": {
                                TEST_APPROVER_ID: TEST_APPROVER_PUBLIC_KEY.hex()
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                consumed = load_verified_signed_approval(
                    approval_database,
                    counting_stage.loaded_artifact.staged_change_digest,
                    request_path,
                    signed_path,
                    profile_path,
                    trusted_verifier_authority_keys=trusted_verifier_keys,
                    now=approval_now + timedelta(seconds=1),
                )
                self.assertEqual(
                    consumed.result["verifier_trust"]["status"],
                    "cryptographically_revalidated_request_reconstructed",
                )
                with self.assertRaises(SignedApprovalError):
                    load_verified_signed_approval(
                        approval_database,
                        counting_stage.loaded_artifact.staged_change_digest,
                        request_path,
                        signed_path,
                        profile_path,
                        trusted_verifier_authority_keys={
                            "different-authority": authority_public_key_for_test
                        },
                        now=approval_now + timedelta(seconds=1),
                    )

                verifier_key_set_path = approval_root / "verifier-authority.json"
                verifier_key_set = {
                    "schema": "control-plane-authority-key-set/v1",
                    "keys": {
                        "synthetic-authority-exp732": authority_public_key_for_test.hex()
                    },
                }
                verifier_key_set_path.write_text(
                    json.dumps(verifier_key_set, sort_keys=True), encoding="utf-8"
                )
                verifier_key_set_digest = sha256_bytes(
                    verifier_key_set_path.read_bytes()
                )
                approver_authority_key = Ed25519PrivateKey.generate()
                approver_authority_key_id = "synthetic-approver-authority-exp738"
                approver_authority_public_key = approver_authority_key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
                approver_key_set_path = approval_root / "approver-authority.json"
                approver_key_set = {
                    "schema": "control-plane-authority-key-set/v1",
                    "keys": {
                        approver_authority_key_id: approver_authority_public_key.hex()
                    },
                }
                approver_key_set_path.write_text(
                    json.dumps(approver_key_set, sort_keys=True), encoding="utf-8"
                )
                approver_key_set_digest = sha256_bytes(
                    approver_key_set_path.read_bytes()
                )
                approver_enrollment_path = approval_root / "approver-enrollment.json"
                approver_enrollment_path.write_bytes(
                    build_signed_approver_trust_enrollment(
                        enrollment_id="synthetic-approver-enrollment-exp738",
                        authority_key_id=approver_authority_key_id,
                        approver_id=TEST_APPROVER_ID,
                        approver_public_key=TEST_APPROVER_PUBLIC_KEY,
                        trust_profile_digest=sha256_digest(
                            json.loads(profile_path.read_text(encoding="utf-8"))
                        ),
                        provider_repository_id=target_binding.provider_repository_id,
                        signing_key=approver_authority_key,
                        issued_at=approval_now - timedelta(minutes=1),
                        expires_at=approval_now + timedelta(days=1),
                    )
                )

                stage_before_publication = approval_database.read_bytes()
                enrolled_cli_args = [
                    str(approval_database),
                    counting_stage.loaded_artifact.staged_change_digest,
                    str(request_path),
                    str(signed_path),
                    str(profile_path),
                    "--approver-enrollment",
                    str(approver_enrollment_path),
                    "--authority-key-set",
                    str(approver_key_set_path),
                    "--authority-key-set-digest",
                    approver_key_set_digest,
                ]
                missing_pins_stdout, missing_pins_stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(missing_pins_stdout), redirect_stderr(
                    missing_pins_stderr
                ):
                    missing_pins_code = signed_mock_publication_main(
                        enrolled_cli_args, now=approval_now + timedelta(seconds=1)
                    )
                self.assertEqual(missing_pins_code, 2)
                self.assertEqual(missing_pins_stdout.getvalue(), "")
                self.assertIn("signed approval:", missing_pins_stderr.getvalue())

                wrong_verifier_key_set_path = approval_root / "wrong-verifier-authority.json"
                wrong_verifier_key_set = {
                    "schema": "control-plane-authority-key-set/v1",
                    "keys": {
                        "different-authority": authority_public_key_for_test.hex()
                    },
                }
                wrong_verifier_key_set_path.write_text(
                    json.dumps(wrong_verifier_key_set, sort_keys=True),
                    encoding="utf-8",
                )
                wrong_verifier_key_set_digest = sha256_bytes(
                    wrong_verifier_key_set_path.read_bytes()
                )
                wrong_pins_stdout, wrong_pins_stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(wrong_pins_stdout), redirect_stderr(
                    wrong_pins_stderr
                ):
                    wrong_pins_code = signed_mock_publication_main(
                        [
                            *enrolled_cli_args,
                            "--verifier-authority-key-set",
                            str(wrong_verifier_key_set_path),
                            "--verifier-authority-key-set-digest",
                            wrong_verifier_key_set_digest,
                        ],
                        now=approval_now + timedelta(seconds=1),
                    )
                self.assertEqual(wrong_pins_code, 2)
                self.assertEqual(wrong_pins_stdout.getvalue(), "")
                self.assertIn("signed approval:", wrong_pins_stderr.getvalue())
                self.assertEqual(
                    approval_database.read_bytes(), stage_before_publication
                )

                JournaledProposalWorker.resume_existing(
                    FixedWorker(),
                    observer_store,
                    process_id=process_id,
                    run_id=run_id,
                )
                observer_store.close()
                observer_bytes_before_rejected_run = observer_database.read_bytes()
                rejected_stdout, rejected_stderr = io.StringIO(), io.StringIO()
                rejected_observer_argv = [
                    *enrolled_cli_args,
                    "--verifier-authority-key-set",
                    str(verifier_key_set_path),
                    "--verifier-authority-key-set-digest",
                    verifier_key_set_digest,
                    "--observer-db",
                    str(observer_database),
                    "--observer-run-id",
                    "run-exp738-unrecognized",
                ]
                with redirect_stdout(rejected_stdout), redirect_stderr(rejected_stderr):
                    rejected_code = signed_mock_publication_main(
                        rejected_observer_argv,
                        now=approval_now + timedelta(seconds=1),
                    )
                self.assertEqual(rejected_code, 2)
                self.assertIn("observer run rejected", rejected_stderr.getvalue())
                self.assertEqual(rejected_stdout.getvalue(), "")
                self.assertEqual(
                    observer_database.read_bytes(), observer_bytes_before_rejected_run
                )
                publication_stdout, publication_stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(publication_stdout), redirect_stderr(
                    publication_stderr
                ):
                    publication_code = signed_mock_publication_main(
                        [
                            *enrolled_cli_args,
                            "--verifier-authority-key-set",
                            str(verifier_key_set_path),
                            "--verifier-authority-key-set-digest",
                            verifier_key_set_digest,
                            "--observer-db",
                            str(observer_database),
                            "--observer-run-id",
                            run_id,
                        ],
                        now=approval_now + timedelta(seconds=1),
                    )
                observer_store = SQLiteObservationStore(observer_database)
                self.addCleanup(observer_store.close)
                self.assertEqual(
                    publication_code,
                    0,
                    publication_stderr.getvalue()
                    + repr(observer_store.events()[-4:]),
                )
                self.assertEqual(publication_stderr.getvalue(), "")
                receipt_evidence = json.loads(publication_stdout.getvalue())
                expected_intent = request["intent"]
                self.assertEqual(receipt_evidence["status"], "mock_published")
                self.assertEqual(
                    receipt_evidence["staged_change_digest"],
                    counting_stage.loaded_artifact.staged_change_digest,
                )
                self.assertEqual(
                    receipt_evidence["repository_id"],
                    target_binding.provider_repository_id,
                )
                self.assertEqual(receipt_evidence["branch"], expected_intent["branch"])
                self.assertEqual(
                    receipt_evidence["idempotency_key"],
                    expected_intent["idempotency_key"],
                )
                self.assertEqual(
                    receipt_evidence["destination"], "in_memory_mock_only"
                )
                self.assertIs(receipt_evidence["external_write"], False)
                self.assertIs(receipt_evidence["identity_authenticated"], False)
                self.assertEqual(
                    approval_database.read_bytes(), stage_before_publication
                )
                final_events = observer_store.events()
                self.assertEqual({event["run_id"] for event in final_events}, {run_id})
                final_labels = {
                    event["decision_or_tool"]
                    for event in final_events
                    if event.get("event_type") in {"tool_requested", "decision_proposed"}
                }
                self.assertIn("ControlledPublication.local-mock", final_labels)
                self.assertIn("SignedApproval.verify", final_labels)
                for required_label in (
                    "GitHubSnapshot.GET.commit",
                    "GitHubRawCommitObjectSource.read",
                    "ProposalWorker.propose",
                    "IndependentVerifier.verify",
                    "StagedArtifactStore.save",
                    "StagedArtifactStore.load",
                ):
                    self.assertIn(required_label, final_labels)
                self.assertEqual(receipt_evidence["observer"]["run_id"], run_id)
                self.assertEqual(
                    receipt_evidence["observer"]["completeness"], "partial"
                )

                legacy_payload = counting_stage.loaded_artifact.payload_copy()
                legacy_proof = legacy_payload["verifier_trust_evidence"]
                legacy_proof["schema"] = "persisted-verifier-trust-evidence/v1"
                legacy_proof.pop("verifier_request_base64")
                legacy_proof.pop("request_context")
                legacy_bytes = canonical_json(legacy_payload)
                legacy_artifact = StagedArtifact(
                    staged_change_digest=counting_stage.loaded_artifact.staged_change_digest,
                    verified_contents_digest=counting_stage.loaded_artifact.verified_contents_digest,
                    artifact_digest=sha256_bytes(legacy_bytes),
                    canonical_payload=legacy_bytes.decode("utf-8"),
                )
                legacy_revalidated = verify_staged_verifier_provenance(
                    legacy_artifact,
                    trusted_authority_keys={
                        "synthetic-authority-exp732": authority_public_key_for_test
                    },
                    now=datetime.now(timezone.utc),
                )
                self.assertFalse(legacy_revalidated.request_input_reconstructed)
                with self.assertRaisesRegex(
                    VerifierProvenanceError,
                    "^verifier provenance: stage evidence verification failed$",
                ) as wrong_authority:
                    verify_staged_verifier_provenance(
                        counting_stage.loaded_artifact,
                        trusted_authority_keys={
                            "synthetic-authority-exp732": b"x" * 32
                        },
                        now=datetime.now(timezone.utc),
                    )
                self.assertNotIn(
                    persisted_proof["signed_response_base64"],
                    str(wrong_authority.exception),
                )
                with self.assertRaises(VerifierProvenanceError):
                    verify_staged_verifier_provenance(
                        counting_stage.loaded_artifact,
                        trusted_authority_keys={
                            "synthetic-authority-exp732": authority_public_key_for_test
                        },
                        now=datetime.now(timezone.utc) + timedelta(seconds=301),
                    )
                with self.assertRaises(VerifierProvenanceError):
                    verify_staged_verifier_provenance(
                        counting_stage.loaded_artifact,
                        trusted_authority_keys={
                            "synthetic-authority-exp732": authority_public_key_for_test
                        },
                        now=datetime.now(timezone.utc) - timedelta(seconds=31),
                    )

                def rebuild_stage(payload):
                    encoded = canonical_json(payload)
                    return StagedArtifact(
                        staged_change_digest=counting_stage.loaded_artifact.staged_change_digest,
                        verified_contents_digest=counting_stage.loaded_artifact.verified_contents_digest,
                        artifact_digest=sha256_bytes(encoded),
                        canonical_payload=encoded.decode("utf-8"),
                    )

                noncanonical_request_payload = counting_stage.loaded_artifact.payload_copy()
                noncanonical_proof = noncanonical_request_payload[
                    "verifier_trust_evidence"
                ]
                noncanonical_request = base64.b64decode(
                    noncanonical_proof["verifier_request_base64"], validate=True
                )
                noncanonical_proof["verifier_request_base64"] = base64.b64encode(
                    b" " + noncanonical_request
                ).decode("ascii")
                with self.assertRaises(DurableStageError):
                    rebuild_stage(noncanonical_request_payload)

                duplicate_request_payload = counting_stage.loaded_artifact.payload_copy()
                duplicate_proof = duplicate_request_payload["verifier_trust_evidence"]
                duplicate_request = (
                    b'{"schema_version":3,"schema_version":3}'
                )
                duplicate_proof["verifier_request_base64"] = base64.b64encode(
                    duplicate_request
                ).decode("ascii")
                duplicate_proof["request_digest"] = sha256_bytes(duplicate_request)
                with self.assertRaises(DurableStageError):
                    rebuild_stage(duplicate_request_payload)

                altered_snapshot_payload = counting_stage.loaded_artifact.payload_copy()
                altered_snapshot_proof = altered_snapshot_payload[
                    "verifier_trust_evidence"
                ]
                altered_request_bytes = base64.b64decode(
                    altered_snapshot_proof["verifier_request_base64"], validate=True
                )
                altered_request = json.loads(altered_request_bytes)
                altered_snapshot = altered_request["verifier_input"]["snapshot_files"]
                altered_file = bytearray(
                    base64.b64decode(altered_snapshot[0][2], validate=True)
                )
                altered_file[0] ^= 1
                altered_snapshot[0][2] = base64.b64encode(altered_file).decode("ascii")
                altered_snapshot_bytes = canonical_json(altered_request)
                altered_snapshot_proof["verifier_request_base64"] = base64.b64encode(
                    altered_snapshot_bytes
                ).decode("ascii")
                altered_snapshot_proof["request_digest"] = sha256_bytes(
                    altered_snapshot_bytes
                )
                with self.assertRaises(DurableStageError):
                    rebuild_stage(altered_snapshot_payload)

                altered_candidate_payload = counting_stage.loaded_artifact.payload_copy()
                altered_candidate_proof = altered_candidate_payload[
                    "verifier_trust_evidence"
                ]
                altered_candidate_request = json.loads(
                    base64.b64decode(
                        altered_candidate_proof["verifier_request_base64"], validate=True
                    )
                )
                altered_candidate_request["verifier_input"]["verified_contents"][0][1] += (
                    "\n# substituted request candidate"
                )
                altered_candidate_bytes = canonical_json(altered_candidate_request)
                altered_candidate_digest = sha256_bytes(altered_candidate_bytes)
                altered_candidate_proof["verifier_request_base64"] = base64.b64encode(
                    altered_candidate_bytes
                ).decode("ascii")
                altered_candidate_proof["request_digest"] = altered_candidate_digest
                changed_response = json.loads(
                    base64.b64decode(
                        altered_candidate_proof["signed_response_base64"], validate=True
                    )
                )
                changed_response["request_digest"] = altered_candidate_digest
                changed_response_bytes = canonical_json(changed_response)
                altered_candidate_proof["signed_response_base64"] = base64.b64encode(
                    changed_response_bytes
                ).decode("ascii")
                altered_candidate_payload["seed"]["verifier_attestation_digest"] = (
                    sha256_bytes(changed_response_bytes)
                )
                with self.assertRaises(DurableStageError):
                    rebuild_stage(altered_candidate_payload)

                oversized_request_payload = counting_stage.loaded_artifact.payload_copy()
                oversized_proof = oversized_request_payload["verifier_trust_evidence"]
                oversized_proof["verifier_request_base64"] = base64.b64encode(
                    b"x" * (2_000_000 + 1)
                ).decode("ascii")
                with self.assertRaises(DurableStageError):
                    rebuild_stage(oversized_request_payload)
                tampered_payload = counting_stage.loaded_artifact.payload_copy()
                tampered_evidence = tampered_payload["verifier_trust_evidence"]
                tampered_response = json.loads(
                    base64.b64decode(
                        tampered_evidence["signed_response_base64"], validate=True
                    )
                )
                tampered_response["signature"] = "00" * 64
                tampered_response_bytes = canonical_json(tampered_response)
                tampered_evidence["signed_response_base64"] = base64.b64encode(
                    tampered_response_bytes
                ).decode("ascii")
                tampered_digest = sha256_bytes(tampered_response_bytes)
                tampered_payload["seed"]["verifier_attestation_digest"] = (
                    tampered_digest
                )
                tampered_artifact_bytes = canonical_json(tampered_payload)
                tampered_artifact = StagedArtifact(
                    staged_change_digest=counting_stage.loaded_artifact.staged_change_digest,
                    verified_contents_digest=counting_stage.loaded_artifact.verified_contents_digest,
                    artifact_digest=sha256_bytes(tampered_artifact_bytes),
                    canonical_payload=tampered_artifact_bytes.decode("utf-8"),
                )
                with self.assertRaises(VerifierProvenanceError):
                    verify_staged_verifier_provenance(
                        tampered_artifact,
                        trusted_authority_keys={
                            "synthetic-authority-exp732": authority_public_key_for_test
                        },
                        now=datetime.now(timezone.utc),
                    )
                for evidence_field, seed_field in (
                    ("trust_enrollment_base64", "verifier_trust_enrollment_digest"),
                    ("host_trust_decision_base64", "verifier_host_trust_decision_digest"),
                ):
                    authority_tampered_payload = (
                        counting_stage.loaded_artifact.payload_copy()
                    )
                    authority_tampered_evidence = authority_tampered_payload[
                        "verifier_trust_evidence"
                    ]
                    authority_record = json.loads(
                        base64.b64decode(
                            authority_tampered_evidence[evidence_field], validate=True
                        )
                    )
                    authority_record["signature"] = "00" * 64
                    authority_record_bytes = canonical_json(authority_record)
                    authority_tampered_evidence[evidence_field] = base64.b64encode(
                        authority_record_bytes
                    ).decode("ascii")
                    changed_digest = sha256_bytes(authority_record_bytes)
                    authority_tampered_payload["seed"][seed_field] = changed_digest
                    if evidence_field == "trust_enrollment_base64":
                        linked_decision = json.loads(
                            base64.b64decode(
                                authority_tampered_evidence[
                                    "host_trust_decision_base64"
                                ],
                                validate=True,
                            )
                        )
                        linked_decision["enrollment_digest"] = changed_digest
                        linked_decision_bytes = canonical_json(linked_decision)
                        authority_tampered_evidence[
                            "host_trust_decision_base64"
                        ] = base64.b64encode(linked_decision_bytes).decode("ascii")
                        authority_tampered_payload["seed"][
                            "verifier_host_trust_decision_digest"
                        ] = sha256_bytes(linked_decision_bytes)
                    authority_tampered_bytes = canonical_json(
                        authority_tampered_payload
                    )
                    authority_tampered_artifact = StagedArtifact(
                        staged_change_digest=counting_stage.loaded_artifact.staged_change_digest,
                        verified_contents_digest=counting_stage.loaded_artifact.verified_contents_digest,
                        artifact_digest=sha256_bytes(authority_tampered_bytes),
                        canonical_payload=authority_tampered_bytes.decode("utf-8"),
                    )
                    with self.assertRaises(VerifierProvenanceError):
                        verify_staged_verifier_provenance(
                            authority_tampered_artifact,
                            trusted_authority_keys={
                                "synthetic-authority-exp732": authority_public_key_for_test
                            },
                            now=datetime.now(timezone.utc),
                        )
                rendered_review = render_stage_preview(counting_stage.saved_artifact)
                self.assertIn('"signed_evidence_status": "stored_not_revalidated"', rendered_review)
                self.assertNotIn(
                    persisted_proof["signed_response_base64"], rendered_review
                )
                self.assertNotIn(
                    persisted_proof["verifier_request_base64"], rendered_review
                )
                self.assertNotIn(
                    persisted_proof["signed_response_base64"],
                    json.dumps(evidence, sort_keys=True),
                )
                self.assertNotIn(
                    persisted_proof["verifier_request_base64"],
                    json.dumps(evidence, sort_keys=True),
                )
                altered_payload = counting_stage.saved_artifact.payload_copy()
                altered_payload["verifier_trust_evidence"]["request_digest"] = (
                    "sha256:" + "0" * 64
                )
                altered_raw = canonical_json(altered_payload)
                with self.assertRaisesRegex(
                    DurableStageError,
                    "^durable stage: verifier evidence is invalid$",
                ):
                    StagedArtifact(
                        staged_change_digest=counting_stage.saved_artifact.staged_change_digest,
                        verified_contents_digest=counting_stage.saved_artifact.verified_contents_digest,
                        artifact_digest=sha256_bytes(altered_raw),
                        canonical_payload=altered_raw.decode("utf-8"),
                    )
                self.assertIn("StagedArtifactStore.save", labels)
                self.assertIn("StagedArtifactStore.load", labels)
            else:
                self.assertEqual(evidence["status"], "failed")
                self.assertEqual(evidence["failure_code"], "verifier-trust-unestablished")
                self.assertTrue(
                    evidence["verifier_attestation"][
                        "trust_enrollment_digest"
                    ].startswith("sha256:")
                )
                self.assertIs(
                    evidence["verifier_attestation"]["independent_host_trust_established"],
                    False,
                )
                self.assertEqual((counting_stage.save_calls, counting_stage.load_calls), (0, 0))
                self.assertNotIn("StagedArtifactStore.save", labels)
                self.assertNotIn("StagedArtifactStore.load", labels)
        else:
            self.assertEqual(evidence["status"], "verified")
            self.assertEqual((counting_stage.save_calls, counting_stage.load_calls), (1, 1))
        self.assertEqual(transport.paths, list(expected_paths))
        self.assertEqual(commit_source_calls, [(commit_oid, tree_oid)])
        self.assertEqual(run_ids, {worker.observer_reference()["run_id"]})
        self.assertEqual(
            labels[:5],
            [
                "GitHubSnapshot.GET.commit",
                "GitHubRawCommitObjectSource.read",
                "GitHubSnapshot.GET.tree",
                "GitHubSnapshot.GET.blob",
                "PinnedSnapshot.validate-fixed-pin",
            ],
        )
        self.assertIn("ProposalWorker.propose", labels)
        self.assertIn("SandboxSession.run.target-tests", labels)
        self.assertIn("IndependentVerifier.verify", labels)
        if not signed_attestation:
            self.assertIn("StagedArtifactStore.save", labels)
            self.assertIn("StagedArtifactStore.load", labels)
        self.assertEqual(
            [event["sequence"] for event in events], list(range(len(events)))
        )

    def test_safe_pinned_cli_failure_code_projection(self):
        self.assertEqual(
            _safe_pinned_cli_failure_code(
                '{"status":"failed","failure_code":"verifier-not-pass",'
                '"detail":"synthetic-private-value-EXP695"}'
            ),
            "verifier-not-pass",
        )
        self.assertEqual(
            _safe_pinned_cli_failure_code(
                '{"status":"failed","failure_code":"remote-snapshot-http-503"}'
            ),
            "remote-snapshot-http-status",
        )
        for untrusted_output in (
            '{"status":"failed","failure_code":"synthetic-private-value-EXP695"}',
            '{"status":"failed","failure_code":42}',
            "not-json synthetic-private-value-EXP695",
        ):
            with self.subTest(output_type=type(untrusted_output).__name__):
                result = _safe_pinned_cli_failure_code(untrusted_output)
                self.assertEqual(result, "unavailable")
                self.assertNotIn("synthetic-private-value-EXP695", result)

    def test_safe_last_observer_marker_projection(self):
        canary = "synthetic-private-value-EXP697"
        self.assertEqual(
            _safe_last_observer_marker(
                [
                    {
                        "event_type": "tool_completed",
                        "decision_or_tool": "ProposalWorker.propose",
                        "payload": canary,
                    },
                    {
                        "event_type": "tool_failed",
                        "decision_or_tool": "SandboxSession.run.target-tests",
                        "payload": canary,
                    },
                ]
            ),
            "tool_failed:SandboxSession.run.target-tests",
        )
        self.assertEqual(
            _safe_last_observer_marker(
                [
                    {
                        "event_type": "tool_failed",
                        "status": "failed",
                        "decision_or_tool": "SandboxSession.run.target-tests",
                        "error_code": "sandbox-command-nonzero",
                        "payload": canary,
                    },
                    {
                        "event_type": "tool_requested",
                        "status": "pending",
                        "decision_or_tool": "SandboxSession.close.target-execution",
                        "payload": canary,
                    },
                ]
            ),
            "tool_failed:SandboxSession.run.target-tests:sandbox-command-nonzero",
        )
        for untrusted_error in (canary, 7, "sandbox-command-nonzero-extra"):
            with self.subTest(error_code_type=type(untrusted_error).__name__):
                result = _safe_last_observer_marker(
                    [
                        {
                            "event_type": "tool_failed",
                            "status": "failed",
                            "decision_or_tool": "SandboxSession.run.target-tests",
                            "error_code": untrusted_error,
                            "payload": canary,
                        }
                    ]
                )
                self.assertEqual(
                    result, "tool_failed:SandboxSession.run.target-tests"
                )
                self.assertNotIn(canary, result)
        for untrusted_events in (
            [{"event_type": "unknown-event", "decision_or_tool": "ProposalWorker.propose", "payload": canary}],
            [{"event_type": "tool_failed", "decision_or_tool": canary, "payload": canary}],
            ["malformed-event"],
            None,
        ):
            with self.subTest(event_type=type(untrusted_events).__name__):
                result = _safe_last_observer_marker(untrusted_events)
                self.assertEqual(result, "unavailable")
                self.assertNotIn(canary, result)

    def test_safe_target_probe_failure_marker_projection(self):
        self.assertEqual(
            _safe_target_probe_failure_marker(
                CommandResult(
                    ("python3",),
                    1,
                    "agent00x:test-failure:sqlite-range-status\n",
                    "synthetic private stderr",
                )
            ),
            "target-test-failure:sqlite-range-status",
        )
        canary = "synthetic-private-value-EXP715"
        untrusted_results = (
            CommandResult(("python3",), 0, "agent00x:test-failure:valid-row", ""),
            CommandResult(("python3",), True, "agent00x:test-failure:valid-row", ""),
            CommandResult(("python3",), 1, f"agent00x:test-failure:{canary}", ""),
            CommandResult(
                ("python3",),
                1,
                "agent00x:test-failure:valid-row\n" + canary,
                "",
            ),
            CommandResult(("python3",), 1, "x" * 4097, ""),
            object(),
        )
        for untrusted in untrusted_results:
            with self.subTest(result_type=type(untrusted).__name__):
                marker = _safe_target_probe_failure_marker(untrusted)
                self.assertEqual(marker, "unavailable")
                self.assertNotIn(canary, marker)

    def test_probe_diagnostic_backend_captures_only_the_safe_marker(self):
        canary = "synthetic-private-value-EXP715-backend"

        class Session:
            def run(self, argv, timeout_seconds=30):
                return CommandResult(
                    tuple(argv),
                    1,
                    "agent00x:test-failure:malformed-no-write\n",
                    canary,
                )

            def close(self):
                return None

        class Backend:
            def create(self, snapshot, allowed_commands):
                return Session()

        evidence = {}
        session = _ProbeDiagnosticBackend(Backend(), evidence).create(
            Path("/synthetic/snapshot"), {"python3"}
        )
        result = session.run(("python3", "-c", "pass"))
        self.assertEqual(
            evidence,
            {"target_probe_failure_marker": "target-test-failure:malformed-no-write"},
        )
        self.assertNotIn(canary, repr(evidence))
        self.assertEqual(result.stderr, canary)

    def test_remote_claim_revalidation_accepts_docker_copy_with_executable_file(self):
        raw_files = (
            ("README.md", "100644", b"synthetic pinned readme\n"),
            ("scripts/probe.sh", "100755", b"#!/bin/sh\nexit 0\n"),
        )
        blobs = tuple(
            GitHubBlobClaim(
                path=path,
                mode=mode,
                sha=hashlib.sha1(
                    b"blob " + str(len(content)).encode("ascii") + b"\0" + content
                ).hexdigest(),
                size=len(content),
                content=content,
                content_digest=sha256_bytes(content),
            )
            for path, mode, content in raw_files
        )
        claim_digest = sha256_digest(
            {
                "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
                "files": [
                    {
                        "path": path,
                        "content_digest": sha256_bytes(content),
                        "mode": mode,
                    }
                    for path, mode, content in raw_files
                ],
            }
        )
        snapshot = GitHubSnapshotContents(
            claim=GitHubSnapshotClaim(
                owner="FixtureOwner",
                repository="mode-fixture",
                commit_oid="c" * 40,
                tree_oid="d" * 40,
                content_digest=claim_digest,
            ),
            files=blobs,
        )
        readme = raw_files[0][2].decode("utf-8")
        proposed_readme = readme + "\nsynthetic update\n"

        class FixedBoundWorker:
            def __init__(self):
                self.calls = 0

            def propose(self, _task):
                self.calls += 1
                return WorkerProposal(changes=(("README.md", proposed_readme),))

        worker = FixedBoundWorker()

        class BoundAcceptingVerifier:
            def __init__(self):
                self.calls = 0

            def verify(self, prepared):
                self.calls += 1
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="synthetic-mode-claim-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        verifier = BoundAcceptingVerifier()

        class RecordingDockerSandboxBackend(DockerSandboxBackend):
            def __init__(self):
                super().__init__("synthetic-local-image")
                self.sessions = []
                self.initial_workspace_digests = []
                self.initial_snapshot_files = []

            def create(self, snapshot_path, allowed_commands):
                session = super().create(snapshot_path, allowed_commands)
                self.sessions.append(session)
                self.initial_workspace_digests.append(
                    executor_module.compute_snapshot_tree_digest(session.workspace)
                )
                self.initial_snapshot_files.append(
                    tuple(
                        (
                            path.relative_to(session.snapshot).as_posix(),
                            "100755" if path.stat().st_mode & 0o111 else "100644",
                            path.read_bytes(),
                        )
                        for path in sorted(session.snapshot.rglob("*"))
                        if path.is_file() and not path.is_symlink()
                    )
                )
                return session

        backend = RecordingDockerSandboxBackend()
        backend._assert_image_available = lambda: None
        docker_commands = []

        def fake_docker_run(command, **_kwargs):
            docker_commands.append(tuple(command))
            stdout = "synthetic-container-id\n" if command[1:2] == ["run"] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        python = sys.executable
        with patch("app_contracts.sandbox.subprocess.run", side_effect=fake_docker_run):
            with materialize_github_snapshot(snapshot) as lease:
                result = run_local_execution(
                    ExecutionRequest(
                        process_id="process-synthetic-mode-claim",
                        task_id="task-synthetic-mode-claim",
                        repository_id="FixtureOwner/mode-fixture",
                        base_commit=snapshot.claim.commit_oid,
                        snapshot_path=lease.path,
                        allowed_commands=frozenset({Path(python).name}),
                        declared_change_paths=("README.md",),
                        test_command=(python, "-c", "assert True"),
                        task_instruction="Make a harmless synthetic README update",
                        context_files=(("README.md", readme),),
                        remote_snapshot=snapshot,
                        remote_workspace=lease,
                    ),
                    worker,
                    verifier=verifier,
                    sandbox_backend=backend,
                )

        self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
        self.assertEqual(worker.calls, 1)
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(len(backend.sessions), 2)
        self.assertEqual(backend.initial_workspace_digests, [claim_digest, claim_digest])
        self.assertEqual(
            len([command for command in docker_commands if len(command) > 1 and command[1] == "run"]),
            2,
        )
        for index, session in enumerate(backend.sessions):
            copied_files = backend.initial_snapshot_files[index]
            self.assertEqual(copied_files, raw_files)
            self.assertEqual(executor_module.verifier_snapshot_tree_digest(copied_files), claim_digest)
            self.assertTrue(session._closed)
            self.assertFalse(session._root.exists())

    def test_remote_composition_requires_persists_previews_and_mock_approves_exact_digest(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# synthetic remote composition fixture\n"
        channel = FixedChatCompletionsChannel(proposed_content)
        worker = DeepSeekProposalWorker(channel=channel)
        nonce = "4" * 64
        verifier = SubprocessVerifier(
            VerifierProcessConfig(
                executable=sys.executable,
                argv=(
                    sys.executable,
                    "-m",
                    "app_contracts.verifier_container_entrypoint",
                    "--invocation-nonce=" + nonce,
                ),
                timeout_seconds=30,
                max_stdout_bytes=65_536,
                max_stderr_bytes=4_096,
            ),
            environ={"PYTHONPATH": str(ROOT / "src")},
        )
        python = sys.executable
        test_command = (
            python,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )
        with tempfile.TemporaryDirectory(prefix="remote-composition-stage-") as directory:
            stage_database = Path(directory) / "stages.sqlite3"
            observer_database = Path(directory) / "observations.sqlite3"
            with (
                SQLiteStagedArtifactStore(stage_database) as stage_store,
                SQLiteObservationStore(observer_database) as observer_store,
            ):
                result = run_remote_snapshot_execution(
                    snapshot,
                    process_id="process-remote-composition-001",
                    task_id="task-remote-composition-001",
                    task_instruction="Add a harmless fixture-only comment to calculator.py",
                    declared_change_paths=("calculator.py",),
                    allowed_commands=frozenset({Path(python).name}),
                    test_command=test_command,
                    worker=worker,
                    verifier=verifier,
                    sandbox_backend=LocalProcessSandboxBackend(),
                    context_files=(("calculator.py", base_content),),
                    stage_sink=stage_store,
                    observation_store=observer_store,
                )
                self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
                self.assertIsNotNone(result.staged_change_digest)
                artifact = stage_store.load(result.staged_change_digest)
                observer_events = observer_store.events()

            report = report_from_sqlite(observer_database)
            self.assertEqual(report["snapshot"]["event_count"], 21)
            self.assertEqual(report["snapshot"]["checkpoint_count"], 10)
            self.assertEqual(len(report["facts"]), 21)
            self.assertEqual(
                [event["sequence"] for event in report["facts"]], list(range(21))
            )
            self.assertEqual(
                [
                    event.get("decision_or_tool")
                    for event in observer_events
                    if event["event_type"] == "tool_requested"
                ],
                [
                    "SandboxBackend.create.target-execution",
                    "ProposalWorker.propose",
                    "SandboxSession.run.target-tests",
                    "SandboxBackend.create.verifier-replay",
                    "SandboxSession.run.verifier-replay",
                    "SandboxSession.close.verifier-replay",
                    "IndependentVerifier.verify",
                    "StagedArtifactStore.save",
                    "StagedArtifactStore.load",
                    "SandboxSession.close.target-execution",
                ],
            )
            self.assertEqual(len({event["run_id"] for event in report["facts"]}), 1)
            self.assertEqual(
                report["facts"][3]["causal_event_ids"],
                [report["facts"][2]["event_id"]],
            )
            self.assertEqual(
                report["facts"][5]["causal_event_ids"],
                [report["facts"][4]["event_id"]],
            )
            self.assertEqual(
                report["facts"][7]["causal_event_ids"],
                [report["facts"][6]["event_id"]],
            )
            self.assertEqual(
                report["facts"][9]["causal_event_ids"],
                [report["facts"][8]["event_id"]],
            )
            self.assertEqual(
                report["facts"][11]["causal_event_ids"],
                [report["facts"][10]["event_id"]],
            )
            self.assertEqual(
                observer_events[5]["decision_or_tool"],
                "SandboxSession.run.target-tests",
            )
            self.assertEqual(
                observer_events[9]["decision_or_tool"],
                "SandboxSession.run.verifier-replay",
            )
            self.assertEqual(
                observer_events[13]["decision_or_tool"],
                "IndependentVerifier.verify",
            )
            self.assertEqual(
                observer_events[15]["decision_or_tool"],
                "StagedArtifactStore.save",
            )
            self.assertEqual(
                observer_events[17]["decision_or_tool"],
                "StagedArtifactStore.load",
            )
            self.assertEqual(report["checkpoints"][2]["event_cursor"], 4)
            self.assertEqual(report["checkpoints"][4]["event_cursor"], 8)
            self.assertEqual(report["checkpoints"][6]["event_cursor"], 12)
            self.assertEqual(report["checkpoints"][8]["event_cursor"], 16)

            self.assertEqual(channel.calls, 1)
            self.assertEqual(artifact.staged_change_digest, result.staged_change_digest)
            preview = json.loads(render_stage_preview(artifact))
            self.assertEqual(
                preview["stage"]["staged_change_digest"], result.staged_change_digest
            )
            self.assertEqual(preview["approval"], "not_created")
            self.assertEqual(preview["publication"], "not_attempted")

            receipt = run_local_mock_publication(
                artifact,
                result.staged_change_digest,
                "agent/remote-composition-mock",
                "master",
                now=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(receipt.staged_change_digest, result.staged_change_digest)
            self.assertEqual(receipt.repository_id, "FixtureOwner/calculator-fixture")

    def test_observed_stage_readback_mismatch_is_rejected_by_executor(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# mismatched readback fixture\n"
        python = sys.executable
        observer_store = ObservationStore()

        class FixedWorker:
            def propose(self, _worker_input):
                return WorkerProposal((("calculator.py", proposed_content),))

        class AcceptingVerifier:
            def verify(self, prepared):
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="synthetic-mismatched-stage-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        class MismatchingStageSink:
            def save(self, artifact):
                return artifact

            def load(self, _digest):
                return object()

        result = run_remote_snapshot_execution(
            snapshot,
            process_id="process-stage-readback-check",
            task_id="task-stage-readback-check",
            task_instruction="Add a harmless fixture-only comment to calculator.py",
            declared_change_paths=("calculator.py",),
            allowed_commands=frozenset({Path(python).name}),
            test_command=(python, "-c", "pass"),
            worker=FixedWorker(),
            verifier=AcceptingVerifier(),
            sandbox_backend=LocalProcessSandboxBackend(),
            context_files=(("calculator.py", base_content),),
            stage_sink=MismatchingStageSink(),
            observation_store=observer_store,
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failure_code, "stage-persistence-failed")
        events = observer_store.events()
        stage_load = next(
            event for event in events
            if event.get("decision_or_tool") == "StagedArtifactStore.load"
            and event["event_type"] == "tool_requested"
        )
        self.assertEqual(stage_load["event_type"], "tool_requested")
        self.assertEqual(
            next(
                event for event in events
                if event.get("invocation_id") == stage_load["invocation_id"]
                and event["event_type"] == "tool_completed"
            )["event_type"],
            "tool_completed",
        )
        self.assertNotIn("mismatched readback fixture", repr(events))

    def test_pinned_operator_cli_fails_closed_before_approval_without_signed_verifier_proof(self):
        self._run_pinned_operator_cli_to_signed_mock_receipt_same_observer_run(
            use_docker=False
        )

    def test_synthetic_rest_snapshot_fails_closed_before_approval_without_signed_verifier_proof(self):
        self._run_pinned_operator_cli_to_signed_mock_receipt_same_observer_run(
            use_docker=False,
            synthetic_rest_snapshot=True,
        )

    def test_synthetic_rest_snapshot_reaches_enrolled_mock_receipt_with_signed_verifier_proof(self):
        self._run_pinned_operator_cli_to_signed_mock_receipt_same_observer_run(
            use_docker=False,
            synthetic_rest_snapshot=True,
            signed_verifier_attestation=True,
        )

    def test_synthetic_codeload_snapshot_reaches_enrolled_mock_receipt_with_signed_verifier_proof(self):
        self._run_pinned_operator_cli_to_signed_mock_receipt_same_observer_run(
            use_docker=False,
            synthetic_codeload_snapshot=True,
            signed_verifier_attestation=True,
        )

    def test_public_snapshot_success_evidence_is_opt_in_bounded_and_content_free(self):
        _snapshot, file_contents = make_full_snapshot()
        snapshot_metadata = {
            "commit_oid": PINNED_COMMIT,
            "tree_oid": PINNED_TREE,
            "content_digest": PINNED_CONTENT_DIGEST,
            "file_count": PINNED_FILE_COUNT,
        }
        staged_digest = "sha256:" + "c" * 64
        receipt = {
            "status": "mock_published",
            "staged_change_digest": staged_digest,
            "identity_authenticated": False,
            "external_write": False,
            "observer_completeness": "partial",
        }
        request_counts = {
            "readiness_gets": 1,
            "commit_gets": 1,
            "tree_gets": 1,
            "blob_gets": 23,
            "raw_commit_fetches": 1,
            "runtime_invocations": 1,
        }
        quiet = io.StringIO()
        _emit_public_snapshot_evidence(
            quiet,
            enabled=False,
            snapshot_metadata=snapshot_metadata,
            staged_change_digest=staged_digest,
            observer_run_id="run-public-evidence-test-001",
            request_counts=request_counts,
            receipt=receipt,
        )
        self.assertEqual(quiet.getvalue(), "")

        output = io.StringIO()
        _emit_public_snapshot_evidence(
            output,
            enabled=True,
            snapshot_metadata=snapshot_metadata,
            staged_change_digest=staged_digest,
            observer_run_id="run-public-evidence-test-001",
            request_counts=request_counts,
            receipt=receipt,
        )
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(_PUBLIC_SNAPSHOT_EVIDENCE_PREFIX))
        record = json.loads(lines[0][len(_PUBLIC_SNAPSHOT_EVIDENCE_PREFIX) :])
        self.assertEqual(record["schema"], "public-snapshot-observer-mock-evidence/v1")
        self.assertEqual(record["snapshot"]["commit_oid"], PINNED_COMMIT)
        self.assertEqual(record["snapshot"]["tree_oid"], PINNED_TREE)
        self.assertEqual(record["snapshot"]["content_digest"], PINNED_CONTENT_DIGEST)
        self.assertEqual(record["snapshot"]["file_count"], PINNED_FILE_COUNT)
        self.assertEqual(record["staged_change_digest"], staged_digest)
        self.assertEqual(record["observer_run_id"], "run-public-evidence-test-001")
        self.assertEqual(record["request_counts"], request_counts)
        self.assertEqual(record["receipt"], receipt)
        self.assertNotIn(file_contents, output.getvalue())

        failed_output = io.StringIO()
        with self.assertRaisesRegex(ValueError, "evidence is invalid"):
            _emit_public_snapshot_evidence(
                failed_output,
                enabled=True,
                snapshot_metadata=snapshot_metadata,
                staged_change_digest=staged_digest,
                observer_run_id="bad run id",
                request_counts=request_counts,
                receipt=receipt,
            )
        self.assertEqual(failed_output.getvalue(), "")

        over_limit_output = io.StringIO()
        over_limit_counts = dict(request_counts, blob_gets=24)
        with self.assertRaisesRegex(ValueError, "evidence is invalid"):
            _emit_public_snapshot_evidence(
                over_limit_output,
                enabled=True,
                snapshot_metadata=snapshot_metadata,
                staged_change_digest=staged_digest,
                observer_run_id="run-public-evidence-test-001",
                request_counts=over_limit_counts,
                receipt=receipt,
            )
        self.assertEqual(over_limit_output.getvalue(), "")

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1"
        and os.environ.get("AGENT00X_VERIFIER_IMAGE_ID") == VERIFIER_RUNTIME_IMAGE_ID
        and os.environ.get("AGENT00X_VERIFIER_CODE_DIGEST")
        == VERIFIER_RUNTIME_CODE_DIGEST
        and os.environ.get("AGENT00X_DOCKER_EXECUTABLE") == "/usr/local/bin/docker",
        "exact pinned Docker composition is opt-in",
    )
    def test_pinned_operator_cli_to_signed_mock_receipt_same_observer_run_docker(self):
        self._run_pinned_operator_cli_to_signed_mock_receipt_same_observer_run(
            use_docker=True,
            signed_verifier_attestation=True,
        )

    @unittest.skipUnless(
        os.environ.get("RUN_PUBLIC_READONLY_SNAPSHOT_TESTS") == "1"
        and os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1"
        and os.environ.get("AGENT00X_VERIFIER_IMAGE_ID") == VERIFIER_RUNTIME_IMAGE_ID
        and os.environ.get("AGENT00X_VERIFIER_CODE_DIGEST")
        == VERIFIER_RUNTIME_CODE_DIGEST
        and os.environ.get("AGENT00X_DOCKER_EXECUTABLE") == "/usr/local/bin/docker",
        "exact public snapshot and pinned Docker composition are opt-in",
    )
    def test_pinned_public_snapshot_to_enrolled_mock_receipt_docker(self):
        from urllib.parse import urlsplit

        class CountedPublicTransport:
            def __init__(self):
                self.inner = GitHubAnonymousSnapshotTransport(timeout_seconds=15)
                self.readiness_calls = 0
                self.readiness_marker = "unavailable"
                self.reset_marker = "reset-unavailable"
                self.request_kinds = []

            def read_rate_limit(self):
                self.readiness_calls += 1
                if self.readiness_calls != 1:
                    raise AssertionError("readiness request limit exceeded")
                evidence = self.inner.read_rate_limit()
                self.readiness_marker = _safe_readiness_marker(evidence)
                self.reset_marker = _safe_rate_reset_marker(evidence)
                if (
                    evidence.status != 200
                    or evidence.remaining is None
                    or evidence.remaining < 35
                ):
                    raise AssertionError("readiness threshold not met")
                return evidence

            def __call__(self, method, url, headers, max_bytes, *, allow_redirects):
                parsed = urlsplit(url)
                if parsed.hostname != "api.github.com" or parsed.scheme != "https":
                    raise AssertionError("public host restriction violated")
                repository_prefix = (
                    f"/repos/{PINNED_OWNER}/{PINNED_REPOSITORY}/"
                )
                if parsed.path == repository_prefix + "commits/" + PINNED_COMMIT:
                    kind = "commit"
                elif parsed.path == repository_prefix + "git/trees/" + PINNED_TREE:
                    kind = "tree"
                elif (
                    parsed.path.startswith(repository_prefix + "git/blobs/")
                    and len(parsed.path.rsplit("/", 1)[-1]) == 40
                    and all(
                        char in "0123456789abcdef"
                        for char in parsed.path.rsplit("/", 1)[-1]
                    )
                ):
                    kind = "blob"
                else:
                    raise AssertionError("public endpoint restriction violated")
                if len(self.request_kinds) >= 25:
                    raise AssertionError("public GET limit exceeded")
                self.request_kinds.append(kind)
                result = self.inner(
                    method,
                    url,
                    headers,
                    max_bytes,
                    allow_redirects=allow_redirects,
                )
                return result

        class CountedCommitSource:
            def __init__(self):
                self.calls = 0
                self.inner = GitHubRawCommitObjectSource(
                    "/usr/bin/git", timeout_seconds=15
                )

            def __call__(self, claim):
                self.calls += 1
                if self.calls != 1:
                    raise AssertionError("raw commit fetch limit exceeded")
                return self.inner(claim)

        transport = CountedPublicTransport()
        commit_source = CountedCommitSource()
        runtime_invocations = []
        self._run_pinned_operator_cli_to_signed_mock_receipt_same_observer_run(
            use_docker=True,
            signed_verifier_attestation=True,
            public_transport=transport,
            public_commit_source=commit_source,
            runtime_invocations=runtime_invocations,
        )

    def _run_pinned_operator_cli_to_signed_mock_receipt_same_observer_run(
        self,
        *,
        use_docker: bool,
        public_transport: object | None = None,
        public_commit_source: object | None = None,
        synthetic_rest_snapshot: bool = False,
        synthetic_codeload_snapshot: bool = False,
        signed_verifier_attestation: bool = False,
        runtime_invocations: list | None = None,
    ):
        runtime_invocation_counter = (
            [] if runtime_invocations is None else runtime_invocations
        )
        public_mode = public_transport is not None
        synthetic_snapshot_transport = None
        synthetic_snapshot_commit_source = None
        synthetic_snapshot_paths = None
        if not public_mode:
            base_snapshot, base_content = make_full_snapshot()
            if synthetic_rest_snapshot:
                (
                    snapshot,
                    synthetic_snapshot_transport,
                    synthetic_snapshot_commit_source,
                    synthetic_snapshot_paths,
                ) = _synthetic_rest_snapshot_source(
                    base_content.encode("utf-8"),
                    base_snapshot.claim.owner,
                    base_snapshot.claim.repository,
                )
            elif synthetic_codeload_snapshot:
                snapshot = GitHubSnapshotContents(
                    claim=replace(
                        base_snapshot.claim,
                        evidence_origin="github_codeload_archive",
                    ),
                    files=tuple(
                        replace(blob, evidence_origin="github_codeload_archive")
                        for blob in base_snapshot.files
                    ),
                )
            else:
                snapshot = GitHubSnapshotContents(
                    claim=base_snapshot.claim,
                    files=base_snapshot.files,
                    verified_commit_object=GitCommitObject(
                        base_snapshot.claim.commit_oid,
                        base_snapshot.claim.tree_oid,
                    ),
                )
            proposed_content = base_content + "\n# synthetic end-to-end candidate\n"
        else:
            snapshot = None
            proposed_content = None
        python = sys.executable
        profile_values = (
            {
                "REMOTE_REPOSITORY_OWNER": PINNED_OWNER,
                "REMOTE_REPOSITORY_NAME": PINNED_REPOSITORY,
                "REMOTE_REPOSITORY_COMMIT": PINNED_COMMIT,
                "REMOTE_REPOSITORY_TREE": PINNED_TREE,
                "REMOTE_REPOSITORY_CONTENT_DIGEST": PINNED_CONTENT_DIGEST,
                "REMOTE_REPOSITORY_FILE_COUNT": PINNED_FILE_COUNT,
            }
            if public_mode
            else {
                "REMOTE_REPOSITORY_OWNER": snapshot.claim.owner,
                "REMOTE_REPOSITORY_NAME": snapshot.claim.repository,
                "REMOTE_REPOSITORY_COMMIT": snapshot.claim.commit_oid,
                "REMOTE_REPOSITORY_TREE": snapshot.claim.tree_oid,
                "REMOTE_REPOSITORY_CONTENT_DIGEST": snapshot.claim.content_digest,
                "REMOTE_REPOSITORY_FILE_COUNT": len(snapshot.files),
            }
        )
        source_repository_id = (
            f"{PINNED_OWNER}/{PINNED_REPOSITORY}"
            if public_mode
            else f"{snapshot.claim.owner}/{snapshot.claim.repository}"
        )
        binding = RepositoryTargetBinding(
            source_repository_id,
            "github-installation/456/repository/1001",
        )
        request_environment = {
            "AGENT_GITHUB_TEST_REPOSITORY": binding.source_repository_id,
            "AGENT_GITHUB_INSTALLATION_ID": "456",
            "AGENT_GITHUB_REPOSITORY_ID": "1001",
        }
        synthetic_credential_canary = "SYNTHETIC-API-CREDENTIAL-CANARY-EXP675"
        credential_reads = []
        worker_candidates = []

        class SyntheticCredentialChannel:
            def __init__(self, credential_source):
                self.credential_source = credential_source

            def consume_for_fake_worker(self):
                value = self.credential_source()
                credential_reads.append("read")
                return value

        class FixedWorker:
            def __init__(self, channel=None):
                self.channel = channel

            def propose(self, worker_input):
                if self.channel is not None:
                    self.channel.consume_for_fake_worker()
                if not public_mode:
                    context = dict(worker_input.context_files)
                    if context.get("calculator.py") != base_content:
                        raise AssertionError(
                            "synthetic Worker context differs from fetched snapshot"
                        )
                    return WorkerProposal((("calculator.py", proposed_content),))
                context = dict(worker_input.context_files)
                source = context.get("backend/routes.py")
                fetched_snapshot = runtime_result.get("snapshot")
                if type(fetched_snapshot) is not GitHubSnapshotContents:
                    raise AssertionError("synthetic Worker ran before snapshot fetch")
                expected_source = next(
                    blob.content.decode("utf-8", errors="strict")
                    for blob in fetched_snapshot.files
                    if blob.path == "backend/routes.py"
                )
                if source != expected_source:
                    raise AssertionError("synthetic Worker context differs from pinned bytes")
                candidate = _strict_signed_range_routes_candidate(source)
                worker_candidates.append(candidate)
                return WorkerProposal((("backend/routes.py", candidate),))

        verifier_authority_key = Ed25519PrivateKey.generate()
        verifier_authority_key_id = "synthetic-authority-exp739"
        verifier_authority_public_key = verifier_authority_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

        class AcceptingVerifier:
            def __init__(self, delegate=None):
                self.delegate = delegate

            def verify(self, prepared):
                if signed_verifier_attestation:
                    from app_contracts.signed_verifier_client import (
                        SignedVerifierClient,
                        SignedVerifierHTTPSTransport,
                    )
                    from app_contracts.signed_verifier_service import (
                        VerifierProfile,
                        handle_signed_verifier_invocation,
                    )
                    from app_contracts.verifier_host_trust_decision import (
                        build_signed_verifier_host_trust_decision,
                    )
                    from app_contracts.verifier_trust_enrollment import (
                        build_signed_verifier_trust_enrollment,
                    )

                    signing_key = Ed25519PrivateKey.generate()
                    profile = VerifierProfile(
                        repository_id=prepared.repository_id,
                        base_commit=prepared.base_commit,
                        snapshot_tree_digest=prepared.snapshot_tree_digest,
                        snapshot_file_count=len(prepared.snapshot_files),
                        allowed_change_paths=prepared.declared_change_paths,
                        test_command=prepared.test_command,
                        test_timeout_seconds=prepared.test_timeout_seconds,
                        verifier_image_id=VERIFIER_RUNTIME_IMAGE_ID,
                        verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
                        signer_key_id="synthetic-verifier-exp739",
                    )
                    runtime_result["verifier_profile_digest"] = profile.profile_digest
                    runtime_result["expected_verifier_id"] = profile.expected_verifier_id

                    class SyntheticPassVerifier:
                        def verify(self, verifier_input):
                            if self.delegate is not None:
                                return self.delegate.verify(verifier_input)
                            return VerifierResult(
                                process_id=verifier_input.process_id,
                                base_commit=verifier_input.base_commit,
                                snapshot_tree_digest=verifier_input.snapshot_tree_digest,
                                replay_result_digest=verifier_input.replay_result_digest,
                                verifier_id=profile.expected_verifier_id,
                                patch_digest=verifier_input.patch_digest,
                                evidence_digest=verifier_input.evidence_digest,
                                verification_digest=verifier_input.verification_digest,
                                verified_contents_digest=verifier_input.verified_contents_digest,
                                verdict=VerifierVerdict.PASS,
                                evidence_origin="local_test",
                            )

                    SyntheticPassVerifier.delegate = self.delegate

                    endpoint_url = "https://verifier.example.test/v1/verify"
                    worker_host_id = "synthetic-worker-host-exp739"
                    verifier_host_id = "synthetic-verifier-host-exp739"
                    issued_at = datetime.now(timezone.utc).replace(microsecond=0)
                    separation_digest = "sha256:" + "7" * 64
                    enrollment_bytes = build_signed_verifier_trust_enrollment(
                        enrollment_id="synthetic-enrollment-exp739",
                        authority_key_id=verifier_authority_key_id,
                        endpoint_url=endpoint_url,
                        verifier_id=profile.expected_verifier_id,
                        verifier_profile_digest=profile.profile_digest,
                        verifier_key_id=profile.signer_key_id,
                        verifier_public_key=signing_key.public_key().public_bytes(
                            serialization.Encoding.Raw, serialization.PublicFormat.Raw
                        ),
                        worker_host_id=worker_host_id,
                        verifier_host_id=verifier_host_id,
                        host_separation_evidence_digest=separation_digest,
                        signing_key=verifier_authority_key,
                        issued_at=issued_at,
                        expires_at=issued_at + timedelta(hours=1),
                    )
                    decision_bytes = build_signed_verifier_host_trust_decision(
                        decision_id="synthetic-host-review-exp739",
                        authority_key_id=verifier_authority_key_id,
                        enrollment_digest=sha256_bytes(enrollment_bytes),
                        endpoint_url=endpoint_url,
                        verifier_id=profile.expected_verifier_id,
                        verifier_profile_digest=profile.profile_digest,
                        verifier_key_id=profile.signer_key_id,
                        worker_host_id=worker_host_id,
                        verifier_host_id=verifier_host_id,
                        host_separation_evidence_digest=separation_digest,
                        signing_key=verifier_authority_key,
                        issued_at=issued_at,
                        expires_at=issued_at + timedelta(minutes=30),
                    )

                    class FakeVerifierResponse:
                        status = 200

                        def __init__(self, body):
                            self.body = body

                        def getheader(self, name):
                            return "application/json" if name == "Content-Type" else None

                        def read(self, limit):
                            return self.body[:limit]

                        def close(self):
                            return None

                    class FakeVerifierConnection:
                        def configure(self, _host, *, port, timeout, context):
                            self.port = port
                            self.timeout = timeout
                            self.context = context
                            return self

                        def request(self, method, path, *, body, headers):
                            if (
                                (method, path) != ("POST", "/v1/verify")
                                or headers.get("Authorization") is not None
                            ):
                                raise AssertionError("synthetic verifier route mismatch")
                            response_body = handle_signed_verifier_invocation(
                                body,
                                profile=profile,
                                verifier=SyntheticPassVerifier(),
                                signing_key=signing_key,
                                issued_at=issued_at,
                            )
                            self.response = FakeVerifierResponse(response_body)

                        def getresponse(self):
                            return self.response

                        def close(self):
                            return None

                    verifier_connection = FakeVerifierConnection()
                    verifier_transport = SignedVerifierHTTPSTransport(
                        endpoint_url,
                        connection_factory=lambda host, *, port, timeout, context: verifier_connection.configure(
                            host, port=port, timeout=timeout, context=context
                        ),
                    )

                    client = SignedVerifierClient.from_trust_enrollment(
                        profile,
                        verifier_transport,
                        enrollment_bytes,
                        trusted_authority_keys={
                            verifier_authority_key_id: verifier_authority_public_key
                        },
                        expected_endpoint_url=endpoint_url,
                        expected_worker_host_id=worker_host_id,
                        expected_verifier_host_id=verifier_host_id,
                        host_trust_decision_bytes=decision_bytes,
                        now=issued_at,
                    )
                    return client.verify(prepared)
                return VerifierResult(
                    process_id=prepared.process_id,
                    base_commit=prepared.base_commit,
                    snapshot_tree_digest=prepared.snapshot_tree_digest,
                    replay_result_digest=prepared.replay_result_digest,
                    verifier_id="synthetic-exp648-verifier",
                    patch_digest=prepared.patch_digest,
                    evidence_digest=prepared.evidence_digest,
                    verification_digest=prepared.verification_digest,
                    verified_contents_digest=prepared.verified_contents_digest,
                    verdict=VerifierVerdict.PASS,
                )

        now = datetime.now(timezone.utc).replace(microsecond=0)
        branch = (
            "agent/exp694-pinned-snapshot"
            if public_mode
            else "agent/exp648-vertical-slice"
        )
        policy_version = (
            "synthetic-exp694-policy-v1"
            if public_mode
            else "synthetic-exp648-policy-v1"
        )
        with tempfile.TemporaryDirectory(prefix="exp648-vertical-slice-") as directory:
            root = Path(directory)
            stage_database = root / "stage.sqlite3"
            observer_database = root / "observer.sqlite3"
            request_path = root / "approval-request.json"
            signed_path = root / "signed-approval.json"
            profile_path = root / "trust-profile.json"
            enrollment_path = root / "approver-enrollment.json"
            authority_key_set_path = root / "authority-key-set.json"
            verifier_authority_key_set_path = root / "verifier-authority-key-set.json"
            verifier_authority_key_set = {
                "schema": "control-plane-authority-key-set/v1",
                "keys": {
                    verifier_authority_key_id: verifier_authority_public_key.hex()
                },
            }
            verifier_authority_key_set_path.write_text(
                json.dumps(
                    verifier_authority_key_set,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            verifier_authority_key_set_digest = sha256_bytes(
                verifier_authority_key_set_path.read_bytes()
            )
            readiness = GitHubRateLimitEvidence(
                status=200,
                remaining=50,
                reset_unix=int(time.time()) + 3600,
                observed_monotonic=time.monotonic(),
            )

            class ReadinessTransport:
                calls = 0

                def read_rate_limit(self):
                    self.calls += 1
                    if public_mode:
                        return public_transport.read_rate_limit()
                    return readiness

            readiness_transport = ReadinessTransport()
            fake_response = {"status": 200, "body": b"synthetic snapshot metadata"}
            fake_transport = (
                synthetic_snapshot_transport
                if synthetic_rest_snapshot
                else lambda *_args, **_kwargs: fake_response
            )
            fake_commit_source = (
                synthetic_snapshot_commit_source
                if synthetic_rest_snapshot
                else lambda _claim: b"synthetic raw commit bytes"
            )
            synthetic_archive_bytes = b"bounded synthetic codeload archive fixture"

            def fake_archive_transport(owner, repository, commit_oid):
                if (owner, repository, commit_oid) != (
                    snapshot.claim.owner,
                    snapshot.claim.repository,
                    snapshot.claim.commit_oid,
                ):
                    raise AssertionError("synthetic codeload request is not pinned")
                return synthetic_archive_bytes

            def fake_archive_reader(request, transport):
                self.assertEqual(request.owner, snapshot.claim.owner)
                self.assertEqual(request.repository, snapshot.claim.repository)
                self.assertEqual(request.commit_oid, snapshot.claim.commit_oid)
                self.assertEqual(request.tree_oid, snapshot.claim.tree_oid)
                self.assertEqual(request.content_digest, snapshot.claim.content_digest)
                self.assertEqual(request.file_count, len(snapshot.files))
                self.assertEqual(
                    transport(request.owner, request.repository, request.commit_oid),
                    synthetic_archive_bytes,
                )
                runtime_result["snapshot"] = snapshot
                return snapshot
            runtime_result = {}

            def snapshot_reader(request, transport, *, commit_object_source):
                if public_mode or synthetic_rest_snapshot:
                    fetched = read_github_snapshot_contents(
                        request,
                        transport,
                        commit_object_source=commit_object_source,
                    )
                    runtime_result["snapshot"] = fetched
                    return fetched
                response = transport(
                    "GET",
                    "https://api.github.com/repos/"
                    + request.owner
                    + "/"
                    + request.repository
                    + "/commits/"
                    + request.commit_oid,
                    {
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2026-03-10",
                    },
                    1_000_000,
                    allow_redirects=False,
                )
                self.assertIs(response, fake_response)
                self.assertEqual(commit_object_source(snapshot.claim), b"synthetic raw commit bytes")
                return snapshot

            def fake_runtime(**kwargs):
                stage_path = kwargs["stage_database_path"]
                observer_store = kwargs["observation_store"]
                if use_docker:
                    docker_verifier = DockerContainerVerifier(
                        VerifierContainerConfig(
                            os.environ["AGENT00X_DOCKER_EXECUTABLE"],
                            os.environ["AGENT00X_VERIFIER_IMAGE_ID"],
                            os.environ["AGENT00X_VERIFIER_CODE_DIGEST"],
                            timeout_seconds=60,
                            max_stdout_bytes=65_536,
                            max_stderr_bytes=16_384,
                        )
                    )
                    verifier = (
                        AcceptingVerifier(docker_verifier)
                        if signed_verifier_attestation
                        else docker_verifier
                    )
                    sandbox_backend = DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID)
                    if public_mode:
                        sandbox_backend = _ProbeDiagnosticBackend(
                            sandbox_backend, runtime_result
                        )
                    test_command = (
                        PINNED_HTTP_DB_TEST_COMMAND
                        if public_mode
                        else (
                            "python3",
                            "-c",
                            "from calculator import add; assert add(20, 22) == 42",
                        )
                    )
                    allowed_commands = frozenset({"python3"})
                else:
                    verifier = AcceptingVerifier()
                    sandbox_backend = LocalProcessSandboxBackend()
                    test_command = (
                        python,
                        "-c",
                        "from calculator import add; assert add(20, 22) == 42",
                    )
                    allowed_commands = frozenset({Path(python).name})
                with SQLiteStagedArtifactStore(stage_path) as stage_store:
                    profile = worker_cli.RemoteSnapshotExecutionProfile(
                        process_id=kwargs["process_id"],
                        task_id=kwargs["task_id"],
                        task_instruction=(
                            "Require strict signed-64 integer inputs for level, correct, "
                            "wrong, total and time_ms; invalid values must return HTTP "
                            "422 before a database write, while a valid payload still "
                            "returns HTTP 200 and writes one row."
                            if public_mode
                            else "Add a harmless synthetic comment to calculator.py"
                        ),
                        declared_change_paths=(
                            ("backend/routes.py",)
                            if public_mode
                            else ("calculator.py",)
                        ),
                        allowed_commands=allowed_commands,
                        test_command=test_command,
                        worker=FixedWorker(),
                        verifier=verifier,
                        sandbox_backend=sandbox_backend,
                        stage_sink=stage_store,
                        stage_database_path=stage_path,
                        observation_store=observer_store,
                        snapshot_evidence_origin=(
                            "github_codeload_archive"
                            if synthetic_codeload_snapshot
                            else "github_rest_api_claim"
                        ),
                    )
                    with (
                        patch.multiple(worker_cli, **profile_values),
                        patch.object(
                            worker_cli,
                            "GitHubAnonymousSnapshotTransport",
                            return_value=(
                                public_transport if public_mode else fake_transport
                            ),
                        ),
                        patch.object(
                            worker_cli,
                            "GitHubRawCommitObjectSource",
                            return_value=(
                                public_commit_source if public_mode else fake_commit_source
                            ),
                        ),
                        patch.object(
                            worker_cli,
                            "read_github_snapshot_contents",
                            side_effect=snapshot_reader,
                        ),
                        patch.object(
                            worker_cli,
                            "GitHubCodeloadArchiveTransport",
                            return_value=fake_archive_transport,
                        ),
                        patch.object(
                            worker_cli,
                            "read_github_archive_snapshot_contents",
                            side_effect=fake_archive_reader,
                        ),
                    ):
                        try:
                            code = worker_cli.main(
                                ["--remote-snapshot-execute"],
                                stdout=kwargs["stdout"],
                                stderr=kwargs["stderr"],
                                remote_execution_profile=profile,
                                execution_permit=kwargs["execution_permit"],
                                execution_worker=kwargs["execution_worker"],
                            )
                        except Exception as exc:
                            runtime_result["exception_type"] = type(exc).__name__
                            raise
                runtime_result["code"] = code
                if code != 0:
                    getvalue = getattr(kwargs.get("stdout"), "getvalue", None)
                    runtime_result["failure_code"] = _safe_pinned_cli_failure_code(
                        getvalue() if callable(getvalue) else None
                    )
                    try:
                        failed_events = observer_store.events()
                        runtime_result["observer_marker"] = _safe_last_observer_marker(
                            failed_events
                        )
                    except Exception:
                        runtime_result["observer_marker"] = "unavailable"
                return code

            def safe_fake_runtime(**kwargs):
                runtime_invocation_counter.append("invoked")
                try:
                    return fake_runtime(**kwargs)
                except Exception as exc:
                    runtime_result["exception_type"] = type(exc).__name__
                    raise

            pinned_stdout, pinned_stderr = io.StringIO(), io.StringIO()
            authorization_profiles = dict(pinned_worker_cli.AUTHORIZATION_PROFILES)
            authorization_origins = dict(
                pinned_worker_cli.AUTHORIZATION_SNAPSHOT_ORIGINS
            )
            if synthetic_codeload_snapshot:
                authorization_origins["EXP-634"] = "github_codeload_archive"
            with (
                patch.object(pinned_worker_cli, "DeepSeekProposalWorker", FixedWorker),
                patch.object(
                    pinned_worker_cli,
                    "DeepSeekHTTPChannel",
                    SyntheticCredentialChannel,
                ),
                patch.object(
                    pinned_worker_cli,
                    "TerminalPromptCredentialSource",
                    lambda: lambda: synthetic_credential_canary,
                ),
                patch.object(
                    pinned_worker_cli,
                    "AUTHORIZATION_PROFILES",
                    authorization_profiles,
                ),
                patch.object(
                    pinned_worker_cli,
                    "AUTHORIZATION_SNAPSHOT_ORIGINS",
                    authorization_origins,
                ),
                patch.multiple(worker_cli, **profile_values),
            ):
                pinned_argv = [
                    str(stage_database),
                    "--observation-database",
                    str(observer_database),
                ]
                pinned_code = pinned_worker_cli.main(
                    pinned_argv,
                    input_fn=lambda _prompt: pinned_worker_cli.CONFIRMATION_PHRASE,
                    stdout=pinned_stdout,
                    stderr=pinned_stderr,
                    readiness_transport_factory=lambda: readiness_transport,
                    runtime_runner=safe_fake_runtime,
                    docker_which=lambda _name: "/synthetic/docker",
                    docker_inspect=lambda _path: None,
                )
            self.assertEqual(
                pinned_code,
                0,
                "pinned_code=failed; "
                f"runtime_code={runtime_result.get('code', 'unavailable')}; "
                f"runtime_failure_code={runtime_result.get('failure_code', 'none')}; "
                f"runtime_observer_marker={runtime_result.get('observer_marker', 'none')}; "
                f"public_readiness={getattr(public_transport, 'readiness_marker', 'fixture')}; "
                f"public_rate_reset={getattr(public_transport, 'reset_marker', 'fixture')}; "
                "target_probe_failure="
                f"{runtime_result.get('target_probe_failure_marker', 'unavailable')}; "
                "public_attempts="
                f"{_safe_public_attempt_counts(getattr(public_transport, 'readiness_calls', 0), len(getattr(public_transport, 'request_kinds', ())), getattr(public_commit_source, 'calls', 0), len(runtime_invocation_counter))}; "
                "runtime_exception_type="
                f"{runtime_result.get('exception_type', 'none')}; "
                f"runtime_invocations={len(runtime_invocation_counter)}",
            )
            self.assertEqual(runtime_result["code"], 0)
            self.assertEqual(credential_reads, ["read"])
            self.assertEqual(readiness_transport.calls, 1)
            if public_mode:
                snapshot = runtime_result.get("snapshot")
                self.assertIs(type(snapshot), GitHubSnapshotContents)
                self.assertEqual(snapshot.claim.evidence_origin, "github_rest_api_claim")
                self.assertEqual(snapshot.claim.owner, PINNED_OWNER)
                self.assertEqual(snapshot.claim.repository, PINNED_REPOSITORY)
                self.assertEqual(snapshot.claim.commit_oid, PINNED_COMMIT)
                self.assertEqual(snapshot.claim.tree_oid, PINNED_TREE)
                self.assertEqual(len(snapshot.files), PINNED_FILE_COUNT)
                self.assertEqual(snapshot.claim.content_digest, PINNED_CONTENT_DIGEST)
                self.assertEqual(
                    snapshot.verified_commit_object.commit_oid, PINNED_COMMIT
                )
                self.assertEqual(snapshot.verified_commit_object.tree_oid, PINNED_TREE)
                self.assertEqual(public_transport.readiness_calls, 1)
                self.assertEqual(public_transport.request_kinds.count("commit"), 1)
                self.assertEqual(public_transport.request_kinds.count("tree"), 1)
                self.assertEqual(
                    public_transport.request_kinds.count("blob"), PINNED_FILE_COUNT
                )
                self.assertEqual(
                    len(public_transport.request_kinds), 2 + PINNED_FILE_COUNT
                )
                self.assertEqual(public_commit_source.calls, 1)
                self.assertEqual(len(worker_candidates), 1)
                proposed_content = worker_candidates[0]
            elif synthetic_rest_snapshot:
                fetched_snapshot = runtime_result.get("snapshot")
                self.assertIs(type(fetched_snapshot), GitHubSnapshotContents)
                self.assertIsNot(fetched_snapshot, snapshot)
                self.assertEqual(fetched_snapshot.claim, snapshot.claim)
                self.assertEqual(fetched_snapshot.files, snapshot.files)
                self.assertEqual(
                    fetched_snapshot.verified_commit_object,
                    snapshot.verified_commit_object,
                )
                self.assertEqual(
                    synthetic_snapshot_transport.paths,
                    list(synthetic_snapshot_paths),
                )
                self.assertEqual(
                    synthetic_snapshot_commit_source.claims,
                    [(snapshot.claim.commit_oid, snapshot.claim.tree_oid)],
                )
            self.assertNotIn("synthetic", pinned_stderr.getvalue())
            pinned_records = [
                json.loads(line)
                for line in pinned_stdout.getvalue().splitlines()
                if line.startswith("{")
            ]
            worker_evidence = next(
                record
                for record in pinned_records
                if record.get("schema") == "remote-snapshot-execution-evidence/v1"
            )
            self.assertEqual(worker_evidence["status"], "verified")
            self.assertEqual(worker_evidence["approval"], "not_created")
            run_id = worker_evidence["observer"]["run_id"]
            with SQLiteObservationStore(observer_database) as observer_store:
                initial_events = observer_store.events()
            self.assertEqual(initial_events[-1]["sequence"], len(initial_events) - 1)
            self.assertEqual({event["run_id"] for event in initial_events}, {run_id})
            if synthetic_rest_snapshot:
                requested = [
                    event["decision_or_tool"]
                    for event in initial_events
                    if event.get("event_type") == "tool_requested"
                ]
                self.assertEqual(
                    requested[:5],
                    [
                        "GitHubReadiness.fetch",
                        "GitHubSnapshot.GET.commit",
                        "GitHubRawCommitObjectSource.read",
                        "GitHubSnapshot.GET.tree",
                        "GitHubSnapshot.GET.blob",
                    ],
                )
                self.assertIn(
                    "PinnedSnapshot.validate-fixed-pin",
                    [event.get("decision_or_tool") for event in initial_events],
                )
            if synthetic_codeload_snapshot:
                archive_events = [
                    event
                    for event in initial_events
                    if event.get("decision_or_tool")
                    == "GitHubCodeloadArchive.GET.archive"
                ]
                self.assertEqual(len(archive_events), 1)
                self.assertEqual(archive_events[0]["event_type"], "tool_requested")
                self.assertNotIn(synthetic_archive_bytes.decode(), repr(initial_events))
            execution = SimpleNamespace(
                status=ExecutionStatus.VERIFIED,
                staged_change_digest=worker_evidence["staged_change_digest"],
            )
            with SQLiteStagedArtifactStore(stage_database, read_only=True) as stage_store:
                artifact = stage_store.load(execution.staged_change_digest)
            self.assertEqual(artifact.staged_change_digest, execution.staged_change_digest)
            if use_docker:
                expected_verifier_id = (
                    f"docker-image:{os.environ['AGENT00X_VERIFIER_IMAGE_ID']}"
                    f"/code:{os.environ['AGENT00X_VERIFIER_CODE_DIGEST']}"
                )
                staged_payload = artifact.payload_copy()
                if signed_verifier_attestation:
                    verifier_result_payload = staged_payload["verifier_result"]
                    verifier_evidence = staged_payload["verifier_trust_evidence"]
                    signed_response = json.loads(
                        base64.b64decode(
                            verifier_evidence["signed_response_base64"],
                            validate=True,
                        )
                    )
                    enrollment = json.loads(
                        base64.b64decode(
                            verifier_evidence["trust_enrollment_base64"],
                            validate=True,
                        )
                    )
                    host_decision = json.loads(
                        base64.b64decode(
                            verifier_evidence["host_trust_decision_base64"],
                            validate=True,
                        )
                    )
                    invocation_nonce = signed_response["invocation_nonce"]
                    self.assertRegex(invocation_nonce, r"^[0-9a-f]{64}$")
                    self.assertEqual(
                        verifier_result_payload["verifier_id"], invocation_nonce
                    )
                    self.assertEqual(
                        signed_response["response"]["verifier_result"]["verifier_id"],
                        invocation_nonce,
                    )
                    self.assertEqual(
                        signed_response["verifier_profile_digest"],
                        runtime_result["verifier_profile_digest"],
                    )
                    self.assertEqual(
                        staged_payload["seed"]["verifier_attestation_profile_digest"],
                        runtime_result["verifier_profile_digest"],
                    )
                    self.assertEqual(
                        runtime_result["expected_verifier_id"], expected_verifier_id
                    )
                    for trust_record in (enrollment, host_decision):
                        self.assertEqual(
                            trust_record["verifier_id"], expected_verifier_id
                        )
                        self.assertEqual(
                            trust_record["verifier_profile_digest"],
                            runtime_result["verifier_profile_digest"],
                        )
                else:
                    self.assertEqual(
                        staged_payload["verifier_result"]["verifier_id"],
                        expected_verifier_id,
                    )
            stage_bytes_before = stage_database.read_bytes()

            request_stdout, request_stderr = io.StringIO(), io.StringIO()
            request_argv = [
                str(stage_database),
                execution.staged_change_digest,
                branch,
                "master",
                "approval-exp648-vertical-slice",
                TEST_APPROVER_ID,
                policy_version,
            ]
            if signed_verifier_attestation:
                request_argv.extend(
                    [
                        "--verifier-authority-key-set",
                        str(verifier_authority_key_set_path),
                        "--verifier-authority-key-set-digest",
                        verifier_authority_key_set_digest,
                    ]
                )
            with redirect_stdout(request_stdout), redirect_stderr(request_stderr):
                request_code = approval_request_main(
                    request_argv,
                    environ=request_environment,
                    now=now,
                )
            if not signed_verifier_attestation:
                self.assertEqual(request_code, 2, request_stderr.getvalue())
                self.assertIn(
                    "approval request: verifier provenance trust is unavailable",
                    request_stderr.getvalue(),
                )
                self.assertEqual(request_stdout.getvalue(), "")
                self.assertEqual(stage_database.read_bytes(), stage_bytes_before)
                return
            self.assertEqual(request_code, 0, request_stderr.getvalue())
            self.assertEqual(request_stderr.getvalue(), "")

            request_data = json.loads(request_stdout.getvalue())
            request_path.write_text(
                json.dumps(request_data, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            signed_approval = sign_test_approval(request_data["unsigned_approval"])
            signed_path.write_text(
                json.dumps(
                    {"schema": "signed-approval/v1", "approval": signed_approval},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            trust_profile = {
                "schema": "approval-trust-profile/v1",
                "policy_version": policy_version,
                "target": {
                    "source_repository_id": binding.source_repository_id,
                    "provider_repository_id": binding.provider_repository_id,
                },
                "allowed_repositories": [binding.provider_repository_id],
                "allowed_actuators": ["github-app-actuator"],
                "allowed_approver_ids": [TEST_APPROVER_ID],
                "trusted_approver_public_keys": {
                    TEST_APPROVER_ID: TEST_APPROVER_PUBLIC_KEY.hex()
                },
            }
            profile_path.write_text(
                json.dumps(trust_profile, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            authority_key = Ed25519PrivateKey.generate()
            authority_key_id = "synthetic-exp648-authority"
            authority_public_key = authority_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            authority_key_set = {
                "schema": "control-plane-authority-key-set/v1",
                "keys": {authority_key_id: authority_public_key.hex()},
            }
            authority_key_set_path.write_text(
                json.dumps(authority_key_set, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            enrollment = build_signed_approver_trust_enrollment(
                enrollment_id="synthetic-exp648-approver-enrollment",
                authority_key_id=authority_key_id,
                approver_id=TEST_APPROVER_ID,
                approver_public_key=TEST_APPROVER_PUBLIC_KEY,
                trust_profile_digest=sha256_digest(trust_profile),
                provider_repository_id=binding.provider_repository_id,
                signing_key=authority_key,
                issued_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(days=1),
            )
            enrollment_path.write_bytes(enrollment)
            authority_key_set_digest = sha256_bytes(authority_key_set_path.read_bytes())
            approval_input_bytes = {
                path: path.read_bytes()
                for path in (
                    request_path,
                    signed_path,
                    profile_path,
                    enrollment_path,
                    authority_key_set_path,
                    *(
                        (verifier_authority_key_set_path,)
                        if signed_verifier_attestation
                        else ()
                    ),
                )
            }

            publication_stdout, publication_stderr = io.StringIO(), io.StringIO()
            publication_argv = [
                str(stage_database),
                execution.staged_change_digest,
                str(request_path),
                str(signed_path),
                str(profile_path),
                "--approver-enrollment",
                str(enrollment_path),
                "--authority-key-set",
                str(authority_key_set_path),
                "--authority-key-set-digest",
                authority_key_set_digest,
                "--observer-db",
                str(observer_database),
                "--observer-run-id",
                run_id,
            ]
            if signed_verifier_attestation:
                publication_argv.extend(
                    [
                        "--verifier-authority-key-set",
                        str(verifier_authority_key_set_path),
                        "--verifier-authority-key-set-digest",
                        verifier_authority_key_set_digest,
                    ]
                )
            with redirect_stdout(publication_stdout), redirect_stderr(publication_stderr):
                publication_code = signed_mock_publication_main(
                    publication_argv,
                    now=now + timedelta(seconds=1),
                )
            self.assertEqual(publication_code, 0, publication_stderr.getvalue())
            receipt = json.loads(publication_stdout.getvalue())
            self.assertEqual(receipt["status"], "mock_published")
            self.assertEqual(receipt["staged_change_digest"], execution.staged_change_digest)
            self.assertEqual(receipt["repository_id"], binding.provider_repository_id)
            self.assertEqual(receipt["branch"], branch)
            self.assertEqual(receipt["base_branch"], "master")
            self.assertEqual(
                receipt["idempotency_key"],
                json.loads(request_path.read_text(encoding="utf-8"))["intent"][
                    "idempotency_key"
                ],
            )
            self.assertIs(receipt["identity_authenticated"], False)
            self.assertIs(receipt["external_write"], False)
            self.assertEqual(receipt["staged_change_digest"], execution.staged_change_digest)
            self.assertEqual(
                receipt["trust_profile_origin"], "authority_enrolled_approver_key"
            )
            self.assertEqual(
                receipt["approver_enrollment"]["authority_key_id"],
                authority_key_id,
            )
            self.assertEqual(
                receipt["authority_key_set_digest"], authority_key_set_digest
            )
            self.assertEqual(receipt["observer"]["run_id"], run_id)
            self.assertGreater(receipt["observer"]["as_of_cursor"], len(initial_events) - 1)
            self.assertEqual(
                request_data["stage"]["staged_change_digest"],
                execution.staged_change_digest,
            )
            self.assertEqual(request_data["status"], "unsigned")
            self.assertIs(request_data["provider_write"], False)
            self.assertEqual(
                approval_input_bytes,
                {path: path.read_bytes() for path in approval_input_bytes},
            )
            self.assertEqual(stage_bytes_before, stage_database.read_bytes())
            report = report_from_sqlite(observer_database)
            with SQLiteObservationStore(observer_database) as reopened_observer:
                events_after_publication = reopened_observer.events()
            facts = list(events_after_publication)
            self.assertEqual(report["snapshot"]["event_count"], len(initial_events) + 14)
            self.assertEqual([event["sequence"] for event in facts], list(range(len(facts))))
            self.assertEqual({event["run_id"] for event in facts}, {run_id})
            self.assertEqual(
                [
                    event.get("decision_or_tool")
                    for event in facts
                    if event.get("agent_id") == "service-publication-observer"
                    and event.get("event_type")
                    in {"decision_proposed", "tool_requested"}
                ],
                [
                    "GitHubReadiness.fetch",
                    "RemoteExecutionPermit.issue",
                    "ControlledPublication.local-mock",
                    "SignedApproval.verify",
                    "Approval.validate",
                    "PolicyEngine.evaluate",
                    "Gateway.authorize",
                    "CredentialBroker.open-channel",
                    "Publication.dispatch",
                ],
            )
            self.assertNotIn(proposed_content, repr(facts))
            self.assertNotIn(TEST_APPROVER_PUBLIC_KEY.hex(), repr(facts))

            assert_canary_absent(
                synthetic_credential_canary,
                {
                    "worker-stdout": pinned_stdout.getvalue(),
                    "worker-stderr": pinned_stderr.getvalue(),
                    "approval-request-stdout": request_stdout.getvalue(),
                    "approval-request-stderr": request_stderr.getvalue(),
                    "publication-stdout": publication_stdout.getvalue(),
                    "publication-stderr": publication_stderr.getvalue(),
                    "stage-database": stage_database.read_bytes(),
                    "observer-database": observer_database.read_bytes(),
                    "approval-request-file": request_path.read_bytes(),
                    "signed-approval-file": signed_path.read_bytes(),
                    "trust-profile-file": profile_path.read_bytes(),
                    "approver-enrollment-file": enrollment_path.read_bytes(),
                    "authority-key-set-file": authority_key_set_path.read_bytes(),
                    "observer-report": report,
                    "mock-receipt": receipt,
                },
            )

            before_repeat = observer_database.read_bytes()
            repeated_output, repeated_error = io.StringIO(), io.StringIO()
            with redirect_stdout(repeated_output), redirect_stderr(repeated_error):
                repeated_code = signed_mock_publication_main(
                    [
                        str(stage_database),
                        execution.staged_change_digest,
                        str(request_path),
                        str(signed_path),
                        str(profile_path),
                        "--approver-enrollment",
                        str(enrollment_path),
                        "--authority-key-set",
                        str(authority_key_set_path),
                        "--authority-key-set-digest",
                        authority_key_set_digest,
                        "--observer-db",
                        str(observer_database),
                        "--observer-run-id",
                        run_id,
                    ],
                    now=now + timedelta(seconds=2),
                )
            self.assertEqual(repeated_code, 2)
            self.assertIn("observer run rejected", repeated_error.getvalue())
            self.assertEqual(repeated_output.getvalue(), "")
            self.assertEqual(before_repeat, observer_database.read_bytes())

            if (
                public_mode
                and os.environ.get("AGENT00X_EMIT_PUBLIC_SNAPSHOT_EVIDENCE") == "1"
            ):
                _emit_public_snapshot_evidence(
                    sys.stdout,
                    enabled=True,
                    snapshot_metadata={
                        "commit_oid": snapshot.claim.commit_oid,
                        "tree_oid": snapshot.claim.tree_oid,
                        "content_digest": snapshot.claim.content_digest,
                        "file_count": len(snapshot.files),
                    },
                    staged_change_digest=execution.staged_change_digest,
                    observer_run_id=run_id,
                    request_counts={
                        "readiness_gets": public_transport.readiness_calls,
                        "commit_gets": public_transport.request_kinds.count("commit"),
                        "tree_gets": public_transport.request_kinds.count("tree"),
                        "blob_gets": public_transport.request_kinds.count("blob"),
                        "raw_commit_fetches": public_commit_source.calls,
                        "runtime_invocations": len(runtime_invocation_counter),
                    },
                    receipt={
                        "status": receipt["status"],
                        "staged_change_digest": receipt["staged_change_digest"],
                        "identity_authenticated": receipt["identity_authenticated"],
                        "external_write": receipt["external_write"],
                        "observer_completeness": receipt["observer"]["completeness"],
                    },
                )

    def test_deepseek_fake_worker_remote_replay_verifier_seed_and_intent(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# synthetic deepseek pipeline fixture\n"
        channel = FixedChatCompletionsChannel(proposed_content)
        worker = DeepSeekProposalWorker(channel=channel)
        nonce = "3" * 64
        verifier = SubprocessVerifier(
            VerifierProcessConfig(
                executable=sys.executable,
                argv=(
                    sys.executable,
                    "-m",
                    "app_contracts.verifier_container_entrypoint",
                    "--invocation-nonce=" + nonce,
                ),
                timeout_seconds=30,
                max_stdout_bytes=65_536,
                max_stderr_bytes=4_096,
            ),
            environ={"PYTHONPATH": str(ROOT / "src")},
        )
        python = sys.executable
        test_command = (
            python,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )

        with materialize_github_snapshot(snapshot) as workspace:
            workspace_path = workspace.path
            request = ExecutionRequest(
                process_id="process-remote-deepseek-001",
                task_id="task-remote-deepseek-001",
                repository_id="FixtureOwner/calculator-fixture",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=workspace.path,
                allowed_commands=frozenset({Path(python).name}),
                declared_change_paths=("calculator.py",),
                test_command=test_command,
                task_instruction="Add a harmless fixture-only comment to calculator.py",
                context_files=(("calculator.py", base_content),),
                remote_snapshot=snapshot,
                remote_workspace=workspace,
            )
            result = run_local_execution(
                request,
                worker,
                verifier=verifier,
                sandbox_backend=LocalProcessSandboxBackend(),
            )
            self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
            self.assertEqual(channel.calls, 1)
            self.assertEqual(channel.payloads[0]["model"], "deepseek-flash")
            self.assertEqual(channel.payloads[0]["response_format"], {"type": "json_object"})
            self.assertEqual(result.verifier_result.verifier_id, nonce)
            self.assertIsNotNone(result.verifier_result.replay_result_digest)
            seed = build_publication_seed(request, result)
            intent = derive_publication_intent(seed, "agent/deepseek-fixture", "master")
            self.assertEqual(seed.staged_change_digest, intent.staged_change_digest)
            self.assertEqual(seed.snapshot_claim_digest, result.snapshot_claim_digest)
            for value in (repr(result), repr(seed), repr(intent)):
                self.assertNotIn("synthetic deepseek pipeline fixture", value)
                self.assertNotIn("must not enter proposal or evidence", value)
                self.assertNotIn(base_content, value)

        self.assertTrue(workspace.closed)
        self.assertFalse(workspace_path.exists())

    def test_remote_snapshot_worker_replay_verifier_seed_and_intent(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# synthetic mvp pipeline fixture\n"
        channel = FixedResponsesChannel(proposed_content)
        worker = OpenAIProposalWorker(channel=channel)

        nonce = "1" * 64
        verifier_config = VerifierProcessConfig(
            executable=sys.executable,
            argv=(
                sys.executable,
                "-m",
                "app_contracts.verifier_container_entrypoint",
                "--invocation-nonce=" + nonce,
            ),
            timeout_seconds=30,
            max_stdout_bytes=65_536,
            max_stderr_bytes=4_096,
        )
        verifier = SubprocessVerifier(
            verifier_config,
            environ={"PYTHONPATH": str(ROOT / "src")},
        )
        python = sys.executable
        request_command = (
            python,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )
        allowed_commands = frozenset({Path(python).name})

        with materialize_github_snapshot(snapshot) as workspace:
            workspace_path = workspace.path
            request = ExecutionRequest(
                process_id="process-remote-mvp-001",
                task_id="task-remote-mvp-001",
                repository_id="FixtureOwner/calculator-fixture",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=workspace.path,
                allowed_commands=allowed_commands,
                declared_change_paths=("calculator.py",),
                test_command=request_command,
                task_instruction="Add a harmless fixture-only comment to calculator.py",
                context_files=(("calculator.py", base_content),),
                remote_snapshot=snapshot,
                remote_workspace=workspace,
            )
            result = run_local_execution(
                request,
                worker,
                verifier=verifier,
                sandbox_backend=LocalProcessSandboxBackend(),
            )
            self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
            self.assertEqual(channel.calls, 1)
            self.assertEqual(result.verifier_result.verifier_id, nonce)
            self.assertIsNotNone(result.verifier_result.replay_result_digest)
            expected_claim_digest = sha256_digest(
                {
                    "canonicalization": "github-rest-snapshot-claim/v1",
                    "owner": snapshot.claim.owner,
                    "repository": snapshot.claim.repository,
                    "commit_oid": snapshot.claim.commit_oid,
                    "tree_oid": snapshot.claim.tree_oid,
                    "content_digest": snapshot.claim.content_digest,
                    "full_snapshot": snapshot.claim.full_snapshot,
                    "selected_paths": snapshot.claim.selected_paths,
                    "evidence_origin": snapshot.claim.evidence_origin,
                }
            )
            self.assertEqual(result.snapshot_claim_digest, expected_claim_digest)

            seed = build_publication_seed(request, result)
            intent = derive_publication_intent(seed, "agent/remote-mvp-smoke", "master")
            self.assertEqual(seed.staged_change_digest, intent.staged_change_digest)
            self.assertEqual(seed.snapshot_claim_digest, result.snapshot_claim_digest)
            self.assertEqual(intent.base_commit, snapshot.claim.commit_oid)
            self.assertEqual(intent.repository_id, "FixtureOwner/calculator-fixture")
            for value in (repr(result), repr(seed), repr(intent)):
                self.assertNotIn("synthetic mvp pipeline fixture", value)
                self.assertNotIn(base_content, value)

        self.assertTrue(workspace.closed)
        self.assertFalse(workspace_path.exists())

    def test_remote_seed_approval_and_mock_publication_share_exact_digest(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# synthetic mvp publication fixture\n"
        channel = FixedResponsesChannel(proposed_content)
        worker = OpenAIProposalWorker(channel=channel)
        nonce = "2" * 64
        verifier = SubprocessVerifier(
            VerifierProcessConfig(
                executable=sys.executable,
                argv=(
                    sys.executable,
                    "-m",
                    "app_contracts.verifier_container_entrypoint",
                    "--invocation-nonce=" + nonce,
                ),
                timeout_seconds=30,
                max_stdout_bytes=65_536,
                max_stderr_bytes=4_096,
            ),
            environ={"PYTHONPATH": str(ROOT / "src")},
        )
        python = sys.executable
        test_command = (
            python,
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )
        captured: dict = {}
        with materialize_github_snapshot(snapshot) as workspace:
            request = ExecutionRequest(
                process_id="process-remote-publication-001",
                task_id="task-remote-publication-001",
                repository_id="FixtureOwner/calculator-fixture",
                base_commit=snapshot.claim.commit_oid,
                snapshot_path=workspace.path,
                allowed_commands=frozenset({Path(python).name}),
                declared_change_paths=("calculator.py",),
                test_command=test_command,
                task_instruction="Add a harmless fixture-only comment to calculator.py",
                context_files=(("calculator.py", base_content),),
                remote_snapshot=snapshot,
                remote_workspace=workspace,
            )
            real_prepare = executor_module.prepare_change

            def capture_stage(sandbox, **kwargs):
                prepared = real_prepare(sandbox, **kwargs)
                captured["stage"] = dict(prepared.staged_change)
                captured["prepared"] = prepared
                return prepared

            with tempfile.TemporaryDirectory(prefix="remote-pipeline-stage-") as stage_directory:
                stage_database = Path(stage_directory) / "stages.sqlite3"
                with SQLiteStagedArtifactStore(stage_database) as stage_store:
                    with patch("app_contracts.executor.prepare_change", side_effect=capture_stage):
                        result = run_local_execution(
                            request,
                            worker,
                            verifier=verifier,
                            sandbox_backend=LocalProcessSandboxBackend(),
                            stage_sink=stage_store,
                            require_durable_stage=True,
                        )
                    persisted_artifact = stage_store.load(result.staged_change_digest)
            self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
            self.assertEqual(channel.calls, 1)
            seed = build_publication_seed(request, result)
            intent = derive_publication_intent(seed, "agent/remote-mock-publication", "master")
            staged_change = persisted_artifact.payload_copy()["staged_change"]
            self.assertEqual(staged_change, captured["stage"])
            self.assertEqual(sha256_digest(staged_change), intent.staged_change_digest)

            now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
            mock_receipt = run_local_mock_publication(
                persisted_artifact,
                persisted_artifact.staged_change_digest,
                "agent/remote-mock-publication",
                "master",
                now=now,
            )
            self.assertEqual(mock_receipt.staged_change_digest, intent.staged_change_digest)
            self.assertEqual(mock_receipt.repository_id, intent.repository_id)

            expires_at = (now + timedelta(hours=1)).isoformat()
            policy_version = "remote-fixture-policy-v1"
            approval_id = "approval-remote-fixture-001"
            engine_intent = {
                "process_id": intent.process_id,
                "repository_id": intent.repository_id,
                "base_commit": intent.base_commit,
                "operation": "publish_pull_request",
                "approval_id": approval_id,
                "expires_at": expires_at,
                "branch_namespace": intent.branch.split("/", 1)[0],
                "idempotency_key": intent.idempotency_key,
                "staged_change_digest": intent.staged_change_digest,
            }
            approval = sign_test_approval({
                "schema_version": 1,
                "process_id": intent.process_id,
                "repository_id": intent.repository_id,
                "operation": "publish_pull_request",
                "approval_id": approval_id,
                "approver_id": "user-alice",
                "policy_version": policy_version,
                "expires_at": expires_at,
                "staged_change_digest": intent.staged_change_digest,
                "approved_intent_digest": sha256_digest(engine_intent),
                "approved_at": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            })
            policy = DeterministicPolicy(
                PolicyConfig(
                    version=policy_version,
                    allowed_repositories=frozenset({intent.repository_id}),
                    allowed_actuators=frozenset({"test-actuator"}),
                    allowed_approver_ids=frozenset(TEST_APPROVER_PUBLIC_KEYS),
                    trusted_approver_public_keys=TEST_APPROVER_PUBLIC_KEYS,
                    decision_ttl_seconds=300,
                )
            )
            actuator_request = {
                "operation": "publish_pull_request",
                "repository_id": intent.repository_id,
                "actuator_id": "test-actuator",
                "base_branch": intent.base_branch,
                "staged_change_digest": intent.staged_change_digest,
                "branch_namespace": intent.branch.split("/", 1)[0],
                "idempotency_key": intent.idempotency_key,
            }
            grant = {
                "credential_grant_id": "test-only-grant-001",
                "actuator_id": "test-actuator",
                "repository_id": intent.repository_id,
                "operation": "publish_pull_request",
                "request_digest": sha256_digest(actuator_request),
                "single_use": True,
                "credential_class": "github-app-installation",
                "expires_at": expires_at,
            }

            diagnostic_decision = policy.decide(
                decision_id="decision-remote-fixture-diagnostic",
                actuator_request=actuator_request,
                approval=approval,
                staged_change=staged_change,
                intent=engine_intent,
                now=now,
            )
            self.assertEqual(diagnostic_decision["effect"], "allow", diagnostic_decision["reason_codes"])

            def envelope():
                return {
                    "intent": {"operation": "publish_pull_request"},
                    "destination": {
                        "port": "approval",
                        "repository_id": intent.repository_id,
                        "base_branch": intent.base_branch,
                    },
                    "source": {
                        "protocol": "internal",
                        "principal_id": intent.process_id,
                    },
                    "security": {"tainted": False, "sensitivity": "internal"},
                    "payload": {"content_digest": intent.staged_change_digest},
                    "correlation_id": intent.idempotency_key,
                }

            class AllowGateway:
                def __init__(self):
                    self.calls = 0

                def __call__(self, _envelope, *, now):
                    self.calls += 1
                    return GatewayDecision(
                        GatewayPath.SLOW, True, ("write-or-unknown-operation",)
                    )

            endpoint = MockGitHubEndpoint()
            broker = InMemoryCredentialBroker(lambda: endpoint)
            gateway = AllowGateway()

            def load_stage(candidate_seed):
                self.assertEqual(candidate_seed.staged_change_digest, intent.staged_change_digest)
                return staged_change

            with tempfile.TemporaryDirectory() as directory:
                journal_path = Path(directory) / "journal.sqlite"
                with PublicationJournal(journal_path) as journal:
                    receipt = run_controlled_local_publication(
                        seed,
                        intent,
                        approval,
                        policy,
                        engine_intent,
                        load_stage,
                        "decision-remote-fixture-001",
                        gateway,
                        envelope(),
                        broker,
                        grant,
                        journal,
                        endpoint,
                        actuator_id="test-actuator",
                        now=now,
                    )
                    self.assertEqual(receipt.repository_id, intent.repository_id)
                    self.assertEqual(receipt.staged_change_digest, intent.staged_change_digest)
                    self.assertEqual(journal.get(intent.process_id).status, "completed")
                    self.assertEqual(gateway.calls, 1)
                    self.assertEqual(len(broker.opened_grants), 1)

                bad_endpoint = MockGitHubEndpoint()
                bad_broker = InMemoryCredentialBroker(lambda: bad_endpoint)
                bad_gateway = AllowGateway()
                with PublicationJournal(Path(directory) / "denied.sqlite") as denied_journal:
                    bad_approval = dict(
                        approval,
                        staged_change_digest="sha256:" + "f" * 64,
                    )
                    with self.assertRaises(ContractValidationError) as raised:
                        run_controlled_local_publication(
                            seed,
                            intent,
                            bad_approval,
                            policy,
                            engine_intent,
                            load_stage,
                            "decision-remote-fixture-denied",
                            bad_gateway,
                            envelope(),
                            bad_broker,
                            grant,
                            denied_journal,
                            bad_endpoint,
                            actuator_id="test-actuator",
                            now=now,
                        )
                    self.assertNotIn("sha256:", str(raised.exception))
                    self.assertEqual(bad_gateway.calls, 0)
                    self.assertEqual(bad_broker.opened_grants, [])
                    self.assertIsNone(
                        bad_endpoint.find_by_idempotency_key(intent.idempotency_key)
                    )
                    with self.assertRaises(KeyError):
                        denied_journal.get(intent.process_id)


@unittest.skipUnless(
    os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1"
    and re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        os.environ.get("AGENT00X_VERIFIER_IMAGE_ID", ""),
    )
    and re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        os.environ.get("AGENT00X_VERIFIER_CODE_DIGEST", ""),
    )
    and os.path.isabs(os.environ.get("AGENT00X_DOCKER_EXECUTABLE", "")),
    "real Docker verifier composition is opt-in",
)
class RemoteSnapshotVerifierStageDockerTests(unittest.TestCase):
    def test_container_verifier_completes_synthetic_stage(self):
        snapshot, base_content = make_full_snapshot()
        proposed_content = base_content + "\n# docker-verifier-stage-fixture\n"
        channel = FixedChatCompletionsChannel(proposed_content)
        worker = DeepSeekProposalWorker(channel=channel)
        verifier_image_id = os.environ["AGENT00X_VERIFIER_IMAGE_ID"]
        verifier_code_digest = os.environ["AGENT00X_VERIFIER_CODE_DIGEST"]
        verifier = DockerContainerVerifier(
            VerifierContainerConfig(
                os.environ["AGENT00X_DOCKER_EXECUTABLE"],
                verifier_image_id,
                verifier_code_digest,
                timeout_seconds=60,
                max_stdout_bytes=65_536,
                max_stderr_bytes=16_384,
            )
        )
        test_command = (
            "python3",
            "-c",
            "from calculator import add; assert add(20, 22) == 42",
        )

        with tempfile.TemporaryDirectory(prefix="synthetic-docker-stage-") as directory:
            stage_database = Path(directory) / "stage.sqlite3"
            with SQLiteStagedArtifactStore(stage_database) as stage_store:
                result = run_remote_snapshot_execution(
                    snapshot,
                    process_id="process-synthetic-docker-stage-001",
                    task_id="task-synthetic-docker-stage-001",
                    task_instruction="Add one harmless synthetic fixture comment",
                    declared_change_paths=("calculator.py",),
                    allowed_commands=frozenset({"python3"}),
                    test_command=test_command,
                    test_timeout_seconds=20,
                    worker=worker,
                    verifier=verifier,
                    sandbox_backend=DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID),
                    context_files=(("calculator.py", base_content),),
                    stage_sink=stage_store,
                )
                self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
                self.assertIsNotNone(result.staged_change_digest)
                artifact = stage_store.load(result.staged_change_digest)
                self.assertEqual(
                    artifact.staged_change_digest, result.staged_change_digest
                )

            self.assertEqual(channel.calls, 1)
            self.assertEqual(
                result.verifier_result.verifier_id,
                f"docker-image:{verifier_image_id}/code:{verifier_code_digest}",
            )
            preview = json.loads(render_stage_preview(artifact))
            self.assertEqual(
                preview["stage"]["staged_change_digest"],
                result.staged_change_digest,
            )
            self.assertEqual(preview["approval"], "not_created")
            self.assertEqual(preview["publication"], "not_attempted")
            receipt = run_local_mock_publication(
                artifact,
                result.staged_change_digest,
                "agent/synthetic-docker-stage-mock",
                "master",
                now=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(
                receipt.staged_change_digest, result.staged_change_digest
            )
        self.assertEqual(receipt.repository_id, "FixtureOwner/calculator-fixture")


@unittest.skipUnless(
    os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1"
    and os.environ.get("AGENT00X_TARGET_IMAGE_ID") == TARGET_RUNTIME_IMAGE_ID
    and os.environ.get("AGENT00X_DOCKER_EXECUTABLE") == "/usr/local/bin/docker",
    "synthetic pinned target probe is opt-in",
)
class PinnedTargetProbeSyntheticDockerTests(unittest.TestCase):
    def test_pinned_http_db_probe_on_synthetic_app_docker(self):
        base_routes = '''from fastapi import APIRouter
from backend.database import conn

router = APIRouter()

@router.post("/save-session")
def save_session(data: dict):
    conn.execute(
        "INSERT INTO sessions (telegram_id, level, correct, wrong, total, time_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            data.get('telegram_id', 'local'),
            data.get('level', 1),
            data.get('correct', 0),
            data.get('wrong', 0),
            data.get('total', 10),
            data.get('time_ms', 0),
        ),
    )
    conn.commit()
    return {"status": "ok"}
'''
        candidate = _strict_signed_range_routes_candidate(base_routes)
        with tempfile.TemporaryDirectory(prefix="pinned-probe-synthetic-app-") as directory:
            snapshot = Path(directory) / "snapshot"
            backend_path = snapshot / "backend"
            backend_path.mkdir(parents=True)
            (backend_path / "__init__.py").write_text("", encoding="utf-8")
            (backend_path / "routes.py").write_text(candidate, encoding="utf-8")
            (backend_path / "main.py").write_text(
                "from fastapi import FastAPI\n"
                "from backend.routes import router\n"
                "app = FastAPI()\n"
                "app.include_router(router)\n",
                encoding="utf-8",
            )
            (backend_path / "database.py").write_text(
                "import sqlite3\n"
                "conn = sqlite3.connect('brainbooster.db', check_same_thread=False)\n"
                "conn.execute('CREATE TABLE sessions (telegram_id TEXT, level INTEGER, "
                "correct INTEGER, wrong INTEGER, total INTEGER, time_ms INTEGER)')\n",
                encoding="utf-8",
            )
            session = DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID).create(
                snapshot, {"python3"}
            )
            try:
                result = session.run(
                    PINNED_HTTP_DB_TEST_COMMAND,
                    timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                )
                marker = _safe_target_probe_failure_marker(result)
                self.assertEqual(
                    result.returncode,
                    0,
                    f"synthetic probe failed; safe_marker={marker}",
                )
            finally:
                session.close()

    def test_pinned_http_db_overflow_status_docker(self):
        base_routes = '''from fastapi import APIRouter
from backend.database import conn

router = APIRouter()

@router.post("/save-session")
def save_session(data: dict):
    conn.execute(
        "INSERT INTO sessions (telegram_id, level, correct, wrong, total, time_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            data.get('telegram_id', 'local'),
            data.get('level', 1),
            data.get('correct', 0),
            data.get('wrong', 0),
            data.get('total', 10),
            data.get('time_ms', 0),
        ),
    )
    conn.commit()
    return {"status": "ok"}
'''
        candidate = _strict_signed_range_routes_candidate(base_routes)
        with tempfile.TemporaryDirectory(prefix="pinned-overflow-synthetic-app-") as directory:
            snapshot = Path(directory) / "snapshot"
            backend_path = snapshot / "backend"
            backend_path.mkdir(parents=True)
            (backend_path / "__init__.py").write_text("", encoding="utf-8")
            (backend_path / "routes.py").write_text(candidate, encoding="utf-8")
            (backend_path / "main.py").write_text(
                "from fastapi import FastAPI\n"
                "from backend.routes import router\n"
                "app = FastAPI()\n"
                "app.include_router(router)\n",
                encoding="utf-8",
            )
            (backend_path / "database.py").write_text(
                "import sqlite3\n"
                "conn = sqlite3.connect('brainbooster.db', check_same_thread=False)\n"
                "conn.execute('CREATE TABLE sessions (telegram_id TEXT, level INTEGER, "
                "correct INTEGER, wrong INTEGER, total INTEGER, time_ms INTEGER)')\n",
                encoding="utf-8",
            )
            session = DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID).create(
                snapshot, {"python3"}
            )
            try:
                result = session.run(
                    ("python3", "-c", _PINNED_HTTP_DB_OVERFLOW_DIAGNOSTIC),
                    timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                )
                marker = _safe_overflow_diagnostic_marker(result)
                self.assertEqual(
                    result.returncode,
                    0,
                    f"synthetic overflow diagnostic failed; safe_marker={marker}",
                )
                self.assertNotEqual(marker, "unavailable")
                print(marker)
            finally:
                session.close()

    def test_pinned_http_db_overflow_exception_category_docker(self):
        # Keep the synthetic endpoint's exact source shape so each candidate
        # replacement is exercised; no real target source is used.
        source_routes = '''from fastapi import APIRouter
from backend.database import conn

router = APIRouter()

@router.post("/save-session")
def save_session(data: dict):
    conn.execute(
        "INSERT INTO sessions (telegram_id, level, correct, wrong, total, time_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (data.get('telegram_id', 'local'), data.get('level', 1), data.get('correct', 0),
         data.get('wrong', 0), data.get('total', 10), data.get('time_ms', 0)),
    )
    conn.commit()
    return {"status": "ok"}
'''
        candidate = _strict_signed_range_routes_candidate(source_routes)
        diagnostic = r'''import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from fastapi.responses import Response

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
base = f"http://127.0.0.1:{port}"
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    deadline = time.monotonic() + 5
    while True:
        if server.poll() is not None:
            print("agent00x:overflow-exception:category=other", flush=True)
            raise SystemExit(2)
        try:
            with urllib.request.urlopen(base + "/openapi.json", timeout=1) as response:
                if response.status != 200:
                    print("agent00x:overflow-exception:category=other", flush=True)
                    raise SystemExit(2)
            break
        except (OSError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                print("agent00x:overflow-exception:category=other", flush=True)
                raise SystemExit(2)
            time.sleep(0.05)
    request = urllib.request.Request(
        base + "/save-session",
        data=b'{"telegram_id":"synthetic-probe","level":1e309,"correct":1,"wrong":0,"total":1,"time_ms":250}',
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=2)
        category = response.headers.get("X-Agent00X-Exception-Category", "none")
        response.close()
    except urllib.error.HTTPError as error:
        category = error.headers.get("X-Agent00X-Exception-Category", "none")
        error.close()
    if category not in {"overflow", "type", "value", "sqlite", "attribute", "key", "other", "none"}:
        print("agent00x:overflow-exception:category=other", flush=True)
        raise SystemExit(2)
    print("agent00x:overflow-exception:category=" + category, flush=True)
finally:
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=2)
'''
        middleware = '''
import sqlite3
from fastapi.responses import Response

@app.middleware("http")
async def safe_exception_category(request, call_next):
    try:
        return await call_next(request)
    except Exception as error:
        categories = {
            OverflowError: "overflow", TypeError: "type", ValueError: "value",
            sqlite3.Error: "sqlite", AttributeError: "attribute", KeyError: "key",
        }
        category = categories.get(type(error), "other")
        return Response(status_code=500, headers={"X-Agent00X-Exception-Category": category})
'''
        with tempfile.TemporaryDirectory(prefix="pinned-overflow-category-app-") as directory:
            snapshot = Path(directory) / "snapshot"
            backend_path = snapshot / "backend"
            backend_path.mkdir(parents=True)
            (backend_path / "__init__.py").write_text("", encoding="utf-8")
            (backend_path / "routes.py").write_text(candidate, encoding="utf-8")
            (backend_path / "main.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                + middleware
                + "\nfrom backend.routes import router\napp.include_router(router)\n",
                encoding="utf-8",
            )
            (backend_path / "database.py").write_text(
                "import sqlite3\n"
                "conn = sqlite3.connect('brainbooster.db', check_same_thread=False)\n"
                "conn.execute('CREATE TABLE sessions (telegram_id TEXT, level INTEGER, "
                "correct INTEGER, wrong INTEGER, total INTEGER, time_ms INTEGER)')\n",
                encoding="utf-8",
            )
            session = DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID).create(
                snapshot, {"python3"}
            )
            try:
                result = session.run(
                    ("python3", "-c", diagnostic),
                    timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                )
                marker = _safe_overflow_exception_category_marker(result)
                self.assertEqual(
                    result.returncode,
                    0,
                    f"synthetic exception diagnostic failed; safe_marker={marker}",
                )
                self.assertNotEqual(marker, "unavailable")
                print(marker)
            finally:
                session.close()

    def test_pinned_http_db_overflow_exception_reraise_docker(self):
        source_routes = '''from fastapi import APIRouter
from backend.database import conn

router = APIRouter()

@router.post("/save-session")
def save_session(data: dict):
    conn.execute(
        "INSERT INTO sessions (telegram_id, level, correct, wrong, total, time_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (data.get('telegram_id', 'local'), data.get('level', 1), data.get('correct', 0),
         data.get('wrong', 0), data.get('total', 10), data.get('time_ms', 0)),
    )
    conn.commit()
    return {"status": "ok"}
'''
        candidate = _strict_signed_range_routes_candidate(source_routes)
        diagnostic = r'''import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
base = f"http://127.0.0.1:{port}"
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    deadline = time.monotonic() + 5
    while True:
        if server.poll() is not None:
            print("agent00x:overflow-exception:category=other", flush=True)
            raise SystemExit(2)
        try:
            with urllib.request.urlopen(base + "/openapi.json", timeout=1) as response:
                if response.status != 200:
                    print("agent00x:overflow-exception:category=other", flush=True)
                    raise SystemExit(2)
            break
        except (OSError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                print("agent00x:overflow-exception:category=other", flush=True)
                raise SystemExit(2)
            time.sleep(0.05)
    request = urllib.request.Request(
        base + "/save-session",
        data=b'{"telegram_id":"synthetic-probe","level":1e309,"correct":1,"wrong":0,"total":1,"time_ms":250}',
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2):
            pass
    except urllib.error.HTTPError as error:
        error.close()
    with sqlite3.connect("brainbooster.db", timeout=2) as connection:
        rows = connection.execute("SELECT category FROM diagnostics").fetchall()
    if len(rows) != 1 or type(rows[0][0]) is not str or rows[0][0] not in {
        "overflow", "type", "value", "sqlite", "attribute", "key", "other"
    }:
        print("agent00x:overflow-exception:category=other", flush=True)
        raise SystemExit(2)
    print("agent00x:overflow-exception:category=" + rows[0][0], flush=True)
finally:
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=2)
'''
        middleware = '''
import sqlite3
from backend.database import conn

@app.middleware("http")
async def safe_exception_category(request, call_next):
    try:
        return await call_next(request)
    except Exception as error:
        categories = {
            OverflowError: "overflow", TypeError: "type", ValueError: "value",
            sqlite3.Error: "sqlite", AttributeError: "attribute", KeyError: "key",
        }
        category = categories.get(type(error), "other")
        conn.execute("INSERT INTO diagnostics (category) VALUES (?)", (category,))
        conn.commit()
        raise
'''
        with tempfile.TemporaryDirectory(prefix="pinned-overflow-reraise-app-") as directory:
            snapshot = Path(directory) / "snapshot"
            backend_path = snapshot / "backend"
            backend_path.mkdir(parents=True)
            (backend_path / "__init__.py").write_text("", encoding="utf-8")
            (backend_path / "routes.py").write_text(candidate, encoding="utf-8")
            (backend_path / "main.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                + middleware
                + "\nfrom backend.routes import router\napp.include_router(router)\n",
                encoding="utf-8",
            )
            (backend_path / "database.py").write_text(
                "import sqlite3\n"
                "conn = sqlite3.connect('brainbooster.db', check_same_thread=False)\n"
                "conn.execute('CREATE TABLE sessions (telegram_id TEXT, level INTEGER, "
                "correct INTEGER, wrong INTEGER, total INTEGER, time_ms INTEGER)')\n"
                "conn.execute('CREATE TABLE diagnostics (category TEXT)')\n",
                encoding="utf-8",
            )
            session = DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID).create(
                snapshot, {"python3"}
            )
            try:
                result = session.run(
                    ("python3", "-c", diagnostic),
                    timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                )
                marker = _safe_overflow_exception_category_marker(result)
                self.assertEqual(
                    result.returncode,
                    0,
                    f"synthetic re-raise diagnostic failed; safe_marker={marker}",
                )
                self.assertNotEqual(marker, "unavailable")
                print(marker)
            finally:
                session.close()

    def test_pinned_http_db_candidate_numeric_contract_docker(self):
        source_routes = '''from fastapi import APIRouter
from backend.database import conn

router = APIRouter()

@router.post("/save-session")
def save_session(data: dict):
    conn.execute(
        "INSERT INTO sessions (telegram_id, level, correct, wrong, total, time_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (data.get('telegram_id', 'local'), data.get('level', 1), data.get('correct', 0),
         data.get('wrong', 0), data.get('total', 10), data.get('time_ms', 0)),
    )
    conn.commit()
    return {"status": "ok"}
'''
        candidate = _strict_signed_range_routes_candidate(source_routes)
        probe = r'''import json
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

def fail(category):
    print("agent00x:numeric-contract:FAIL:" + category, flush=True)
    raise SystemExit(1)

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
base = f"http://127.0.0.1:{port}"
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
def post(payload):
    request = urllib.request.Request(
        base + "/save-session", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        return status
def rows():
    with sqlite3.connect("brainbooster.db", timeout=2) as connection:
        return connection.execute(
            "SELECT telegram_id, level, correct, wrong, total, time_ms FROM sessions"
        ).fetchall()
try:
    deadline = time.monotonic() + 5
    while True:
        if server.poll() is not None:
            fail("readiness-exit")
        try:
            with urllib.request.urlopen(base + "/openapi.json", timeout=1) as response:
                if response.status != 200:
                    fail("readiness-exit")
            break
        except (OSError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                fail("readiness-timeout")
            time.sleep(0.05)
    fields = ("level", "correct", "wrong", "total", "time_ms")
    malformed = (True, 1.5, "1", 9223372036854775808, -9223372036854775809)
    for field in fields:
        for value in malformed:
            payload = {"telegram_id": "synthetic-probe", "level": 2, "correct": 1, "wrong": 0, "total": 1, "time_ms": 250}
            payload[field] = value
            status = post(json.dumps(payload, separators=(",", ":")).encode())
            if status != 422:
                fail("invalid-status")
            if rows() != []:
                fail("invalid-no-write")
    overflow = b'{"telegram_id":"synthetic-probe","level":1e309,"correct":1,"wrong":0,"total":1,"time_ms":250}'
    if post(overflow) != 422:
        fail("overflow-status")
    if rows() != []:
        fail("overflow-no-write")
    valid = {"telegram_id": "synthetic-probe", "level": 2, "correct": 1, "wrong": 0, "total": 1, "time_ms": 250}
    if post(json.dumps(valid, separators=(",", ":")).encode()) != 200:
        fail("valid-status")
    expected = [("synthetic-probe", 2, 1, 0, 1, 250)]
    if rows() != expected:
        fail("valid-row")
    print("agent00x:numeric-contract:PASS", flush=True)
finally:
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=2)
'''
        with tempfile.TemporaryDirectory(prefix="pinned-numeric-contract-app-") as directory:
            snapshot = Path(directory) / "snapshot"
            backend_path = snapshot / "backend"
            backend_path.mkdir(parents=True)
            (backend_path / "__init__.py").write_text("", encoding="utf-8")
            (backend_path / "routes.py").write_text(candidate, encoding="utf-8")
            (backend_path / "main.py").write_text(
                "from fastapi import FastAPI\n"
                "from backend.routes import router\n"
                "app = FastAPI()\n"
                "app.include_router(router)\n",
                encoding="utf-8",
            )
            (backend_path / "database.py").write_text(
                "import sqlite3\n"
                "conn = sqlite3.connect('brainbooster.db', check_same_thread=False)\n"
                "conn.execute('CREATE TABLE sessions (telegram_id TEXT, level INTEGER, "
                "correct INTEGER, wrong INTEGER, total INTEGER, time_ms INTEGER)')\n",
                encoding="utf-8",
            )
            session = DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID).create(
                snapshot, {"python3"}
            )
            try:
                result = session.run(
                    ("python3", "-c", probe),
                    timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                )
                marker = _safe_candidate_numeric_contract_marker(result)
                self.assertEqual(
                    result.returncode,
                    0,
                    f"synthetic numeric contract failed; safe_marker={marker}",
                )
                self.assertEqual(marker, "candidate-numeric-contract:PASS")
                print(marker)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
