from __future__ import annotations

import json
import unittest

from app_contracts.local_ollama_channel import (
    LOCAL_OLLAMA_HOST,
    LOCAL_OLLAMA_MODEL,
    LOCAL_OLLAMA_PORT,
)
from app_contracts.r5_local_model_preflight import (
    EXPECTED_OLLAMA_VERSION,
    OLLAMA_TAGS_PATH,
    OLLAMA_VERSION_PATH,
    R5LocalModelPreflightError,
    R5LocalOllamaMetadataPreflight,
)


class _Response:
    def __init__(self, body: bytes, *, status: int = 200, content_type: str = "application/json"):
        self.status = status
        self.body = body
        self.content_type = content_type
        self.closed = False

    def getheader(self, name: str):
        if name == "Content-Type":
            return self.content_type
        if name == "Content-Length":
            return str(len(self.body))
        return None

    def read(self, limit: int) -> bytes:
        return self.body[:limit]

    def close(self) -> None:
        self.closed = True


class _Connection:
    def __init__(self, response: _Response):
        self.response = response
        self.requests: list[tuple[str, str, dict]] = []
        self.closed = False

    def request(self, method: str, path: str, *, headers: dict) -> None:
        self.requests.append((method, path, headers))

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


def _response(value: object) -> _Response:
    return _Response(json.dumps(value, separators=(",", ":")).encode("utf-8"))


