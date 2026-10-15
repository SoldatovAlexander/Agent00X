from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from app_contracts.deepseek_worker import MODEL_NAME, REASONING_EFFORT
from app_contracts.deepseek_http_channel import (
    DeepSeekHTTPChannelError,
    _encode_request as _encode_http_request,
)
from app_contracts.worker_model_protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_LOCAL_MODEL_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    ModelRequestProtocolError,
    encode_chat_completions_request,
)


def _valid_payload() -> dict:
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


class WorkerModelProtocolTests(unittest.TestCase):
    def test_fixed_bounds_and_compact_request_encoding(self):
        payload = _valid_payload()
        encoded = encode_chat_completions_request(payload)
        self.assertEqual(encoded, json.dumps(
            payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8"))
        self.assertLessEqual(len(encoded), MAX_REQUEST_BYTES)
        self.assertEqual(MAX_REQUEST_BYTES, 128_000)
        self.assertEqual(MAX_RESPONSE_BYTES, 65_536)
        self.assertEqual(MAX_TIMEOUT_SECONDS, 30.0)
        self.assertEqual(MAX_LOCAL_MODEL_TIMEOUT_SECONDS, 180.0)

    def test_http_adapter_preserves_protocol_bytes_and_fixed_error_contract(self):
        payload = _valid_payload()
        self.assertEqual(
            encode_chat_completions_request(payload),
            _encode_http_request(payload),
        )
        oversized = _valid_payload()
        oversized["messages"][1]["content"] = "x" * MAX_REQUEST_BYTES
        with self.assertRaisesRegex(
            DeepSeekHTTPChannelError,
            "^deepseek channel: request exceeds limit$",
        ):
            _encode_http_request(oversized)

    def test_invalid_shape_has_fixed_protocol_error(self):
        with self.assertRaises(ModelRequestProtocolError) as raised:
            encode_chat_completions_request({"model": "unexpected"})
        self.assertEqual(raised.exception.reason, "invalid")
        self.assertEqual(str(raised.exception), "invalid")

    def test_oversized_request_has_fixed_protocol_error(self):
        payload = _valid_payload()
        payload["messages"][1]["content"] = "x" * MAX_REQUEST_BYTES
        with self.assertRaises(ModelRequestProtocolError) as raised:
            encode_chat_completions_request(payload)
        self.assertEqual(raised.exception.reason, "too_large")
        self.assertEqual(str(raised.exception), "too_large")

    def test_module_has_no_transport_or_optional_dependency_imports(self):
        source_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "app_contracts"
            / "worker_model_protocol.py"
        )
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(module)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(imported.isdisjoint({"http", "ssl", "certifi", "socket", "credential_source"}))

    def test_worker_ipc_imports_protocol_without_http_transport(self):
        source_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "app_contracts"
            / "worker_model_ipc.py"
        )
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertIn("worker_model_protocol", imported_modules)
        self.assertNotIn("deepseek_http_channel", imported_modules)


if __name__ == "__main__":
    unittest.main()
