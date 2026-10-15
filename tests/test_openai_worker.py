from __future__ import annotations

import ast
import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import (
    ExecutionError,
    WorkerInput,
    WorkerProposal,
    WorkerTerminalOutcome,
)
from app_contracts.openai_worker import (
    OpenAIProposalWorker,
    OpenAIResponsesChannel,
    ResponsesModelResult,
    build_responses_payload,
)
import app_contracts.openai_worker as worker_module


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


class FakeChannel:
    def __init__(self, result=None, error=None):
        self.calls = 0
        self.received: list[dict] = []
        self.timeouts: list[float] = []
        self.result = result
        self.error = error

    def create_response(self, payload: dict, *, timeout_seconds: float) -> ResponsesModelResult:
        self.calls += 1
        self.received.append(payload)
        self.timeouts.append(timeout_seconds)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def success_result(content: str = "fixed content") -> ResponsesModelResult:
    payload = {
        "schema": "agent00x-worker-result/v2",
        "outcome": "changes",
        "changes": [{"path": "calculator.py", "content": content}],
        "reason_code": None,
    }
    return ResponsesModelResult(status="completed", output_text=json.dumps(payload))


class RequestMappingTests(unittest.TestCase):
    def test_exact_request_mapping_and_single_call(self):
        channel = FakeChannel(result=success_result("mapped content"))
        worker = OpenAIProposalWorker(channel=channel)
        task = valid_task(
            task_instruction="Do the fix",
            context_files=(("calculator.py", "file body"),),
        )
        proposal = worker.propose(task)
        self.assertEqual(channel.calls, 1)
        self.assertEqual(channel.timeouts, [30.0])
        self.assertEqual(proposal, WorkerProposal((("calculator.py", "mapped content"),)))
        payload = channel.received[0]
        self.assertEqual(payload["model"], "gpt-6.1-sol")
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertEqual(payload["max_output_tokens"], 4096)
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["tools"], [])
        text_format = payload["text"]["format"]
        self.assertEqual(text_format["type"], "json_schema")
        self.assertEqual(text_format["strict"], True)
        schema = text_format["schema"]
        self.assertEqual(
            schema["required"], ["schema", "outcome", "changes", "reason_code"]
        )
        changes_schema = schema["properties"]["changes"]
        self.assertGreaterEqual(changes_schema["minItems"], 1)
        item_schema = changes_schema["items"]
        self.assertEqual(set(item_schema["required"]), {"path", "content"})
        user_blocks = payload["input"][0]["content"]
        texts = [block["text"] for block in user_blocks]
        self.assertIn("Do the fix", texts[0])
        self.assertTrue(any("calculator.py" in text and "file body" in text for text in texts[1:]))
        serialized = json.dumps(payload)
        for sentinel in ("credential", "api_key", "apikey", "Authorization", "Bearer sk-"):
            self.assertNotIn(sentinel, serialized)
        self.assertNotIn("task-local-001", serialized)

    def test_build_payload_uses_only_instruction_and_context(self):
        task = valid_task(
            task_instruction="Only this",
            context_files=(("calculator.py", "only context"),),
        )
        payload = build_responses_payload(task)
        serialized = json.dumps(payload)
        self.assertIn("Only this", serialized)
        self.assertIn("only context", serialized)
        self.assertNotIn("process-local-001", serialized)
        self.assertNotIn("fixture-repository", serialized)
        self.assertNotIn("fixture-base-001", serialized)


class ModelInputValidationTests(unittest.TestCase):
    def test_invalid_channel_gives_model_input_invalid_with_zero_calls(self):
        task = valid_task()
        for channel in (None, object(), "channel", 42):
            with self.subTest(channel=repr(channel)[:20]):
                worker = OpenAIProposalWorker(channel=channel)
                with self.assertRaisesRegex(
                    ExecutionError, "^execution worker: model input is invalid$"
                ):
                    worker.propose(task)

        class NoCreate:
            pass

        class NonCallableCreate:
            create_response = "not-callable"

        for channel in (NoCreate(), NonCallableCreate()):
            with self.subTest(channel=type(channel).__name__):
                worker = OpenAIProposalWorker(channel=channel)
                with self.assertRaisesRegex(
                    ExecutionError, "^execution worker: model input is invalid$"
                ):
                    worker.propose(task)

    def test_missing_instruction_or_context_gives_model_input_invalid(self):
        for task in (
            valid_task(task_instruction=None),
            valid_task(context_files=()),
        ):
            with self.subTest(task=(task.task_instruction, task.context_files)):
                channel = FakeChannel(result=success_result())
                worker = OpenAIProposalWorker(channel=channel)
                with self.assertRaisesRegex(
                    ExecutionError, "^execution worker: model input is invalid$"
                ):
                    worker.propose(task)
                self.assertEqual(channel.calls, 0)

    def test_empty_instruction_rejected_at_worker_input_construction(self):
        with self.assertRaisesRegex(
            ExecutionError, "^execution request: worker input is invalid$"
        ):
            valid_task(task_instruction="")

    def test_non_worker_input_gives_model_input_invalid(self):
        channel = FakeChannel(result=success_result())
        worker = OpenAIProposalWorker(channel=channel)
        for value in (None, object(), {"task_instruction": "x"}):
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(
                    ExecutionError, "^execution worker: model input is invalid$"
                ):
                    worker.propose(value)
        self.assertEqual(channel.calls, 0)


