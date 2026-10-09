"""Opt-in actual Worker-in-container stdio integration with a fake model host."""

from __future__ import annotations

import json
import os
from pathlib import Path
import select
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import uuid
import unittest

from app_contracts.brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID
from app_contracts.deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
    build_chat_completions_payload,
)
from app_contracts.executor import WorkerInput
from app_contracts.worker_model_ipc import (
    _MAX_REQUEST_BYTES,
    _MAX_RESPONSE_BYTES,
    _decode_json,
    _encode_result,
)


REQUEST_SCHEMA = "agent00x-worker-model-request/v1"
WORKER_INPUT_SCHEMA = "agent00x-worker-input/v1"
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
CHILD_PROGRAM = r'''
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
        "declared_change_paths", "task_instruction", "context_files"
    } or task_envelope.get("schema") != "agent00x-worker-input/v1":
        raise ValueError
    task = WorkerInput(
        process_id=task_envelope["process_id"],
        task_id=task_envelope["task_id"],
        repository_id=task_envelope["repository_id"],
        base_commit=task_envelope["base_commit"],
        declared_change_paths=tuple(task_envelope["declared_change_paths"]),
        task_instruction=task_envelope["task_instruction"],
        context_files=tuple((item["path"], item["content"]) for item in task_envelope["context_files"]),
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


def _encode_frame(value: object, *, maximum: int) -> bytes:
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


def _decode_frame(frame: bytes, *, maximum: int) -> object:
    if type(frame) is not bytes or len(frame) < 5:
        raise ValueError("worker container frame invalid")
    (size,) = struct.unpack(">I", frame[:4])
    if size <= 0 or size > maximum or len(frame) != size + 4:
        raise ValueError("worker container frame exceeds limit")
    try:
        return json.loads(
            frame[4:].decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except Exception:
        raise ValueError("worker container frame invalid") from None


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
    try:
        return _decode_json(body, maximum=maximum)
    except Exception:
        raise ValueError("worker container frame invalid") from None


def _write_frame(stream, value: object, *, maximum: int) -> None:
    frame = _encode_frame(value, maximum=maximum)
    stream.write(frame)
    stream.flush()


def _container_not_found(returncode: object, stderr: object) -> bool:
    if type(returncode) is not int or returncode != 1 or type(stderr) is not bytes:
        return False
    diagnostic = stderr.lower()
    return b"no such object" in diagnostic or b"no such container" in diagnostic


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
    values: dict[str, str] = {}
    for entry in entries:
        if type(entry) is not str or "=" not in entry:
            return None
        name, value = entry.split("=", 1)
        if not name or name in values:
            return None
        values[name] = value
    return values


def _synthetic_task() -> WorkerInput:
    return WorkerInput(
        process_id="exp765-synthetic-process",
        task_id="exp765-synthetic-task",
        repository_id="synthetic-repository",
        base_commit="c" * 40,
        declared_change_paths=("calculator.py",),
        task_instruction="Fix the synthetic calculator edge case",
        context_files=(("calculator.py", "synthetic existing content"),),
    )


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


class FakeHostChannel:
    def __init__(self) -> None:
        self.calls = 0
        self.payload: dict | None = None
        self.timeout_seconds: float | None = None

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        self.calls += 1
        self.payload = payload
        self.timeout_seconds = timeout_seconds
        return ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=(
                            '{"changes":[{"path":"calculator.py",'
                            '"content":"fixed by container worker"}]}'
                        ),
                        reasoning_content="synthetic reasoning must not cross IPC",
                    ),
                ),
            )
        )


class WorkerContainerStdioTests(unittest.TestCase):
    def test_embedded_worker_program_is_syntactically_valid(self):
        compile(CHILD_PROGRAM, "<worker-container-program>", "exec")

    def test_fixed_import_categories_are_allowlisted(self):
        self.assertTrue(WORKER_STATUS_CATEGORIES)
        self.assertTrue(
            all(
                category.isascii()
                and category.replace("-", "").isalnum()
                and category == category.lower()
                for category in WORKER_STATUS_CATEGORIES
            )
        )
        self.assertIn("observation-store-import-failed", WORKER_STATUS_CATEGORIES)
        self.assertIn("observer-runtime-import-failed", WORKER_STATUS_CATEGORIES)

    def test_schema_staging_contains_only_fixed_required_inputs(self):
        with tempfile.TemporaryDirectory() as source_temp:
            with tempfile.TemporaryDirectory() as staging_temp:
                source_directory = Path(source_temp)
                staging_directory = Path(staging_temp)
                for name in WORKER_SCHEMA_FILES:
                    (source_directory / name).write_text(name, encoding="utf-8")
                (source_directory / "unrelated.schema.json").write_text(
                    "unrelated", encoding="utf-8"
                )

                _stage_worker_schemas(source_directory, staging_directory)

                self.assertEqual(
                    {path.name for path in staging_directory.iterdir()},
                    set(WORKER_SCHEMA_FILES),
                )
                for name in WORKER_SCHEMA_FILES:
                    self.assertEqual(
                        (staging_directory / name).read_text(encoding="utf-8"),
                        name,
                    )

    def test_environment_comparison_ignores_order_but_rejects_duplicates(self):
        expected = ["PATH=/usr/bin", "PYTHONPATH=/opt/target", "FLAG=1"]
        self.assertEqual(
            _environment_mapping(expected),
            _environment_mapping(["FLAG=1", "PATH=/usr/bin", "PYTHONPATH=/opt/target"]),
        )
        self.assertIsNone(
            _environment_mapping(["PATH=/usr/bin", "PATH=/bin"])
        )
        self.assertIsNone(_environment_mapping(["PATH=/usr/bin", "MALFORMED"]))

    def test_status_parser_accepts_only_fixed_phase_categories(self):
        self.assertEqual(
            _status_category(
                {"schema": STATUS_SCHEMA, "status": "worker-input-imported"}
            ),
            "worker-input-imported",
        )
        self.assertIsNone(
            _status_category(
                {"schema": STATUS_SCHEMA, "status": "ModuleNotFoundError: raw"}
            )
        )
        self.assertIsNone(_status_category({"schema": STATUS_SCHEMA, "status": "ready", "detail": "x"}))

    def test_cleanup_classifier_requires_explicit_not_found_marker(self):
        self.assertTrue(_container_not_found(1, b"Error: No such object: synthetic"))
        self.assertFalse(_container_not_found(1, b"daemon unavailable"))
        self.assertFalse(_container_not_found(0, b"No such object"))

    def _expect_status(self, process, expected: str) -> None:
        try:
            frame = _read_frame(
                process.stdout,
                maximum=4096,
                deadline=time.monotonic() + 10,
            )
        except Exception:
            exit_code = process.poll()
            if exit_code is None:
                try:
                    process.terminate()
                    exit_code = process.wait(timeout=3)
                except Exception:
                    try:
                        process.kill()
                        exit_code = process.wait(timeout=3)
                    except Exception:
                        exit_code = -1
            self.fail(f"worker startup produced no status frame (runner_exit={exit_code})")
        observed = _status_category(frame)
        if observed is None:
            self.fail("worker startup status frame invalid")
        if observed != expected:
            self.fail(f"worker startup stopped (phase={observed})")

    def test_local_frame_helpers_reject_duplicate_and_oversized_input(self):
        frame = _encode_frame({"schema": REQUEST_SCHEMA, "content": "synthetic"}, maximum=256)
        self.assertEqual(
            _decode_frame(frame, maximum=256),
            {"schema": REQUEST_SCHEMA, "content": "synthetic"},
        )
        duplicate = b'{"schema":"x","schema":"y"}'
        with self.assertRaisesRegex(ValueError, "frame invalid"):
            _decode_frame(struct.pack(">I", len(duplicate)) + duplicate, maximum=256)
        with self.assertRaisesRegex(ValueError, "exceeds limit"):
            _encode_frame({"value": "x" * 256}, maximum=256)

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1",
        "actual Worker container stdio test is opt-in",
    )
    def _legacy_actual_worker_runs_network_none_and_returns_fake_candidate(self):
        docker = os.environ.get("AGENT00X_DOCKER_EXECUTABLE") or shutil.which("docker")
        self.assertIsInstance(docker, str, "Docker executable unavailable")
        self.assertTrue(Path(docker).is_absolute(), "Docker executable must be absolute")
        root = Path(__file__).resolve().parents[1]
        source_directory = root / "src" / "app_contracts"
        self.assertTrue(source_directory.is_dir(), "worker source unavailable")
        self.assertFalse(source_directory.is_symlink(), "worker source unavailable")
        schema_source_directory = root / "schemas"
        self.assertTrue(schema_source_directory.is_dir(), "worker schemas unavailable")
        schema_mount = tempfile.TemporaryDirectory(prefix="agent00x-exp772-schemas-")
        schema_directory = Path(schema_mount.name)
        _stage_worker_schemas(schema_source_directory, schema_directory)

        try:
            image = subprocess.run(
                [docker, "image", "inspect", "--format={{json .Config.Env}}", TARGET_RUNTIME_IMAGE_ID],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception:
            self.fail("pinned target image preflight failed")
        self.assertEqual(image.returncode, 0, "pinned target image unavailable")
        try:
            image_environment = json.loads(image.stdout)
        except Exception:
            self.fail("pinned target image metadata was malformed")
        expected_environment = [
            item for item in image_environment if not item.startswith("PYTHONPATH=")
        ] + [f"PYTHONPATH={CONTAINER_PYTHONPATH}"]

        task = _synthetic_task()
        task_frame = {
            "schema": WORKER_INPUT_SCHEMA,
            "process_id": task.process_id,
            "task_id": task.task_id,
            "repository_id": task.repository_id,
            "base_commit": task.base_commit,
            "declared_change_paths": list(task.declared_change_paths),
            "task_instruction": task.task_instruction,
            "context_files": [
                {"path": path, "content": content}
                for path, content in task.context_files
            ],
        }
        container_name = f"agent00x-exp765-{uuid.uuid4().hex}"
        command = [
            docker,
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
            CHILD_PROGRAM,
        ]
        process: subprocess.Popen | None = None
        try:
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=False,
                )
            except Exception:
                self.fail("worker container process could not start")
            self.assertIsNotNone(process.stdin)
            self.assertIsNotNone(process.stdout)
            _write_frame(process.stdin, task_frame, maximum=_MAX_REQUEST_BYTES)

            for expected_status in (
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
            ):
                self._expect_status(process, expected_status)

            try:
                request = _read_frame(
                    process.stdout,
                    maximum=_MAX_REQUEST_BYTES,
                    deadline=time.monotonic() + 15,
                )
            except Exception:
                self._expect_status(process, "ready")
                raise AssertionError("worker model request unavailable") from None
            expected_payload = build_chat_completions_payload(task)
            self.assertTrue(
                type(request) is dict
                and set(request) == {"schema", "timeout_seconds", "payload"}
                and request.get("schema") == REQUEST_SCHEMA
                and type(request.get("timeout_seconds")) in (int, float)
                and 0 < request["timeout_seconds"] <= 30
                and request.get("payload") == expected_payload,
                "worker model request mismatch",
            )

            try:
                inspect = subprocess.run(
                    [docker, "inspect", INSPECT_JSON, container_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except Exception:
                self.fail("worker container inspection failed")
            self.assertEqual(inspect.returncode, 0, "worker container inspection failed")
            try:
                details = json.loads(inspect.stdout)
                if type(details) is not dict:
                    raise ValueError
                host_config = details["HostConfig"]
                config = details["Config"]
                state = details["State"]
                mounts = details["Mounts"]
            except Exception:
                self.fail("worker container inspection was malformed")
            self.assertIs(state.get("Running"), True)
            self.assertEqual(details.get("Image"), TARGET_RUNTIME_IMAGE_ID)
            self.assertEqual(host_config.get("NetworkMode"), "none")
            self.assertIs(host_config.get("ReadonlyRootfs"), True)
            self.assertIn("ALL", host_config.get("CapDrop", []))
            self.assertTrue(
                any("no-new-privileges" in item for item in host_config.get("SecurityOpt", []))
            )
            self.assertEqual(config.get("User"), CONTAINER_USER)
            self.assertIs(config.get("OpenStdin"), True)
            self.assertIs(config.get("Tty"), False)
            self.assertEqual(
                _environment_mapping(config.get("Env")),
                _environment_mapping(expected_environment),
            )
            self.assertEqual(host_config.get("PidsLimit"), 16)
            self.assertEqual(host_config.get("Memory"), 256 * 1024 * 1024)
            self.assertEqual(host_config.get("NanoCpus"), 500_000_000)
            self.assertEqual(len(mounts), 2)
            mounts_by_destination = {
                mount.get("Destination"): mount for mount in mounts
            }
            self.assertEqual(
                set(mounts_by_destination),
                {CONTAINER_PACKAGE_PATH, CONTAINER_SCHEMA_PATH},
            )
            expected_mounts = {
                CONTAINER_PACKAGE_PATH: source_directory,
                CONTAINER_SCHEMA_PATH: schema_directory,
            }
            for destination, source in expected_mounts.items():
                mount = mounts_by_destination[destination]
                self.assertTrue(
                    mount.get("Type") == "bind"
                    and mount.get("Source") == str(source)
                    and mount.get("RW") is False,
                    "worker read-only mount mismatch",
                )

            host_channel = FakeHostChannel()
            result = host_channel.create_chat_completion(
                request["payload"],
                timeout_seconds=request["timeout_seconds"],
            )
            self.assertEqual(host_channel.calls, 1)
            response = _encode_result(result)
            self.assertNotIn(b"synthetic reasoning must not cross IPC", response)
            self.assertLessEqual(len(response), _MAX_RESPONSE_BYTES)
            _write_frame(process.stdin, _decode_json(response, maximum=_MAX_RESPONSE_BYTES), maximum=_MAX_RESPONSE_BYTES)

            proposal = _read_frame(
                process.stdout,
                maximum=_MAX_RESPONSE_BYTES,
                deadline=time.monotonic() + 15,
            )
            self.assertTrue(
                proposal
                == {
                    "schema": PROPOSAL_SCHEMA,
                    "changes": [["calculator.py", "fixed by container worker"]],
                },
                "worker proposal mismatch",
            )
            process.stdin.close()
            process.stdin = None
            process.wait(timeout=10)
            self.assertEqual(process.returncode, 0, "worker container process failed")
            self.assertEqual(host_channel.calls, 1)
            self.assertLessEqual(host_channel.timeout_seconds, 30)
        finally:
            cleanup_unconfirmed = False
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=3)
                except Exception:
                    try:
                        process.kill()
                        process.wait(timeout=3)
                    except Exception:
                        pass
            if process is not None:
                try:
                    subprocess.run(
                        [docker, "rm", "--force", container_name],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                except Exception:
                    cleanup_unconfirmed = True
            if process is not None:
                try:
                    remaining = subprocess.run(
                        [docker, "inspect", INSPECT_ID, container_name],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    )
                except Exception:
                    cleanup_unconfirmed = True
                else:
                    if not _container_not_found(
                        remaining.returncode,
                        remaining.stderr,
                    ):
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
                self.fail("worker container cleanup could not be confirmed")


if __name__ == "__main__":
    unittest.main()
