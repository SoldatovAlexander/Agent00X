"""Opt-in synthetic stdio IPC probe for the pinned network-none image."""

from __future__ import annotations

import json
import os
from pathlib import Path
import select
import shutil
import struct
import subprocess
import sys
import time
import uuid
import unittest

from app_contracts.brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID
from app_contracts.deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
    DeepSeekProposalWorker,
    build_chat_completions_payload,
)
from app_contracts.executor import WorkerInput
from app_contracts.worker_model_ipc import (
    StdioChatCompletionsChannel,
    WorkerModelIPCError,
    _MAX_REQUEST_BYTES,
    _decode_json,
    _encode_result,
)


MAX_FRAME_BYTES = 16_384
REQUEST_SCHEMA = "agent00x-stdio-model-request/v1"
RESPONSE_SCHEMA = "agent00x-stdio-model-response/v1"
INSPECT_FORMAT_ARGUMENT = "--format={{json .}}"
CONTAINER_USER = f"{os.getuid()}:{os.getgid()}"
CHILD_PROGRAM = r'''
import json, struct, sys
def read_exact(stream, count):
    chunks = []
    remaining = count
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise SystemExit(21)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
def read_frame(stream):
    size = struct.unpack(">I", read_exact(stream, 4))[0]
    if size <= 0 or size > 16384:
        raise SystemExit(22)
    return json.loads(read_exact(stream, size).decode("utf-8"))
def write_frame(stream, value):
    payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
    stream.write(struct.pack(">I", len(payload)) + payload)
    stream.flush()
write_frame(sys.stdout.buffer, {
    "schema": "agent00x-stdio-model-request/v1",
    "payload": {
        "model": "deepseek-flash",
        "messages": [{"role": "user", "content": "synthetic stdio probe"}],
    },
})
response = read_frame(sys.stdin.buffer)
if response != {
    "schema": "agent00x-stdio-model-response/v1",
    "content": "synthetic response",
}:
    raise SystemExit(23)
write_frame(sys.stdout.buffer, {"schema": "agent00x-stdio-model-complete/v1"})
'''.strip()

WORKER_CHILD_PROGRAM = r'''
import json, struct, sys
from app_contracts.deepseek_worker import DeepSeekProposalWorker
from app_contracts.executor import WorkerInput
from app_contracts.worker_model_ipc import StdioChatCompletionsChannel, WorkerModelIPCError
from app_contracts.deepseek_worker import build_chat_completions_payload
task = WorkerInput(
    process_id="stdio-process-001",
    task_id="stdio-task-001",
    repository_id="synthetic-repository",
    base_commit="b" * 40,
    declared_change_paths=("calculator.py",),
    task_instruction="Fix the synthetic calculator edge case",
    context_files=(("calculator.py", "synthetic existing content"),),
)
channel = StdioChatCompletionsChannel(sys.stdin.buffer, sys.stdout.buffer)
proposal = DeepSeekProposalWorker(channel=channel).propose(task)
replay_rejected = False
try:
    channel.create_chat_completion(
        build_chat_completions_payload(task), timeout_seconds=1
    )
except WorkerModelIPCError:
    replay_rejected = True
payload = json.dumps(
    {
        "schema": "agent00x-stdio-worker-result/v1",
        "changes": proposal.changes,
        "replay_rejected": replay_rejected,
    },
    ensure_ascii=False,
    allow_nan=False,
    separators=(",", ":"),
).encode("utf-8")
sys.stdout.buffer.write(struct.pack(">I", len(payload)) + payload)
sys.stdout.buffer.flush()
'''.strip()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _encode_frame(value: object, *, maximum: int = MAX_FRAME_BYTES) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        raise ValueError("stdio IPC frame invalid") from None
    if not payload or len(payload) > maximum:
        raise ValueError("stdio IPC frame exceeds limit")
    return struct.pack(">I", len(payload)) + payload


