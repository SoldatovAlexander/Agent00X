"""DeepSeek Chat Completions proposal adapter behind an opaque channel.

This module contains no provider SDK, HTTP, network, filesystem, environment,
or credential access. Production credential transport is a separate boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .executor import ExecutionError, WorkerInput, WorkerProposal
from .openai_worker import (
    CHANNEL_TIMEOUT_SECONDS,
    MAX_MODEL_OUTPUT_BYTES,
    MAX_RENDERED_USER_BYTES,
    ResponsesModelResult,
    parse_model_result,
)

MODEL_NAME = "deepseek-flash"
REASONING_EFFORT = "low"
MAX_OUTPUT_TOKENS = 4096

_SYSTEM_INSTRUCTION = (
    "Return only valid JSON matching this exact shape: "
    '{"changes":[{"path":"relative/path","content":"complete file text"}]}. '
    "Include at least one change. Do not use markdown fences or extra keys."
)


@dataclass(frozen=True)
class ChatCompletionMessage:
    role: str
    content: str | None
    tool_calls: tuple[object, ...] = ()
    refusal: str | None = None
    # The channel may receive provider reasoning data, but the worker never uses
    # or returns it. Keeping it out of logs and proposal data is intentional.
    reasoning_content: object | None = None


@dataclass(frozen=True)
class ChatCompletionChoice:
    finish_reason: str
    message: ChatCompletionMessage


@dataclass(frozen=True)
class ChatCompletionsModelResult:
    choices: tuple[ChatCompletionChoice, ...]


@runtime_checkable
class DeepSeekChatCompletionsChannel(Protocol):
    """Opaque single-call transport. Implementations own credential handling."""

    def create_chat_completion(
        self, payload: dict, *, timeout_seconds: float
    ) -> ChatCompletionsModelResult: ...


@dataclass(frozen=True)
class DeepSeekProposalWorker:
    """Map bounded caller input to a single JSON-mode Chat Completions call."""

    channel: object

    def propose(self, task: WorkerInput) -> WorkerProposal:
        if not isinstance(task, WorkerInput):
            raise ExecutionError("execution worker: model input is invalid")
        create = getattr(self.channel, "create_chat_completion", None)
        if not callable(create):
            raise ExecutionError("execution worker: model input is invalid")
        if not isinstance(task.task_instruction, str) or not task.task_instruction:
            raise ExecutionError("execution worker: model input is invalid")
        if not isinstance(task.context_files, tuple) or not task.context_files:
            raise ExecutionError("execution worker: model input is invalid")
        try:
            payload = build_chat_completions_payload(task)
            rendered_bytes = len(payload["messages"][1]["content"].encode("utf-8"))
        except Exception:
            raise ExecutionError("execution worker: model input is invalid") from None
        if rendered_bytes > MAX_RENDERED_USER_BYTES:
            raise ExecutionError("execution worker: model input is invalid")
        try:
            result = create(payload, timeout_seconds=CHANNEL_TIMEOUT_SECONDS)
        except Exception:
            raise ExecutionError("execution worker: provider request failed") from None
        output = _extract_content(result)
        return parse_model_result(
            ResponsesModelResult(status="completed", output_text=output),
            task.declared_change_paths,
        )


def build_chat_completions_payload(task: WorkerInput) -> dict:
    """Build one deterministic request from instruction and caller context only."""
    instruction = task.task_instruction
    context = task.context_files
    assert isinstance(instruction, str)
    assert isinstance(context, tuple)
    user_content = instruction
    for path, text in context:
        assert isinstance(path, str)
        assert isinstance(text, str)
        user_content += "\n\nContext file: " + path + "\n" + text
    return {
        "model": MODEL_NAME,
        "reasoning_effort": REASONING_EFFORT,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_content},
        ],
    }


def _extract_content(result: object) -> str:
    if type(result) is not ChatCompletionsModelResult:
        raise ExecutionError("execution worker: provider response is invalid")
    if len(result.choices) != 1:
        raise ExecutionError("execution worker: provider response is invalid")
    choice = result.choices[0]
    if type(choice) is not ChatCompletionChoice or choice.finish_reason != "stop":
        raise ExecutionError("execution worker: provider response is invalid")
    message = choice.message
    if type(message) is not ChatCompletionMessage:
        raise ExecutionError("execution worker: provider response is invalid")
    if (
        message.role != "assistant"
        or message.tool_calls
        or message.refusal is not None
    ):
        raise ExecutionError("execution worker: provider response is invalid")
    output = message.content
    if not isinstance(output, str) or not output:
        raise ExecutionError("execution worker: provider response is invalid")
    try:
        if len(output.encode("utf-8")) > MAX_MODEL_OUTPUT_BYTES:
            raise ExecutionError("execution worker: provider response is invalid")
    except ExecutionError:
        raise
    except Exception:
        raise ExecutionError("execution worker: provider response is invalid") from None
    return output
