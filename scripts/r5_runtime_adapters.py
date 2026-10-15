"""Construct fixed R5 runtime collaborators without invoking them or opening stores."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import re
import threading

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
from app_contracts.verifier_container import (
    DockerContainerVerifier,
    VerifierContainerConfig,
)
from scripts.r5_batch_selection import (
    R5SelectedAttempt,
    select_first_five_attempts,
    select_r5_attempts,
)


R5_PROCESS_ID = "process-r5-preregistered-study-v1"
R5_WORKER_TIMEOUT_SECONDS = 60.0
R5_VERIFIER_TIMEOUT_SECONDS = 60
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class R5RuntimeAdapterError(ValueError):
    """A fixed, redacted R5 runtime-adapter configuration failure."""


@dataclass(frozen=True, repr=False)
class R5RuntimeAdapters:
    worker_factory: object = field(repr=False)
    verifier: object = field(repr=False)
    sandbox_backend: object = field(repr=False)
    stage_sink: object = field(repr=False)
    observation_store: object = field(repr=False)

    def __repr__(self) -> str:
        return "R5RuntimeAdapters(fixed_pins=True, contents='opaque')"


class _R5WorkerFactory:
    def __init__(
        self,
        *,
        docker_executable: str,
        observation_store: SQLiteObservationStore,
        worker_timeout_seconds: float,
        selected_attempts: tuple[R5SelectedAttempt, ...],
    ) -> None:
        self._docker_executable = docker_executable
        self._observation_store = observation_store
        self._worker_timeout_seconds = worker_timeout_seconds
        self._scheduled = {item.attempt_id: item for item in selected_attempts}
        self._claimed_task_ids: set[str] = set()
        self._lock = threading.Lock()

    def __call__(self, selected_attempt: object) -> JournaledProposalWorker:
        try:
            if type(selected_attempt) is not R5SelectedAttempt:
                raise ValueError
            expected = self._scheduled.get(selected_attempt.attempt_id)
            if (
                expected is None
                or selected_attempt != expected
                or selected_attempt.worker_input != expected.worker_input
            ):
                raise ValueError
            worker_input = selected_attempt.worker_input
            expected_task_id = "task-" + selected_attempt.attempt_id.lower()
            if (
                worker_input.process_id != R5_PROCESS_ID
                or worker_input.task_id != expected_task_id
            ):
                raise ValueError
            with self._lock:
                if expected_task_id in self._claimed_task_ids:
                    raise ValueError
                # A constructor failure is still consumed; this factory never retries an ID.
                self._claimed_task_ids.add(expected_task_id)
            channel = LocalOllamaChatCompletionsChannel()
            worker = ContainerProposalWorker(
                channel,
                docker_executable=self._docker_executable,
                model_timeout_seconds=self._worker_timeout_seconds,
            )
            return JournaledProposalWorker(
                worker,
                self._observation_store,
                process_id=R5_PROCESS_ID,
                task_id=expected_task_id,
            )
        except R5RuntimeAdapterError:
            raise
        except Exception:
            raise R5RuntimeAdapterError(
                "R5 runtime adapters: Worker construction rejected"
            ) from None


def build_r5_runtime_adapters(
    *,
    docker_executable: str,
    stage_store: object,
    observation_store: object,
    worker_timeout_seconds: float = R5_WORKER_TIMEOUT_SECONDS,
    verifier_timeout_seconds: int = R5_VERIFIER_TIMEOUT_SECONDS,
    selected_attempts: tuple[R5SelectedAttempt, ...] | None = None,
) -> R5RuntimeAdapters:
    """Build collaborators around caller-opened SQLite stores and exact profile pins."""

    try:
        _validate_configuration(
            docker_executable=docker_executable,
            stage_store=stage_store,
            observation_store=observation_store,
            worker_timeout_seconds=worker_timeout_seconds,
            verifier_timeout_seconds=verifier_timeout_seconds,
        )
        scheduled = (
            select_first_five_attempts()
            if selected_attempts is None
            else selected_attempts
        )
        if (
            type(scheduled) is not tuple
            or not 1 <= len(scheduled) <= 5
            or any(type(item) is not R5SelectedAttempt for item in scheduled)
            or any(
                provided != expected
                for provided, expected in zip(
                    scheduled,
                    select_r5_attempts(tuple(item.attempt_id for item in scheduled)),
                    strict=True,
                )
            )
        ):
            raise ValueError
        worker_factory = _R5WorkerFactory(
            docker_executable=docker_executable,
            observation_store=observation_store,
            worker_timeout_seconds=float(worker_timeout_seconds),
            selected_attempts=scheduled,
        )
        verifier_config = VerifierContainerConfig(
            docker_executable=docker_executable,
            runtime_image_id=VERIFIER_RUNTIME_IMAGE_ID,
            verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
            timeout_seconds=verifier_timeout_seconds,
        )
        verifier = DockerContainerVerifier(verifier_config)
        sandbox_backend = DockerSandboxBackend(
            TARGET_RUNTIME_IMAGE_ID,
            memory="512m",
            cpus="1.0",
            pids_limit=64,
        )
        return R5RuntimeAdapters(
            worker_factory=worker_factory,
            verifier=verifier,
            sandbox_backend=sandbox_backend,
            stage_sink=stage_store,
            observation_store=observation_store,
        )
    except R5RuntimeAdapterError:
        raise
    except Exception:
        raise R5RuntimeAdapterError(
            "R5 runtime adapters: fixed configuration rejected"
        ) from None


def _validate_configuration(
    *,
    docker_executable: object,
    stage_store: object,
    observation_store: object,
    worker_timeout_seconds: object,
    verifier_timeout_seconds: object,
) -> None:
    if (
        type(docker_executable) is not str
        or not Path(docker_executable).is_absolute()
        or type(stage_store) is not SQLiteStagedArtifactStore
        or getattr(stage_store, "_connection", None) is None
        or getattr(stage_store, "_read_only", True) is not False
        or type(observation_store) is not SQLiteObservationStore
        or getattr(observation_store, "_connection", None) is None
        or type(worker_timeout_seconds) not in {int, float}
        or isinstance(worker_timeout_seconds, bool)
        or not math.isfinite(float(worker_timeout_seconds))
        or not 0 < float(worker_timeout_seconds) <= 300
        or type(verifier_timeout_seconds) is not int
        or not 35 <= verifier_timeout_seconds <= 300
        or not all(
            type(pin) is str and _DIGEST.fullmatch(pin) is not None
            for pin in (
                TARGET_RUNTIME_IMAGE_ID,
                VERIFIER_RUNTIME_IMAGE_ID,
                VERIFIER_RUNTIME_CODE_DIGEST,
            )
        )
    ):
        raise R5RuntimeAdapterError(
            "R5 runtime adapters: fixed configuration rejected"
        )
