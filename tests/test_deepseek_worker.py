from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
    DeepSeekProposalWorker,
    build_chat_completions_payload,
)
from app_contracts.executor import (
    ExecutionError,
    WorkerInput,
    WorkerProposal,
    WorkerTerminalOutcome,
)


def valid_task(**overrides) -> WorkerInput:
    fields = {
        "process_id": "process-local-001",
        "task_id": "task-local-001",
        "repository_id": "fixture-repository",
        "base_commit": "fixture-base-001",
        "declared_change_paths": ("calculator.py",),
        "task_instruction": "Fix calculator edge case",
        "context_files": (("calculator.py", "current content"),),
    }
    fields.update(overrides)
    return WorkerInput(**fields)


def result(
    content: str = '{"changes":[{"path":"calculator.py","content":"fixed"}]}',
    *,
    finish_reason: str = "stop",
    role: str = "assistant",
    tool_calls: tuple[object, ...] = (),
    refusal: str | None = None,
    reasoning_content: object | None = None,
    choice_count: int = 1,
) -> ChatCompletionsModelResult:
    choice = ChatCompletionChoice(
        finish_reason=finish_reason,
        message=ChatCompletionMessage(
            role=role,
            content=content,
            tool_calls=tool_calls,
            refusal=refusal,
            reasoning_content=reasoning_content,
        ),
    )
    return ChatCompletionsModelResult((choice,) * choice_count)


class FakeChannel:
    def __init__(self, model_result=None, error=None):
        self.calls = 0
        self.received: list[dict] = []
        self.timeouts: list[float] = []
        self.model_result = model_result
        self.error = error

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        self.calls += 1
        self.received.append(payload)
        self.timeouts.append(timeout_seconds)
        if self.error is not None:
            raise self.error
        return self.model_result


class RequestMappingTests(unittest.TestCase):
    def test_exact_request_mapping_and_one_call(self):
        channel = FakeChannel(result("{\"changes\":[{\"path\":\"calculator.py\",\"content\":\"mapped\"}]}"))
        worker = DeepSeekProposalWorker(channel=channel)
        task = valid_task(
            task_instruction="Do the fix",
            context_files=(("calculator.py", "file body"),),
        )
        proposal = worker.propose(task)
        self.assertEqual(channel.calls, 1)
        self.assertEqual(channel.timeouts, [30.0])
        self.assertEqual(proposal, WorkerProposal((("calculator.py", "mapped"),)))
        payload = channel.received[0]
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertIs(payload["stream"], False)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("tools", payload)
        self.assertEqual([message["role"] for message in payload["messages"]], ["system", "user"])
        self.assertIn("json", payload["messages"][0]["content"].lower())
        self.assertIn('"agent00x-worker-result/v2"', payload["messages"][0]["content"])
        self.assertIn('"target_test_outcome_unknown"', payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][1]["content"], "Do the fix\n\nContext file: calculator.py\nfile body")
        serialized = json.dumps(payload)
        for sentinel in ("process-local-001", "task-local-001", "fixture-repository", "fixture-base-001"):
            self.assertNotIn(sentinel, serialized)
        for sentinel in ("credential", "api_key", "apikey", "Authorization", "Bearer sk-"):
            self.assertNotIn(sentinel, serialized)

    def test_explicit_local_timeout_is_forwarded_and_capped(self):
        channel = FakeChannel(result())
        DeepSeekProposalWorker(channel=channel, timeout_seconds=180).propose(valid_task())
        self.assertEqual(channel.timeouts, [180])

        invalid_channel = FakeChannel(result())
        with self.assertRaises(ExecutionError):
            DeepSeekProposalWorker(
                channel=invalid_channel, timeout_seconds=181
            ).propose(valid_task())
        self.assertEqual(invalid_channel.calls, 0)

    def test_builder_uses_only_instruction_and_context(self):
        payload = build_chat_completions_payload(valid_task())
        serialized = json.dumps(payload)
        self.assertIn("Fix calculator edge case", serialized)
        self.assertIn("current content", serialized)
        self.assertNotIn("fixture-repository", serialized)

    def test_rendered_prompt_bound_fails_before_channel_call(self):
        task = valid_task(
            declared_change_paths=("a.py", "b.py"),
            context_files=(("a.py", "a" * 9_980), ("b.py", "b" * 9_980)),
        )
        channel = FakeChannel(result())
        with self.assertRaisesRegex(ExecutionError, "^execution worker: model input is invalid$"):
            DeepSeekProposalWorker(channel).propose(task)
        self.assertEqual(channel.calls, 0)

    def test_invalid_channel_or_task_fails_before_call(self):
        for channel in (None, object(), "channel", 42):
            with self.subTest(channel=type(channel).__name__):
                with self.assertRaisesRegex(ExecutionError, "^execution worker: model input is invalid$"):
                    DeepSeekProposalWorker(channel).propose(valid_task())
        channel = FakeChannel(result())
        with self.assertRaisesRegex(ExecutionError, "^execution worker: model input is invalid$"):
            DeepSeekProposalWorker(channel).propose(object())
        self.assertEqual(channel.calls, 0)


