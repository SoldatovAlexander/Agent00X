from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
    DeepSeekProposalWorker,
)
from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.brainbooster_target_profile import (
    EXPECTED_CANDIDATE_DIGEST,
    PINNED_COMMIT,
    PINNED_CONTENT_DIGEST,
    PINNED_HTTP_DB_TEST_COMMAND,
    PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
    PINNED_HTTP_DB_VERIFIER_PROBE,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
    TARGET_RUNTIME_IMAGE_ID,
    VERIFIER_CONTEXT_MODULES,
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
    PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
)
from app_contracts.durable_stage import SQLiteStagedArtifactStore
from app_contracts.executor import (
    ExecutionError,
    ExecutionRequest,
    ExecutionStatus,
    VerifierInput,
    verifier_snapshot_tree_digest,
)
from app_contracts.github_http_transport import GitHubAnonymousSnapshotTransport
from app_contracts.github_snapshot import (
    GitHubSnapshotRequest,
    read_github_snapshot_contents,
)
from app_contracts.sandbox import DockerSandboxBackend
from app_contracts.stage_approval import run_local_mock_publication
from app_contracts.stage_preview import render_stage_preview
from app_contracts.verifier_container import (
    DockerContainerVerifier,
    VerifierContainerConfig,
)
from app_contracts.worker_cli import run_remote_snapshot_execution


def _http_db_verifier_input(
    snapshot_files: tuple[tuple[str, str, bytes], ...], candidate: str
) -> VerifierInput:
    contents = (("backend/routes.py", candidate),)
    return VerifierInput(
        process_id="process-exp522-http-db-001",
        repository_id=f"{PINNED_OWNER}/{PINNED_REPOSITORY}",
        base_commit=PINNED_COMMIT,
        snapshot_tree_digest=verifier_snapshot_tree_digest(snapshot_files),
        declared_change_paths=("backend/routes.py",),
        verified_contents=contents,
        test_command=PINNED_HTTP_DB_TEST_COMMAND,
        test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
        patch_digest=sha256_bytes(candidate.encode("utf-8")),
        evidence_digest=sha256_bytes(b"EXP-522 bounded synthetic verifier input"),
        verification_digest=sha256_bytes(b"EXP-522 expected HTTP/SQLite behavior"),
        verified_contents_digest=sha256_digest(contents),
        replay_result_digest=sha256_bytes(b"EXP-522 fixed local candidate replay"),
        snapshot_files=snapshot_files,
    )


def _target_sandbox_backend() -> DockerSandboxBackend:
    """Use the prepared target runtime, which supplies pinned app dependencies."""

    return DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID)

ROUTE_BEHAVIOR_PROBE = r'''import importlib.util
import sys
import types

effects = {"executes": [], "commits": 0}

class Router:
    def get(self, *_args, **_kwargs):
        return lambda function: function
    def post(self, *_args, **_kwargs):
        return lambda function: function

class HTTPException(Exception):
    def __init__(self, *, status_code, detail):
        self.status_code = status_code
        self.detail = detail

class Cursor:
    def execute(self, sql, values):
        effects["executes"].append((sql, values))

class Connection:
    def commit(self):
        effects["commits"] += 1

fastapi = types.ModuleType("fastapi")
fastapi.APIRouter = Router
fastapi.HTTPException = HTTPException
backend = types.ModuleType("backend")
backend.__path__ = []
logic = types.ModuleType("backend.logic")
logic.generate_example = lambda level: ("1+1", 2)
database = types.ModuleType("backend.database")
database.conn = Connection()
database.c = Cursor()
sys.modules.update({
    "fastapi": fastapi,
    "backend": backend,
    "backend.logic": logic,
    "backend.database": database,
})
spec = importlib.util.spec_from_file_location("target_routes", "backend/routes.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

try:
    module.save_session({"level": "not-an-integer"})
except HTTPException as error:
    assert error.status_code == 422
else:
    raise AssertionError("malformed numeric field was accepted")
assert effects == {"executes": [], "commits": 0}

module.save_session({
    "telegram_id": "synthetic-probe", "level": "2", "correct": "1",
    "wrong": "0", "total": "1", "time_ms": "250",
})
assert len(effects["executes"]) == 1
assert effects["executes"][0][1] == ("synthetic-probe", 2, 1, 0, 1, 250)
assert effects["commits"] == 1
'''


