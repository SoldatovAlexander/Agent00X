from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.deepseek_worker import MODEL_NAME, REASONING_EFFORT
from app_contracts.local_ollama_channel import (
    LOCAL_OLLAMA_HOST,
    LOCAL_OLLAMA_MODEL,
    LOCAL_OLLAMA_MODEL_DIGEST,
    LOCAL_OLLAMA_MODEL_REFERENCE,
    LOCAL_OLLAMA_PATH,
    LOCAL_OLLAMA_PORT,
    LOCAL_OLLAMA_SEED,
    LOCAL_OLLAMA_TEMPERATURE,
    LocalOllamaChatCompletionsChannel,
    LocalOllamaChannelError,
)
from app_contracts.worker_model_protocol import MAX_RESPONSE_BYTES


def model_request() -> dict:
    return {
        "model": MODEL_NAME,
        "reasoning_effort": REASONING_EFFORT,
        "max_tokens": 4096,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Make one bounded change."},
        ],
    }


def response_bytes(*, model: str = LOCAL_OLLAMA_MODEL_REFERENCE, finish_reason: str = "stop") -> bytes:
    return json.dumps(
        {
            "id": "chatcmpl-local-fixture",
            "object": "chat.completion",
            "created": 1,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": {
                        "role": "assistant",
                        "content": '{"changes":[{"path":"backend/routes.py","content":"pass\\n"}]}',
                    },
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, length: str | None = None):
        self.status = status
        self.body = body
        self.length = str(len(body)) if length is None else length
        self.read_limits: list[int] = []

    def getheader(self, name: str):
        if name.lower() == "content-type":
            return "application/json"
        if name.lower() == "content-length":
            return self.length
        return None

    def read(self, amount: int) -> bytes:
        self.read_limits.append(amount)
        return self.body[:amount]


