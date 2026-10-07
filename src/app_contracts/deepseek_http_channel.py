"""Bounded DeepSeek Chat Completions HTTPS channel.

The API key is obtained through an injected callback and exists only while the
transport builds its Authorization header. The callback is an in-process API
boundary, not a security boundary against hostile Python code.
"""

from __future__ import annotations

import http.client
import json
import math
import socket
import ssl
import threading
import time
from typing import Callable

import certifi

from .credential_source import CredentialSource
from .deepseek_worker import (
    MODEL_NAME,
    REASONING_EFFORT,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
)


_API_HOST = "api.deepseek.com"
_API_PATH = "/chat/completions"
_MAX_TIMEOUT_SECONDS = 30.0
_MAX_REQUEST_BYTES = 128_000
_MAX_RESPONSE_BYTES = 65_536


class DeepSeekHTTPChannelError(ValueError):
    """A bounded DeepSeek HTTPS request could not be completed safely."""


class DeepSeekHTTPChannel:
    """Fixed-host, one-call HTTPS transport for the DeepSeek Worker adapter."""

    def __init__(
        self,
        api_key_provider: CredentialSource,
        *,
        connection_factory: Callable[..., object] | None = None,
    ) -> None:
        if not callable(api_key_provider) or (
            connection_factory is not None and not callable(connection_factory)
        ):
            raise DeepSeekHTTPChannelError("deepseek channel: config is invalid")
        self._api_key_provider = api_key_provider
        self._connection_factory = connection_factory
        self._attempt_lock = threading.Lock()
        self._attempt_started = False

    def __repr__(self) -> str:
        return (
            "DeepSeekHTTPChannel(authentication='opaque-provider', "
            "endpoint='api.deepseek.com/chat/completions')"
        )

    def create_chat_completion(
        self, payload: dict, *, timeout_seconds: float
    ) -> ChatCompletionsModelResult:
        timeout = _validate_timeout(timeout_seconds)
        request_body = _encode_request(payload)
        with self._attempt_lock:
            if self._attempt_started:
                raise DeepSeekHTTPChannelError(
                    "deepseek channel: call limit exceeded"
                )
            self._attempt_started = True
        deadline_expired = threading.Event()
        deadline = time.monotonic() + timeout
        try:
            api_key = self._api_key_provider()
        except Exception:
            if time.monotonic() >= deadline:
                raise DeepSeekHTTPChannelError(
                    "deepseek channel: provider request timed out"
                ) from None
            raise DeepSeekHTTPChannelError(
                "deepseek channel: credential provider failed"
            ) from None
        _check_deadline(deadline, deadline_expired)
        if type(api_key) is not str or not api_key or api_key.strip() != api_key:
            raise DeepSeekHTTPChannelError(
                "deepseek channel: credential provider failed"
            )

        connection = None
        timer: threading.Timer | None = None
        try:
            context = _create_verified_ssl_context()
            factory = self._connection_factory or http.client.HTTPSConnection
            connection = factory(_API_HOST, timeout=timeout, context=context)
            _check_deadline(deadline, deadline_expired)

            def abort_connection() -> None:
                deadline_expired.set()
                active_socket = getattr(connection, "sock", None)
                shutdown = getattr(active_socket, "shutdown", None)
                if callable(shutdown):
                    try:
                        shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                close = getattr(connection, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass

            timer = threading.Timer(
                max(0.0, deadline - time.monotonic()), abort_connection
            )
            timer.daemon = True
            timer.start()
            connection.request(
                "POST",
                _API_PATH,
                body=request_body,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            _check_deadline(deadline, deadline_expired)
            response = connection.getresponse()
            _check_deadline(deadline, deadline_expired)
            status = getattr(response, "status", None)
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            _check_deadline(deadline, deadline_expired)
            timer.cancel()
            timer.join()
            timer = None
            _check_deadline(deadline, deadline_expired)
            if type(status) is not int or status != 200:
                raise DeepSeekHTTPChannelError(
                    "deepseek channel: provider response rejected"
                )
            if type(body) is not bytes or len(body) > _MAX_RESPONSE_BYTES:
                raise DeepSeekHTTPChannelError(
                    "deepseek channel: response exceeds limit"
                )
            result = _parse_response(body)
            if result is None:
                raise DeepSeekHTTPChannelError(
                    "deepseek channel: provider response is invalid"
                )
            return result
        except DeepSeekHTTPChannelError:
            raise
        except Exception:
            if deadline_expired.is_set() or (
                deadline is not None and time.monotonic() >= deadline
            ):
                raise DeepSeekHTTPChannelError(
                    "deepseek channel: provider request timed out"
                ) from None
            raise DeepSeekHTTPChannelError(
                "deepseek channel: provider request failed"
            ) from None
        finally:
            if timer is not None:
                timer.cancel()
                timer.join()
            close = getattr(connection, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass


def _check_deadline(deadline: float, expired: threading.Event) -> None:
    if expired.is_set() or time.monotonic() >= deadline:
        raise DeepSeekHTTPChannelError(
            "deepseek channel: provider request timed out"
        )


def _validate_timeout(value: object) -> float:
    try:
        valid = (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and 0 < float(value) <= _MAX_TIMEOUT_SECONDS
        )
    except (OverflowError, TypeError, ValueError):
        valid = False
    if not valid:
        raise DeepSeekHTTPChannelError("deepseek channel: timeout is invalid")
    return float(value)


def _encode_request(payload: object) -> bytes:
    if type(payload) is not dict:
        raise DeepSeekHTTPChannelError("deepseek channel: request is invalid")
    try:
        if (
            set(payload)
            != {
                "model",
                "reasoning_effort",
                "max_tokens",
                "stream",
                "response_format",
                "messages",
            }
            or payload.get("model") != MODEL_NAME
            or payload.get("reasoning_effort") != REASONING_EFFORT
            or payload.get("stream") is not False
            or type(payload.get("max_tokens")) is not int
            or not 0 < payload["max_tokens"] <= 4096
            or payload.get("response_format") != {"type": "json_object"}
            or type(payload.get("messages")) is not list
            or len(payload["messages"]) != 2
            or any(
                type(message) is not dict
                or set(message) != {"role", "content"}
                or type(message.get("role")) is not str
                or type(message.get("content")) is not str
                for message in payload["messages"]
            )
            or payload["messages"][0]["role"] != "system"
            or payload["messages"][1]["role"] != "user"
        ):
            raise ValueError()
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        raise DeepSeekHTTPChannelError("deepseek channel: request is invalid") from None
    if len(encoded) > _MAX_REQUEST_BYTES:
        raise DeepSeekHTTPChannelError("deepseek channel: request exceeds limit")
    return encoded


def _create_verified_ssl_context() -> ssl.SSLContext:
    try:
        context = ssl.create_default_context()
        ca_file = certifi.where()
        if type(ca_file) is not str or not ca_file:
            raise ValueError()
        context.load_verify_locations(cafile=ca_file)
        if (
            not context.check_hostname
            or context.verify_mode != ssl.CERT_REQUIRED
            or context.cert_store_stats().get("x509_ca", 0) < 1
        ):
            raise ValueError()
        return context
    except Exception:
        raise DeepSeekHTTPChannelError(
            "deepseek channel: TLS trust configuration is invalid"
        ) from None


def _parse_response(body: bytes) -> ChatCompletionsModelResult | None:
    try:
        decoded = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
        if type(decoded) is not dict or type(decoded.get("choices")) is not list:
            return None
        choices = decoded["choices"]
        if len(choices) != 1 or type(choices[0]) is not dict:
            return None
        raw_choice = choices[0]
        raw_message = raw_choice.get("message")
        finish_reason = raw_choice.get("finish_reason")
        if (
            type(raw_message) is not dict
            or type(finish_reason) is not str
            or type(raw_message.get("role")) is not str
        ):
            return None
        content = raw_message.get("content")
        tool_calls = raw_message.get("tool_calls", [])
        refusal = raw_message.get("refusal")
        if (
            (content is not None and type(content) is not str)
            or type(tool_calls) is not list
            or (refusal is not None and type(refusal) is not str)
        ):
            return None
        return ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason=finish_reason,
                    message=ChatCompletionMessage(
                        role=raw_message["role"],
                        content=content,
                        tool_calls=tuple(tool_calls),
                        refusal=refusal,
                        # Provider reasoning is deliberately ignored.
                        reasoning_content=None,
                    ),
                ),
            )
        )
    except Exception:
        return None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON property")
        result[key] = value
    return result
