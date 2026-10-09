"""Bounded DeepSeek Chat Completions HTTPS channel.

The API key is obtained through an injected callback and exists only while the
transport builds its Authorization header. The callback is an in-process API
boundary, not a security boundary against hostile Python code.
"""

from __future__ import annotations

import http.client
import ipaddress
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
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
)
from .worker_model_protocol import (
    MAX_REQUEST_BYTES as _MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES as _MAX_RESPONSE_BYTES,
    MAX_TIMEOUT_SECONDS as _MAX_TIMEOUT_SECONDS,
    ModelRequestProtocolError,
    encode_chat_completions_request,
)


_API_HOST = "api.deepseek.com"
_API_PATH = "/chat/completions"
_MAX_DNS_ADDRESSES = 32
_DNS_RESOLVER_SLOT = threading.BoundedSemaphore(1)
_CREDENTIAL_SOURCE_SLOT = threading.BoundedSemaphore(1)


class DeepSeekHTTPChannelError(ValueError):
    """A bounded DeepSeek HTTPS request could not be completed safely."""


def _resolve_addresses(
    deadline: float, expired: threading.Event
) -> tuple[tuple[int, int, int, tuple[object, ...]], ...]:
    """Resolve the fixed API host with one bounded, abandonable wait slot.

    A system resolver call cannot be interrupted portably. If it outlives the
    request deadline its single daemon thread may finish later, but the caller
    never uses late results. The process-wide slot prevents repeated channel
    instances from accumulating an unbounded set of stuck resolver threads.
    """

    if not _DNS_RESOLVER_SLOT.acquire(blocking=False):
        raise DeepSeekHTTPChannelError(
            "deepseek channel: provider request timed out"
        )
    completed = threading.Event()
    resolved: list[object] = []
    failures: list[BaseException] = []

    def resolve() -> None:
        try:
            resolved.append(
                socket.getaddrinfo(
                    _API_HOST, 443, type=socket.SOCK_STREAM
                )
            )
        except BaseException as exc:
            failures.append(exc)
        finally:
            completed.set()
            _DNS_RESOLVER_SLOT.release()

    resolver = threading.Thread(
        target=resolve, name="agent00x-deepseek-dns", daemon=True
    )
    try:
        resolver.start()
    except Exception:
        _DNS_RESOLVER_SLOT.release()
        raise DeepSeekHTTPChannelError(
            "deepseek channel: provider request failed"
        ) from None

    remaining = deadline - time.monotonic()
    if remaining <= 0 or not completed.wait(remaining):
        expired.set()
        raise DeepSeekHTTPChannelError(
            "deepseek channel: provider request timed out"
        )
    _check_deadline(deadline, expired)
    if failures or len(resolved) != 1 or type(resolved[0]) is not list:
        raise DeepSeekHTTPChannelError(
            "deepseek channel: provider request failed"
        )

    addresses: list[tuple[int, int, int, tuple[object, ...]]] = []
    for item in resolved[0]:
        try:
            family, socktype, protocol, _canonical_name, sockaddr = item
            if (
                family not in {socket.AF_INET, socket.AF_INET6}
                or socktype != socket.SOCK_STREAM
                or type(sockaddr) is not tuple
                or not sockaddr
                or type(sockaddr[0]) is not str
            ):
                continue
            ipaddress.ip_address(sockaddr[0])
            address = (family, socktype, protocol, sockaddr)
            if address not in addresses:
                addresses.append(address)
            if len(addresses) > _MAX_DNS_ADDRESSES:
                raise ValueError
        except Exception:
            raise DeepSeekHTTPChannelError(
                "deepseek channel: provider request failed"
            ) from None
    if not addresses:
        raise DeepSeekHTTPChannelError(
            "deepseek channel: provider request failed"
        )
    return tuple(addresses)


def _connect_resolved_addresses(
    addresses: tuple[tuple[int, int, int, tuple[object, ...]], ...],
    *,
    timeout: float,
    source_address: tuple[str, int] | None,
    deadline: float,
    expired: threading.Event,
) -> socket.socket:
    """Connect only to numeric resolver results under the shared deadline."""

    last_error: OSError | None = None
    for family, socktype, protocol, sockaddr in addresses:
        _check_deadline(deadline, expired)
        remaining = min(timeout, deadline - time.monotonic())
        if remaining <= 0:
            _check_deadline(deadline, expired)
        connection_socket = socket.socket(family, socktype, protocol)
        try:
            connection_socket.settimeout(remaining)
            if source_address is not None:
                connection_socket.bind(source_address)
            connection_socket.connect(sockaddr)
            _check_deadline(deadline, expired)
            return connection_socket
        except DeepSeekHTTPChannelError:
            connection_socket.close()
            raise
        except OSError as exc:
            last_error = exc
            connection_socket.close()
    if last_error is not None:
        raise last_error
    raise OSError("connection failed")


def _resolve_credential(
    credential_source: CredentialSource,
    deadline: float,
    expired: threading.Event,
) -> object:
    """Bound the caller's wait for a synchronous credential-source callback.

    Python cannot cancel an arbitrary callback safely. A single process-wide
    daemon slot bounds abandoned calls; a callback that finishes late has its
    result discarded and cannot be used to initiate HTTP.
    """

    if not _CREDENTIAL_SOURCE_SLOT.acquire(blocking=False):
        raise DeepSeekHTTPChannelError(
            "deepseek channel: provider request timed out"
        )
    completed = threading.Event()
    failed = threading.Event()
    result: list[object] = []

    def resolve() -> None:
        try:
            value = credential_source()
        except BaseException:
            failed.set()
        else:
            if not expired.is_set() and time.monotonic() < deadline:
                result.append(value)
            del value
        finally:
            completed.set()
            _CREDENTIAL_SOURCE_SLOT.release()

    callback = threading.Thread(
        target=resolve, name="agent00x-credential-source", daemon=True
    )
    try:
        callback.start()
    except Exception:
        _CREDENTIAL_SOURCE_SLOT.release()
        raise DeepSeekHTTPChannelError(
            "deepseek channel: credential provider failed"
        ) from None

    remaining = deadline - time.monotonic()
    if remaining <= 0 or not completed.wait(remaining):
        expired.set()
        raise DeepSeekHTTPChannelError(
            "deepseek channel: provider request timed out"
        )
    _check_deadline(deadline, expired)
    if failed.is_set() or len(result) != 1:
        raise DeepSeekHTTPChannelError(
            "deepseek channel: credential provider failed"
        )
    return result[0]


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
        api_key = _resolve_credential(
            self._api_key_provider, deadline, deadline_expired
        )
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
            resolved_addresses = None
            if self._connection_factory is None:
                resolved_addresses = _resolve_addresses(deadline, deadline_expired)
                _check_deadline(deadline, deadline_expired)
            connection = factory(_API_HOST, timeout=timeout, context=context)
            if resolved_addresses is not None:

                def connect_to_resolved(
                    _address: tuple[str, int],
                    connect_timeout: float,
                    source_address: tuple[str, int] | None = None,
                ) -> socket.socket:
                    return _connect_resolved_addresses(
                        resolved_addresses,
                        timeout=connect_timeout,
                        source_address=source_address,
                        deadline=deadline,
                        expired=deadline_expired,
                    )

                connection._create_connection = connect_to_resolved
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
    try:
        return encode_chat_completions_request(payload)
    except ModelRequestProtocolError as exc:
        if exc.reason == "too_large":
            raise DeepSeekHTTPChannelError(
                "deepseek channel: request exceeds limit"
            ) from None
        raise DeepSeekHTTPChannelError("deepseek channel: request is invalid") from None


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
