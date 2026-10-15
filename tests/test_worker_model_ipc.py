from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile
import threading
import time
import unittest

from app_contracts.deepseek_worker import (
    MODEL_NAME,
    REASONING_EFFORT,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
)
from app_contracts.worker_model_ipc import (
    StdioChatCompletionsChannel,
    UnixSocketChatCompletionsBroker,
    UnixSocketChatCompletionsChannel,
    WorkerModelIPCError,
)


RESPONSE_CONTENT = '{"changes":[{"path":"file.py","content":"fixed"}]}'
BROKER_RESPONSE_SCHEMA = "agent00x-worker-model-response/v1"
BROKER_REQUEST_SCHEMA = "agent00x-worker-model-request/v1"
MAX_REQUEST_FRAME_BYTES = 128_000
MAX_RESPONSE_FRAME_BYTES = 65_536


def valid_payload() -> dict:
    return {
        "model": MODEL_NAME,
        "reasoning_effort": REASONING_EFFORT,
        "max_tokens": 4096,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "return JSON"},
            {"role": "user", "content": "synthetic task"},
        ],
    }


def valid_result() -> ChatCompletionsModelResult:
    return ChatCompletionsModelResult(
        choices=(
            ChatCompletionChoice(
                finish_reason="stop",
                message=ChatCompletionMessage(
                    role="assistant",
                    content=RESPONSE_CONTENT,
                ),
            ),
        )
    )


