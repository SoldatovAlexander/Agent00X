"""Transport-independent bounds and validation for the Worker model wire format."""

from __future__ import annotations

import json

from .deepseek_worker import MODEL_NAME, REASONING_EFFORT


MAX_TIMEOUT_SECONDS = 30.0
MAX_REQUEST_BYTES = 128_000
MAX_RESPONSE_BYTES = 65_536


class ModelRequestProtocolError(ValueError):
    """A fixed request-protocol validation failure."""

    def __init__(self, reason: str) -> None:
        if reason not in {"invalid", "too_large"}:
            reason = "invalid"
        self.reason = reason
        super().__init__(reason)


def encode_chat_completions_request(payload: object) -> bytes:
    """Validate and encode the one fixed, bounded Chat Completions request."""

    if type(payload) is not dict:
        raise ModelRequestProtocolError("invalid")
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
            raise ValueError
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        raise ModelRequestProtocolError("invalid") from None
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ModelRequestProtocolError("too_large")
    return encoded
