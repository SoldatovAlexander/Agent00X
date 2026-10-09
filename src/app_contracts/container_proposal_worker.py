"""One-shot proposal Worker isolated in the pinned network-disabled container."""

from __future__ import annotations

import json
import os
from pathlib import Path
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import threading
import time
import uuid

from .brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID
from .deepseek_worker import build_chat_completions_payload
from .executor import ExecutionError, WorkerInput, WorkerProposal
from .openai_worker import ResponsesModelResult, parse_model_result
from .worker_model_ipc import _decode_json, _encode_result
from .worker_model_protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_TIMEOUT_SECONDS,
    encode_chat_completions_request,
)


REQUEST_SCHEMA = "agent00x-worker-model-request/v1"
WORKER_INPUT_SCHEMA = "agent00x-worker-input/v2"
PROPOSAL_SCHEMA = "agent00x-worker-proposal/v1"
STATUS_SCHEMA = "agent00x-worker-status/v1"
INSPECT_JSON = "--format={{json .}}"
INSPECT_ID = "--format={{.Id}}"
CONTAINER_USER = f"{os.getuid()}:{os.getgid()}"
CONTAINER_PACKAGE_PATH = "/opt/agent00x/app_contracts"
CONTAINER_SCHEMA_PATH = "/opt/schemas"
CONTAINER_PYTHONPATH = "/opt/agent00x:/opt/target-python"
WORKER_SCHEMA_FILES = (
    "observation-event.schema.json",
    "checkpoint.schema.json",
)
WORKER_STARTUP_STATUSES = (
    "source-package-visible",
    "dependency-1-imported",
    "observation-store-imported",
    "observer-runtime-imported",
    "dependency-3-imported",
    "dependency-4-imported",
    "dependency-5-imported",
    "worker-input-imported",
    "deepseek-worker-imported",
    "stdio-ipc-imported",
    "task-accepted",
    "network-probes-blocked",
    "ready",
)
WORKER_STATUS_CATEGORIES = frozenset(
    {
        "source-package-unavailable",
        "source-package-visible",
        "dependency-1-import-failed",
        "dependency-1-imported",
        "observation-store-import-failed",
        "observation-store-imported",
        "observer-runtime-import-failed",
        "observer-runtime-imported",
        "dependency-3-import-failed",
        "dependency-3-imported",
        "dependency-4-import-failed",
        "dependency-4-imported",
        "dependency-5-import-failed",
        "dependency-5-imported",
        "deepseek-worker-import-failed",
        "deepseek-worker-imported",
        "worker-input-import-failed",
        "worker-input-imported",
        "stdio-ipc-import-failed",
        "stdio-ipc-imported",
        "task-frame-invalid",
        "task-accepted",
        "direct-ip-unblocked",
        "dns-unblocked",
        "network-probes-blocked",
        "ready",
        "worker-runtime-failed",
    }
)
WORKER_CHILD_PROGRAM = r'''
import importlib.util, json, os, select, signal, socket, struct, sys, time
sys.dont_write_bytecode = True
MAX_FRAME = 128000
STATUS_SCHEMA = "agent00x-worker-status/v1"
def reject_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result
def read_exact(stream, size):
    result = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise SystemExit(31)
        result.append(chunk)
        remaining -= len(chunk)
    return b"".join(result)
def read_frame(stream, maximum):
    size = struct.unpack(">I", read_exact(stream, 4))[0]
    if size <= 0 or size > maximum:
        raise SystemExit(32)
    return json.loads(read_exact(stream, size).decode("utf-8"), object_pairs_hook=reject_pairs)
def write_frame(stream, value, maximum):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if not data or len(data) > maximum:
        raise SystemExit(33)
    stream.write(struct.pack(">I", len(data)) + data)
    stream.flush()
def status(value):
    write_frame(sys.stdout.buffer, {"schema": STATUS_SCHEMA, "status": value}, 4096)
try:
    package_spec = importlib.util.find_spec("app_contracts")
    package_locations = tuple(package_spec.submodule_search_locations or ()) if package_spec else ()
    if "/opt/agent00x/app_contracts" not in package_locations:
        status("source-package-unavailable")
        raise SystemExit(40)
except SystemExit:
    raise
except Exception:
    status("source-package-unavailable")
    raise SystemExit(40)
status("source-package-visible")
try:
    import app_contracts.repository_process
except Exception:
    status("dependency-1-import-failed")
    raise SystemExit(40)
status("dependency-1-imported")
try:
    import app_contracts.observation_store
except Exception:
    status("observation-store-import-failed")
    raise SystemExit(40)
status("observation-store-imported")
try:
    import app_contracts.observer_runtime
except Exception:
    status("observer-runtime-import-failed")
    raise SystemExit(40)
status("observer-runtime-imported")
try:
    import app_contracts.sandbox
except Exception:
    status("dependency-3-import-failed")
    raise SystemExit(40)
status("dependency-3-imported")
try:
    import app_contracts.digests
except Exception:
    status("dependency-4-import-failed")
    raise SystemExit(40)
status("dependency-4-imported")
try:
    import app_contracts.pinned_snapshot
except Exception:
    status("dependency-5-import-failed")
    raise SystemExit(40)
status("dependency-5-imported")
try:
    from app_contracts.executor import WorkerInput
except Exception:
    status("worker-input-import-failed")
    raise SystemExit(40)
status("worker-input-imported")
try:
    from app_contracts.deepseek_worker import DeepSeekProposalWorker
except Exception:
    status("deepseek-worker-import-failed")
    raise SystemExit(40)
status("deepseek-worker-imported")
try:
    from app_contracts.worker_model_ipc import StdioChatCompletionsChannel
except Exception:
    status("stdio-ipc-import-failed")
    raise SystemExit(40)
status("stdio-ipc-imported")
def probe_network():
    direct = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    direct.settimeout(1)
    try:
        direct.connect(("1.1.1.1", 53))
    except OSError:
        pass
    else:
        return "direct-ip-unblocked"
    finally:
        direct.close()
    def deadline_handler(_signum, _frame):
        raise TimeoutError()
    signal.signal(signal.SIGALRM, deadline_handler)
    signal.alarm(3)
    try:
        try:
            socket.getaddrinfo("api.github.com", 443)
        except (OSError, InterruptedError, TimeoutError):
            return "network-probes-blocked"
        else:
            return "dns-unblocked"
    finally:
        signal.alarm(0)
try:
    task_envelope = read_frame(sys.stdin.buffer, MAX_FRAME)
    if type(task_envelope) is not dict or set(task_envelope) != {
        "schema", "process_id", "task_id", "repository_id", "base_commit",
        "declared_change_paths", "snapshot_tree_digest", "snapshot_origin",
        "task_instruction", "context_files", "snapshot_claim_digest"
    } or task_envelope.get("schema") != "agent00x-worker-input/v2":
        raise ValueError
    task = WorkerInput(
        process_id=task_envelope["process_id"],
        task_id=task_envelope["task_id"],
        repository_id=task_envelope["repository_id"],
        base_commit=task_envelope["base_commit"],
        declared_change_paths=tuple(task_envelope["declared_change_paths"]),
        snapshot_tree_digest=task_envelope["snapshot_tree_digest"],
        snapshot_origin=task_envelope["snapshot_origin"],
        task_instruction=task_envelope["task_instruction"],
        context_files=tuple((item["path"], item["content"]) for item in task_envelope["context_files"]),
        snapshot_claim_digest=task_envelope["snapshot_claim_digest"],
    )
except Exception:
    status("task-frame-invalid")
    raise SystemExit(41)
status("task-accepted")
network_status = probe_network()
if network_status != "network-probes-blocked":
    status(network_status)
    raise SystemExit(42)
status("network-probes-blocked")
channel = StdioChatCompletionsChannel(sys.stdin.buffer, sys.stdout.buffer)
worker = DeepSeekProposalWorker(channel=channel)
status("ready")
try:
    proposal = worker.propose(task)
except Exception:
    status("worker-runtime-failed")
    raise SystemExit(43)
write_frame(sys.stdout.buffer, {
    "schema": "agent00x-worker-proposal/v1",
    "changes": proposal.changes,
}, 65536)
'''.strip()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _frame_bytes(value: object, *, maximum: int) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        raise ValueError("worker container frame invalid") from None
    if not payload or len(payload) > maximum:
        raise ValueError("worker container frame exceeds limit")
    return struct.pack(">I", len(payload)) + payload


