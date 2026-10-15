"""Bounded GET-only metadata preflight for the fixed local R5 model endpoint."""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import re
import threading
from collections.abc import Callable

from .local_ollama_channel import (
    LOCAL_OLLAMA_HOST,
    LOCAL_OLLAMA_MODEL,
    LOCAL_OLLAMA_PORT,
)


EXPECTED_OLLAMA_VERSION = "0.40.3"
OLLAMA_VERSION_PATH = "/api/version"
OLLAMA_TAGS_PATH = "/api/tags"
MAX_PREFLIGHT_RESPONSE_BYTES = 65_536
PREFLIGHT_TIMEOUT_SECONDS = 8.0
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


_REASON_CODES = frozenset(
    {
        "configuration_rejected",
        "already_used",
        "pin_rejected",
        "version_request_failed",
        "version_identity_mismatch",
        "tags_request_failed",
        "tags_shape_mismatch",
        "model_count_out_of_bounds",
        "model_missing",
        "model_ambiguous",
        "model_digest_malformed",
        "model_digest_mismatch",
        "metadata_request_failed",
    }
)


class R5LocalModelPreflightError(ValueError):
    """A fixed, redacted local-model preflight failure."""

    def __init__(self, reason_code: str) -> None:
        if type(reason_code) is not str or reason_code not in _REASON_CODES:
            reason_code = "metadata_request_failed"
        self.reason_code = reason_code
        super().__init__(f"R5 local model preflight: {reason_code}")


@dataclass(frozen=True, repr=False)
class R5LocalModelMetadata:
    version: str
    model: str
    model_digest: str
    model_count: int

    def __repr__(self) -> str:
        return (
            "R5LocalModelMetadata("
            f"version={self.version!r}, model={self.model!r}, "
            f"model_digest={self.model_digest!r})"
        )


class R5LocalOllamaMetadataPreflight:
    """Read fixed Ollama metadata exactly once; never invoke a model endpoint."""

    def __init__(
        self,
        *,
        connection_factory: Callable[..., object] | None = None,
    ) -> None:
        if connection_factory is not None and not callable(connection_factory):
            raise R5LocalModelPreflightError("configuration_rejected")
        self._connection_factory = connection_factory
        self._used = False
        self._lock = threading.Lock()

    def inspect(self, *, expected_model_digest: str | None = None) -> R5LocalModelMetadata:
        with self._lock:
            if self._used:
                raise R5LocalModelPreflightError("already_used")
            self._used = True
        if expected_model_digest is not None and (
            type(expected_model_digest) is not str
            or _DIGEST.fullmatch(expected_model_digest) is None
        ):
            raise R5LocalModelPreflightError("pin_rejected")
        try:
            try:
                version_payload = self._get_json(OLLAMA_VERSION_PATH)
            except R5LocalModelPreflightError:
                raise R5LocalModelPreflightError("version_request_failed") from None
            if (
                type(version_payload) is not dict
                or set(version_payload) != {"version"}
                or version_payload["version"] != EXPECTED_OLLAMA_VERSION
            ):
                raise R5LocalModelPreflightError("version_identity_mismatch")
            try:
                tags_payload = self._get_json(OLLAMA_TAGS_PATH)
            except R5LocalModelPreflightError:
                raise R5LocalModelPreflightError("tags_request_failed") from None
            if type(tags_payload) is not dict or set(tags_payload) != {"models"}:
                raise R5LocalModelPreflightError("tags_shape_mismatch")
            models = tags_payload["models"]
            if type(models) is not list or len(models) > 256:
                raise R5LocalModelPreflightError("model_count_out_of_bounds")
            matches = [
                item
                for item in models
                if type(item) is dict and item.get("name") == LOCAL_OLLAMA_MODEL
            ]
            if not matches:
                raise R5LocalModelPreflightError("model_missing")
            if len(matches) != 1:
                raise R5LocalModelPreflightError("model_ambiguous")
            model_digest = matches[0].get("digest")
            if type(model_digest) is not str or _DIGEST.fullmatch(model_digest) is None:
                raise R5LocalModelPreflightError("model_digest_malformed")
            if expected_model_digest is not None and model_digest != expected_model_digest:
                raise R5LocalModelPreflightError("model_digest_mismatch")
            return R5LocalModelMetadata(
                version=EXPECTED_OLLAMA_VERSION,
                model=LOCAL_OLLAMA_MODEL,
                model_digest=model_digest,
                model_count=len(models),
            )
        except R5LocalModelPreflightError:
            raise
        except Exception:
            raise R5LocalModelPreflightError("metadata_request_failed") from None

    def _get_json(self, path: str) -> object:
        connection = None
        response = None
        try:
            factory = self._connection_factory or http.client.HTTPConnection
            connection = factory(
                LOCAL_OLLAMA_HOST,
                port=LOCAL_OLLAMA_PORT,
                timeout=PREFLIGHT_TIMEOUT_SECONDS,
            )
            connection.request(
                "GET",
                path,
                headers={"Accept": "application/json"},
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
            if content_length is not None and (
                type(content_length) is not str
                or not content_length.isascii()
                or not content_length.isdecimal()
                or int(content_length) > MAX_PREFLIGHT_RESPONSE_BYTES
            ):
                raise ValueError
            body = response.read(MAX_PREFLIGHT_RESPONSE_BYTES + 1)
            if (
                type(body) is not bytes
                or not body
                or len(body) > MAX_PREFLIGHT_RESPONSE_BYTES
                or (content_length is not None and len(body) != int(content_length))
            ):
                raise ValueError
            return json.loads(body.decode("utf-8"), parse_constant=_reject_json_constant)
        except Exception:
            raise R5LocalModelPreflightError("metadata_request_failed") from None
        finally:
            try:
                if response is not None:
                    response.close()
            except Exception:
                pass
            try:
                if connection is not None:
                    connection.close()
            except Exception:
                pass


def _reject_json_constant(_value: str):
    raise ValueError
