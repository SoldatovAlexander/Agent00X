"""Experimental, one-shot Unix-socket bridge for a host-owned model channel.

This is a host-local IPC prototype, not a container boundary or a credential
manager. It never obtains credentials or performs network I/O itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import select
import socket
import stat
import struct
import threading
import time

from .worker_model_protocol import (
    MAX_REQUEST_BYTES as _MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES as _MAX_RESPONSE_BYTES,
    MAX_LOCAL_MODEL_TIMEOUT_SECONDS as _MAX_LOCAL_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS as _MAX_TIMEOUT_SECONDS,
    encode_chat_completions_request as _encode_request,
)
from .deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
)

_REQUEST_SCHEMA = "agent00x-worker-model-request/v1"
_RESPONSE_SCHEMA = "agent00x-worker-model-response/v1"
_FRAME_PREFIX_BYTES = 4
_MAX_REQUEST_FRAME_BYTES = _MAX_REQUEST_BYTES
_MAX_RESPONSE_FRAME_BYTES = _MAX_RESPONSE_BYTES


class WorkerModelIPCError(ValueError):
    """A fixed, redacted failure from the experimental model IPC channel."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    raise ValueError


def _encode_json(value: object, *, maximum: int) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        raise WorkerModelIPCError("worker model IPC: message is invalid") from None
    if not encoded or len(encoded) > maximum:
        raise WorkerModelIPCError("worker model IPC: message exceeds limit")
    return encoded


def _decode_json(encoded: bytes, *, maximum: int) -> object:
    if type(encoded) is not bytes or not encoded or len(encoded) > maximum:
        raise WorkerModelIPCError("worker model IPC: message exceeds limit")
    try:
        return json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except Exception:
        raise WorkerModelIPCError("worker model IPC: message is invalid") from None


def _validate_timeout(
    value: object, *, maximum: float = _MAX_TIMEOUT_SECONDS
) -> float:
    try:
        valid = (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and 0 < float(value) <= maximum
        )
        timeout = float(value)
    except (OverflowError, TypeError, ValueError):
        valid = False
        timeout = 0.0
    if not valid:
        raise WorkerModelIPCError("worker model IPC: timeout is invalid")
    return timeout


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WorkerModelIPCError("worker model IPC: request timed out")
    return remaining