def _decode_frame_bytes(frame: bytes, *, maximum: int = MAX_FRAME_BYTES) -> object:
    if type(frame) is not bytes or len(frame) < 5:
        raise ValueError("stdio IPC frame invalid")
    (size,) = struct.unpack(">I", frame[:4])
    if size <= 0 or size > maximum or len(frame) != size + 4:
        raise ValueError("stdio IPC frame exceeds limit")
    try:
        return json.loads(
            frame[4:].decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except Exception:
        raise ValueError("stdio IPC frame invalid") from None


def _read_pipe_exact(stream, size: int, *, timeout_seconds: float) -> bytes:
    deadline = time.monotonic() + timeout_seconds
    chunks: list[bytes] = []
    remaining = size
    descriptor = stream.fileno()
    while remaining:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise ValueError("stdio IPC timed out")
        readable, _writable, _exceptional = select.select([descriptor], [], [], timeout)
        if not readable:
            raise ValueError("stdio IPC timed out")
        chunk = os.read(descriptor, remaining)
        if not chunk:
            raise ValueError("stdio IPC transport failed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_pipe_frame(
    stream,
    *,
    timeout_seconds: float,
    maximum: int = MAX_FRAME_BYTES,
) -> object:
    prefix = _read_pipe_exact(stream, 4, timeout_seconds=timeout_seconds)
    (size,) = struct.unpack(">I", prefix)
    if size <= 0 or size > maximum:
        raise ValueError("stdio IPC frame exceeds limit")
    body = _read_pipe_exact(stream, size, timeout_seconds=timeout_seconds)
    try:
        return _decode_json(body, maximum=maximum)
    except WorkerModelIPCError:
        raise ValueError("stdio IPC frame invalid") from None


class FakeChannel:
    def __init__(self) -> None:
        self.calls = 0

    def create_chat_completion(self, payload: object) -> dict[str, str]:
        self.calls += 1
        if payload != {
            "model": "deepseek-flash",
            "messages": [{"role": "user", "content": "synthetic stdio probe"}],
        }:
            raise ValueError("fake channel request mismatch")
        return {"schema": RESPONSE_SCHEMA, "content": "synthetic response"}


class RecordingModelChannel:
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
                        content='{"changes":[{"path":"calculator.py","content":"fixed via stdio"}]}',
                        reasoning_content="synthetic reasoning must not cross IPC",
                    ),
                ),
            )
        )


def _synthetic_worker_input() -> WorkerInput:
    return WorkerInput(
        process_id="stdio-process-001",
        task_id="stdio-task-001",
        repository_id="synthetic-repository",
        base_commit="b" * 40,
        declared_change_paths=("calculator.py",),
        task_instruction="Fix the synthetic calculator edge case",
        context_files=(("calculator.py", "synthetic existing content"),),
    )


