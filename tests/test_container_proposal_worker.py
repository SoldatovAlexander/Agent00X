from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from app_contracts.container_proposal_worker import (
    CONTAINER_PACKAGE_PATH,
    CONTAINER_SCHEMA_PATH,
    WORKER_CHILD_PROGRAM,
    WORKER_SCHEMA_FILES,
    WORKER_STARTUP_STATUSES,
    WORKER_STATUS_CATEGORIES,
    ContainerProposalWorker,
    _environment_mapping,
    _frame_bytes,
    _read_frame,
    _stage_worker_schemas,
    _status_category,
    _worker_input_frame,
)
from app_contracts.deepseek_worker import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionsModelResult,
)
from app_contracts.executor import (
    ExecutionError,
    WorkerInput,
    WorkerProposal,
    WorkerTerminalOutcome,
)


def _task() -> WorkerInput:
    return WorkerInput(
        process_id="process-exp776-synthetic",
        task_id="task-exp776-synthetic",
        repository_id="synthetic/repository",
        base_commit="c" * 40,
        declared_change_paths=("calculator.py",),
        task_instruction="Fix the synthetic calculator case",
        context_files=(("calculator.py", "synthetic input"),),
    )


class FakeChannel:
    def __init__(self) -> None:
        self.calls = 0

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        self.calls += 1
        return ChatCompletionsModelResult(
            choices=(
                ChatCompletionChoice(
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=(
                            '{"changes":[{"path":"calculator.py",'
                            '"content":"fixed in isolated worker"}]}'
                        ),
                    ),
                ),
            )
        )