class ResponseValidationTests(unittest.TestCase):
    def test_terminal_outcome_is_parsed_without_patch(self):
        channel = FakeChannel(
            result(
                json.dumps(
                    {
                        "schema": "agent00x-worker-result/v2",
                        "outcome": "blocked",
                        "changes": None,
                        "reason_code": "target_test_outcome_unknown",
                    }
                )
            )
        )
        self.assertEqual(
            DeepSeekProposalWorker(channel).propose(valid_task()),
            WorkerTerminalOutcome("blocked", "target_test_outcome_unknown"),
        )
        self.assertEqual(channel.calls, 1)

    def test_rejects_non_stop_or_malformed_provider_results(self):
        cases = (
            None,
            object(),
            ChatCompletionsModelResult(()),
            result(choice_count=2),
            result(finish_reason="length"),
            result(finish_reason="content_filter"),
            result(finish_reason="tool_calls"),
            result(role="user"),
            result(tool_calls=({"type": "function"},)),
            result(refusal="declined"),
            result(content=""),
            result(content=None),
            result(content=42),
            result(content="not json{"),
            result(content='{"changes":[{"path":"calculator.py","content":"a","content":"b"}]}'),
            result(content='{"changes":[{"path":"outside.py","content":"x"}]}'),
            result(content='{"changes":[]}'),
        )
        for response in cases:
            channel = FakeChannel(response)
            with self.subTest(response=type(response).__name__):
                with self.assertRaisesRegex(ExecutionError, "^execution worker: provider response is invalid$"):
                    DeepSeekProposalWorker(channel).propose(valid_task())
                self.assertEqual(channel.calls, 1)

    def test_oversized_content_fails_closed(self):
        channel = FakeChannel(result(content="x" * (32_768 + 1)))
        with self.assertRaisesRegex(ExecutionError, "^execution worker: provider response is invalid$"):
            DeepSeekProposalWorker(channel).propose(valid_task())
        self.assertEqual(channel.calls, 1)

    def test_reasoning_content_is_not_used_or_returned(self):
        channel = FakeChannel(result(reasoning_content="private reasoning sentinel"))
        proposal = DeepSeekProposalWorker(channel).propose(valid_task())
        self.assertEqual(proposal, WorkerProposal((("calculator.py", "fixed"),)))
        self.assertNotIn("private reasoning sentinel", repr(proposal))

    def test_transport_exception_is_sanitized_without_retry(self):
        for failure in (
            RuntimeError("provider error secret sentinel"),
            TimeoutError("provider timeout secret sentinel"),
        ):
            channel = FakeChannel(error=failure)
            with self.subTest(error=type(failure).__name__):
                with self.assertRaisesRegex(ExecutionError, "^execution worker: provider request failed$") as error:
                    DeepSeekProposalWorker(channel).propose(valid_task())
                self.assertNotIn("secret sentinel", str(error.exception))
                self.assertEqual(channel.calls, 1)


class BoundaryTests(unittest.TestCase):
    def test_source_has_no_live_transport_sdk_environment_or_file_access(self):
        tree = ast.parse((ROOT / "src/app_contracts/deepseek_worker.py").read_text(encoding="utf-8"))
        forbidden_imports = {"http", "urllib", "requests", "httpx", "openai", "os", "subprocess"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(forbidden_imports.intersection(alias.name.split(".")[0] for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden_imports)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"open", "exec", "eval", "compile"})
            elif isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"environ", "getenv", "urlopen", "request"})


if __name__ == "__main__":
    unittest.main()