def _read_exact(connection: socket.socket, size: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    remaining_size = size
    while remaining_size:
        connection.settimeout(_remaining(deadline))
        try:
            chunk = connection.recv(remaining_size)
        except Exception:
            raise WorkerModelIPCError("worker model IPC: transport failed") from None
        if not chunk:
            raise WorkerModelIPCError("worker model IPC: transport failed")
        chunks.append(chunk)
        remaining_size -= len(chunk)
    return b"".join(chunks)


def _read_frame(
    connection: socket.socket, *, maximum: int, deadline: float
) -> bytes:
    prefix = _read_exact(connection, _FRAME_PREFIX_BYTES, deadline)
    (size,) = struct.unpack(">I", prefix)
    if size == 0 or size > maximum:
        raise WorkerModelIPCError("worker model IPC: message exceeds limit")
    return _read_exact(connection, size, deadline)


def _write_frame(
    connection: socket.socket,
    payload: bytes,
    *,
    maximum: int,
    deadline: float,
) -> None:
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        raise WorkerModelIPCError("worker model IPC: message exceeds limit")
    connection.settimeout(_remaining(deadline))
    try:
        connection.sendall(struct.pack(">I", len(payload)) + payload)
    except Exception:
        raise WorkerModelIPCError("worker model IPC: transport failed") from None


def _validate_pipe_stream(stream: object) -> int:
    try:
        descriptor = stream.fileno()
        metadata = os.fstat(descriptor)
        if type(descriptor) is not int or not stat.S_ISFIFO(metadata.st_mode):
            raise ValueError
        return descriptor
    except Exception:
        raise WorkerModelIPCError("worker model IPC: stream unavailable") from None


def _read_stream_exact(descriptor: int, size: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    remaining_size = size
    while remaining_size:
        remaining_time = _remaining(deadline)
        try:
            readable, _writable, _exceptional = select.select(
                [descriptor], [], [], remaining_time
            )
            if not readable:
                raise WorkerModelIPCError("worker model IPC: request timed out")
            try:
                chunk = os.read(descriptor, remaining_size)
            except BlockingIOError:
                continue
        except WorkerModelIPCError:
            raise
        except Exception:
            raise WorkerModelIPCError("worker model IPC: transport failed") from None
        if not chunk:
            raise WorkerModelIPCError("worker model IPC: transport failed")
        chunks.append(chunk)
        remaining_size -= len(chunk)
    return b"".join(chunks)


def _write_stream_all(descriptor: int, payload: bytes, deadline: float) -> None:
    offset = 0
    while offset < len(payload):
        remaining_time = _remaining(deadline)
        try:
            _readable, writable, _exceptional = select.select(
                [], [descriptor], [], remaining_time
            )
            if not writable:
                raise WorkerModelIPCError("worker model IPC: request timed out")
            try:
                written = os.write(descriptor, payload[offset:])
            except BlockingIOError:
                continue
        except WorkerModelIPCError:
            raise
        except Exception:
            raise WorkerModelIPCError("worker model IPC: transport failed") from None
        if written <= 0:
            raise WorkerModelIPCError("worker model IPC: transport failed")
        offset += written


def _read_stream_frame(
    descriptor: int, *, maximum: int, deadline: float
) -> bytes:
    prefix = _read_stream_exact(descriptor, _FRAME_PREFIX_BYTES, deadline)
    (size,) = struct.unpack(">I", prefix)
    if size == 0 or size > maximum:
        raise WorkerModelIPCError("worker model IPC: message exceeds limit")
    return _read_stream_exact(descriptor, size, deadline)


def _write_stream_frame(
    descriptor: int, payload: bytes, *, maximum: int, deadline: float
) -> None:
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        raise WorkerModelIPCError("worker model IPC: message exceeds limit")
    _write_stream_all(descriptor, struct.pack(">I", len(payload)) + payload, deadline)


def _validate_socket_path(path: str | os.PathLike[str]) -> Path:
    try:
        socket_path = Path(path)
        if (
            not socket_path.is_absolute()
            or ".." in socket_path.parts
            or socket_path == Path(socket_path.anchor)
            or socket_path.name in {"", ".", ".."}
            or socket_path.is_symlink()
            or os.path.lexists(socket_path)
        ):
            raise ValueError
        parent = socket_path.parent
        parent_stat = parent.lstat()
        if (
            not stat.S_ISDIR(parent_stat.st_mode)
            or stat.S_ISLNK(parent_stat.st_mode)
            or parent_stat.st_uid != os.getuid()
            or stat.S_IMODE(parent_stat.st_mode) & 0o077
        ):
            raise ValueError
        return socket_path
    except Exception:
        raise WorkerModelIPCError("worker model IPC: socket path unavailable") from None


def _encode_result(result: object) -> bytes:
    if type(result) is not ChatCompletionsModelResult or len(result.choices) != 1:
        raise WorkerModelIPCError("worker model IPC: channel result invalid")
    choice = result.choices[0]
    if type(choice) is not ChatCompletionChoice or type(choice.finish_reason) is not str:
        raise WorkerModelIPCError("worker model IPC: channel result invalid")
    message = choice.message
    if (
        type(message) is not ChatCompletionMessage
        or type(message.role) is not str
        or (message.content is not None and type(message.content) is not str)
        or type(message.tool_calls) is not tuple
        or (message.refusal is not None and type(message.refusal) is not str)
    ):
        raise WorkerModelIPCError("worker model IPC: channel result invalid")
    return _encode_json(
        {
            "schema": _RESPONSE_SCHEMA,
            "result": {
                "finish_reason": choice.finish_reason,
                "message": {
                    "role": message.role,
                    "content": message.content,
                    "tool_calls": list(message.tool_calls),
                    "refusal": message.refusal,
                },
            },
        },
        maximum=_MAX_RESPONSE_FRAME_BYTES,
    )


def _decode_result(encoded: bytes) -> ChatCompletionsModelResult:
    value = _decode_json(encoded, maximum=_MAX_RESPONSE_FRAME_BYTES)
    if type(value) is not dict or set(value) != {"schema", "result"}:
        raise WorkerModelIPCError("worker model IPC: response is invalid")
    if value.get("schema") != _RESPONSE_SCHEMA:
        raise WorkerModelIPCError("worker model IPC: response is invalid")
    result = value.get("result")
    if type(result) is not dict or set(result) != {"finish_reason", "message"}:
        raise WorkerModelIPCError("worker model IPC: response is invalid")
    message = result.get("message")
    if type(message) is not dict or set(message) != {
        "role",
        "content",
        "tool_calls",
        "refusal",
    }:
        raise WorkerModelIPCError("worker model IPC: response is invalid")
    if (
        type(result.get("finish_reason")) is not str
        or type(message.get("role")) is not str
        or (message.get("content") is not None and type(message.get("content")) is not str)
        or type(message.get("tool_calls")) is not list
        or (message.get("refusal") is not None and type(message.get("refusal")) is not str)
    ):
        raise WorkerModelIPCError("worker model IPC: response is invalid")
    return ChatCompletionsModelResult(
        choices=(
            ChatCompletionChoice(
                finish_reason=result["finish_reason"],
                message=ChatCompletionMessage(
                    role=message["role"],
                    content=message["content"],
                    tool_calls=tuple(message["tool_calls"]),
                    refusal=message["refusal"],
                    reasoning_content=None,
                ),
            ),
        )
    )


class StdioChatCompletionsChannel:
    """One-call adapter over explicitly injected anonymous binary pipes."""

    def __init__(
        self,
        reader: object,
        writer: object,
        *,
        maximum_timeout_seconds: float = _MAX_TIMEOUT_SECONDS,
    ) -> None:
        self._reader_fd = _validate_pipe_stream(reader)
        self._writer_fd = _validate_pipe_stream(writer)
        if self._reader_fd == self._writer_fd:
            raise WorkerModelIPCError("worker model IPC: stream unavailable")
        self._maximum_timeout_seconds = _validate_timeout(
            maximum_timeout_seconds, maximum=_MAX_LOCAL_TIMEOUT_SECONDS
        )
        self._attempt_lock = threading.Lock()
        self._attempt_started = False
        self._closed = False

    def __repr__(self) -> str:
        return "StdioChatCompletionsChannel(streams='injected', calls=one-shot)"

    def create_chat_completion(
        self, payload: dict, *, timeout_seconds: float
    ) -> ChatCompletionsModelResult:
        timeout = _validate_timeout(
            timeout_seconds, maximum=self._maximum_timeout_seconds
        )
        try:
            _encode_request(payload)
            request = _encode_json(
                {
                    "schema": _REQUEST_SCHEMA,
                    "timeout_seconds": timeout,
                    "payload": payload,
                },
                maximum=_MAX_REQUEST_FRAME_BYTES,
            )
        except Exception:
            raise WorkerModelIPCError("worker model IPC: request is invalid") from None
        with self._attempt_lock:
            if self._attempt_started or self._closed:
                raise WorkerModelIPCError("worker model IPC: call limit exceeded")
            self._attempt_started = True
        deadline = time.monotonic() + timeout
        try:
            reader_blocking = os.get_blocking(self._reader_fd)
            writer_blocking = os.get_blocking(self._writer_fd)
        except Exception:
            raise WorkerModelIPCError("worker model IPC: stream unavailable") from None
        reader_changed = False
        try:
            os.set_blocking(self._reader_fd, False)
            reader_changed = True
            os.set_blocking(self._writer_fd, False)
        except Exception:
            if reader_changed:
                try:
                    os.set_blocking(self._reader_fd, reader_blocking)
                except Exception:
                    pass
            raise WorkerModelIPCError("worker model IPC: stream unavailable") from None
        try:
            _write_stream_frame(
                self._writer_fd,
                request,
                maximum=_MAX_REQUEST_FRAME_BYTES,
                deadline=deadline,
            )
            response = _read_stream_frame(
                self._reader_fd,
                maximum=_MAX_RESPONSE_FRAME_BYTES,
                deadline=deadline,
            )
            decoded = _decode_json(response, maximum=_MAX_RESPONSE_FRAME_BYTES)
            if (
                type(decoded) is dict
                and set(decoded) == {"schema", "error"}
                and decoded.get("schema") == _RESPONSE_SCHEMA
                and decoded.get("error") == "request_failed"
            ):
                raise WorkerModelIPCError("worker model IPC: request failed")
            return _decode_result(response)
        finally:
            restore_failed = False
            for descriptor, blocking in (
                (self._reader_fd, reader_blocking),
                (self._writer_fd, writer_blocking),
            ):
                try:
                    os.set_blocking(descriptor, blocking)
                except Exception:
                    restore_failed = True
            with self._attempt_lock:
                self._closed = True
            if restore_failed:
                raise WorkerModelIPCError("worker model IPC: stream cleanup failed") from None


class UnixSocketChatCompletionsChannel:
    """One-call worker-side client; it has no credential or network adapter."""

    def __init__(
        self,
        socket_path: str | os.PathLike[str],
        *,
        maximum_timeout_seconds: float = _MAX_TIMEOUT_SECONDS,
    ) -> None:
        self._socket_path = Path(socket_path)
        self._maximum_timeout_seconds = _validate_timeout(
            maximum_timeout_seconds, maximum=_MAX_LOCAL_TIMEOUT_SECONDS
        )
        self._attempt_lock = threading.Lock()
        self._attempt_started = False

    def __repr__(self) -> str:
        return "UnixSocketChatCompletionsChannel(socket='configured')"

    def create_chat_completion(
        self, payload: dict, *, timeout_seconds: float
    ) -> ChatCompletionsModelResult:
        timeout = _validate_timeout(
            timeout_seconds, maximum=self._maximum_timeout_seconds
        )
        try:
            _encode_request(payload)
            request = _encode_json(
                {
                    "schema": _REQUEST_SCHEMA,
                    "timeout_seconds": timeout,
                    "payload": payload,
                },
                maximum=_MAX_REQUEST_FRAME_BYTES,
            )
        except Exception:
            raise WorkerModelIPCError("worker model IPC: request is invalid") from None
        with self._attempt_lock:
            if self._attempt_started:
                raise WorkerModelIPCError("worker model IPC: call limit exceeded")
            self._attempt_started = True
        deadline = time.monotonic() + timeout
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(timeout)
            connection.connect(str(self._socket_path))
            _write_frame(
                connection,
                request,
                maximum=_MAX_REQUEST_FRAME_BYTES,
                deadline=deadline,
            )
            response = _read_frame(
                connection,
                maximum=_MAX_RESPONSE_FRAME_BYTES,
                deadline=deadline,
            )
            return _decode_result(response)
        except WorkerModelIPCError:
            raise
        except Exception:
            raise WorkerModelIPCError("worker model IPC: transport failed") from None
        finally:
            connection.close()


class UnixSocketChatCompletionsBroker:
    """Single-request host-side delegate around an injected chat channel."""

    def __init__(
        self,
        socket_path: str | os.PathLike[str],
        channel: object,
        *,
        timeout_seconds: float = _MAX_TIMEOUT_SECONDS,
    ) -> None:
        if not callable(getattr(channel, "create_chat_completion", None)):
            raise WorkerModelIPCError("worker model IPC: broker config invalid")
        self._socket_path = _validate_socket_path(socket_path)
        self._channel = channel
        self._timeout_seconds = _validate_timeout(
            timeout_seconds, maximum=_MAX_LOCAL_TIMEOUT_SECONDS
        )
        self._server: socket.socket | None = None
        self._socket_identity: tuple[int, int] | None = None
        self._used = False
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return "UnixSocketChatCompletionsBroker(channel='injected', calls=one-shot)"

    def open(self) -> None:
        with self._lock:
            if self._server is not None or self._used:
                raise WorkerModelIPCError("worker model IPC: broker unavailable")
            _validate_socket_path(self._socket_path)
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(self._socket_path))
                os.chmod(self._socket_path, 0o600, follow_symlinks=False)
                metadata = self._socket_path.lstat()
                if not stat.S_ISSOCK(metadata.st_mode):
                    raise ValueError
                self._socket_identity = (metadata.st_dev, metadata.st_ino)
                server.listen(1)
                server.settimeout(self._timeout_seconds)
                self._server = server
            except Exception:
                server.close()
                self._remove_owned_socket()
                raise WorkerModelIPCError("worker model IPC: broker unavailable") from None

    def serve_once(self) -> None:
        with self._lock:
            if self._used or self._server is None:
                raise WorkerModelIPCError("worker model IPC: call limit exceeded")
            self._used = True
            server = self._server
        deadline = time.monotonic() + self._timeout_seconds
        connection: socket.socket | None = None
        try:
            try:
                connection, _address = server.accept()
                request_bytes = _read_frame(
                    connection,
                    maximum=_MAX_REQUEST_FRAME_BYTES,
                    deadline=deadline,
                )
                request = _decode_json(request_bytes, maximum=_MAX_REQUEST_FRAME_BYTES)
                if (
                    type(request) is not dict
                    or set(request) != {"schema", "timeout_seconds", "payload"}
                    or request.get("schema") != _REQUEST_SCHEMA
                ):
                    raise WorkerModelIPCError("worker model IPC: request is invalid")
                timeout = min(
                    self._timeout_seconds,
                    _validate_timeout(
                        request.get("timeout_seconds"),
                        maximum=self._timeout_seconds,
                    ),
                    _remaining(deadline),
                )
                payload = request.get("payload")
                _encode_request(payload)
                result = self._channel.create_chat_completion(
                    payload,
                    timeout_seconds=timeout,
                )
                response = _encode_result(result)
            except Exception:
                response = _encode_json(
                    {"schema": _RESPONSE_SCHEMA, "error": "request_failed"},
                    maximum=_MAX_RESPONSE_FRAME_BYTES,
                )
            try:
                _write_frame(
                    connection,
                    response,
                    maximum=_MAX_RESPONSE_FRAME_BYTES,
                    deadline=deadline,
                )
            except WorkerModelIPCError:
                # A client may reach its own deadline and close while the
                # injected channel is completing. Do not log or expose details.
                pass
        except Exception:
            raise WorkerModelIPCError("worker model IPC: request failed") from None
        finally:
            if connection is not None:
                connection.close()
            self.close()

    def close(self) -> None:
        with self._lock:
            server = self._server
            self._server = None
        if server is not None:
            server.close()
        self._remove_owned_socket()

    def _remove_owned_socket(self) -> None:
        identity = self._socket_identity
        self._socket_identity = None
        if identity is None:
            return
        try:
            metadata = self._socket_path.lstat()
            if (
                stat.S_ISSOCK(metadata.st_mode)
                and (metadata.st_dev, metadata.st_ino) == identity
            ):
                self._socket_path.unlink()
        except Exception:
            pass

    def __enter__(self) -> "UnixSocketChatCompletionsBroker":
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