def _control_plane_candidate(source: str) -> str:
    candidate = source.replace(
        "from fastapi import APIRouter\n",
        "from fastapi import APIRouter, HTTPException\n",
        1,
    )
    old = (
        "    level = int(data.get('level', 1))\n"
        "    correct = int(data.get('correct', 0))\n"
        "    wrong = int(data.get('wrong', 0))\n"
        "    total = int(data.get('total', 10))\n"
        "    time_ms = int(data.get('time_ms', 0))\n"
    )
    new = (
        "    try:\n"
        "        level = int(data.get('level', 1))\n"
        "        correct = int(data.get('correct', 0))\n"
        "        wrong = int(data.get('wrong', 0))\n"
        "        total = int(data.get('total', 10))\n"
        "        time_ms = int(data.get('time_ms', 0))\n"
        "    except (OverflowError, TypeError, ValueError):\n"
        "        raise HTTPException(status_code=422, detail='numeric session fields must be integers') from None\n"
    )
    if candidate == source or candidate.count(old) != 1:
        raise ValueError("synthetic candidate base did not match pinned route")
    return candidate.replace(old, new, 1)


class _FixedProposalChannel:
    """Explicitly synthetic one-shot channel; it never contacts a provider."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        del payload, timeout_seconds
        self.calls += 1
        output = json.dumps(
            {"changes": [{"path": "backend/routes.py", "content": self.content}]},
            separators=(",", ":"),
        )
        return ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason="stop",
                    message=ChatCompletionMessage(role="assistant", content=output),
                ),
            )
        )


def _build_verifier_runtime() -> tuple[str, str, str]:
    docker = shutil.which("docker")
    if not docker or not Path(docker).is_absolute():
        raise RuntimeError("Docker executable unavailable")
    source_root = ROOT / "src" / "app_contracts"
    with tempfile.TemporaryDirectory(prefix="agent00x-exp466-build-") as build_root, tempfile.TemporaryDirectory(
        prefix="agent00x-exp466-docker-config-"
    ) as docker_config:
        context = Path(build_root)
        package_dir = context / "src" / "app_contracts"
        package_dir.mkdir(parents=True)
        shutil.copyfile(ROOT / "containers" / "verifier" / "Dockerfile", context / "Dockerfile")
        shutil.copyfile(
            ROOT / "containers" / "target-runtime" / "requirements.lock",
            context / "requirements.lock",
        )
        for module in VERIFIER_CONTEXT_MODULES:
            shutil.copyfile(source_root / module, package_dir / module)

        env = dict(os.environ)
        env["DOCKER_CONFIG"] = docker_config
        env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
        image_inspect = subprocess.run(
            [docker, "--host=unix:///var/run/docker.sock", "image", "inspect", "--format", "{{.Id}}", TARGET_RUNTIME_IMAGE_ID],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=env,
        )
        if image_inspect.returncode != 0 or image_inspect.stdout.strip() != TARGET_RUNTIME_IMAGE_ID:
            raise RuntimeError("pinned target dependency image unavailable")
        source_container = subprocess.run(
            [docker, "--host=unix:///var/run/docker.sock", "create", TARGET_RUNTIME_IMAGE_ID],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=env,
        )
        container_id = source_container.stdout.strip()
        if source_container.returncode != 0 or not container_id:
            raise RuntimeError("pinned target dependency image cannot be copied")
        try:
            (context / "target-python").mkdir()
            package_copy = subprocess.run(
                [docker, "--host=unix:///var/run/docker.sock", "cp", f"{container_id}:/opt/target-python/.", str(context / "target-python")],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=env,
            )
            if package_copy.returncode != 0:
                raise RuntimeError("pinned target dependencies cannot be copied")
        finally:
            subprocess.run(
                [docker, "--host=unix:///var/run/docker.sock", "rm", "--force", container_id],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                env=env,
            )

        code_hash = hashlib.sha256()
        identity_files = [context / "Dockerfile", context / "requirements.lock"]
        identity_files.extend(sorted(package_dir.iterdir(), key=lambda path: path.name))
        for path in identity_files:
            relative = path.relative_to(context).as_posix()
            code_hash.update(relative.encode("utf-8") + b"\0")
            code_hash.update(hashlib.sha256(path.read_bytes()).digest())
        code_digest = "sha256:" + code_hash.hexdigest()
        tag = "agent00x-verifier-exp466:" + uuid.uuid4().hex
        build = subprocess.run(
            [
                docker,
                "--host=unix:///var/run/docker.sock",
                "build",
                "--pull=false",
                "--network=none",
                "--build-arg",
                "SOURCE_DATE_EPOCH=0",
                "--tag",
                tag,
                str(context),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env=env,
        )
        if build.returncode != 0:
            raise RuntimeError("offline verifier image build failed")
        inspect = subprocess.run(
            [docker, "--host=unix:///var/run/docker.sock", "image", "inspect", "--format", "{{.Id}}", tag],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=env,
        )
        image_id = inspect.stdout.strip()
        if inspect.returncode != 0 or not image_id.startswith("sha256:"):
            raise RuntimeError("verifier image identity unavailable")
    return docker, image_id, code_digest


class PinnedTargetCommandContractTests(unittest.TestCase):
    def test_target_sandbox_uses_prepared_runtime_image(self):
        self.assertEqual(
            _target_sandbox_backend().image,
            "sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812",
        )

    def test_http_db_verifier_command_and_timeouts_are_fixed(self):
        self.assertEqual(PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS, 30)
        self.assertEqual(PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS, 60)
        self.assertEqual(PINNED_HTTP_DB_TEST_COMMAND[:2], ("python3", "-c"))
        self.assertEqual(
            PINNED_HTTP_DB_TEST_COMMAND[2], PINNED_HTTP_DB_VERIFIER_PROBE.strip()
        )
        self.assertIn("uvicorn", PINNED_HTTP_DB_VERIFIER_PROBE)
        self.assertIn("SELECT COUNT(*) FROM sessions", PINNED_HTTP_DB_VERIFIER_PROBE)
        self.assertIn("malformed=5 overflow=1 valid=1", PINNED_HTTP_DB_VERIFIER_PROBE)

    def test_route_probe_command_is_trimmed_before_execution_request(self):
        request_fields = {
            "process_id": "process-exp485-command-001",
            "task_id": "task-exp485-command-001",
            "repository_id": "SoldatovAlexander/brainbooster_full_v11",
            "base_commit": PINNED_COMMIT,
            "snapshot_path": ROOT,
            "allowed_commands": frozenset({"python3"}),
            "declared_change_paths": ("backend/routes.py",),
            "task_instruction": "synthetic request-shape regression check",
        }
        with self.assertRaisesRegex(
            ExecutionError, "^execution request: test command is invalid$"
        ):
            ExecutionRequest(
                **request_fields,
                test_command=("python3", "-c", ROUTE_BEHAVIOR_PROBE),
            )

        request = ExecutionRequest(
            **request_fields,
            test_command=("python3", "-c", ROUTE_BEHAVIOR_PROBE.strip()),
        )
        self.assertEqual(request.test_command[-1], ROUTE_BEHAVIOR_PROBE.strip())


@unittest.skipUnless(
    os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1",
    "pinned target Docker pipeline is opt-in",
)
class PinnedTargetStagePipelineTests(unittest.TestCase):
    def test_control_plane_candidate_reaches_trusted_container_stage_and_mock_receipt(self):
        docker = shutil.which("docker")
        self.assertTrue(docker and Path(docker).is_absolute())
        for image_id in (TARGET_RUNTIME_IMAGE_ID, VERIFIER_RUNTIME_IMAGE_ID):
            inspect = subprocess.run(
                [docker, "image", "inspect", "--format", "{{.Id}}", image_id],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(inspect.returncode, 0)
            self.assertEqual(inspect.stdout.strip(), image_id)
        verifier_image_id = VERIFIER_RUNTIME_IMAGE_ID
        verifier_code_digest = VERIFIER_RUNTIME_CODE_DIGEST
        env_config = tempfile.TemporaryDirectory(prefix="agent00x-exp466-docker-config-")
        self.addCleanup(env_config.cleanup)

        request = GitHubSnapshotRequest(
            owner=PINNED_OWNER,
            repository=PINNED_REPOSITORY,
            commit_oid=PINNED_COMMIT,
        )
        snapshot = read_github_snapshot_contents(
            request, GitHubAnonymousSnapshotTransport(timeout_seconds=15)
        )
        self.assertEqual(snapshot.claim.commit_oid, PINNED_COMMIT)
        self.assertEqual(snapshot.claim.tree_oid, PINNED_TREE)
        self.assertTrue(snapshot.claim.full_snapshot)
        self.assertEqual(len(snapshot.files), 23)
        self.assertEqual(snapshot.claim.content_digest, PINNED_CONTENT_DIGEST)
        route_blob = next(blob for blob in snapshot.files if blob.path == "backend/routes.py")
        candidate = _control_plane_candidate(route_blob.content.decode("utf-8"))
        candidate_digest = sha256_bytes(candidate.encode("utf-8"))
        self.assertEqual(candidate_digest, EXPECTED_CANDIDATE_DIGEST)

        channel = _FixedProposalChannel(candidate)
        worker = DeepSeekProposalWorker(channel)
        verifier = DockerContainerVerifier(
            VerifierContainerConfig(
                docker,
                verifier_image_id,
                verifier_code_digest,
                timeout_seconds=PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
                max_stdout_bytes=65_536,
                max_stderr_bytes=16_384,
            )
        )
        sandbox_backend = _target_sandbox_backend()
        test_command = PINNED_HTTP_DB_TEST_COMMAND
        with patch.dict(
            os.environ,
            {
                "DOCKER_CONFIG": env_config.name,
                "DOCKER_HOST": "unix:///var/run/docker.sock",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        ):
            with tempfile.TemporaryDirectory(prefix="agent00x-exp466-stage-") as stage_dir:
                stage_db = Path(stage_dir) / "stage.sqlite3"
                with SQLiteStagedArtifactStore(stage_db) as store:
                    result = run_remote_snapshot_execution(
                        snapshot,
                        process_id="process-exp466-target-001",
                        task_id="task-exp466-target-001",
                        task_instruction=(
                            "Control-plane synthetic candidate: reject malformed numeric "
                            "session input before database writes"
                        ),
                        declared_change_paths=("backend/routes.py",),
                        allowed_commands=frozenset({"python3"}),
                        test_command=test_command,
                        test_timeout_seconds=PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS,
                        worker=worker,
                        verifier=verifier,
                        sandbox_backend=sandbox_backend,
                        context_files=(("backend/routes.py", route_blob.content.decode("utf-8")),),
                        stage_sink=store,
                    )
                    self.assertEqual(result.status, ExecutionStatus.VERIFIED, repr(result))
                    self.assertEqual(channel.calls, 1)
                    self.assertIsNotNone(result.staged_change_digest)
                    self.assertEqual(
                        result.staged_change_digest,
                        store.load(result.staged_change_digest).staged_change_digest,
                    )
                    artifact = store.load(result.staged_change_digest)
                    payload = artifact.payload_copy()
                    self.assertEqual(
                        payload["seed"]["verified_contents_digest"],
                        result.verified_contents_digest,
                    )
                    self.assertEqual(
                        result.verifier_result.verifier_id,
                        f"docker-image:{verifier_image_id}/code:{verifier_code_digest}",
                    )

            preview = json.loads(render_stage_preview(artifact))
            self.assertEqual(preview["stage"]["staged_change_digest"], result.staged_change_digest)
            self.assertEqual(preview["approval"], "not_created")
            self.assertEqual(preview["publication"], "not_attempted")
            receipt = run_local_mock_publication(
                artifact,
                result.staged_change_digest,
                "agent/exp466-local-mock",
                now=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(receipt.staged_change_digest, result.staged_change_digest)
            self.assertEqual(receipt.repository_id, f"{PINNED_OWNER}/{PINNED_REPOSITORY}")


if __name__ == "__main__":
    unittest.main()
