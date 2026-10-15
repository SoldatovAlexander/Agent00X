from __future__ import annotations

import ast
import http.client
import json
import shutil
import socket
import ssl
import subprocess
import threading
import time
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app_contracts.deepseek_http_channel import (
    DeepSeekHTTPChannel,
    DeepSeekHTTPChannelError,
)
from app_contracts.credential_source import CredentialSource
from app_contracts.deepseek_worker import (
    MODEL_NAME,
    REASONING_EFFORT,
    ChatCompletionsModelResult,
    DeepSeekProposalWorker,
)
from app_contracts.executor import WorkerInput, WorkerProposal


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_KEY = "synthetic-deepseek-key-not-a-credential"
RESPONSE_CONTENT = '{"changes":[{"path":"file.py","content":"fixed"}]}'


def valid_payload() -> dict:
    return {
        "model": MODEL_NAME,
        "reasoning_effort": REASONING_EFFORT,
        "max_tokens": 4096,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "return JSON"},
            {"role": "user", "content": "small synthetic task"},
        ],
    }


def valid_response(*, reasoning: str | None = None) -> bytes:
    message = {"role": "assistant", "content": RESPONSE_CONTENT}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return json.dumps(
        {
            "choices": [
                {"finish_reason": "stop", "message": message, "index": 0}
            ]
        }
    ).encode("utf-8")


def _server_tls_context(
    certificate_path: Path, key_path: Path
) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate_path, key_path)
    return context


class FakeResponse:
    def __init__(
        self,
        status: int,
        body: bytes,
        *,
        close_event: threading.Event | None = None,
        block_read: bool = False,
    ) -> None:
        self.status = status
        self._body = body
        self._close_event = close_event
        self._block_read = block_read
        self.read_limits: list[int] = []

    def read(self, amount: int) -> bytes:
        self.read_limits.append(amount)
        if self._block_read and self._close_event is not None:
            self._close_event.wait()
        return self._body[:amount]


class FakeConnection:
    def __init__(
        self,
        response: FakeResponse,
        *,
        error: Exception | None = None,
        block_request: bool = False,
    ) -> None:
        self.response = response
        self.error = error
        self.block_request = block_request
        self.closed_event = threading.Event()
        self.request_started = threading.Event()
        self.request_args: tuple[object, ...] | None = None
        self.request_kwargs: dict[str, object] | None = None
        self.closed = False

    def request(self, *args: object, **kwargs: object) -> None:
        self.request_started.set()
        if self.block_request:
            self.closed_event.wait()
        if self.error is not None:
            raise self.error
        self.request_args = args
        self.request_kwargs = kwargs

    def getresponse(self) -> FakeResponse:
        if self.error is not None:
            raise self.error
        return self.response

    def close(self) -> None:
        self.closed = True
        self.closed_event.set()


class KeyProvider:
    def __init__(self, value: str = SYNTHETIC_KEY, error: Exception | None = None) -> None:
        self.value = value
        self.error = error
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


class LoopbackHTTPServer:
    """Local-only server that withholds response headers or body bytes."""

    def __init__(
        self,
        *,
        block_body: bool,
        tls_context: ssl.SSLContext | None = None,
        response_body: bytes | None = None,
    ) -> None:
        self.block_body = block_body
        self.tls_context = tls_context
        self.response_body = response_body
        self.release = threading.Event()
        self.connected = threading.Event()
        self.request_received = threading.Event()
        self.request_header: bytes | None = None
        self.request_body: bytes | None = None
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(2)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            raw_client, _ = self.listener.accept()
            self.connected.set()
            client = (
                self.tls_context.wrap_socket(raw_client, server_side=True)
                if self.tls_context is not None
                else raw_client
            )
            with client:
                client.settimeout(2)
                request = bytearray()
                while b"\r\n\r\n" not in request:
                    chunk = client.recv(4096)
                    if not chunk:
                        return
                    request.extend(chunk)
                header, body = bytes(request).split(b"\r\n\r\n", 1)
                content_length = 0
                for line in header.split(b"\r\n")[1:]:
                    name, separator, value = line.partition(b":")
                    if separator and name.lower() == b"content-length":
                        content_length = int(value.strip())
                while len(body) < content_length:
                    chunk = client.recv(4096)
                    if not chunk:
                        return
                    body += chunk
                self.request_header = header
                self.request_body = body
                self.request_received.set()
                if self.block_body:
                    client.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 4096\r\n"
                        b"Connection: close\r\n\r\nx"
                    )
                    self.release.wait(2)
                elif self.response_body is not None:
                    client.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                        + f"Content-Length: {len(self.response_body)}\r\n".encode("ascii")
                        + b"Connection: close\r\n\r\n"
                        + self.response_body
                    )
                else:
                    self.release.wait(2)
        except (OSError, TimeoutError):
            pass

    def close(self) -> None:
        self.release.set()
        try:
            self.listener.close()
        except OSError:
            pass
        self.thread.join(timeout=1)
        if self.thread.is_alive():
            raise AssertionError("loopback server thread did not stop")


