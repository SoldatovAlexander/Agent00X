from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_contracts.brainbooster_target_profile import (
    TARGET_RUNTIME_IMAGE_ID,
)
from app_contracts.verifier_image_pin import (
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.container_proposal_worker import ContainerProposalWorker
from app_contracts.durable_stage import SQLiteStagedArtifactStore
from app_contracts.local_ollama_channel import LocalOllamaChatCompletionsChannel
from app_contracts.observation_store import SQLiteObservationStore
from app_contracts.observer_runtime import JournaledProposalWorker
from app_contracts.sandbox import DockerSandboxBackend
from app_contracts.verifier_container import DockerContainerVerifier
from scripts.r5_batch_selection import select_first_five_attempts, select_r5_attempts
from scripts import r5_runtime_adapters
from scripts.r5_runtime_adapters import (
    R5RuntimeAdapterError,
    R5RuntimeAdapters,
    build_r5_runtime_adapters,
)


class R5RuntimeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stage_path = Path(self.temporary.name) / "stage.sqlite3"
        self.stage = SQLiteStagedArtifactStore(self.stage_path)
        self.addCleanup(self.stage.close)
        self.observer = SQLiteObservationStore(":memory:")
        self.addCleanup(self.observer.close)

    def _build(self, **overrides) -> R5RuntimeAdapters:
        arguments = {
            "docker_executable": "/usr/bin/docker",
            "stage_store": self.stage,
            "observation_store": self.observer,
        }
        arguments.update(overrides)
        return build_r5_runtime_adapters(**arguments)

    def test_builds_exact_pinned_adapters_without_invoking_them_or_creating_store(self) -> None:
        stage_stat = self.stage_path.stat()
        event_count = len(self.observer.events())
        with (
            patch.object(
                LocalOllamaChatCompletionsChannel,
                "create_chat_completion",
                side_effect=AssertionError("model request attempted"),
            ) as model_call,
            patch.object(
                ContainerProposalWorker,
                "propose",
                side_effect=AssertionError("Worker invoked"),
            ) as worker_call,
            patch.object(
                DockerContainerVerifier,
                "verify",
                side_effect=AssertionError("verifier invoked"),
            ) as verifier_call,
            patch.object(
                DockerSandboxBackend,
                "create",
                side_effect=AssertionError("Docker sandbox invoked"),
            ) as sandbox_call,
        ):
            adapters = self._build()

        self.assertIs(type(adapters), R5RuntimeAdapters)
        self.assertTrue(callable(adapters.worker_factory))
        self.assertEqual(adapters.sandbox_backend.image, TARGET_RUNTIME_IMAGE_ID)
        self.assertEqual(adapters.sandbox_backend.memory, "512m")
        self.assertEqual(adapters.sandbox_backend.cpus, "1.0")
        self.assertEqual(adapters.sandbox_backend.pids_limit, 64)
        self.assertIs(type(adapters.verifier), DockerContainerVerifier)
        self.assertEqual(
            adapters.verifier._config.runtime_image_id, VERIFIER_RUNTIME_IMAGE_ID
        )
        self.assertEqual(
            adapters.verifier._config.verifier_code_digest,
            VERIFIER_RUNTIME_CODE_DIGEST,
        )
        self.assertEqual(adapters.verifier._config.timeout_seconds, 60)
        self.assertIs(adapters.stage_sink, self.stage)
        self.assertIs(adapters.observation_store, self.observer)
        self.assertEqual(len(self.observer.events()), event_count)
        self.assertEqual(self.stage_path.stat().st_ino, stage_stat.st_ino)
        self.assertEqual(self.stage_path.stat().st_size, stage_stat.st_size)
        self.assertEqual(
            repr(adapters), "R5RuntimeAdapters(fixed_pins=True, contents='opaque')"
        )
        model_call.assert_not_called()
        worker_call.assert_not_called()
        verifier_call.assert_not_called()
        sandbox_call.assert_not_called()

    def test_creates_five_fresh_workers_with_exact_journal_bindings(self) -> None:
        adapters = self._build()
        selected = select_first_five_attempts()
        workers = [adapters.worker_factory(item) for item in selected]

        self.assertTrue(all(type(worker) is JournaledProposalWorker for worker in workers))
        self.assertEqual(len({id(worker) for worker in workers}), 5)
        self.assertEqual(len({id(worker._worker) for worker in workers}), 5)
        self.assertEqual(len({id(worker._worker._channel) for worker in workers}), 5)
        for item, worker in zip(selected, workers, strict=True):
            self.assertTrue(
                worker.matches(
                    self.observer,
                    process_id=item.worker_input.process_id,
                    task_id=item.worker_input.task_id,
                )
            )
            self.assertIs(type(worker._worker), ContainerProposalWorker)
            self.assertIs(type(worker._worker._channel), LocalOllamaChatCompletionsChannel)
            self.assertEqual(worker._worker._docker, "/usr/bin/docker")
            self.assertEqual(worker._worker._model_timeout_seconds, 60.0)
            self.assertFalse(hasattr(worker._worker, "_credential_source"))
        self.assertEqual(len(self.observer.events()), 5)

    def test_runtime_factory_accepts_only_the_explicit_pending_selection(self) -> None:
        selected = select_r5_attempts(("R5-002", "R5-003"))
        adapters = self._build(selected_attempts=selected)
        workers = [adapters.worker_factory(item) for item in selected]
        self.assertEqual(len(workers), 2)
        self.assertTrue(
            all(
                worker.matches(
                    self.observer,
                    process_id=item.worker_input.process_id,
                    task_id=item.worker_input.task_id,
                )
                for item, worker in zip(selected, workers, strict=True)
            )
        )
        with self.assertRaises(R5RuntimeAdapterError):
            adapters.worker_factory(select_first_five_attempts()[0])

    def test_duplicate_and_unregistered_attempts_are_rejected_without_retry(self) -> None:
        adapters = self._build()
        selected = select_first_five_attempts()
        first = selected[0]
        adapters.worker_factory(first)
        with self.assertRaises(R5RuntimeAdapterError):
            adapters.worker_factory(first)
        forged = type(first)(
            **{
                **first.__dict__,
                "worker_input": selected[1].worker_input,
            }
        )
        with self.assertRaises(R5RuntimeAdapterError):
            adapters.worker_factory(forged)

    def test_rejects_bad_pins_timeouts_paths_and_unopened_stores_before_construction(self) -> None:
        with (
            patch.object(r5_runtime_adapters, "DockerSandboxBackend") as backend,
            patch.object(r5_runtime_adapters, "DockerContainerVerifier") as verifier,
        ):
            with self.assertRaises(R5RuntimeAdapterError):
                self._build(docker_executable="docker")
            with self.assertRaises(R5RuntimeAdapterError):
                self._build(worker_timeout_seconds=301)
            with self.assertRaises(R5RuntimeAdapterError):
                self._build(verifier_timeout_seconds=34)
            with self.assertRaises(R5RuntimeAdapterError):
                self._build(stage_store=object())
            backend.assert_not_called()
            verifier.assert_not_called()

        closed_stage = object.__new__(SQLiteStagedArtifactStore)
        closed_stage._connection = None
        closed_stage._read_only = False
        with self.assertRaises(R5RuntimeAdapterError):
            self._build(stage_store=closed_stage)


if __name__ == "__main__":
    unittest.main()
