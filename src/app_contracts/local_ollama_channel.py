"""One-shot, credential-free channel to a fixed local Ollama endpoint."""

from __future__ import annotations

import http.client
import json
import math
import threading
from collections.abc import Callable

from .deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
)
from .worker_model_protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_LOCAL_MODEL_TIMEOUT_SECONDS,
    ModelRequestProtocolError,
    encode_chat_completions_request,
)


LOCAL_OLLAMA_HOST = "127.0.0.1"
LOCAL_OLLAMA_PORT = 11434
LOCAL_OLLAMA_PATH = "/v1/chat/completions"
LOCAL_OLLAMA_MODEL = "qwen2.5-coder:7b"
LOCAL_OLLAMA_MODEL_DIGEST = "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364"
# Ollama resolves this local sha256-<hex> form directly to a manifest blob.
# Do not send the mutable model tag after the metadata preflight.
LOCAL_OLLAMA_MODEL_REFERENCE = f"sha256-{LOCAL_OLLAMA_MODEL_DIGEST}"
LOCAL_OLLAMA_TEMPERATURE = 0.0
LOCAL_OLLAMA_SEED = 42


class LocalOllamaChannelError(ValueError):
    """A fixed, redacted failure from the loopback-only model channel."""


class LocalOllamaChatCompletionsChannel:
    """Send at most one bounded request to the fixed loopback Ollama service.

    There is deliberately no credential interface, configurable URL, proxy,
    redirect handling, or retry. An optional factory exists only for synthetic
    offline tests; production always uses ``HTTPConnection`` to 127.0.0.1.
    """

    def __init__(
        self,
        *,
        connection_factory: Callable[..., object] | None = None,
    ) -> None:
        if connection_factory is not None and not callable(connection_factory):
            raise ValueError("local Ollama channel: configuration is invalid")
        self._connection_factory = connection_factory
        self._used = False
        self._lock = threading.Lock()

    def create_chat_completion(
        self, payload: dict, *, timeout_seconds: float
    ) -> ChatCompletionsModelResult:
        with self._lock:
            if self._used:
                raise LocalOllamaChannelError("local Ollama channel: request unavailable")
            self._used = True
        try:
            timeout = _validate_timeout(timeout_seconds)
            encoded_request = encode_chat_completions_request(payload)
            if len(encoded_request) > MAX_REQUEST_BYTES:
                raise ValueError
            wire_payload = {
                "model": LOCAL_OLLAMA_MODEL_REFERENCE,
                "max_tokens": payload["max_tokens"],
                "temperature": LOCAL_OLLAMA_TEMPERATURE,
                "seed": LOCAL_OLLAMA_SEED,
                "stream": False,
                "response_format": {"type": "json_object"},
                "messages": payload["messages"],
            }
            body = json.dumps(
                wire_payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if not body or len(body) > MAX_REQUEST_BYTES:
                raise ValueError
            factory = self._connection_factory or http.client.HTTPConnection
            connection = factory(
                LOCAL_OLLAMA_HOST,
                port=LOCAL_OLLAMA_PORT,
                timeout=timeout,
            )
            connection.request(
                "POST",
                LOCAL_OLLAMA_PATH,
                body=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            if type(getattr(response, "status", None)) is not int or response.status != 200:
                raise ValueError
            content_type = response.getheader("Content-Type")
            if (
                type(content_type) is not str
                or content_type.split(";", 1)[0].strip().lower() != "application/json"
            ):
                raise ValueError
            content_length = response.getheader("Content-Length")
            if content_length is not None:
                if (
                    type(content_length) is not str
                    or not content_length.isascii()
                    or not content_length.isdecimal()
                    or int(content_length) > MAX_RESPONSE_BYTES
                ):
                    raise ValueError
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
            if (
                type(response_body) is not bytes
                or not response_body
                or len(response_body) > MAX_RESPONSE_BYTES
                or (content_length is not None and len(response_body) != int(content_length))
            ):
                raise ValueError
            result = _decode_response(response_body)
            return result
        except LocalOllamaChannelError:
            raise
        except Exception:
            raise LocalOllamaChannelError(
                "local Ollama channel: request failed"
            ) from None
        finally:
            try:
                if "connection" in locals():
                    connection.close()
            except Exception:
                pass


def _validate_timeout(value: object) -> float:
    try:
        timeout = float(value)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or timeout > MAX_LOCAL_MODEL_TIMEOUT_SECONDS
        ):
            raise ValueError
        return timeout
    except Exception:
        raise LocalOllamaChannelError(
            "local Ollama channel: request failed"
        ) from None


def _decode_response(encoded: bytes) -> ChatCompletionsModelResult:
    def reject_constant(_value: str) -> None:
        raise ValueError

    try:
        value = json.loads(encoded.decode("utf-8"), parse_constant=reject_constant)
        if (
            type(value) is not dict
            or value.get("model") != LOCAL_OLLAMA_MODEL_REFERENCE
            or type(value.get("choices")) is not list
            or len(value["choices"]) != 1
        ):
            raise ValueError
        choice = value["choices"][0]
        if (
            type(choice) is not dict
            or choice.get("finish_reason") != "stop"
            or type(choice.get("message")) is not dict
        ):
            raise ValueError
        message = choice["message"]
        if (
            message.get("role") != "assistant"
            or type(message.get("content")) is not str
            or not message["content"]
            or message.get("tool_calls") not in (None, [])
            or message.get("refusal") not in (None, "")
        ):
            raise ValueError
        return ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=message["content"],
                    ),
                ),
            )
        )
    except Exception:
        raise LocalOllamaChannelError(
            "local Ollama channel: response is invalid"
        ) from None