class ProviderResponseTests(unittest.TestCase):
    def test_legacy_v1_patch_remains_accepted(self):
        channel = FakeChannel(
            result=ResponsesModelResult(
                status="completed",
                output_text=json.dumps(
                    {"changes": [{"path": "calculator.py", "content": "legacy"}]}
                ),
            )
        )
        self.assertEqual(
            OpenAIProposalWorker(channel=channel).propose(valid_task()),
            WorkerProposal((("calculator.py", "legacy"),)),
        )
        self.assertEqual(channel.calls, 1)

    def test_legacy_v1_patch_remains_accepted(self):
        channel = FakeChannel(
            result=ResponsesModelResult(
                status="completed",
                output_text=json.dumps(
                    {"changes": [{"path": "calculator.py", "content": "legacy"}]}
                ),
            )
        )
        self.assertEqual(
            OpenAIProposalWorker(channel=channel).propose(valid_task()),
            WorkerProposal((("calculator.py", "legacy"),)),
        )
        self.assertEqual(channel.calls, 1)

    def test_v2_terminal_outcomes_are_exact_and_bounded(self):
        cases = (
            ("clarification_required", "conflicting_requirements"),
            ("blocked", "target_test_outcome_unknown"),
            ("denied", "publication_not_authorized"),
        )
        for outcome, reason_code in cases:
            payload = {
                "schema": "agent00x-worker-result/v2",
                "outcome": outcome,
                "changes": None,
                "reason_code": reason_code,
            }
            channel = FakeChannel(
                result=ResponsesModelResult(
                    status="completed", output_text=json.dumps(payload)
                )
            )
            result = OpenAIProposalWorker(channel=channel).propose(valid_task())
            self.assertEqual(result, WorkerTerminalOutcome(outcome, reason_code))
            self.assertEqual(channel.calls, 1)

    def test_v2_changes_are_accepted_and_mixed_envelopes_rejected(self):
        valid = {
            "schema": "agent00x-worker-result/v2",
            "outcome": "changes",
            "changes": [{"path": "calculator.py", "content": "v2"}],
            "reason_code": None,
        }
        self.assertEqual(
            OpenAIProposalWorker(
                channel=FakeChannel(
                    result=ResponsesModelResult(
                        status="completed", output_text=json.dumps(valid)
                    )
                )
            ).propose(valid_task()),
            WorkerProposal((("calculator.py", "v2"),)),
        )
        invalid = (
            {**valid, "reason_code": "publication_not_authorized"},
            {**valid, "extra": True},
            {**valid, "schema": "agent00x-worker-result/v3"},
            {**valid, "outcome": "blocked"},
            {**valid, "outcome": [], "reason_code": None},
            {**valid, "changes": None},
        )
        for payload in invalid:
            channel = FakeChannel(
                result=ResponsesModelResult(
                    status="completed", output_text=json.dumps(payload)
                )
            )
            with self.subTest(payload=payload), self.assertRaisesRegex(
                ExecutionError, "provider response is invalid"
            ):
                OpenAIProposalWorker(channel=channel).propose(valid_task())

    def test_refusal_incomplete_or_bad_output_gives_response_invalid(self):
        cases = [
            ResponsesModelResult(status="completed", output_text=json.dumps({"changes": [{"path": "calculator.py", "content": "x"}]}), refusal="declined"),
            ResponsesModelResult(status="incomplete", output_text=json.dumps({"changes": [{"path": "calculator.py", "content": "x"}]})),
            ResponsesModelResult(status="failed", output_text=json.dumps({"changes": [{"path": "calculator.py", "content": "x"}]})),
            ResponsesModelResult(status="completed", output_text=None),
            ResponsesModelResult(status="completed", output_text=""),
            ResponsesModelResult(status="completed", output_text=42),
            ResponsesModelResult(status="completed", output_text="not json{"),
            ResponsesModelResult(status="completed", output_text=json.dumps({"nope": []})),
            ResponsesModelResult(status="completed", output_text=json.dumps({"changes": []})),
        ]
        for result in cases:
            with self.subTest(result=repr(result)[:60]):
                channel = FakeChannel(result=result)
                worker = OpenAIProposalWorker(channel=channel)
                with self.assertRaisesRegex(
                    ExecutionError, "^execution worker: provider response is invalid$"
                ):
                    worker.propose(valid_task())
                self.assertEqual(channel.calls, 1)

    def test_bad_proposal_shape_gives_response_invalid(self):
        bad_payloads = [
            {"changes": [{"path": "other.py", "content": "x"}]},
            {"changes": [{"path": "/tmp/x.py", "content": "x"}]},
            {"changes": [{"path": "calculator.py", "content": "x", "extra": 1}]},
            {"changes": [{"path": "calculator.py"}]},
            {"changes": [{"path": "calculator.py", "content": 42}]},
            {"changes": [{"path": "calculator.py", "content": "one"}, {"path": "calculator.py", "content": "two"}]},
            {"changes": "not-a-list"},
        ]
        for payload in bad_payloads:
            with self.subTest(payload=repr(payload)[:60]):
                channel = FakeChannel(
                    result=ResponsesModelResult(status="completed", output_text=json.dumps(payload))
                )
                worker = OpenAIProposalWorker(channel=channel)
                with self.assertRaisesRegex(
                    ExecutionError, "^execution worker: provider response is invalid$"
                ):
                    worker.propose(valid_task())
                self.assertEqual(channel.calls, 1)

    def test_channel_exception_gives_request_failed(self):
        for error in (RuntimeError("boom"), TimeoutError("slow"), ValueError("bad")):
            with self.subTest(error=type(error).__name__):
                channel = FakeChannel(error=error)
                worker = OpenAIProposalWorker(channel=channel)
                with self.assertRaisesRegex(
                    ExecutionError, "^execution worker: provider request failed$"
                ) as raised:
                    worker.propose(valid_task())
                self.assertNotIn("boom", str(raised.exception))
                self.assertEqual(channel.calls, 1)

    def test_malformed_result_type_gives_response_invalid(self):
        channel = FakeChannel(result={"status": "completed"})
        worker = OpenAIProposalWorker(channel=channel)
        with self.assertRaisesRegex(
            ExecutionError, "^execution worker: provider response is invalid$"
        ):
            worker.propose(valid_task())
        self.assertEqual(channel.calls, 1)