class LoopbackHTTPConnection(http.client.HTTPConnection):
    def __init__(self, port: int, timeout: float) -> None:
        super().__init__("127.0.0.1", port, timeout=timeout)


class LoopbackHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self, port: int, timeout: float, context: ssl.SSLContext
    ) -> None:
        super().__init__("api.deepseek.com", port, timeout=timeout, context=context)
        self._create_connection = lambda address, timeout, source_address: socket.create_connection(
            ("127.0.0.1", port), timeout, source_address
        )


class NonReadingLoopbackServer:
    """Local TCP peer that accepts a request but never drains its body."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.connected = threading.Event()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(2)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            client, _ = self.listener.accept()
            with client:
                client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
                self.connected.set()
                self.release.wait(2)
        except (OSError, TimeoutError):
            pass

    def close(self) -> None:
        self.release.set()
        try:
            self.listener.close()
        except OSError:
            pass
        self.thread.join(timeout=1)
        if self.thread.is_alive():
            raise AssertionError("non-reading loopback server did not stop")


class ConstrainedLoopbackHTTPConnection(LoopbackHTTPConnection):
    def __init__(self, port: int, timeout: float) -> None:
        super().__init__(port, timeout)
        self.send_started = threading.Event()
        self.request_completed = threading.Event()
        self._create_connection = self._connect_with_small_send_buffer

    @staticmethod
    def _connect_with_small_send_buffer(address, timeout, source_address):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        client.settimeout(timeout)
        try:
            if source_address is not None:
                client.bind(source_address)
            client.connect(address)
            return client
        except Exception:
            client.close()
            raise

    def send(self, data: bytes) -> None:
        self.send_started.set()
        super().send(data)

    def request(self, *args: object, **kwargs: object) -> None:
        super().request(*args, **kwargs)
        self.request_completed.set()


class DeepSeekHTTPChannelTests(unittest.TestCase):
    def test_synthetic_key_provider_implements_portable_source_contract(self):
        provider = KeyProvider()

        self.assertIsInstance(provider, CredentialSource)
        self.assertEqual(provider(), SYNTHETIC_KEY)
        self.assertEqual(provider.calls, 1)

    def make_channel(
        self,
        *,
        status: int = 200,
        body: bytes | None = None,
        provider: KeyProvider | None = None,
        connection_error: Exception | None = None,
        block_request: bool = False,
        block_read: bool = False,
    ):
        key_provider = provider or KeyProvider()
        response = FakeResponse(
            status,
            body if body is not None else valid_response(),
            block_read=block_read,
        )
        connection = FakeConnection(
            response, error=connection_error, block_request=block_request
        )
        response._close_event = connection.closed_event
        factory_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def factory(*args: object, **kwargs: object) -> FakeConnection:
            factory_calls.append((args, kwargs))
            return connection

        return (
            DeepSeekHTTPChannel(key_provider, connection_factory=factory),
            key_provider,
            response,
            connection,
            factory_calls,
        )

    def test_posts_fixed_endpoint_with_verified_tls_and_bounded_timeout(self):
        channel, provider, response, connection, factory_calls = self.make_channel()
        result = channel.create_chat_completion(valid_payload(), timeout_seconds=12.5)

        self.assertIs(type(result), ChatCompletionsModelResult)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(factory_calls), 1)
        args, kwargs = factory_calls[0]
        self.assertEqual(args, ("api.deepseek.com",))
        self.assertEqual(kwargs["timeout"], 12.5)
        context = kwargs["context"]
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

        method, path = connection.request_args
        headers = connection.request_kwargs["headers"]
        body = connection.request_kwargs["body"]
        self.assertEqual((method, path), ("POST", "/chat/completions"))
        self.assertEqual(headers["Authorization"], f"Bearer {SYNTHETIC_KEY}")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body), valid_payload())
        self.assertEqual(response.read_limits, [65_537])
        self.assertTrue(connection.closed)

    def test_key_is_not_returned_or_represented(self):
        channel, *_ = self.make_channel(body=valid_response(reasoning="private reasoning sentinel"))
        result = channel.create_chat_completion(valid_payload(), timeout_seconds=1)

        self.assertNotIn(SYNTHETIC_KEY, repr(channel))
        self.assertNotIn(SYNTHETIC_KEY, repr(result))
        self.assertNotIn("private reasoning sentinel", repr(result))
        self.assertIsNone(result.choices[0].message.reasoning_content)

    def test_provider_failure_is_sanitized_and_stops_before_network(self):
        provider = KeyProvider(error=RuntimeError("synthetic secret sentinel"))
        channel, _, _, _, factory_calls = self.make_channel(provider=provider)

        with self.assertRaisesRegex(
            DeepSeekHTTPChannelError, "^deepseek channel: credential provider failed$"
        ) as error:
            channel.create_chat_completion(valid_payload(), timeout_seconds=1)

        self.assertNotIn("synthetic secret sentinel", str(error.exception))
        self.assertEqual(provider.calls, 1)
        self.assertEqual(factory_calls, [])

    def test_provider_that_returns_after_deadline_stops_before_connection(self):
        provider_calls: list[None] = []
        release_provider = threading.Event()
        provider_finished = threading.Event()

        def slow_provider() -> str:
            provider_calls.append(None)
            release_provider.wait(1)
            provider_finished.set()
            return SYNTHETIC_KEY

        channel, _, _, _, factory_calls = self.make_channel(provider=slow_provider)
        try:
            with self.assertRaisesRegex(
                DeepSeekHTTPChannelError,
                "^deepseek channel: provider request timed out$",
            ) as error:
                channel.create_chat_completion(valid_payload(), timeout_seconds=0.01)

            self.assertNotIn(SYNTHETIC_KEY, str(error.exception))
            self.assertEqual(provider_calls, [None])
            self.assertEqual(factory_calls, [])
        finally:
            release_provider.set()
            self.assertTrue(provider_finished.wait(1))

    def test_provider_exception_after_deadline_is_sanitized_as_timeout(self):
        provider_calls: list[None] = []
        release_provider = threading.Event()
        provider_finished = threading.Event()

        def slow_failing_provider() -> str:
            provider_calls.append(None)
            release_provider.wait(1)
            provider_finished.set()
            raise RuntimeError(SYNTHETIC_KEY)

        channel, _, _, _, factory_calls = self.make_channel(provider=slow_failing_provider)
        try:
            with self.assertRaisesRegex(
                DeepSeekHTTPChannelError,
                "^deepseek channel: provider request timed out$",
            ) as error:
                channel.create_chat_completion(valid_payload(), timeout_seconds=0.01)

            self.assertNotIn(SYNTHETIC_KEY, str(error.exception))
            self.assertEqual(provider_calls, [None])
            self.assertEqual(factory_calls, [])
        finally:
            release_provider.set()
            self.assertTrue(provider_finished.wait(1))

    def test_blocked_credential_callback_uses_one_process_wide_slot(self):
        provider_started = threading.Event()
        release_provider = threading.Event()
        provider_finished = threading.Event()
        provider_calls: list[None] = []

        def blocked_provider() -> str:
            provider_calls.append(None)
            provider_started.set()
            release_provider.wait(1)
            provider_finished.set()
            return SYNTHETIC_KEY

        first, _, _, _, first_factory_calls = self.make_channel(
            provider=blocked_provider
        )
        second_provider = KeyProvider()
        second, _, _, _, second_factory_calls = self.make_channel(
            provider=second_provider
        )
        try:
            started = time.monotonic()
            with self.assertRaisesRegex(
                DeepSeekHTTPChannelError,
                "^deepseek channel: provider request timed out$",
            ):
                first.create_chat_completion(valid_payload(), timeout_seconds=0.05)
            self.assertTrue(provider_started.is_set())
            self.assertLess(time.monotonic() - started, 0.5)

            started = time.monotonic()
            with self.assertRaisesRegex(
                DeepSeekHTTPChannelError,
                "^deepseek channel: provider request timed out$",
            ):
                second.create_chat_completion(valid_payload(), timeout_seconds=1)
            self.assertLess(time.monotonic() - started, 0.25)
            self.assertEqual(provider_calls, [None])
            self.assertEqual(second_provider.calls, 0)
            self.assertEqual(first_factory_calls, [])
            self.assertEqual(second_factory_calls, [])
        finally:
            release_provider.set()
            self.assertTrue(provider_finished.wait(1))

    def test_channel_instance_allows_only_one_provider_attempt(self):
        channel, provider, _, connection, factory_calls = self.make_channel()

        first = channel.create_chat_completion(valid_payload(), timeout_seconds=1)
        self.assertIs(type(first), ChatCompletionsModelResult)
        with self.assertRaisesRegex(
            DeepSeekHTTPChannelError, "^deepseek channel: call limit exceeded$"
        ):
            channel.create_chat_completion(valid_payload(), timeout_seconds=1)

        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(factory_calls), 1)
        self.assertTrue(connection.closed)

    def test_failed_provider_attempt_cannot_be_retried_on_same_channel(self):
        provider = KeyProvider(error=RuntimeError("synthetic secret sentinel"))
        channel, _, _, _, factory_calls = self.make_channel(provider=provider)

        for expected in (
            "deepseek channel: credential provider failed",
            "deepseek channel: call limit exceeded",
        ):
            with self.assertRaisesRegex(DeepSeekHTTPChannelError, f"^{expected}$") as error:
                channel.create_chat_completion(valid_payload(), timeout_seconds=1)
            self.assertNotIn("synthetic secret sentinel", str(error.exception))

        self.assertEqual(provider.calls, 1)
        self.assertEqual(factory_calls, [])

    def test_concurrent_calls_reserve_only_one_provider_attempt(self):
        channel, provider, _, _, factory_calls = self.make_channel()
        start = threading.Barrier(3)
        outcomes: list[str] = []

        def invoke() -> None:
            start.wait(timeout=2)
            try:
                channel.create_chat_completion(valid_payload(), timeout_seconds=1)
            except DeepSeekHTTPChannelError as error:
                outcomes.append(str(error))
            else:
                outcomes.append("completed")

        threads = [threading.Thread(target=invoke) for _ in range(2)]
        for thread in threads:
            thread.start()
        start.wait(timeout=2)
        for thread in threads:
            thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertCountEqual(
            outcomes,
            ["completed", "deepseek channel: call limit exceeded"],
        )
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(factory_calls), 1)

    def test_blank_or_whitespace_key_is_rejected_without_echo(self):
        for key in ("", " synthetic "):
            provider = KeyProvider(value=key)
            channel, _, _, _, factory_calls = self.make_channel(provider=provider)
            with self.subTest(key=key):
                with self.assertRaises(DeepSeekHTTPChannelError) as error:
                    channel.create_chat_completion(valid_payload(), timeout_seconds=1)
                if key:
                    self.assertNotIn(key.strip(), str(error.exception))
                self.assertEqual(factory_calls, [])

    def test_timeout_must_be_finite_positive_and_at_most_thirty_seconds(self):
        for timeout in (0, -1, 30.1, float("inf"), float("nan"), True, "1"):
            provider = KeyProvider()
            channel, _, _, _, factory_calls = self.make_channel(provider=provider)
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(
                    DeepSeekHTTPChannelError, "^deepseek channel: timeout is invalid$"
                ):
                    channel.create_chat_completion(valid_payload(), timeout_seconds=timeout)
                self.assertEqual(provider.calls, 0)
                self.assertEqual(factory_calls, [])

    def test_invalid_or_oversized_request_is_rejected_before_key_lookup(self):
        invalid = valid_payload()
        invalid["model"] = "caller-selected-hostile-model"
        provider = KeyProvider()
        channel, _, _, _, factory_calls = self.make_channel(provider=provider)
        with self.assertRaises(DeepSeekHTTPChannelError):
            channel.create_chat_completion(invalid, timeout_seconds=1)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(factory_calls, [])

        oversized = valid_payload()
        oversized["messages"][1]["content"] = "x" * 130_000
        channel, provider, _, _, factory_calls = self.make_channel(provider=provider)
        with self.assertRaisesRegex(
            DeepSeekHTTPChannelError, "^deepseek channel: request exceeds limit$"
        ):
            channel.create_chat_completion(oversized, timeout_seconds=1)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(factory_calls, [])

    def test_invalid_input_does_not_consume_the_one_attempt_allowance(self):
        channel, provider, _, _, factory_calls = self.make_channel()
        invalid = valid_payload()
        invalid["stream"] = True

        with self.assertRaisesRegex(
            DeepSeekHTTPChannelError, "^deepseek channel: request is invalid$"
        ):
            channel.create_chat_completion(invalid, timeout_seconds=1)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(factory_calls, [])

        result = channel.create_chat_completion(valid_payload(), timeout_seconds=1)
        self.assertIs(type(result), ChatCompletionsModelResult)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(factory_calls), 1)

    def test_non_200_status_redirect_and_body_limit_are_sanitized(self):
        for status, body, expected in (
            (302, b"secret redirect body", "deepseek channel: provider response rejected"),
            (500, b"secret provider body", "deepseek channel: provider response rejected"),
            (200, b"x" * 65_537, "deepseek channel: response exceeds limit"),
        ):
            channel, provider, response, connection, factory_calls = self.make_channel(
                status=status, body=body
            )
            with self.subTest(status=status, expected=expected):
                with self.assertRaisesRegex(DeepSeekHTTPChannelError, f"^{expected}$") as error:
                    channel.create_chat_completion(valid_payload(), timeout_seconds=2)
                self.assertNotIn("secret", str(error.exception))
                self.assertEqual(provider.calls, 1)
                self.assertEqual(len(factory_calls), 1)
                self.assertTrue(connection.closed)
                if status == 200 and len(body) > 65_536:
                    self.assertEqual(response.read_limits, [65_537])

    def test_invalid_response_and_duplicate_json_keys_are_sanitized(self):
        for body in (
            b"response body secret sentinel",
            b'{"choices":[],"choices":[]}',
            b'{"choices":[{"finish_reason":"stop","message":{"role":"assistant","content":4}}]}',
        ):
            channel, *_ = self.make_channel(body=body)
            with self.subTest(body=body[:30]):
                with self.assertRaisesRegex(
                    DeepSeekHTTPChannelError,
                    "^deepseek channel: provider response is invalid$",
                ) as error:
                    channel.create_chat_completion(valid_payload(), timeout_seconds=2)
                self.assertNotIn("secret sentinel", str(error.exception))

    def test_transport_failure_is_sanitized_and_not_retried(self):
        provider = KeyProvider()
        channel, _, _, connection, factory_calls = self.make_channel(
            provider=provider,
            connection_error=TimeoutError("provider body secret sentinel"),
        )
        with self.assertRaisesRegex(
            DeepSeekHTTPChannelError, "^deepseek channel: provider request failed$"
        ) as error:
            channel.create_chat_completion(valid_payload(), timeout_seconds=3)
        self.assertNotIn("secret sentinel", str(error.exception))
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(factory_calls), 1)
        self.assertTrue(connection.closed)

    def test_deadline_closes_a_blocked_request_without_retry(self):
        channel, provider, _, connection, factory_calls = self.make_channel(
            block_request=True
        )

        started = time.monotonic()
        with self.assertRaisesRegex(
            DeepSeekHTTPChannelError,
            "^deepseek channel: provider request timed out$",
        ):
            context = ssl.create_default_context()
            with patch(
                "app_contracts.deepseek_http_channel._create_verified_ssl_context",
                return_value=context,
            ):
                channel.create_chat_completion(
                    valid_payload(), timeout_seconds=0.05
                )
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.0)
        self.assertTrue(connection.closed)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(factory_calls), 1)
        self.assertTrue(connection.request_started.is_set())

    def test_deadline_closes_a_blocked_response_read_without_retry(self):
        channel, provider, response, connection, factory_calls = self.make_channel(
            block_read=True
        )

        started = time.monotonic()
        with self.assertRaisesRegex(
            DeepSeekHTTPChannelError,
            "^deepseek channel: provider request timed out$",
        ):
            channel.create_chat_completion(valid_payload(), timeout_seconds=0.05)
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.0)
        self.assertTrue(connection.closed)
        self.assertEqual(response.read_limits, [65_537])
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(factory_calls), 1)

    def test_deadline_shuts_down_real_loopback_header_and_body_reads(self):
        for block_body in (False, True):
            with self.subTest(block_body=block_body):
                server = LoopbackHTTPServer(block_body=block_body)
                provider = KeyProvider()
                connections: list[LoopbackHTTPConnection] = []

                def factory(host: str, *, timeout: float, context: ssl.SSLContext):
                    self.assertEqual(host, "api.deepseek.com")
                    connection = LoopbackHTTPConnection(server.port, timeout)
                    connections.append(connection)
                    return connection

                channel = DeepSeekHTTPChannel(
                    provider, connection_factory=factory
                )
                started = time.monotonic()
                try:
                    with self.assertRaisesRegex(
                        DeepSeekHTTPChannelError,
                        "^deepseek channel: provider request timed out$",
                    ):
                        channel.create_chat_completion(
                            valid_payload(), timeout_seconds=0.1
                        )
                    elapsed = time.monotonic() - started
                    self.assertTrue(server.request_received.is_set())
                    self.assertLess(elapsed, 1.0)
                    self.assertEqual(provider.calls, 1)
                    self.assertEqual(len(connections), 1)
                    self.assertIsNone(connections[0].sock)
                finally:
                    server.close()

    def test_deadline_shuts_down_real_loopback_tls_header_and_body_reads(self):
        openssl = shutil.which("openssl")
        if openssl is None:
            self.skipTest("openssl is unavailable for ephemeral TLS fixture")

        with tempfile.TemporaryDirectory(prefix="deepseek-loopback-tls-") as temp_dir:
            certificate_path = Path(temp_dir) / "server-cert.pem"
            key_path = Path(temp_dir) / "server-key.pem"
            subprocess.run(
                [
                    openssl,
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    str(key_path),
                    "-out",
                    str(certificate_path),
                    "-days",
                    "1",
                    "-nodes",
                    "-subj",
                    "/CN=api.deepseek.com",
                    "-addext",
                    "subjectAltName=DNS:api.deepseek.com",
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(certificate_path, key_path)

            for block_body in (False, True):
                with self.subTest(block_body=block_body):
                    server = LoopbackHTTPServer(
                        block_body=block_body, tls_context=server_context
                    )
                    provider = KeyProvider()
                    connections: list[LoopbackHTTPSConnection] = []

                    def factory(
                        host: str, *, timeout: float, context: ssl.SSLContext
                    ):
                        self.assertEqual(host, "api.deepseek.com")
                        context.load_verify_locations(cafile=certificate_path)
                        connection = LoopbackHTTPSConnection(
                            server.port, timeout, context
                        )
                        connections.append(connection)
                        return connection

                    channel = DeepSeekHTTPChannel(
                        provider, connection_factory=factory
                    )
                    started = time.monotonic()
                    try:
                        with self.assertRaisesRegex(
                            DeepSeekHTTPChannelError,
                            "^deepseek channel: provider request timed out$",
                        ):
                            channel.create_chat_completion(
                                valid_payload(), timeout_seconds=0.5
                            )
                        elapsed = time.monotonic() - started
                        self.assertTrue(server.request_received.is_set())
                        self.assertLess(elapsed, 1.0)
                        self.assertEqual(provider.calls, 1)
                        self.assertEqual(len(connections), 1)
                        self.assertIsNone(connections[0].sock)
                    finally:
                        server.close()

    def test_worker_proposal_round_trips_through_local_verified_https(self):
        openssl = shutil.which("openssl")
        if openssl is None:
            self.skipTest("openssl is unavailable for ephemeral TLS fixture")

        with tempfile.TemporaryDirectory(prefix="deepseek-worker-tls-") as temp_dir:
            certificate_path = Path(temp_dir) / "server-cert.pem"
            key_path = Path(temp_dir) / "server-key.pem"
            subprocess.run(
                [
                    openssl,
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    str(key_path),
                    "-out",
                    str(certificate_path),
                    "-days",
                    "1",
                    "-nodes",
                    "-subj",
                    "/CN=api.deepseek.com",
                    "-addext",
                    "subjectAltName=DNS:api.deepseek.com",
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
            proposal_content = json.dumps(
                {"changes": [{"path": "calculator.py", "content": "fixed locally"}]}
            )
            provider_response = json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": proposal_content,
                                "reasoning_content": "synthetic reasoning sentinel",
                            },
                        }
                    ]
                }
            ).encode("utf-8")
            server = LoopbackHTTPServer(
                block_body=False,
                tls_context=_server_tls_context(certificate_path, key_path),
                response_body=provider_response,
            )
            key_provider = KeyProvider()
            client_context = ssl.create_default_context()
            client_context.load_verify_locations(cafile=certificate_path)
            worker = DeepSeekProposalWorker(DeepSeekHTTPChannel(key_provider))
            task = WorkerInput(
                process_id="synthetic-process",
                task_id="synthetic-task",
                repository_id="synthetic-repository",
                base_commit="synthetic-base",
                declared_change_paths=("calculator.py",),
                task_instruction="Fix this synthetic calculator case",
                context_files=(("calculator.py", "current synthetic code"),),
            )
            try:
                with patch(
                    "app_contracts.deepseek_http_channel.socket.getaddrinfo",
                    return_value=[
                        (
                            socket.AF_INET,
                            socket.SOCK_STREAM,
                            socket.IPPROTO_TCP,
                            "",
                            ("127.0.0.1", server.port),
                        )
                    ],
                ) as resolver, patch(
                    "app_contracts.deepseek_http_channel._create_verified_ssl_context",
                    return_value=client_context,
                ):
                    proposal = worker.propose(task)
                self.assertEqual(
                    proposal,
                    WorkerProposal((("calculator.py", "fixed locally"),)),
                )
                resolver.assert_called_once_with(
                    "api.deepseek.com", 443, type=socket.SOCK_STREAM
                )
                self.assertTrue(server.request_received.is_set())
                self.assertIsNotNone(server.request_header)
                self.assertIsNotNone(server.request_body)
                self.assertEqual(
                    server.request_header.splitlines()[0],
                    b"POST /chat/completions HTTP/1.1",
                )
                headers = {
                    name.strip().lower(): value.strip()
                    for name, value in (
                        line.partition(b":")[::2]
                        for line in server.request_header.splitlines()[1:]
                    )
                    if name
                }
                self.assertEqual(
                    headers[b"authorization"], f"Bearer {SYNTHETIC_KEY}".encode()
                )
                request_payload = json.loads(server.request_body)
                self.assertEqual(request_payload["model"], MODEL_NAME)
                self.assertEqual(request_payload["reasoning_effort"], REASONING_EFFORT)
                self.assertIs(request_payload["stream"], False)
                self.assertEqual(
                    request_payload["response_format"], {"type": "json_object"}
                )
                self.assertNotIn(SYNTHETIC_KEY.encode(), server.request_body)
                self.assertEqual(key_provider.calls, 1)
                self.assertNotIn(SYNTHETIC_KEY, repr(proposal))
                self.assertNotIn("synthetic reasoning sentinel", repr(proposal))
            finally:
                server.close()

    def test_deadline_shuts_down_a_stalled_loopback_tls_handshake(self):
        server = LoopbackHTTPServer(block_body=False)
        provider = KeyProvider()
        connections: list[LoopbackHTTPSConnection] = []

        def factory(host: str, *, timeout: float, context: ssl.SSLContext):
            self.assertEqual(host, "api.deepseek.com")
            connection = LoopbackHTTPSConnection(server.port, timeout, context)
            connections.append(connection)
            return connection

        channel = DeepSeekHTTPChannel(provider, connection_factory=factory)
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(
                DeepSeekHTTPChannelError,
                "^deepseek channel: provider request timed out$",
            ):
                channel.create_chat_completion(valid_payload(), timeout_seconds=0.5)
            elapsed = time.monotonic() - started
            self.assertTrue(server.connected.is_set())
            self.assertLess(elapsed, 1.0)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(len(connections), 1)
            self.assertIsNone(connections[0].sock)
        finally:
            server.close()

    def test_deadline_shuts_down_a_blocked_loopback_request_body_send(self):
        server = NonReadingLoopbackServer()
        provider = KeyProvider()
        connections: list[ConstrainedLoopbackHTTPConnection] = []

        def factory(host: str, *, timeout: float, context: ssl.SSLContext):
            self.assertEqual(host, "api.deepseek.com")
            connection = ConstrainedLoopbackHTTPConnection(server.port, timeout)
            connections.append(connection)
            return connection

        channel = DeepSeekHTTPChannel(provider, connection_factory=factory)
        payload = valid_payload()
        payload["messages"][1]["content"] = "x" * 127_500
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(
                DeepSeekHTTPChannelError,
                "^deepseek channel: provider request timed out$",
            ):
                channel.create_chat_completion(payload, timeout_seconds=0.5)
            elapsed = time.monotonic() - started
            self.assertTrue(server.connected.is_set())
            self.assertLess(elapsed, 1.0)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(len(connections), 1)
            self.assertTrue(connections[0].send_started.is_set())
            self.assertIsNone(connections[0].sock)
            if connections[0].request_completed.is_set():
                self.skipTest(
                    "this OS accepted the full bounded upload despite constrained loopback buffers"
                )
            self.assertFalse(connections[0].request_completed.is_set())
        finally:
            server.close()

    def test_dns_timeout_fails_before_connection_construction(self):
        resolver_started = threading.Event()
        release_resolver = threading.Event()
        resolver_finished = threading.Event()

        def blocked_resolver(*args: object, **kwargs: object):
            resolver_started.set()
            release_resolver.wait(2)
            resolver_finished.set()
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", 443),
                )
            ]

        channel = DeepSeekHTTPChannel(KeyProvider())
        started = time.monotonic()
        try:
            with patch(
                "app_contracts.deepseek_http_channel.socket.getaddrinfo",
                side_effect=blocked_resolver,
            ), patch(
                "app_contracts.deepseek_http_channel.http.client.HTTPSConnection"
            ) as connection_factory:
                with self.assertRaisesRegex(
                    DeepSeekHTTPChannelError,
                    "^deepseek channel: provider request timed out$",
                ):
                    channel.create_chat_completion(
                        valid_payload(), timeout_seconds=0.05
                    )
                self.assertTrue(resolver_started.is_set())
                self.assertLess(time.monotonic() - started, 1.0)
                connection_factory.assert_not_called()
        finally:
            release_resolver.set()
            self.assertTrue(resolver_finished.wait(1))

    def test_dns_failure_is_sanitized_before_connection_construction(self):
        channel = DeepSeekHTTPChannel(KeyProvider())
        with patch(
            "app_contracts.deepseek_http_channel.socket.getaddrinfo",
            side_effect=OSError("synthetic DNS detail sentinel"),
        ), patch(
            "app_contracts.deepseek_http_channel.http.client.HTTPSConnection"
        ) as connection_factory:
            with self.assertRaisesRegex(
                DeepSeekHTTPChannelError,
                "^deepseek channel: provider request failed$",
            ) as error:
                channel.create_chat_completion(valid_payload(), timeout_seconds=1)
        self.assertNotIn("synthetic DNS detail sentinel", str(error.exception))
        connection_factory.assert_not_called()

    def test_unfinished_dns_resolver_occupies_only_one_process_slot(self):
        resolver_started = threading.Event()
        release_resolver = threading.Event()
        resolver_finished = threading.Event()
        calls = 0

        def blocked_resolver(*args: object, **kwargs: object):
            nonlocal calls
            calls += 1
            resolver_started.set()
            release_resolver.wait(2)
            resolver_finished.set()
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", 443),
                )
            ]

        try:
            with patch(
                "app_contracts.deepseek_http_channel.socket.getaddrinfo",
                side_effect=blocked_resolver,
            ), patch(
                "app_contracts.deepseek_http_channel.http.client.HTTPSConnection"
            ) as connection_factory:
                first = DeepSeekHTTPChannel(KeyProvider())
                with self.assertRaisesRegex(
                    DeepSeekHTTPChannelError,
                    "^deepseek channel: provider request timed out$",
                ):
                    first.create_chat_completion(valid_payload(), timeout_seconds=0.05)
                self.assertTrue(resolver_started.is_set())

                second = DeepSeekHTTPChannel(KeyProvider())
                started = time.monotonic()
                with self.assertRaisesRegex(
                    DeepSeekHTTPChannelError,
                    "^deepseek channel: provider request timed out$",
                ):
                    second.create_chat_completion(valid_payload(), timeout_seconds=1)
                self.assertLess(time.monotonic() - started, 0.25)
                self.assertEqual(calls, 1)
                connection_factory.assert_not_called()
        finally:
            release_resolver.set()
            self.assertTrue(resolver_finished.wait(1))

    def test_invalid_configuration_is_rejected(self):
        for provider, factory in ((None, None), (lambda: "key", object())):
            with self.subTest(provider=provider, factory=factory):
                with self.assertRaises(DeepSeekHTTPChannelError):
                    DeepSeekHTTPChannel(provider, connection_factory=factory)

    def test_source_does_not_read_environment_or_files(self):
        tree = ast.parse(
            (ROOT / "src/app_contracts/deepseek_http_channel.py").read_text(
                encoding="utf-8"
            )
        )
        forbidden = {"os", "subprocess", "requests", "httpx", "openai"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(
                    forbidden.intersection(alias.name.split(".")[0] for alias in node.names)
                )
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"open", "exec", "eval", "compile"})


if __name__ == "__main__":
    unittest.main()