class FakeChannel:
    def __init__(self, result: object | None = None, *, delay: float = 0) -> None:
        self.result = valid_result() if result is None else result
        self.delay = delay
        self.calls = 0
        self.payload: dict | None = None
        self.timeout: float | None = None

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        self.calls += 1
        self.payload = payload
        self.timeout = timeout_seconds
        if self.delay:
            time.sleep(self.delay)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class WorkerModelIPCTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="agent00x-model-ipc-")
        self.directory = Path(self.temp.name)
        self.directory.chmod(0o700)
        self.socket_path = self.directory / "broker.sock"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def start_broker(self, channel: object, *, timeout: float = 2):
        broker = UnixSocketChatCompletionsBroker(
            self.socket_path,
            channel,
            timeout_seconds=timeout,
        )
        broker.open()
        failures: list[BaseException] = []

        def serve() -> None:
            try:
                broker.serve_once()
            except BaseException as exc:
                failures.append(exc)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        return broker, thread, failures

    def raw_exchange(self, request_bytes: bytes) -> dict:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(2)
        try:
            connection.connect(str(self.socket_path))
            connection.sendall(struct.pack(">I", len(request_bytes)) + request_bytes)
            prefix = self.read_exact(connection, 4)
            (response_size,) = struct.unpack(">I", prefix)
            self.assertGreater(response_size, 0)
            self.assertLessEqual(response_size, MAX_RESPONSE_FRAME_BYTES)
            return json.loads(self.read_exact(connection, response_size).decode("utf-8"))
        finally:
            connection.close()

    @staticmethod
    def read_exact(connection: socket.socket, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = connection.recv(remaining)
            if not chunk:
                raise AssertionError("response frame was incomplete")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def test_fake_channel_round_trip_is_one_shot_and_cleans_private_socket(self):
        channel = FakeChannel()
        broker, thread, failures = self.start_broker(channel)
        self.assertEqual(stat.S_IMODE(self.socket_path.stat().st_mode), 0o600)

        client = UnixSocketChatCompletionsChannel(self.socket_path)
        result = client.create_chat_completion(valid_payload(), timeout_seconds=1)
        thread.join(timeout=2)
        broker.close()

        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, "broker failed")
        self.assertEqual(channel.calls, 1)
        self.assertTrue(channel.payload == valid_payload(), "payload forwarding mismatch")
        self.assertLessEqual(channel.timeout, 1)
        self.assertIs(type(result), ChatCompletionsModelResult)
        self.assertTrue(
            result.choices[0].message.content == RESPONSE_CONTENT,
            "typed result mismatch",
        )
        self.assertFalse(self.socket_path.exists())
        with self.assertRaisesRegex(WorkerModelIPCError, "call limit exceeded"):
            client.create_chat_completion(valid_payload(), timeout_seconds=1)
        self.assertEqual(channel.calls, 1)

    def test_invalid_payload_is_rejected_before_fake_channel(self):
        channel = FakeChannel()
        broker, thread, failures = self.start_broker(channel)
        request = {
            "schema": BROKER_REQUEST_SCHEMA,
            "timeout_seconds": 1,
            "payload": {**valid_payload(), "model": "unexpected"},
        }
        response = self.raw_exchange(json.dumps(request).encode("utf-8"))
        thread.join(timeout=2)
        broker.close()

        self.assertEqual(response.get("schema"), BROKER_RESPONSE_SCHEMA)
        self.assertEqual(response.get("error"), "request_failed")
        self.assertFalse(failures, "broker failed")
        self.assertEqual(channel.calls, 0)

    def test_unknown_endpoint_or_credential_fields_are_rejected(self):
        for extra_field in (
            {"endpoint": "https://example.invalid"},
            {"api_key": "synthetic-must-not-cross-ipc"},
        ):
            with self.subTest(extra_field=next(iter(extra_field))):
                channel = FakeChannel()
                broker, thread, failures = self.start_broker(channel)
                request = {
                    "schema": BROKER_REQUEST_SCHEMA,
                    "timeout_seconds": 1,
                    "payload": valid_payload(),
                    **extra_field,
                }
                response = self.raw_exchange(json.dumps(request).encode("utf-8"))
                thread.join(timeout=2)
                broker.close()
                self.assertEqual(response.get("error"), "request_failed")
                self.assertFalse(failures, "broker failed")
                self.assertEqual(channel.calls, 0)

    def test_duplicate_json_keys_are_rejected_before_fake_channel(self):
        channel = FakeChannel()
        broker, thread, failures = self.start_broker(channel)
        request = (
            b'{"schema":"agent00x-worker-model-request/v1",'
            b'"schema":"agent00x-worker-model-request/v1",'
            b'"timeout_seconds":1,"payload":{}}'
        )
        response = self.raw_exchange(request)
        thread.join(timeout=2)
        broker.close()

        self.assertEqual(response.get("error"), "request_failed")
        self.assertFalse(failures, "broker failed")
        self.assertEqual(channel.calls, 0)

    def test_oversized_request_header_is_rejected_without_body_or_channel_call(self):
        channel = FakeChannel()
        broker, thread, failures = self.start_broker(channel)
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(2)
        try:
            connection.connect(str(self.socket_path))
            connection.sendall(struct.pack(">I", MAX_REQUEST_FRAME_BYTES + 1))
            prefix = self.read_exact(connection, 4)
            (response_size,) = struct.unpack(">I", prefix)
            response = json.loads(self.read_exact(connection, response_size).decode("utf-8"))
        finally:
            connection.close()
        thread.join(timeout=2)
        broker.close()

        self.assertEqual(response.get("error"), "request_failed")
        self.assertFalse(failures, "broker failed")
        self.assertEqual(channel.calls, 0)

    def test_oversized_typed_result_is_replaced_with_fixed_error(self):
        oversized_result = ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        role="assistant",
                        content="x" * MAX_RESPONSE_FRAME_BYTES,
                    ),
                ),
            )
        )
        channel = FakeChannel(oversized_result)
        broker, thread, failures = self.start_broker(channel)
        client = UnixSocketChatCompletionsChannel(self.socket_path)
        with self.assertRaises(WorkerModelIPCError):
            client.create_chat_completion(valid_payload(), timeout_seconds=1)
        thread.join(timeout=2)
        broker.close()

        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, "broker failed")
        self.assertEqual(channel.calls, 1)

    def test_broker_closes_after_first_exchange_and_rejects_second_connection(self):
        channel = FakeChannel()
        broker, thread, failures = self.start_broker(channel)
        client = UnixSocketChatCompletionsChannel(self.socket_path)
        result = client.create_chat_completion(valid_payload(), timeout_seconds=1)
        thread.join(timeout=2)
        broker.close()

        self.assertIs(type(result), ChatCompletionsModelResult)
        self.assertFalse(failures, "broker failed")
        second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        second.settimeout(1)
        try:
            with self.assertRaises(OSError):
                second.connect(str(self.socket_path))
        finally:
            second.close()
        self.assertEqual(channel.calls, 1)

    def test_invalid_timeout_is_rejected_before_connecting(self):
        client = UnixSocketChatCompletionsChannel(self.socket_path)
        for invalid in (True, 0, -1, float("inf"), 31):
            with self.subTest(timeout=invalid):
                with self.assertRaisesRegex(WorkerModelIPCError, "timeout is invalid"):
                    client.create_chat_completion(valid_payload(), timeout_seconds=invalid)

    def test_local_timeout_profile_is_bounded_and_one_shot(self):
        channel = FakeChannel()
        broker, thread, failures = self.start_broker(channel, timeout=180)
        client = UnixSocketChatCompletionsChannel(
            self.socket_path, maximum_timeout_seconds=180
        )
        result = client.create_chat_completion(valid_payload(), timeout_seconds=180)
        thread.join(timeout=2)
        broker.close()

        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, "broker failed")
        self.assertEqual(channel.calls, 1)
        self.assertLessEqual(channel.timeout, 180)
        self.assertGreater(channel.timeout, 179.9)
        self.assertIs(type(result), ChatCompletionsModelResult)
        with self.assertRaisesRegex(WorkerModelIPCError, "timeout is invalid"):
            UnixSocketChatCompletionsChannel(
                self.socket_path, maximum_timeout_seconds=181
            )

    def test_r5_60_second_timeout_profile_is_accepted_with_existing_cap(self):
        reader_fd, writer_fd = os.pipe()
        reader = os.fdopen(reader_fd, "rb", buffering=0)
        writer = os.fdopen(writer_fd, "wb", buffering=0)
        try:
            StdioChatCompletionsChannel(
                reader, writer, maximum_timeout_seconds=60.0
            )
        finally:
            reader.close()
            writer.close()

        socket_channel = UnixSocketChatCompletionsChannel(
            self.socket_path, maximum_timeout_seconds=60.0
        )
        self.assertEqual(socket_channel._maximum_timeout_seconds, 60.0)

    def test_channel_maximum_timeout_rejects_invalid_values(self):
        invalid_values = (True, 0, -1, float("nan"), float("inf"), 181)
        reader_fd, writer_fd = os.pipe()
        reader = os.fdopen(reader_fd, "rb", buffering=0)
        writer = os.fdopen(writer_fd, "wb", buffering=0)
        try:
            for value in invalid_values:
                with self.subTest(channel="stdio", timeout=value):
                    with self.assertRaisesRegex(
                        WorkerModelIPCError, "timeout is invalid"
                    ):
                        StdioChatCompletionsChannel(
                            reader, writer, maximum_timeout_seconds=value
                        )
        finally:
            reader.close()
            writer.close()

        for value in invalid_values:
            with self.subTest(channel="unix_socket", timeout=value):
                with self.assertRaisesRegex(
                    WorkerModelIPCError, "timeout is invalid"
                ):
                    UnixSocketChatCompletionsChannel(
                        self.socket_path, maximum_timeout_seconds=value
                    )

    def test_bad_parent_permissions_fail_closed(self):
        child = self.directory / "shared"
        child.mkdir()
        child.chmod(0o755)
        try:
            with self.assertRaisesRegex(WorkerModelIPCError, "socket path unavailable"):
                UnixSocketChatCompletionsBroker(child / "broker.sock", FakeChannel())
        finally:
            child.chmod(0o700)

    def test_channel_errors_are_redacted_over_ipc(self):
        channel = FakeChannel(RuntimeError("raw-provider-error-marker"))
        broker, thread, failures = self.start_broker(channel)
        client = UnixSocketChatCompletionsChannel(self.socket_path)
        with self.assertRaises(WorkerModelIPCError) as raised:
            client.create_chat_completion(valid_payload(), timeout_seconds=1)
        thread.join(timeout=2)
        broker.close()

        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, "broker failed")
        self.assertEqual(channel.calls, 1)
        self.assertNotIn("raw-provider-error-marker", str(raised.exception))

    def test_client_deadline_bounds_wait_for_fake_channel(self):
        channel = FakeChannel(delay=0.2)
        broker, thread, failures = self.start_broker(channel, timeout=1)
        client = UnixSocketChatCompletionsChannel(self.socket_path)
        with self.assertRaises(WorkerModelIPCError):
            client.create_chat_completion(valid_payload(), timeout_seconds=0.05)
        thread.join(timeout=2)
        broker.close()

        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, "broker failed")
        self.assertEqual(channel.calls, 1)
        self.assertLessEqual(channel.timeout, 0.05)


if __name__ == "__main__":
    unittest.main()