class CostBoundsTests(unittest.TestCase):
    def test_rendered_user_content_over_limit_gives_model_input_invalid(self):
        task = WorkerInput(
            process_id="process-local-001",
            task_id="task-local-001",
            repository_id="fixture-repository",
            base_commit="fixture-base-001",
            declared_change_paths=("a.py", "b.py"),
            task_instruction="i" * 4096,
            context_files=(("a.py", "y" * 8250), ("b.py", "z" * 8250)),
        )
        channel = FakeChannel(result=success_result())
        worker = OpenAIProposalWorker(channel=channel)
        with self.assertRaisesRegex(
            ExecutionError, "^execution worker: model input is invalid$"
        ):
            worker.propose(task)
        self.assertEqual(channel.calls, 0)

    def test_output_over_byte_limit_gives_response_invalid_before_parsing(self):
        big_content = "Q" * 33_000
        output = json.dumps({"changes": [{"path": "calculator.py", "content": big_content}]})
        self.assertGreater(len(output.encode("utf-8")), 32_768)
        channel = FakeChannel(
            result=ResponsesModelResult(status="completed", output_text=output)
        )
        worker = OpenAIProposalWorker(channel=channel)
        with self.assertRaisesRegex(
            ExecutionError, "^execution worker: provider response is invalid$"
        ):
            worker.propose(valid_task())
        self.assertEqual(channel.calls, 1)

    def test_timeout_passed_once_as_keyword_only(self):
        channel = FakeChannel(result=success_result())
        worker = OpenAIProposalWorker(channel=channel)
        worker.propose(valid_task())
        self.assertEqual(channel.calls, 1)
        self.assertEqual(channel.timeouts, [30.0])


