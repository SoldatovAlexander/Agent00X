"""Measure complete R5 Worker-input token counts through a local tokenizer.

No inference is performed. Importing this module is inert; executing ``main``
uses exactly 20 /apply-template and 20 /tokenize calls on loopback.
"""

from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
from typing import Callable, TextIO
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.deepseek_worker import (
    _SYSTEM_INSTRUCTION,
    build_chat_completions_payload,
)
from scripts.r5_worker_input import (
    R5WorkerInputError,
    SOURCE_SHA256,
    SOURCE_SIZE,
    _CONTEXT_DIGESTS,
    _CONTEXT_SIZES,
    _read_fixed_inputs,
    build_r5_worker_input,
)


HOST = "127.0.0.1"
PORT = 18080
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 65_536
RUNTIME_COMMIT = "631109b34da437a3c4a5ebd75091d677671392e3"
MODEL_LAYER_SHA256 = "60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463"
_SCENARIO_IDS = (
    "S1-canonical-repair",
    "S2-transfer-time-ms",
    "S3-incomplete-conflict",
    "S4-test-tool-failure",
    "S5-denied-publication",
)
_ARMS = ("A", "B", "C", "D")


class R5TokenParityError(ValueError):
    """Fixed local token measurement failure; never includes prompt data."""


def _reject_constant(_value: str):
    raise ValueError


def _post_json(path: str, payload: dict, connection_factory: Callable[..., object]):
    connection = None
    try:
        body = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
        connection = connection_factory(HOST, port=PORT, timeout=TIMEOUT_SECONDS)
        connection.request(
            "POST",
            path,
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
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if (
            type(raw) is not bytes
            or not raw
            or len(raw) > MAX_RESPONSE_BYTES
            or (content_length is not None and len(raw) != int(content_length))
        ):
            raise ValueError
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        if type(value) is not dict:
            raise ValueError
        return value
    except Exception:
        raise R5TokenParityError("R5 token measurement: request failed") from None
    finally:
        try:
            if connection is not None:
                connection.close()
        except Exception:
            pass


def _build_inputs() -> list[tuple[str, str, str, dict]]:
    try:
        casebook, _source = _read_fixed_inputs()
        if casebook.get("execution_state") != "PREREGISTERED_NOT_RUN":
            raise ValueError
        first_attempt: dict[tuple[str, str], str] = {}
        for run in casebook["run_order"]:
            first_attempt.setdefault(
                (run["scenario_id"], run["arm_id"]), run["attempt_id"]
            )
        expected_pairs = {
            (scenario_id, arm_id)
            for scenario_id in _SCENARIO_IDS
            for arm_id in _ARMS
        }
        if set(first_attempt) != expected_pairs or len(first_attempt) != 20:
            raise ValueError
        result: list[tuple[str, str, str, dict]] = []
        for scenario_id in _SCENARIO_IDS:
            for arm_id in _ARMS:
                worker_input = build_r5_worker_input(first_attempt[(scenario_id, arm_id)])
                payload = build_chat_completions_payload(worker_input)
                if (
                    type(payload) is not dict
                    or type(payload.get("messages")) is not list
                    or len(payload["messages"]) != 2
                    or payload["messages"][0]
                    != {"role": "system", "content": _SYSTEM_INSTRUCTION}
                ):
                    raise ValueError
                result.append((scenario_id, arm_id, first_attempt[(scenario_id, arm_id)], payload))
        return result
    except Exception:
        raise R5TokenParityError("R5 token measurement: input preflight failed") from None


def run_measurement(
    connection_factory: Callable[..., object] = http.client.HTTPConnection,
    output: TextIO = sys.stdout,
) -> int:
    """Make the one fixed 20+20 request sequence and emit bounded evidence."""

    completed = 0
    try:
        inputs = _build_inputs()
        applied: dict[tuple[str, str], str] = {}
    except R5TokenParityError:
        output.write('{"status":"STOPPED","step":"input-preflight","completed_requests":0}\n')
        return 2

    try:
        for scenario_id, arm_id, _attempt_id, payload in inputs:
            response = _post_json(
                "/apply-template",
                {"messages": payload["messages"], "add_generation_prompt": True},
                connection_factory,
            )
            completed += 1
            prompt = response.get("prompt")
            if (
                set(response) != {"prompt"}
                or type(prompt) is not str
                or not prompt
                or len(prompt.encode("utf-8")) > MAX_RESPONSE_BYTES
            ):
                raise R5TokenParityError("R5 token measurement: template response invalid")
            applied[(scenario_id, arm_id)] = prompt

        counts: dict[str, dict[str, int]] = {}
        for scenario_id, arm_id, _attempt_id, _payload in inputs:
            response = _post_json(
                "/tokenize",
                {
                    "content": applied[(scenario_id, arm_id)],
                    "add_special": False,
                    "parse_special": True,
                    "with_pieces": False,
                },
                connection_factory,
            )
            completed += 1
            tokens = response.get("tokens")
            if (
                set(response) != {"tokens"}
                or type(tokens) is not list
                or any(type(token) is not int or token < 0 for token in tokens)
            ):
                raise R5TokenParityError("R5 token measurement: tokenize response invalid")
            counts.setdefault(scenario_id, {})[arm_id] = len(tokens)
        if set(counts) != set(_SCENARIO_IDS) or any(
            set(counts[scenario_id]) != set(_ARMS) for scenario_id in _SCENARIO_IDS
        ):
            raise R5TokenParityError("R5 token measurement: count matrix invalid")

        rows = []
        eligible = True
        for scenario_id in _SCENARIO_IDS:
            values = counts[scenario_id]
            ab = abs(values["A"] - values["B"]) / max(values["A"], values["B"])
            cd = abs(values["C"] - values["D"]) / max(values["C"], values["D"])
            eligible = eligible and ab <= 0.01 and cd <= 0.01
            rows.append(
                {
                    "scenario": scenario_id,
                    "counts": values,
                    "AB_ratio": round(ab, 8),
                    "CD_ratio": round(cd, 8),
                }
            )
        result = {
            "status": "COMPLETE",
            "eligible": eligible,
            "model_layer_sha256": MODEL_LAYER_SHA256,
            "runtime_commit": RUNTIME_COMMIT,
            "source_sha256": SOURCE_SHA256,
            "source_size_bytes": SOURCE_SIZE,
            "context_digests": _CONTEXT_DIGESTS,
            "context_sizes": _CONTEXT_SIZES,
            "scenario_counts": rows,
            "completed_requests": completed,
        }
        output.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    except Exception:
        step = "apply-template" if completed < 20 else "tokenize"
        output.write(
            json.dumps(
                {
                    "status": "STOPPED",
                    "step": step,
                    "completed_requests": completed,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 3


def main() -> int:
    return run_measurement()


if __name__ == "__main__":
    raise SystemExit(main())