class ContainerProposalWorkerTests(unittest.TestCase):
    def test_terminal_child_frame_is_validated_as_bounded_outcome(self):
        worker = object.__new__(ContainerProposalWorker)
        frame = {
            "schema": "agent00x-worker-result/v2",
            "outcome": "denied",
            "changes": None,
            "reason_code": "publication_not_authorized",
        }
        self.assertEqual(
            worker._validated_proposal(frame, _task()),
            WorkerTerminalOutcome("denied", "publication_not_authorized"),
        )
        for malformed in (
            {**frame, "extra": "x"},
            {**frame, "reason_code": "conflicting_requirements"},
            {**frame, "changes": []},
        ):
            with self.subTest(frame=malformed), self.assertRaisesRegex(
                ExecutionError, "proposal is invalid"
            ):
                worker._validated_proposal(malformed, _task())

    def test_child_program_is_syntax_valid_and_statuses_are_fixed(self):
        compile(WORKER_CHILD_PROGRAM, "<container-proposal-worker>", "exec")
        self.assertEqual(len(WORKER_STARTUP_STATUSES), len(set(WORKER_STARTUP_STATUSES)))
        self.assertTrue(WORKER_STARTUP_STATUSES)
        self.assertTrue(
            all(
                item in WORKER_STATUS_CATEGORIES
                and item.isascii()
                and item.replace("-", "").isalnum()
                and item == item.lower()
                for item in WORKER_STARTUP_STATUSES
            )
        )
        self.assertIsNone(
            _status_category(
                {"schema": "agent00x-worker-status/v1", "status": "raw exception"}
            )
        )

    def test_mount_paths_and_environment_mapping_are_exact(self):
        self.assertEqual(CONTAINER_PACKAGE_PATH, "/opt/agent00x/app_contracts")
        self.assertEqual(CONTAINER_SCHEMA_PATH, "/opt/schemas")
        self.assertEqual(
            WORKER_SCHEMA_FILES,
            ("observation-event.schema.json", "checkpoint.schema.json"),
        )
        self.assertEqual(
            _environment_mapping(["A=1", "B=two=three"]),
            _environment_mapping(["B=two=three", "A=1"]),
        )
        self.assertIsNone(_environment_mapping(["A=1", "A=2"]))
        self.assertIsNone(_environment_mapping(["not-an-entry"]))

    def test_schema_staging_copies_only_two_fixed_files(self):
        with tempfile.TemporaryDirectory() as source_temp:
            with tempfile.TemporaryDirectory() as stage_temp:
                source = Path(source_temp)
                stage = Path(stage_temp)
                for name in WORKER_SCHEMA_FILES:
                    (source / name).write_text(name, encoding="utf-8")
                (source / "unrelated.json").write_text("unrelated", encoding="utf-8")
                _stage_worker_schemas(source, stage)
                self.assertEqual({item.name for item in stage.iterdir()}, set(WORKER_SCHEMA_FILES))

    def test_remote_snapshot_identity_fields_survive_worker_input_framing(self):
        tree_digest = "sha256:" + "a" * 64
        claim_digest = "sha256:" + "b" * 64
        task = WorkerInput(
            process_id="process-exp777-snapshot",
            task_id="task-exp777-snapshot",
            repository_id="SoldatovAlexander/brainbooster_full_v11",
            base_commit="2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e",
            declared_change_paths=("backend/routes.py",),
            snapshot_tree_digest=tree_digest,
            snapshot_origin="github_rest_api_claim",
            task_instruction="synthetic task",
            context_files=(("backend/routes.py", "synthetic input"),),
            snapshot_claim_digest=claim_digest,
        )
        frame = _worker_input_frame(task)
        self.assertEqual(frame["snapshot_tree_digest"], tree_digest)
        self.assertEqual(frame["snapshot_origin"], "github_rest_api_claim")
        self.assertEqual(frame["snapshot_claim_digest"], claim_digest)
        self.assertEqual(frame["model_timeout_seconds"], 30.0)
        self.assertEqual(
            _worker_input_frame(task, model_timeout_seconds=180)["model_timeout_seconds"],
            180,
        )

    def test_frame_encoding_is_bounded(self):
        self.assertEqual(_frame_bytes({"x": 1}, maximum=32)[:4], b"\x00\x00\x00\x07")
        with self.assertRaisesRegex(ValueError, "exceeds limit"):
            _frame_bytes({"x": "y" * 32}, maximum=16)

    def test_frame_reader_times_out_without_leaking_stream_data(self):
        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, "rb", buffering=0)
        try:
            with self.assertRaisesRegex(ValueError, "timed out"):
                _read_frame(stream, maximum=64, deadline=time.monotonic() + 0.01)
        finally:
            stream.close()
            os.close(write_fd)

    def test_popen_failure_is_redacted_and_instance_is_one_shot(self):
        channel = FakeChannel()
        worker = ContainerProposalWorker(
            channel,
            docker_executable="/usr/local/bin/docker",
        )
        actual_tempdir = tempfile.TemporaryDirectory

        class TrackedTemporaryDirectory:
            path: str | None = None

            def __init__(self, *args, **kwargs) -> None:
                self.delegate = actual_tempdir(*args, **kwargs)
                self.name = self.delegate.name
                TrackedTemporaryDirectory.path = self.name

            def cleanup(self) -> None:
                self.delegate.cleanup()

        image_env = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(["PATH=/usr/bin", "PYTHONPATH=/opt/target-python"]),
            stderr="",
        )
        with (
            patch("app_contracts.container_proposal_worker.tempfile.TemporaryDirectory", TrackedTemporaryDirectory),
            patch("app_contracts.container_proposal_worker.subprocess.run", return_value=image_env),
            patch(
                "app_contracts.container_proposal_worker.subprocess.Popen",
                side_effect=OSError("synthetic raw launch diagnostic"),
            ) as popen,
        ):
            with self.assertRaisesRegex(ExecutionError, "isolated worker unavailable") as first:
                worker.propose(_task())
            self.assertNotIn("synthetic raw", str(first.exception))
            with self.assertRaisesRegex(ExecutionError, "isolated worker unavailable"):
                worker.propose(_task())
            popen.assert_called_once()
        self.assertIsNotNone(TrackedTemporaryDirectory.path)
        self.assertFalse(Path(TrackedTemporaryDirectory.path).exists())
        self.assertEqual(channel.calls, 0)

    def test_constructor_rejects_invalid_channel_and_relative_docker_path(self):
        with self.assertRaises(ExecutionError):
            ContainerProposalWorker(object(), docker_executable="/usr/local/bin/docker")
        with self.assertRaises(ExecutionError):
            ContainerProposalWorker(FakeChannel(), docker_executable="docker")
        with self.assertRaises(ExecutionError):
            ContainerProposalWorker(
                FakeChannel(),
                docker_executable="/usr/local/bin/docker",
                model_timeout_seconds=181,
            )

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1",
        "pinned container Worker test is opt-in",
    )
    def test_pinned_container_returns_one_fake_proposal(self):
        docker = os.environ.get("AGENT00X_DOCKER_EXECUTABLE") or shutil.which("docker")
        self.assertIsInstance(docker, str)
        self.assertTrue(Path(docker).is_absolute())
        channel = FakeChannel()
        worker = ContainerProposalWorker(channel, docker_executable=docker)

        proposal = worker.propose(_task())

        self.assertEqual(
            proposal,
            WorkerProposal(changes=(("calculator.py", "fixed in isolated worker"),)),
        )
        self.assertEqual(channel.calls, 1)


if __name__ == "__main__":
    unittest.main()