def _read_exact(stream, size: int, *, deadline: float) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    descriptor = stream.fileno()
    while remaining:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise ValueError("worker container exchange timed out")
        readable, _writable, _exceptional = select.select(
            [descriptor], [], [], timeout
        )
        if not readable:
            raise ValueError("worker container exchange timed out")
        chunk = os.read(descriptor, remaining)
        if not chunk:
            raise ValueError("worker container transport failed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_frame(stream, *, maximum: int, deadline: float) -> object:
    prefix = _read_exact(stream, 4, deadline=deadline)
    (size,) = struct.unpack(">I", prefix)
    if size <= 0 or size > maximum:
        raise ValueError("worker container frame exceeds limit")
    body = _read_exact(stream, size, deadline=deadline)
    return _decode_json(body, maximum=maximum)


def _write_frame(stream, value: object, *, maximum: int) -> None:
    stream.write(_frame_bytes(value, maximum=maximum))
    stream.flush()


def _status_category(frame: object) -> str | None:
    if (
        type(frame) is not dict
        or set(frame) != {"schema", "status"}
        or frame.get("schema") != STATUS_SCHEMA
        or type(frame.get("status")) is not str
        or frame.get("status") not in WORKER_STATUS_CATEGORIES
    ):
        return None
    return frame["status"]


def _environment_mapping(entries: object) -> dict[str, str] | None:
    if type(entries) is not list:
        return None
    result: dict[str, str] = {}
    for entry in entries:
        if type(entry) is not str or "=" not in entry:
            return None
        name, value = entry.split("=", 1)
        if not name or name in result:
            return None
        result[name] = value
    return result


def _stage_worker_schemas(source_directory: Path, staging_directory: Path) -> None:
    if not source_directory.is_dir() or not staging_directory.is_dir():
        raise ValueError("schema staging unavailable")
    for name in WORKER_SCHEMA_FILES:
        source = source_directory / name
        if not source.is_file() or source.is_symlink():
            raise ValueError("schema staging unavailable")
        shutil.copyfile(source, staging_directory / name)
    if {path.name for path in staging_directory.iterdir()} != set(WORKER_SCHEMA_FILES):
        raise ValueError("schema staging mismatch")


def _worker_input_frame(task: WorkerInput) -> dict[str, object]:
    return {
        "schema": WORKER_INPUT_SCHEMA,
        "process_id": task.process_id,
        "task_id": task.task_id,
        "repository_id": task.repository_id,
        "base_commit": task.base_commit,
        "declared_change_paths": list(task.declared_change_paths),
        "snapshot_tree_digest": task.snapshot_tree_digest,
        "snapshot_origin": task.snapshot_origin,
        "task_instruction": task.task_instruction,
        "context_files": [
            {"path": path, "content": content}
            for path, content in task.context_files
        ],
        "snapshot_claim_digest": task.snapshot_claim_digest,
    }


def _container_not_found(returncode: object, stderr: object) -> bool:
    if type(returncode) is not int or returncode != 1 or type(stderr) is not bytes:
        return False
    diagnostic = stderr.lower()
    return b"no such object" in diagnostic or b"no such container" in diagnostic


class ContainerProposalWorker:
    """Run one DeepSeek proposal worker inside the fixed network-none image.

    The model channel stays on the host and is injected by the caller. Nothing
    from its credential source or process environment is passed into the
    container. The adapter is one-shot and suppresses all child diagnostics.
    """

    def __init__(self, channel: object, *, docker_executable: str | None = None) -> None:
        if not callable(getattr(channel, "create_chat_completion", None)):
            raise ExecutionError("execution worker: isolated worker unavailable")
        docker = docker_executable or shutil.which("docker")
        if (
            type(docker) is not str
            or not Path(docker).is_absolute()
            or os.getuid() == 0
        ):
            raise ExecutionError("execution worker: isolated worker unavailable")
        self._channel = channel
        self._docker = docker
        self._used = False
        self._used_lock = threading.Lock()

    def propose(self, task: WorkerInput) -> WorkerProposal:
        with self._used_lock:
            if self._used or type(task) is not WorkerInput:
                raise ExecutionError("execution worker: isolated worker unavailable")
            self._used = True
        root = Path(__file__).resolve().parents[2]
        source_directory = root / "src" / "app_contracts"
        schema_source_directory = root / "schemas"
        if not source_directory.is_dir() or source_directory.is_symlink():
            raise ExecutionError("execution worker: isolated worker unavailable")
        if not schema_source_directory.is_dir() or schema_source_directory.is_symlink():
            raise ExecutionError("execution worker: isolated worker unavailable")

        container_name = f"agent00x-worker-{uuid.uuid4().hex}"
        process: subprocess.Popen | None = None
        cleanup_unconfirmed = False
        schema_mount = tempfile.TemporaryDirectory(prefix="agent00x-worker-schemas-")
        schema_directory = Path(schema_mount.name)
        try:
            _stage_worker_schemas(schema_source_directory, schema_directory)
            image_environment = self._image_environment()
            expected_environment = [
                item for item in image_environment if not item.startswith("PYTHONPATH=")
            ] + [f"PYTHONPATH={CONTAINER_PYTHONPATH}"]
            command = [
                self._docker,
                "run",
                "--interactive",
                "--rm",
                "--name",
                container_name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                CONTAINER_USER,
                "--pids-limit",
                "16",
                "--memory",
                "256m",
                "--cpus",
                "0.5",
                "--mount",
                f"type=bind,src={source_directory},dst={CONTAINER_PACKAGE_PATH},readonly",
                "--mount",
                f"type=bind,src={schema_directory},dst={CONTAINER_SCHEMA_PATH},readonly",
                "--env",
                f"PYTHONPATH={CONTAINER_PYTHONPATH}",
                TARGET_RUNTIME_IMAGE_ID,
                "python3",
                "-c",
                WORKER_CHILD_PROGRAM,
            ]
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=False,
                )
            except Exception:
                raise ExecutionError("execution worker: isolated worker unavailable") from None
            if process.stdin is None or process.stdout is None:
                raise ExecutionError("execution worker: isolated worker unavailable")
            _write_frame(process.stdin, _worker_input_frame(task), maximum=MAX_REQUEST_BYTES)
            for expected in WORKER_STARTUP_STATUSES:
                self._expect_status(process, expected)

            request = _read_frame(
                process.stdout,
                maximum=MAX_REQUEST_BYTES,
                deadline=time.monotonic() + MAX_TIMEOUT_SECONDS,
            )
            payload = build_chat_completions_payload(task)
            if (
                type(request) is not dict
                or set(request) != {"schema", "timeout_seconds", "payload"}
                or request.get("schema") != REQUEST_SCHEMA
                or type(request.get("timeout_seconds")) not in (int, float)
                or not 0 < request["timeout_seconds"] <= MAX_TIMEOUT_SECONDS
                or request.get("payload") != payload
            ):
                raise ExecutionError("execution worker: isolated worker request invalid")
            encode_chat_completions_request(request["payload"])
            self._assert_container(container_name, source_directory, schema_directory, expected_environment)

            try:
                result = self._channel.create_chat_completion(
                    request["payload"],
                    timeout_seconds=request["timeout_seconds"],
                )
                encoded_response = _encode_result(result)
                response = _decode_json(encoded_response, maximum=MAX_RESPONSE_BYTES)
            except Exception:
                raise ExecutionError("execution worker: model channel failed") from None
            _write_frame(process.stdin, response, maximum=MAX_RESPONSE_BYTES)

            proposal_frame = _read_frame(
                process.stdout,
                maximum=MAX_RESPONSE_BYTES,
                deadline=time.monotonic() + MAX_TIMEOUT_SECONDS,
            )
            proposal = self._validated_proposal(proposal_frame, task)
            try:
                process.stdin.close()
                process.stdin = None
                process.wait(timeout=10)
            except Exception:
                raise ExecutionError("execution worker: isolated worker failed") from None
            if process.returncode != 0:
                raise ExecutionError("execution worker: isolated worker failed")
            return proposal
        except ExecutionError:
            raise
        except Exception:
            raise ExecutionError("execution worker: isolated worker failed") from None
        finally:
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=3)
                except Exception:
                    try:
                        process.kill()
                        process.wait(timeout=3)
                    except Exception:
                        cleanup_unconfirmed = True
            if process is not None:
                try:
                    subprocess.run(
                        [self._docker, "rm", "--force", container_name],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                except Exception:
                    cleanup_unconfirmed = True
                try:
                    remaining = subprocess.run(
                        [self._docker, "inspect", INSPECT_ID, container_name],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    )
                except Exception:
                    cleanup_unconfirmed = True
                else:
                    if not _container_not_found(remaining.returncode, remaining.stderr):
                        cleanup_unconfirmed = True
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        try:
                            stream.close()
                        except Exception:
                            cleanup_unconfirmed = True
            schema_mount.cleanup()
            if schema_directory.exists():
                cleanup_unconfirmed = True
            if cleanup_unconfirmed:
                raise ExecutionError("execution worker: isolated worker cleanup failed") from None

    def _image_environment(self) -> list[str]:
        try:
            result = subprocess.run(
                [self._docker, "image", "inspect", "--format={{json .Config.Env}}", TARGET_RUNTIME_IMAGE_ID],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode != 0:
                raise ValueError
            value = json.loads(result.stdout)
            if type(value) is not list or any(type(item) is not str for item in value):
                raise ValueError
            return value
        except Exception:
            raise ExecutionError("execution worker: pinned image unavailable") from None

    def _expect_status(self, process: subprocess.Popen, expected: str) -> None:
        if process.stdout is None:
            raise ExecutionError("execution worker: isolated worker startup failed")
        try:
            frame = _read_frame(
                process.stdout,
                maximum=4096,
                deadline=time.monotonic() + 10,
            )
            observed = _status_category(frame)
        except Exception:
            raise ExecutionError("execution worker: isolated worker startup failed") from None
        if observed != expected:
            raise ExecutionError("execution worker: isolated worker startup failed")

    def _assert_container(
        self,
        container_name: str,
        source_directory: Path,
        schema_directory: Path,
        expected_environment: list[str],
    ) -> None:
        try:
            result = subprocess.run(
                [self._docker, "inspect", INSPECT_JSON, container_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                raise ValueError
            details = json.loads(result.stdout)
            host_config = details["HostConfig"]
            config = details["Config"]
            mounts = details["Mounts"]
            if (
                details.get("Image") != TARGET_RUNTIME_IMAGE_ID
                or details.get("State", {}).get("Running") is not True
                or host_config.get("NetworkMode") != "none"
                or host_config.get("ReadonlyRootfs") is not True
                or "ALL" not in host_config.get("CapDrop", [])
                or not any("no-new-privileges" in item for item in host_config.get("SecurityOpt", []))
                or config.get("User") != CONTAINER_USER
                or config.get("OpenStdin") is not True
                or config.get("Tty") is not False
                or _environment_mapping(config.get("Env")) != _environment_mapping(expected_environment)
                or host_config.get("PidsLimit") != 16
                or host_config.get("Memory") != 256 * 1024 * 1024
                or host_config.get("NanoCpus") != 500_000_000
                or type(mounts) is not list
                or len(mounts) != 2
                or _environment_mapping(expected_environment) is None
                or _environment_mapping(config.get("Env")) is None
            ):
                raise ValueError
            mounts_by_destination = {mount.get("Destination"): mount for mount in mounts}
            expected_mounts = {
                CONTAINER_PACKAGE_PATH: source_directory,
                CONTAINER_SCHEMA_PATH: schema_directory,
            }
            if set(mounts_by_destination) != set(expected_mounts):
                raise ValueError
            for destination, source in expected_mounts.items():
                mount = mounts_by_destination[destination]
                if (
                    mount.get("Type") != "bind"
                    or mount.get("Source") != str(source)
                    or mount.get("RW") is not False
                ):
                    raise ValueError
        except Exception:
            raise ExecutionError("execution worker: isolation contract failed") from None

    def _validated_proposal(self, frame: object, task: WorkerInput) -> WorkerProposal:
        if (
            type(frame) is not dict
            or set(frame) != {"schema", "changes"}
            or frame.get("schema") != PROPOSAL_SCHEMA
            or type(frame.get("changes")) is not list
        ):
            raise ExecutionError("execution worker: proposal is invalid")
        try:
            changes = frame["changes"]
            if any(
                type(change) is not list
                or len(change) != 2
                or type(change[0]) is not str
                or type(change[1]) is not str
                for change in changes
            ):
                raise ValueError
            output = json.dumps(
                {
                    "changes": [
                        {"path": path, "content": content}
                        for path, content in changes
                    ]
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            return parse_model_result(
                ResponsesModelResult(status="completed", output_text=output),
                task.declared_change_paths,
            )
        except Exception:
            raise ExecutionError("execution worker: proposal is invalid") from None