class WorkerModelStdioTests(unittest.TestCase):
    def test_inspect_format_argument_is_literal_go_json_template(self):
        self.assertEqual(INSPECT_FORMAT_ARGUMENT, "--format={{json .}}")

    def test_local_frame_parser_rejects_duplicate_malformed_and_oversized(self):
        valid = _encode_frame({"schema": REQUEST_SCHEMA, "content": "synthetic"})
        self.assertEqual(
            _decode_frame_bytes(valid),
            {"schema": REQUEST_SCHEMA, "content": "synthetic"},
        )
        duplicate = b'{"schema":"a","schema":"b"}'
        with self.assertRaisesRegex(ValueError, "frame invalid"):
            _decode_frame_bytes(struct.pack(">I", len(duplicate)) + duplicate)
        malformed = b"not-json"
        with self.assertRaisesRegex(ValueError, "frame invalid"):
            _decode_frame_bytes(struct.pack(">I", len(malformed)) + malformed)
        with self.assertRaisesRegex(ValueError, "exceeds limit"):
            _encode_frame({"content": "x" * MAX_FRAME_BYTES})
        with self.assertRaisesRegex(ValueError, "exceeds limit"):
            _decode_frame_bytes(struct.pack(">I", MAX_FRAME_BYTES + 1) + b"x")

    def test_deepseek_worker_runs_over_pipe_once_and_rejects_replay(self):
        root = Path(__file__).resolve().parents[1]
        process = subprocess.Popen(
            [sys.executable, "-c", WORKER_CHILD_PROGRAM],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={
                "PYTHONPATH": str(root / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            text=False,
        )
        host_channel = RecordingModelChannel()
        try:
            self.assertIsNotNone(process.stdin)
            self.assertIsNotNone(process.stdout)
            request = _read_pipe_frame(
                process.stdout,
                timeout_seconds=8,
                maximum=_MAX_REQUEST_BYTES,
            )
            self.assertEqual(
                type(request),
                dict,
            )
            self.assertEqual(
                set(request),
                {"schema", "timeout_seconds", "payload"},
            )
            self.assertEqual(request["schema"], "agent00x-worker-model-request/v1")
            self.assertTrue(0 < request["timeout_seconds"] <= 30)
            task = _synthetic_worker_input()
            self.assertEqual(request["payload"], build_chat_completions_payload(task))

            result = host_channel.create_chat_completion(
                request["payload"],
                timeout_seconds=request["timeout_seconds"],
            )
            self.assertEqual(host_channel.calls, 1)
            response = _encode_result(result)
            self.assertNotIn(b"synthetic reasoning must not cross IPC", response)
            process.stdin.write(struct.pack(">I", len(response)) + response)
            process.stdin.flush()

            proposal = _read_pipe_frame(
                process.stdout,
                timeout_seconds=8,
                maximum=65_536,
            )
            self.assertEqual(
                proposal,
                {
                    "schema": "agent00x-stdio-worker-result/v1",
                    "changes": [["calculator.py", "fixed via stdio"]],
                    "replay_rejected": True,
                },
            )
            process.stdin.close()
            process.stdin = None
            process.wait(timeout=5)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(host_channel.calls, 1)
            self.assertLessEqual(host_channel.timeout_seconds, 30)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()

    def test_invalid_request_is_rejected_before_pipe_write(self):
        host_read, worker_write = os.pipe()
        worker_read, host_write = os.pipe()
        reader = os.fdopen(worker_read, "rb", buffering=0)
        writer = os.fdopen(worker_write, "wb", buffering=0)
        channel = StdioChatCompletionsChannel(reader, writer)
        host_channel = RecordingModelChannel()
        try:
            invalid_payload = {
                **build_chat_completions_payload(_synthetic_worker_input()),
                "endpoint": "https://example.invalid",
            }
            with self.assertRaisesRegex(WorkerModelIPCError, "request is invalid"):
                channel.create_chat_completion(
                    invalid_payload,
                    timeout_seconds=1,
                )
            readable, _writable, _exceptional = select.select([host_read], [], [], 0.05)
            self.assertEqual(readable, [])
            self.assertEqual(host_channel.calls, 0)
        finally:
            reader.close()
            writer.close()
            os.close(host_read)
            os.close(host_write)

    def test_duplicate_response_is_redacted_and_does_not_trigger_fake_channel(self):
        host_read, worker_write = os.pipe()
        worker_read, host_write = os.pipe()
        reader = os.fdopen(worker_read, "rb", buffering=0)
        writer = os.fdopen(worker_write, "wb", buffering=0)
        channel = StdioChatCompletionsChannel(reader, writer)
        host_channel = RecordingModelChannel()
        duplicate = (
            b'{"schema":"agent00x-worker-model-response/v1",'
            b'"error":"request_failed","error":"synthetic-sensitive-marker"}'
        )
        try:
            os.write(host_write, struct.pack(">I", len(duplicate)) + duplicate)
            with self.assertRaises(WorkerModelIPCError) as raised:
                channel.create_chat_completion(
                    build_chat_completions_payload(_synthetic_worker_input()),
                    timeout_seconds=1,
                )
            self.assertNotIn("synthetic-sensitive-marker", str(raised.exception))
            self.assertEqual(host_channel.calls, 0)
            with os.fdopen(os.dup(host_read), "rb", buffering=0) as host_reader:
                request = _read_pipe_frame(
                    host_reader,
                    timeout_seconds=1,
                    maximum=_MAX_REQUEST_BYTES,
                )
            self.assertEqual(request["schema"], "agent00x-worker-model-request/v1")
        finally:
            reader.close()
            writer.close()
            os.close(host_read)
            os.close(host_write)

    def test_channel_timeout_is_bounded_and_prevents_replay(self):
        host_read, worker_write = os.pipe()
        worker_read, host_write = os.pipe()
        reader = os.fdopen(worker_read, "rb", buffering=0)
        writer = os.fdopen(worker_write, "wb", buffering=0)
        channel = StdioChatCompletionsChannel(reader, writer)
        host_channel = RecordingModelChannel()
        started = time.monotonic()
        try:
            payload = build_chat_completions_payload(_synthetic_worker_input())
            with self.assertRaisesRegex(WorkerModelIPCError, "request timed out"):
                channel.create_chat_completion(payload, timeout_seconds=0.05)
            self.assertLess(time.monotonic() - started, 1)
            with self.assertRaisesRegex(WorkerModelIPCError, "call limit exceeded"):
                channel.create_chat_completion(payload, timeout_seconds=1)

            with os.fdopen(os.dup(host_read), "rb", buffering=0) as host_reader:
                request = _read_pipe_frame(
                    host_reader,
                    timeout_seconds=1,
                    maximum=_MAX_REQUEST_BYTES,
                )
            self.assertEqual(request["payload"], payload)
            readable, _writable, _exceptional = select.select([host_read], [], [], 0.05)
            self.assertEqual(readable, [])
            self.assertEqual(host_channel.calls, 0)
        finally:
            reader.close()
            writer.close()
            os.close(host_read)
            os.close(host_write)

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1",
        "Docker stdio IPC probe is opt-in",
    )
    def test_network_none_container_exchanges_one_fake_model_frame_over_stdio(self):
        docker = os.environ.get("AGENT00X_DOCKER_EXECUTABLE") or shutil.which("docker")
        self.assertIsInstance(docker, str, "Docker executable unavailable")
        self.assertTrue(Path(docker).is_absolute(), "Docker executable must be absolute")

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
            expected_environment = json.loads(image.stdout)
        except Exception:
            self.fail("pinned target image metadata was malformed")

        container_name = f"agent00x-exp762-{uuid.uuid4().hex}"
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
            TARGET_RUNTIME_IMAGE_ID,
            "python3",
            "-c",
            CHILD_PROGRAM,
        ]
        process: subprocess.Popen | None = None
        cleanup_container = False
        try:
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                )
            except Exception:
                self.fail("synthetic container process could not start")
            self.assertIsNotNone(process.stdout)
            self.assertIsNotNone(process.stdin)

            request = _read_pipe_frame(process.stdout, timeout_seconds=10)
            self.assertEqual(
                request,
                {
                    "schema": REQUEST_SCHEMA,
                    "payload": {
                        "model": "deepseek-flash",
                        "messages": [
                            {"role": "user", "content": "synthetic stdio probe"}
                        ],
                    },
                },
            )
            channel = FakeChannel()

            try:
                inspect = subprocess.run(
                    [docker, "inspect", INSPECT_FORMAT_ARGUMENT, container_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except Exception:
                self.fail("container security inspection failed")
            self.assertEqual(inspect.returncode, 0, "container security inspection failed")
            try:
                details = json.loads(inspect.stdout)
                if type(details) is not dict:
                    raise ValueError
                host_config = details["HostConfig"]
                config = details["Config"]
                state = details["State"]
                mounts = details["Mounts"]
            except Exception:
                self.fail("container security inspection was malformed")
            self.assertIs(state.get("Running"), True)
            self.assertEqual(host_config.get("NetworkMode"), "none")
            self.assertIs(host_config.get("ReadonlyRootfs"), True)
            self.assertIn("ALL", host_config.get("CapDrop", []))
            self.assertTrue(
                any("no-new-privileges" in item for item in host_config.get("SecurityOpt", []))
            )
            self.assertEqual(config.get("User"), CONTAINER_USER)
            self.assertIs(config.get("OpenStdin"), True)
            self.assertIs(config.get("Tty"), False)
            self.assertEqual(config.get("Env"), expected_environment)
            self.assertEqual(host_config.get("PidsLimit"), 16)
            self.assertEqual(host_config.get("Memory"), 256 * 1024 * 1024)
            self.assertEqual(host_config.get("NanoCpus"), 500_000_000)
            self.assertEqual(mounts, [])

            response = channel.create_chat_completion(request["payload"])
            self.assertEqual(channel.calls, 1)
            process.stdin.write(_encode_frame(response))
            process.stdin.flush()
            process.stdin.close()
            process.stdin = None
            try:
                trailing_stdout, _hidden_stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                cleanup_container = True
                self.fail("synthetic container process exceeded deadline")
            self.assertEqual(process.returncode, 0, "synthetic container process failed")
            completion = _decode_frame_bytes(trailing_stdout)
            self.assertEqual(completion, {"schema": "agent00x-stdio-model-complete/v1"})
            self.assertEqual(channel.calls, 1)
        finally:
            cleanup_unconfirmed = False
            if process is not None and process.poll() is None:
                cleanup_container = True
                try:
                    process.terminate()
                    process.wait(timeout=3)
                except Exception:
                    try:
                        process.kill()
                        process.wait(timeout=3)
                    except Exception:
                        pass
            if cleanup_container:
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
                        [docker, "inspect", "--format={{.Id}}", container_name],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    )
                except Exception:
                    cleanup_unconfirmed = True
                else:
                    if remaining.returncode != 1:
                        cleanup_unconfirmed = True
            if cleanup_unconfirmed:
                self.fail("container cleanup could not be confirmed")


if __name__ == "__main__":
    unittest.main()