class R5LocalModelPreflightTests(unittest.TestCase):
    def _run(self, responses: list[_Response], *, expected_digest: str | None = None):
        connections: list[_Connection] = []

        def factory(host: str, *, port: int, timeout: float) -> _Connection:
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(host, LOCAL_OLLAMA_HOST)
            self.assertEqual(port, 11434)
            self.assertEqual(port, LOCAL_OLLAMA_PORT)
            self.assertGreater(timeout, 0)
            connection = _Connection(responses[len(connections)])
            connections.append(connection)
            return connection

        result = R5LocalOllamaMetadataPreflight(
            connection_factory=factory
        ).inspect(expected_model_digest=expected_digest)
        return result, connections

    def _assert_reason(self, responses: list[_Response], reason: str, *, expected_digest: str | None = None):
        with self.assertRaises(R5LocalModelPreflightError) as raised:
            self._run(responses, expected_digest=expected_digest)
        self.assertEqual(raised.exception.reason_code, reason)
        self.assertNotIn("prompt", str(raised.exception).lower())
        self.assertNotIn("token", str(raised.exception).lower())

    def test_requests_only_fixed_loopback_metadata_paths_and_returns_minimal_metadata(self) -> None:
        digest = "a" * 64
        result, connections = self._run(
            [
                _response({"version": EXPECTED_OLLAMA_VERSION}),
                _response({"models": [{"name": LOCAL_OLLAMA_MODEL, "digest": digest}]}),
            ],
            expected_digest=digest,
        )

        self.assertEqual(
            [call for connection in connections for call in connection.requests],
            [
                ("GET", OLLAMA_VERSION_PATH, {"Accept": "application/json"}),
                ("GET", OLLAMA_TAGS_PATH, {"Accept": "application/json"}),
            ],
        )
        self.assertEqual(result.version, EXPECTED_OLLAMA_VERSION)
        self.assertEqual(result.model, LOCAL_OLLAMA_MODEL)
        self.assertEqual(result.model_digest, digest)
        self.assertEqual(result.model_count, 1)
        self.assertEqual(
            set(result.__dict__), {"version", "model", "model_digest", "model_count"}
        )
        self.assertTrue(all(connection.closed for connection in connections))

    def test_rejects_wrong_runtime_or_model_identity(self) -> None:
        digest = "b" * 64
        self._assert_reason(
            [_response({"version": "0.40.4"})], "version_identity_mismatch"
        )
        self._assert_reason(
            [
                _response({"version": EXPECTED_OLLAMA_VERSION}),
                _response({"models": [{"name": "other-model", "digest": digest}]}),
            ],
            "model_missing",
        )
        self._assert_reason(
            [
                _response({"version": EXPECTED_OLLAMA_VERSION}),
                _response(
                    {
                        "models": [
                            {"name": LOCAL_OLLAMA_MODEL, "digest": digest},
                            {"name": LOCAL_OLLAMA_MODEL, "digest": digest},
                        ]
                    }
                ),
            ],
            "model_ambiguous",
        )

    def test_exposes_only_fixed_categories_for_each_metadata_gate(self) -> None:
        digest = "e" * 64
        self._assert_reason(
            [_response({"unexpected": "shape"})], "version_identity_mismatch"
        )
        self._assert_reason(
            [
                _response({"version": EXPECTED_OLLAMA_VERSION}),
                _response({"unexpected": "shape"}),
            ],
            "tags_shape_mismatch",
        )
        self._assert_reason(
            [
                _response({"version": EXPECTED_OLLAMA_VERSION}),
                _response({"models": [{}] * 257}),
            ],
            "model_count_out_of_bounds",
        )
        self._assert_reason(
            [
                _response({"version": EXPECTED_OLLAMA_VERSION}),
                _response({"models": [{"name": LOCAL_OLLAMA_MODEL, "digest": "bad"}]}),
            ],
            "model_digest_malformed",
        )
        self._assert_reason(
            [
                _response({"version": EXPECTED_OLLAMA_VERSION}),
                _response({"models": [{"name": LOCAL_OLLAMA_MODEL, "digest": digest}]}),
            ],
            "model_digest_mismatch",
            expected_digest="f" * 64,
        )

    def test_labels_version_and_tags_request_failures_without_exception_text(self) -> None:
        failing_factory = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("secret endpoint detail")
        )
        with self.assertRaises(R5LocalModelPreflightError) as version_error:
            R5LocalOllamaMetadataPreflight(
                connection_factory=failing_factory
            ).inspect()
        self.assertEqual(version_error.exception.reason_code, "version_request_failed")
        self.assertNotIn("secret endpoint detail", str(version_error.exception))

        digest = "a" * 64
        calls = 0

        def fail_tags_factory(host: str, *, port: int, timeout: float):
            nonlocal calls
            calls += 1
            if calls == 1:
                return _Connection(_response({"version": EXPECTED_OLLAMA_VERSION}))
            raise OSError("secret tags detail")

        with self.assertRaises(R5LocalModelPreflightError) as tags_error:
            R5LocalOllamaMetadataPreflight(
                connection_factory=fail_tags_factory
            ).inspect()
        self.assertEqual(tags_error.exception.reason_code, "tags_request_failed")
        self.assertNotIn("secret tags detail", str(tags_error.exception))

    def test_rejects_malformed_oversized_and_wrong_content_type_responses(self) -> None:
        malformed = _Response(b'{"version":NaN}')
        oversized = _Response(b"x" * 65_537)
        wrong_type = _Response(b'{"version":"0.40.3"}', content_type="text/plain")
        for response in (malformed, oversized, wrong_type):
            with self.subTest(response=response):
                with self.assertRaises(R5LocalModelPreflightError):
                    self._run([response])

    def test_rejects_digest_mismatch_without_leaking_payload(self) -> None:
        actual = "c" * 64
        secretish_payload = {"models": [{"name": LOCAL_OLLAMA_MODEL, "digest": actual}]}
        with self.assertRaises(R5LocalModelPreflightError) as raised:
            self._run(
                [
                    _response({"version": EXPECTED_OLLAMA_VERSION}),
                    _response(secretish_payload),
                ],
                expected_digest="d" * 64,
            )
        self.assertNotIn(actual, str(raised.exception))
        self.assertNotIn("prompt", str(raised.exception).lower())
        self.assertNotIn("token", str(raised.exception).lower())

    def test_is_one_shot_even_after_failure(self) -> None:
        preflight = R5LocalOllamaMetadataPreflight(
            connection_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError())
        )
        with self.assertRaises(R5LocalModelPreflightError):
            preflight.inspect()
        with self.assertRaises(R5LocalModelPreflightError) as raised:
            preflight.inspect()
        self.assertEqual(raised.exception.reason_code, "already_used")


if __name__ == "__main__":
    unittest.main()
