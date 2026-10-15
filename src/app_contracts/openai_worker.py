"""OpenAI Responses adapter behind an opaque broker channel.

Local fake-channel adapter only. No HTTP, network, filesystem, environment,
or credential access. The future live transport is out of scope.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .executor import (
    MAX_PROPOSAL_FILE_BYTES,
    MAX_PROPOSAL_FILES,
    MAX_PROPOSAL_PATH_BYTES,
    MAX_PROPOSAL_TOTAL_BYTES,
    ExecutionError,
    WorkerInput,
    WorkerProposal,
    WorkerTerminalOutcome,
)

MODEL_NAME = "gpt-6.1-sol"
REASONING_EFFORT = "low"
MAX_OUTPUT_TOKENS = 4096
MAX_RENDERED_USER_BYTES = 20_000
MAX_MODEL_OUTPUT_BYTES = 32_768
CHANNEL_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class ResponsesModelResult:
    """Completed structured model result without credential material."""

    status: str
    output_text: str | None
    refusal: str | None = None


@runtime_checkable
class OpenAIResponsesChannel(Protocol):
    """Opaque test transport; takes only payload, returns only model result."""

    def create_response(self, payload: dict, *, timeout_seconds: float) -> ResponsesModelResult: ...


@dataclass(frozen=True)
class OpenAIProposalWorker:
    """Deterministic adapter from WorkerInput to WorkerProposal via fake channel."""

    channel: object

    def propose(self, task: WorkerInput) -> WorkerProposal:
        if not isinstance(task, WorkerInput):
            raise ExecutionError("execution worker: model input is invalid")
        create = getattr(self.channel, "create_response", None)
        if not callable(create):
            raise ExecutionError("execution worker: model input is invalid")
        instruction = task.task_instruction
        if not isinstance(instruction, str) or not instruction:
            raise ExecutionError("execution worker: model input is invalid")
        context = task.context_files
        if not isinstance(context, tuple) or len(context) == 0:
            raise ExecutionError("execution worker: model input is invalid")
        payload = build_responses_payload(task)
        try:
            rendered_bytes = 0
            for block in payload["input"][0]["content"]:
                rendered_bytes += len(block["text"].encode("utf-8"))
        except Exception:
            raise ExecutionError("execution worker: model input is invalid") from None
        if rendered_bytes > MAX_RENDERED_USER_BYTES:
            raise ExecutionError("execution worker: model input is invalid")
        try:
            result = create(payload, timeout_seconds=CHANNEL_TIMEOUT_SECONDS)
        except Exception:
            raise ExecutionError("execution worker: provider request failed") from None
        return parse_model_result(result, task.declared_change_paths)


def build_responses_payload(task: WorkerInput) -> dict:
    """Build one deterministic Responses API payload from instruction/context only."""
    instruction = task.task_instruction
    context = task.context_files
    assert isinstance(instruction, str)
    assert isinstance(context, tuple)
    content_blocks: list[dict] = [{"type": "input_text", "text": instruction}]
    for path, text in context:
        assert isinstance(path, str)
        assert isinstance(text, str)
        content_blocks.append({"type": "input_text", "text": "path: " + path + "\n" + text})
    return {
        "model": MODEL_NAME,
        "reasoning": {"effort": REASONING_EFFORT},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": False,
        "tools": [],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "worker_proposal",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["schema", "outcome", "changes", "reason_code"],
                    "properties": {
                        "schema": {"type": "string", "enum": ["agent00x-worker-result/v2"]},
                        "outcome": {
                            "type": "string",
                            "enum": ["changes", "clarification_required", "blocked", "denied"],
                        },
                        "changes": {
                            "type": ["array", "null"],
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["path", "content"],
                                "properties": {
                                    "path": {"type": "string", "minLength": 1},
                                    "content": {"type": "string"},
                                },
                            },
                        },
                        "reason_code": {
                            "type": ["string", "null"],
                            "enum": [
                                "conflicting_requirements",
                                "target_test_outcome_unknown",
                                "publication_not_authorized",
                                None,
                            ],
                        },
                    },
                },
            }
        },
        "input": [{"role": "user", "content": content_blocks}],
    }


def parse_model_result(
    result: object, declared_change_paths: object
) -> WorkerProposal | WorkerTerminalOutcome:
    """Convert the legacy patch or exact bounded v2 Worker result."""
    if type(result) is not ResponsesModelResult:
        raise ExecutionError("execution worker: provider response is invalid")
    if result.refusal is not None:
        raise ExecutionError("execution worker: provider response is invalid")
    if result.status != "completed":
        raise ExecutionError("execution worker: provider response is invalid")
    output = result.output_text
    if not isinstance(output, str) or not output:
        raise ExecutionError("execution worker: provider response is invalid")
    try:
        if len(output.encode("utf-8")) > MAX_MODEL_OUTPUT_BYTES:
            raise ExecutionError("execution worker: provider response is invalid")
    except ExecutionError:
        raise
    except Exception:
        raise ExecutionError("execution worker: provider response is invalid") from None
    try:
        parsed = json.loads(
            output,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except Exception:
        raise ExecutionError("execution worker: provider response is invalid") from None
    if type(parsed) is not dict:
        raise ExecutionError("execution worker: provider response is invalid")
    if "schema" in parsed or "outcome" in parsed or "reason_code" in parsed:
        if (
            set(parsed) != {"schema", "outcome", "changes", "reason_code"}
            or parsed.get("schema") != "agent00x-worker-result/v2"
        ):
            raise ExecutionError("execution worker: provider response is invalid")
        outcome = parsed.get("outcome")
        changes = parsed.get("changes")
        reason_code = parsed.get("reason_code")
        if outcome == "changes":
            if reason_code is not None:
                raise ExecutionError("execution worker: provider response is invalid")
        else:
            expected_reasons = {
                "clarification_required": "conflicting_requirements",
                "blocked": "target_test_outcome_unknown",
                "denied": "publication_not_authorized",
            }
            if (
                type(outcome) is not str
                or outcome not in expected_reasons
                or changes is not None
                or reason_code != expected_reasons.get(outcome)
            ):
                raise ExecutionError("execution worker: provider response is invalid")
            return WorkerTerminalOutcome(outcome=outcome, reason_code=reason_code)
    else:
        if set(parsed) != {"changes"}:
            raise ExecutionError("execution worker: provider response is invalid")
        changes = parsed.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ExecutionError("execution worker: provider response is invalid")
    if not isinstance(declared_change_paths, tuple) or not declared_change_paths:
        raise ExecutionError("execution worker: provider response is invalid")
    declared_normalized = set()
    for declared in declared_change_paths:
        if not isinstance(declared, str):
            raise ExecutionError("execution worker: provider response is invalid")
        declared_normalized.add(posixpath.normpath(declared))
    detached: list[tuple[str, str]] = []
    seen: set[str] = set()
    total_bytes = 0
    for entry in changes:
        if type(entry) is not dict or set(entry.keys()) != {"path", "content"}:
            raise ExecutionError("execution worker: provider response is invalid")
        path = entry["path"]
        content = entry["content"]
        if not isinstance(path, str) or not path or not isinstance(content, str):
            raise ExecutionError("execution worker: provider response is invalid")
        if not _is_safe_relative_path(path):
            raise ExecutionError("execution worker: provider response is invalid")
        try:
            path_bytes = path.encode("utf-8")
            content_bytes = content.encode("utf-8")
        except UnicodeEncodeError:
            raise ExecutionError("execution worker: provider response is invalid") from None
        if len(path_bytes) > MAX_PROPOSAL_PATH_BYTES:
            raise ExecutionError("execution worker: provider response is invalid")
        if len(content_bytes) > MAX_PROPOSAL_FILE_BYTES:
            raise ExecutionError("execution worker: provider response is invalid")
        normalized = posixpath.normpath(path)
        if normalized in seen or normalized not in declared_normalized:
            raise ExecutionError("execution worker: provider response is invalid")
        seen.add(normalized)
        total_bytes += len(path_bytes) + len(content_bytes)
        if total_bytes > MAX_PROPOSAL_TOTAL_BYTES:
            raise ExecutionError("execution worker: provider response is invalid")
        detached.append((path, content))
    if len(detached) > MAX_PROPOSAL_FILES:
        raise ExecutionError("execution worker: provider response is invalid")
    return WorkerProposal(tuple(detached))


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise ValueError("duplicate JSON key")
        found[key] = value
    return found


def _reject_constant(value: str) -> object:
    raise ValueError("invalid JSON constant")


def _is_safe_relative_path(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value.startswith("/")
        or "\\" in value
        or "//" in value
        or "/./" in value
        or value.endswith("/.")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and value not in {"", "."}