class FakeConnection:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.requests: list[tuple[object, ...]] = []
        self.closed = False

    def request(self, *args, **kwargs):
        self.requests.append((*args, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class LocalOllamaChannelTests(unittest.TestCase):
    def make_channel(self, response: FakeResponse):
        connection = FakeConnection(response)
        factory_calls: list[tuple[object, ...]] = []

        def factory(host, *, port, timeout):
            factory_calls.append((host, port, timeout))
            return connection

        return LocalOllamaChatCompletionsChannel(connection_factory=factory), connection, factory_calls

    def test_sends_one_credential_free_request_to_exact_loopback_model_endpoint(self):
        response = FakeResponse(response_bytes())
        channel, connection, factory_calls = self.make_channel(response)

        result = channel.create_chat_completion(model_request(), timeout_seconds=12)

        self.assertEqual(factory_calls, [(LOCAL_OLLAMA_HOST, LOCAL_OLLAMA_PORT, 12.0)])
        self.assertEqual(len(connection.requests), 1)
        method, path, options = connection.requests[0]
        self.assertEqual((method, path), ("POST", LOCAL_OLLAMA_PATH))
        headers = options["headers"]
        self.assertNotIn("Authorization", headers)
        wire_request = json.loads(options["body"])
        self.assertEqual(
            wire_request["model"],
            f"sha256-{LOCAL_OLLAMA_MODEL_DIGEST}",
        )
        self.assertEqual(wire_request["messages"], model_request()["messages"])
        self.assertEqual(wire_request["temperature"], LOCAL_OLLAMA_TEMPERATURE)
        self.assertEqual(wire_request["seed"], LOCAL_OLLAMA_SEED)
        self.assertFalse(wire_request["stream"])
        self.assertEqual(result.choices[0].message.role, "assistant")
        self.assertIn('"changes"', result.choices[0].message.content)
        self.assertEqual(response.read_limits, [MAX_RESPONSE_BYTES + 1])
        self.assertTrue(connection.closed)

    def test_sampling_is_fixed_by_local_channel_not_caller_payload(self):
        response = FakeResponse(response_bytes())
        channel, connection, _factory_calls = self.make_channel(response)
        payload = model_request()
        payload["temperature"] = 1.75
        payload["seed"] = 999

        with self.assertRaises(LocalOllamaChannelError):
            channel.create_chat_completion(payload, timeout_seconds=12)

        self.assertEqual(connection.requests, [])

    def test_channel_is_one_shot_even_after_success(self):
        channel, _connection, _calls = self.make_channel(FakeResponse(response_bytes()))
        channel.create_chat_completion(model_request(), timeout_seconds=1)
        with self.assertRaises(LocalOllamaChannelError):
            channel.create_chat_completion(model_request(), timeout_seconds=1)

    def test_connection_failure_is_not_retried_and_consumes_one_shot(self):
        connection = FakeConnection(FakeResponse(response_bytes()))

        def fail_request(*args, **kwargs):
            connection.requests.append((*args, kwargs))
            raise OSError("synthetic connection failure")

        connection.request = fail_request
        factory_calls = []
        channel = LocalOllamaChatCompletionsChannel(
            connection_factory=lambda *_args, **_kwargs: (
                factory_calls.append("called") or connection
            )
        )

        with self.assertRaises(LocalOllamaChannelError):
            channel.create_chat_completion(model_request(), timeout_seconds=1)
        self.assertEqual(factory_calls, ["called"])
        self.assertEqual(len(connection.requests), 1)
        self.assertTrue(connection.closed)

        with self.assertRaises(LocalOllamaChannelError):
            channel.create_chat_completion(model_request(), timeout_seconds=1)
        self.assertEqual(factory_calls, ["called"])
        self.assertEqual(len(connection.requests), 1)

    def test_rejects_non_200_redirect_without_reading_body(self):
        response = FakeResponse(b"redirect", status=302)
        channel, connection, _calls = self.make_channel(response)
        with self.assertRaises(LocalOllamaChannelError):
            channel.create_chat_completion(model_request(), timeout_seconds=1)
        self.assertEqual(len(connection.requests), 1)
        self.assertEqual(response.read_limits, [])
        self.assertTrue(connection.closed)

    def test_rejects_malformed_oversized_wrong_model_and_non_stop_responses(self):
        invalid = (
            FakeResponse(b"not-json"),
            FakeResponse(b"x" * (MAX_RESPONSE_BYTES + 1), length=str(MAX_RESPONSE_BYTES + 1)),
            FakeResponse(response_bytes(model=LOCAL_OLLAMA_MODEL)),
            FakeResponse(response_bytes(finish_reason="length")),
        )
        for response in invalid:
            with self.subTest(response=response):
                channel, _connection, _calls = self.make_channel(response)
                with self.assertRaises(LocalOllamaChannelError):
                    channel.create_chat_completion(model_request(), timeout_seconds=1)

    def test_rejects_truncated_response_and_bad_content_type(self):
        complete = response_bytes()
        truncated = FakeResponse(complete[:-2], length=str(len(complete)))
        wrong_type = FakeResponse(complete)
        wrong_type.getheader = lambda name: (
            "text/plain" if name.lower() == "content-type" else str(len(complete))
        )
        for response in (truncated, wrong_type):
            with self.subTest(response=response):
                channel, _connection, _calls = self.make_channel(response)
                with self.assertRaises(LocalOllamaChannelError):
                    channel.create_chat_completion(model_request(), timeout_seconds=1)

    def test_invalid_request_and_timeout_fail_before_connection(self):
        factory_calls: list[bool] = []
        channel = LocalOllamaChatCompletionsChannel(
            connection_factory=lambda *_args, **_kwargs: factory_calls.append(True)
        )
        for payload, timeout in (({}, 1), (model_request(), 181), (model_request(), float("nan"))):
            with self.subTest(timeout=timeout):
                candidate = LocalOllamaChatCompletionsChannel(
                    connection_factory=lambda *_args, **_kwargs: factory_calls.append(True)
                )
                with self.assertRaises(LocalOllamaChannelError):
                    candidate.create_chat_completion(payload, timeout_seconds=timeout)
        self.assertEqual(factory_calls, [])
        with self.assertRaises(ValueError):
            LocalOllamaChatCompletionsChannel(connection_factory=object())

    def test_accepts_exact_local_timeout_cap(self):
        response = FakeResponse(response_bytes())
        channel, _connection, factory_calls = self.make_channel(response)
        channel.create_chat_completion(model_request(), timeout_seconds=180)
        self.assertEqual(factory_calls, [(LOCAL_OLLAMA_HOST, LOCAL_OLLAMA_PORT, 180.0)])


if __name__ == "__main__":
    unittest.main()