class RedactionTests(unittest.TestCase):
    def test_errors_contain_no_sentinels(self):
        instruction = "PROMPT-SENTINEL-9f3a"
        context_text = "CONTEXT-SENTINEL-7c1e"
        task = valid_task(
            task_instruction=instruction,
            context_files=(("calculator.py", context_text),),
        )
        oversized = WorkerInput(
            process_id="process-local-001",
            task_id="task-local-001",
            repository_id="fixture-repository",
            base_commit="fixture-base-001",
            declared_change_paths=("a.py", "b.py"),
            task_instruction="i" * 4096,
            context_files=(("a.py", "y" * 8250), ("b.py", "z" * 8250)),
        )
        channel = FakeChannel(result=success_result())
        with self.assertRaisesRegex(
            ExecutionError, "^execution worker: model input is invalid$"
        ) as raised:
            OpenAIProposalWorker(channel=channel).propose(oversized)
        for sentinel in (instruction, context_text, "PROMPT-SENTINEL", "CONTEXT-SENTINEL"):
            self.assertNotIn(sentinel, str(raised.exception))
        self.assertEqual(channel.calls, 0)

        provider_output = "PROVIDER-RESPONSE-SENTINEL-51bd"
        bad_channel = FakeChannel(
            result=ResponsesModelResult(status="completed", output_text=provider_output)
        )
        with self.assertRaisesRegex(
            ExecutionError, "^execution worker: provider response is invalid$"
        ) as raised:
            OpenAIProposalWorker(channel=bad_channel).propose(task)
        self.assertNotIn(provider_output, str(raised.exception))
        self.assertNotIn(instruction, str(raised.exception))
        self.assertNotIn(context_text, str(raised.exception))

        refusal_text = "REFUSAL-SENTINEL-aa01"
        refusal_channel = FakeChannel(
            result=ResponsesModelResult(
                status="completed",
                output_text=json.dumps({"changes": [{"path": "calculator.py", "content": "x"}]}),
                refusal=refusal_text,
            )
        )
        with self.assertRaisesRegex(
            ExecutionError, "^execution worker: provider response is invalid$"
        ) as raised:
            OpenAIProposalWorker(channel=refusal_channel).propose(task)
        self.assertNotIn(refusal_text, str(raised.exception))

        failing = FakeChannel(error=RuntimeError("EXCEPTION-SENTINEL-c4d2"))
        with self.assertRaisesRegex(
            ExecutionError, "^execution worker: provider request failed$"
        ) as raised:
            OpenAIProposalWorker(channel=failing).propose(task)
        self.assertNotIn("EXCEPTION-SENTINEL", str(raised.exception))
        self.assertNotIn(instruction, str(raised.exception))


class NoExternalAccessTests(unittest.TestCase):
    def test_module_has_no_http_network_file_or_environment_access(self):
        source = Path(worker_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules: set[str] = set()
        called_names: set[str] = set()
        called_attrs: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add((node.module or "").lower())
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called_names.add(func.id.lower())
                elif isinstance(func, ast.Attribute):
                    called_attrs.add(func.attr.lower())
        for forbidden in ("os", "socket", "urllib", "http", "ssl", "subprocess", "requests", "httpx", "openai", "logging"):
            self.assertNotIn(forbidden, imported_modules)
        for forbidden in ("environ", "getenv", "urlopen", "urlretrieve", "get", "post", "request", "getlogger", "basicconfig", "print"):
            self.assertNotIn(forbidden, called_names)
        for forbidden in ("environ", "getenv", "read_text", "write_text", "read_bytes", "write_bytes"):
            self.assertNotIn(forbidden, called_attrs)
        self.assertNotIn("open(", source)

    def test_result_and_worker_records_carry_no_credentials(self):
        result = ResponsesModelResult(status="completed", output_text="{}")
        self.assertEqual(set(ResponsesModelResult.__dataclass_fields__), {"status", "output_text", "refusal"})
        with self.assertRaises(FrozenInstanceError):
            result.status = "other"  # type: ignore[misc]
        self.assertTrue(isinstance(OpenAIProposalWorker(channel=FakeChannel(result=result)), OpenAIProposalWorker))
        self.assertTrue(isinstance(FakeChannel(result=result), OpenAIResponsesChannel))


if __name__ == "__main__":
    unittest.main()
