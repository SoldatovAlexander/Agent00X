"""One-shot local R5 batch CLI; implementation is inert until explicitly invoked."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from typing import Callable, TextIO
from contextlib import contextmanager

from app_contracts.brainbooster_target_profile import (
    PINNED_COMMIT,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    TARGET_RUNTIME_IMAGE_ID,
)
from app_contracts.verifier_image_pin import (
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.durable_stage import SQLiteStagedArtifactStore
from app_contracts.github_git_commit_source import GitHubRawCommitObjectSource
from app_contracts.github_archive_snapshot import GitHubCodeloadArchiveTransport
from app_contracts.github_snapshot import GitCommitObject, GitHubSnapshotContents
from app_contracts.local_ollama_channel import LOCAL_OLLAMA_MODEL
from app_contracts.observation_store import SQLiteObservationStore
from app_contracts.r5_attempt_ledger import (
    R5_EXECUTION_FAILURE_REASONS,
    SQLiteR5AttemptLedger,
)
from app_contracts.r5_local_model_preflight import (
    EXPECTED_OLLAMA_VERSION,
    R5LocalModelPreflightError,
    R5LocalOllamaMetadataPreflight,
    R5LocalModelMetadata,
)
from app_contracts.r5_execution import R5_UNKNOWN_PHASE_CODES
from scripts.r5_batch_selection import (
    EXPECTED_FIRST_FIVE,
    R5SelectedAttempt,
    select_first_five_attempts,
    select_r5_attempts,
)
from scripts.r5_pinned_snapshot import read_pinned_r5_snapshot
from scripts.r5_runtime_adapters import build_r5_runtime_adapters
from scripts.run_r5_preregistered_batch import R5BatchResult, run_first_five_r5_attempts


_CARD_ID = re.compile(r"EXP-[1-9][0-9]{2,5}\Z")
_MODEL_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_R5_BATCH_SECONDS = 2_400
MIN_R5_DISK_FREE_BYTES = 500 * 1024 * 1024


class R5BatchCLIError(ValueError):
    """A fixed, redacted R5 CLI preflight or gate failure."""


class R5BatchDeadlineExceeded(TimeoutError):
    """The local five-attempt execution reached its one-shot wall deadline."""


class _DeadlineWorkerFactory:
    def __init__(self, factory: Callable, deadline: float) -> None:
        self._factory = factory
        self._deadline = deadline
        self.expired = False

    def __call__(self, attempt: object):
        if time.monotonic() >= self._deadline:
            self.expired = True
            raise R5BatchDeadlineExceeded("R5 batch: deadline expired")
        return self._factory(attempt)


@dataclass(frozen=True)
class R5OutputPaths:
    ledger: Path
    stage: Path
    observer: Path


@dataclass
class _OpenedStores:
    ledger: SQLiteR5AttemptLedger
    stage: SQLiteStagedArtifactStore
    observer: SQLiteObservationStore
    owned: dict[Path, tuple[int, int]]
    paths: R5OutputPaths | None = None
    resumed: bool = False
    pending_extension_ids: tuple[str, ...] = ()
    _preserve: bool = False

    def activate(self) -> None:
        if self.pending_extension_ids:
            self.ledger.extend_allowed_attempt_ids(self.pending_extension_ids)
            self.pending_extension_ids = ()
        if self.resumed and getattr(self.stage, "_read_only", False):
            self.stage.close()
            if self.paths is None:
                raise R5BatchCLIError("R5 batch: local stores unavailable")
            self.stage = SQLiteStagedArtifactStore(self.paths.stage)
        self._preserve = True

    def preserve(self) -> None:
        self._preserve = True

    def close(self) -> None:
        errors = []
        for store in (self.observer, self.stage, self.ledger):
            try:
                store.close()
            except Exception:
                errors.append(True)
        if not self._preserve and not errors:
            for path in tuple(self.owned):
                try:
                    current = path.lstat()
                    expected = self.owned[path]
                    if (
                        path.is_symlink()
                        or not path.is_file()
                        or (current.st_dev, current.st_ino) != expected
                    ):
                        errors.append(True)
                        continue
                    path.unlink()
                except FileNotFoundError:
                    pass
                except Exception:
                    errors.append(True)
        if errors:
            raise R5BatchCLIError("R5 batch: local cleanup incomplete") from None


@dataclass(frozen=True)
class _Dependencies:
    transport_factory: Callable[[], object] = GitHubCodeloadArchiveTransport
    commit_source_factory: Callable[[str], object] = lambda git: GitHubRawCommitObjectSource(
        git, timeout_seconds=15
    )
    snapshot_loader: Callable[..., object] = read_pinned_r5_snapshot
    model_preflight_factory: Callable[[], object] = R5LocalOllamaMetadataPreflight
    docker_discover: Callable[[], str | None] = lambda: shutil.which("docker")
    disk_usage: Callable[[str | os.PathLike[str]], object] = shutil.disk_usage
    git_discover: Callable[[], str | None] = lambda: shutil.which("git")
    docker_inspect: Callable[[str, str], None] | None = None
    open_stores: Callable[..., _OpenedStores] | None = None
    adapter_builder: Callable[..., object] = build_r5_runtime_adapters
    batch_runner: Callable[..., object] = run_first_five_r5_attempts


def run_r5_batch_cli(
    argv: list[str] | None = None,
    *,
    input_fn: Callable[[str], str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    interactive: Callable[[], bool] | None = None,
    dependencies: _Dependencies | None = None,
) -> int:
    """Run the supported entrypoint. Merely importing this module performs no IO."""

    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
    read_input = input if input_fn is None else input_fn
    is_interactive = sys.stdin.isatty if interactive is None else interactive
    deps = _Dependencies() if dependencies is None else dependencies
    parser = argparse.ArgumentParser(description="Run one pinned local R5 batch.")
    parser.add_argument("--ledger-db", required=True)
    parser.add_argument("--stage-db", required=True)
    parser.add_argument("--observer-db", required=True)
    parser.add_argument("--model-digest", required=True)
    parser.add_argument("--execution-card-id", required=True)
    parser.add_argument("--resume-existing-stores", action="store_true")
    parser.add_argument("--attempt-ids")
    parser.add_argument("--extend-allowed-attempts", action="store_true")
    parser.add_argument("--continue-after-failed", action="store_true")
    args = parser.parse_args(argv)

    stores: _OpenedStores | None = None
    failure_phase = "arguments"
    try:
        (
            card_id, model_digest, paths, selected, resume, extend_allowed_attempts,
            continue_after_failed,
        ) = _validate_arguments(args)
        failure_phase = "disk"
        available_bytes = _require_disk_headroom(
            paths, deps.disk_usage, allow_existing=resume
        )
        failure_phase = "schedule"
        if not resume and tuple(item.attempt_id for item in selected) != EXPECTED_FIRST_FIVE:
            raise R5BatchCLIError("R5 batch: schedule rejected")

        # All readiness checks precede local database creation.
        failure_phase = "snapshot"
        transport = deps.transport_factory()
        commit_source = deps.commit_source_factory(
            _find_absolute_executable(deps.git_discover)
        )
        snapshot = deps.snapshot_loader(
            transport=transport,
            commit_object_source=commit_source,
        )
        _validate_snapshot(snapshot)
        failure_phase = "model_metadata"
        preflight = deps.model_preflight_factory()
        if not callable(getattr(preflight, "inspect", None)):
            raise R5BatchCLIError("R5 batch: model preflight unavailable")
        model = preflight.inspect(expected_model_digest=model_digest)
        if (
            type(model) is not R5LocalModelMetadata
            or model.version != EXPECTED_OLLAMA_VERSION
            or model.model != LOCAL_OLLAMA_MODEL
            or model.model_digest != model_digest
            or type(model.model_count) is not int
            or not 1 <= model.model_count <= 256
        ):
            raise R5BatchCLIError("R5 batch: model identity rejected")

        failure_phase = "docker_discovery"
        docker = deps.docker_discover()
        if type(docker) is not str or not Path(docker).is_absolute():
            raise R5BatchCLIError("R5 batch: Docker executable unavailable")
        inspect = _inspect_image if deps.docker_inspect is None else deps.docker_inspect
        failure_phase = "target_image"
        inspect(docker, TARGET_RUNTIME_IMAGE_ID)
        failure_phase = "verifier_image"
        inspect(docker, VERIFIER_RUNTIME_IMAGE_ID)
        failure_phase = "deadline_support"
        _require_deadline_support()

        failure_phase = "stores"
        opener = _open_stores if deps.open_stores is None else deps.open_stores
        stores = opener(
            paths,
            resume_existing=resume,
            selected_attempts=selected,
            allow_extension=extend_allowed_attempts,
        )
        if resume:
            records = {record.attempt_id: record for record in stores.ledger.records()}
            if any(
                (
                    attempt.attempt_id not in records
                    and attempt.attempt_id
                    not in getattr(stores, "pending_extension_ids", ())
                )
                or (
                    attempt.attempt_id in records
                    and records[attempt.attempt_id].state != "PENDING"
                )
                for attempt in selected
            ):
                raise R5BatchCLIError("R5 batch: selected attempt is not pending")

        failure_phase = "summary"
        _print_summary(
            output,
            card_id,
            model,
            selected_attempts=selected,
            resume=resume,
            available_bytes=available_bytes,
            snapshot_origin=snapshot.claim.evidence_origin,
            snapshot_tree_oid=snapshot.claim.tree_oid,
            snapshot_content_digest=snapshot.claim.content_digest,
            extend_attempt_ids=getattr(stores, "pending_extension_ids", ()),
            continue_after_failed=continue_after_failed,
        )
        failure_phase = "confirmation"
        if not is_interactive():
            raise R5BatchCLIError("R5 batch: interactive confirmation required")
        gate = f"RUN {card_id} ONCE"
        response = read_input(f"Type {gate} to continue: ")
        if type(response) is not str or response != gate:
            raise R5BatchCLIError("R5 batch: one-shot confirmation did not match")
        activate = getattr(stores, "activate", None)
        if callable(activate):
            activate()
        else:
            stores.preserve()
        if resume:
            records = {record.attempt_id: record for record in stores.ledger.records()}
            if any(
                attempt.attempt_id not in records
                or records[attempt.attempt_id].state != "PENDING"
                for attempt in selected
            ):
                raise R5BatchCLIError("R5 batch: selected attempt is not pending")
        failure_phase = "adapters"
        adapters = deps.adapter_builder(
            docker_executable=docker,
            stage_store=stores.stage,
            observation_store=stores.observer,
            selected_attempts=selected,
        )
        if (
            not callable(getattr(adapters, "worker_factory", None))
            or not callable(getattr(getattr(adapters, "verifier", None), "verify", None))
            or not callable(
                getattr(getattr(adapters, "sandbox_backend", None), "create", None)
            )
            or not callable(getattr(getattr(adapters, "stage_sink", None), "save", None))
            or not callable(getattr(getattr(adapters, "stage_sink", None), "load", None))
            or getattr(adapters, "stage_sink", None) is not stores.stage
            or getattr(adapters, "observation_store", None) is not stores.observer
        ):
            raise R5BatchCLIError("R5 batch: runtime adapter binding rejected")
        deadline = time.monotonic() + MAX_R5_BATCH_SECONDS
        guarded_factory = _DeadlineWorkerFactory(adapters.worker_factory, deadline)
        failure_phase = "execution"
        with _batch_deadline(MAX_R5_BATCH_SECONDS):
            result = deps.batch_runner(
                snapshot,
                stores.ledger,
                worker_factory=guarded_factory,
                verifier=adapters.verifier,
                sandbox_backend=adapters.sandbox_backend,
                stage_sink=adapters.stage_sink,
                observation_store=adapters.observation_store,
                selected_attempts=selected,
                continue_after_failed=continue_after_failed,
            )
        if type(result) is not R5BatchResult:
            raise R5BatchCLIError("R5 batch: result unavailable")
        failure_phase = "result_rendering"
        _print_result(
            output,
            result,
            deadline_expired=guarded_factory.expired
            or time.monotonic() >= deadline,
            selected_attempts=selected,
        )
        return 0 if result.status in {"complete", "complete-with-failures"} else 2
    except R5BatchDeadlineExceeded:
        print(
            "R5 batch: deadline expired; inspect the preserved ledger for claimed or unknown attempts",
            file=error_output,
        )
        return 2
    except R5LocalModelPreflightError as exc:
        print(
            f"R5 batch: model_metadata failed ({exc.reason_code})",
            file=error_output,
        )
        return 2
    except R5BatchCLIError as exc:
        print(str(exc), file=error_output)
        return 2
    except Exception:
        print(f"R5 batch: {failure_phase} failed", file=error_output)
        return 2
    finally:
        if stores is not None:
            try:
                stores.close()
            except Exception:
                print("R5 batch: local cleanup incomplete", file=error_output)


def _validate_arguments(
    args: argparse.Namespace,
) -> tuple[
    str,
    str,
    R5OutputPaths,
    tuple[R5SelectedAttempt, ...],
    bool,
    bool,
    bool,
]:
    try:
        card_id = args.execution_card_id
        model_digest = args.model_digest
        if (
            type(card_id) is not str
            or _CARD_ID.fullmatch(card_id) is None
            or type(model_digest) is not str
            or _MODEL_DIGEST.fullmatch(model_digest) is None
            or not all(_IMAGE_DIGEST.fullmatch(value) for value in (
                TARGET_RUNTIME_IMAGE_ID,
                VERIFIER_RUNTIME_IMAGE_ID,
                VERIFIER_RUNTIME_CODE_DIGEST,
            ))
        ):
            raise ValueError
        resume = args.resume_existing_stores is True
        if type(args.resume_existing_stores) is not bool:
            raise ValueError
        extend_allowed_attempts = args.extend_allowed_attempts is True
        if type(args.extend_allowed_attempts) is not bool:
            raise ValueError
        continue_after_failed = args.continue_after_failed is True
        if type(args.continue_after_failed) is not bool:
            raise ValueError
        if continue_after_failed and (not resume or args.attempt_ids is None):
            raise ValueError
        if args.attempt_ids is None:
            if extend_allowed_attempts:
                raise ValueError
            selected = select_first_five_attempts()
        else:
            if not resume or type(args.attempt_ids) is not str:
                raise ValueError
            parts = args.attempt_ids.split(",")
            if any(not part or part.strip() != part for part in parts):
                raise ValueError
            selected = select_r5_attempts(tuple(parts))
        path_validator = _validate_existing_path if resume else _validate_absent_path
        paths = R5OutputPaths(
            path_validator(args.ledger_db),
            path_validator(args.stage_db),
            path_validator(args.observer_db),
        )
        if len({paths.ledger, paths.stage, paths.observer}) != 3:
            raise ValueError
        if resume:
            _validate_resume_paths(paths)
        return (
            card_id,
            model_digest,
            paths,
            selected,
            resume,
            extend_allowed_attempts,
            continue_after_failed,
        )
    except Exception:
        raise R5BatchCLIError("R5 batch: request paths or pins rejected") from None


def _validate_absent_path(value: object) -> Path:
    try:
        if type(value) is not str:
            raise ValueError
        path = Path(value)
        if (
            not path.is_absolute()
            or path == Path(path.anchor)
            or ".." in path.parts
            or not path.name
            or path.exists()
            or path.is_symlink()
        ):
            raise ValueError
        parent = path.parent.resolve(strict=True)
        if not parent.is_dir():
            raise ValueError
        normalized = parent / path.name
        if normalized.exists() or normalized.is_symlink():
            raise ValueError
        return normalized
    except Exception:
        raise R5BatchCLIError("R5 batch: output path unavailable") from None


def _validate_existing_path(value: object) -> Path:
    try:
        if type(value) is not str:
            raise ValueError
        path = Path(value)
        if (
            not path.is_absolute()
            or path == Path(path.anchor)
            or ".." in path.parts
            or not path.name
            or path.is_symlink()
            or not path.is_file()
        ):
            raise ValueError
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError
        return path.parent.resolve(strict=True) / path.name
    except Exception:
        raise R5BatchCLIError("R5 batch: existing store path unavailable") from None


def _validate_resume_paths(paths: R5OutputPaths) -> None:
    try:
        parents = tuple(path.parent.resolve(strict=True) for path in (paths.ledger, paths.stage, paths.observer))
        devices = tuple(parent.stat().st_dev for parent in parents)
        if len(set(parents)) != 1 or len(set(devices)) != 1:
            raise ValueError
        for path in (paths.ledger, paths.stage, paths.observer):
            _validate_existing_path(str(path))
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{path}{suffix}")
                if sidecar.exists() or sidecar.is_symlink():
                    raise ValueError
    except Exception:
        raise R5BatchCLIError("R5 batch: existing stores unavailable") from None


def _require_disk_headroom(
    paths: R5OutputPaths,
    disk_usage: Callable[[str | os.PathLike[str]], object] = shutil.disk_usage,
    *,
    allow_existing: bool = False,
) -> int:
    try:
        destinations = (paths.ledger, paths.stage, paths.observer)
        parents = tuple(path.parent.resolve(strict=True) for path in destinations)
        if any(not parent.is_dir() for parent in parents):
            raise ValueError
        devices = tuple(parent.stat().st_dev for parent in parents)
        if len(set(devices)) != 1:
            raise ValueError
        if allow_existing:
            _validate_resume_paths(paths)
        for path, parent in zip(destinations, parents):
            if path.parent.resolve(strict=True) != parent or path.is_symlink():
                raise ValueError
            if allow_existing:
                _validate_existing_path(str(path))
            elif path.exists():
                raise ValueError
        usage = disk_usage(parents[0])
        free_bytes = getattr(usage, "free", None)
        if type(free_bytes) is not int or free_bytes < MIN_R5_DISK_FREE_BYTES:
            raise ValueError
        return free_bytes
    except Exception:
        raise R5BatchCLIError("R5 batch: local disk headroom unavailable") from None


def _find_absolute_executable(discover: Callable[[], str | None]) -> str:
    result = discover()
    if type(result) is not str or not Path(result).is_absolute():
        raise R5BatchCLIError("R5 batch: required executable unavailable")
    return result


def _inspect_image(docker_executable: str, image_id: str) -> None:
    if _IMAGE_DIGEST.fullmatch(image_id) is None:
        raise R5BatchCLIError("R5 batch: image pin rejected")
    try:
        result = subprocess.run(
            [docker_executable, "image", "inspect", "--format={{.Id}}", image_id],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        if getattr(result, "stdout", "").strip() != image_id:
            raise ValueError
    except Exception:
        raise R5BatchCLIError("R5 batch: pinned Docker image unavailable") from None


def _require_deadline_support(signal_api=signal) -> None:
    if (
        threading.current_thread() is not threading.main_thread()
        or not hasattr(signal_api, "SIGALRM")
        or not hasattr(signal_api, "ITIMER_REAL")
        or not callable(getattr(signal_api, "setitimer", None))
        or not callable(getattr(signal_api, "getitimer", None))
        or not callable(getattr(signal_api, "signal", None))
        or not callable(getattr(signal_api, "getsignal", None))
    ):
        raise R5BatchCLIError("R5 batch: bounded deadline unavailable")
    try:
        current, interval = signal_api.getitimer(signal_api.ITIMER_REAL)
        if current != 0 or interval != 0:
            raise ValueError
    except Exception:
        raise R5BatchCLIError("R5 batch: bounded deadline unavailable") from None


@contextmanager
def _batch_deadline(seconds: int, *, signal_api=signal):
    _require_deadline_support(signal_api)
    old_handler = signal_api.getsignal(signal_api.SIGALRM)

    def expire(_signum, _frame):
        raise R5BatchDeadlineExceeded("R5 batch: deadline expired")

    signal_api.signal(signal_api.SIGALRM, expire)
    try:
        signal_api.setitimer(signal_api.ITIMER_REAL, float(seconds))
        yield
    finally:
        try:
            signal_api.setitimer(signal_api.ITIMER_REAL, 0.0)
        finally:
            signal_api.signal(signal_api.SIGALRM, old_handler)


def _reserve_new_file(path: Path) -> tuple[int, int]:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        current = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)
            or info.st_nlink != 1
        ):
            raise ValueError
        return info.st_dev, info.st_ino
    finally:
        os.close(descriptor)


def _open_stores(
    paths: R5OutputPaths,
    *,
    resume_existing: bool = False,
    selected_attempts: tuple[R5SelectedAttempt, ...] | None = None,
    allow_extension: bool = False,
) -> _OpenedStores:
    if type(allow_extension) is not bool or (allow_extension and not resume_existing):
        raise R5BatchCLIError("R5 batch: attempt extension rejected")
    selected = select_first_five_attempts() if selected_attempts is None else selected_attempts
    if resume_existing:
        owned: dict[Path, tuple[int, int]] = {}
        before = _file_digests((paths.ledger, paths.stage, paths.observer))
        ledger = stage = observer = None
        try:
            _validate_resume_paths(paths)
            _validate_observer_schema_read_only(paths.observer)
            ledger = SQLiteR5AttemptLedger.open_existing(paths.ledger)
            stage = SQLiteStagedArtifactStore(paths.stage, read_only=True)
            observer = SQLiteObservationStore(paths.observer)
            records = ledger.records()
            allowed = {record.attempt_id for record in records}
            selected_ids = tuple(item.attempt_id for item in selected)
            missing = tuple(item for item in selected_ids if item not in allowed)
            if missing:
                if not allow_extension:
                    raise ValueError
                last_number = max(int(item[3:]) for item in allowed)
                expected = tuple(
                    f"R5-{number:03d}"
                    for number in range(last_number + 1, last_number + 1 + len(missing))
                )
                if missing != expected:
                    raise ValueError
            elif allow_extension:
                raise ValueError
            ledger.close()
            observer.close()
            stage.close()
            ledger = SQLiteR5AttemptLedger.open_existing(paths.ledger)
            stage = SQLiteStagedArtifactStore(paths.stage, read_only=True)
            observer = SQLiteObservationStore(paths.observer)
            if _file_digests((paths.ledger, paths.stage, paths.observer)) != before:
                raise ValueError
            _validate_resume_paths(paths)
            return _OpenedStores(
                ledger, stage, observer, owned, paths=paths, resumed=True,
                pending_extension_ids=missing, _preserve=True,
            )
        except Exception:
            for store in (observer, stage, ledger):
                try:
                    if store is not None:
                        store.close()
                except Exception:
                    pass
            raise R5BatchCLIError("R5 batch: existing stores rejected") from None

    owned: dict[Path, tuple[int, int]] = {}
    ledger = stage = observer = None
    try:
        ledger = SQLiteR5AttemptLedger.create(
            paths.ledger, allowed_attempt_ids=EXPECTED_FIRST_FIVE
        )
        ledger_info = paths.ledger.lstat()
        owned[paths.ledger] = (ledger_info.st_dev, ledger_info.st_ino)
        for path in (paths.stage, paths.observer):
            owned[path] = _reserve_new_file(path)
        stage = SQLiteStagedArtifactStore(paths.stage)
        observer = SQLiteObservationStore(paths.observer)
        _record_sidecars(owned, paths)
        return _OpenedStores(ledger, stage, observer, owned, paths=paths)
    except Exception:
        closed = True
        for store in (observer, stage, ledger):
            try:
                if store is not None:
                    store.close()
            except Exception:
                closed = False
        try:
            _record_sidecars(owned, paths)
        except Exception:
            closed = False
        if closed:
            _remove_owned_files(owned)
        raise R5BatchCLIError("R5 batch: local stores unavailable") from None


def _file_digests(paths: tuple[Path, ...]) -> tuple[str, ...]:
    digests = []
    for path in paths:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digests.append(digest.hexdigest())
    return tuple(digests)


def _validate_observer_schema_read_only(path: Path) -> None:
    connection = None
    try:
        uri = path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
        expected = {
            "observation_events": {"event_id", "cursor", "event_json", "digest"},
            "observation_checkpoints": {
                "checkpoint_id", "cursor", "checkpoint_json", "digest"
            },
        }
        if version != SQLiteObservationStore.SCHEMA_VERSION or not expected.keys() <= tables:
            raise ValueError
        for table, columns in expected.items():
            actual = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if actual != columns:
                raise ValueError
    except Exception:
        raise R5BatchCLIError("R5 batch: existing stores rejected") from None
    finally:
        if connection is not None:
            connection.close()


def _record_sidecars(owned: dict[Path, tuple[int, int]], paths: R5OutputPaths) -> None:
    for path in (paths.ledger, paths.stage, paths.observer):
        for candidate in (Path(f"{path}-wal"), Path(f"{path}-shm")):
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                raise R5BatchCLIError("R5 batch: local store sidecar rejected")
            owned[candidate] = (info.st_dev, info.st_ino)


def _remove_owned_files(owned: dict[Path, tuple[int, int]]) -> None:
    for path, identity in tuple(owned.items()):
        try:
            info = path.lstat()
            if path.is_symlink() or not path.is_file() or (info.st_dev, info.st_ino) != identity:
                continue
            path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _print_summary(
    output: TextIO,
    card_id: str,
    model: R5LocalModelMetadata,
    *,
    available_bytes: int,
    snapshot_origin: str,
    snapshot_tree_oid: str,
    snapshot_content_digest: str,
    selected_attempts: tuple[R5SelectedAttempt, ...] | None = None,
    resume: bool = False,
    extend_attempt_ids: tuple[str, ...] = (),
    continue_after_failed: bool = False,
) -> None:
    selected = (
        select_first_five_attempts()
        if selected_attempts is None
        else selected_attempts
    )
    summary = {
        "operation": "local-r5-preregistered-batch",
        "execution_card_id": card_id,
        "attempt_ids": [item.attempt_id for item in selected],
        "append_attempt_ids_after_confirmation": list(extend_attempt_ids),
        "repository": f"{PINNED_OWNER}/{PINNED_REPOSITORY}",
        "commit": PINNED_COMMIT,
        "tree": snapshot_tree_oid,
        "snapshot_content_digest": snapshot_content_digest,
        "snapshot_origin": snapshot_origin,
        "model": {
            "version": model.version,
            "name": model.model,
            "digest": model.model_digest,
            "model_count": model.model_count,
        },
        "target_image_id": TARGET_RUNTIME_IMAGE_ID,
        "verifier_image_id": VERIFIER_RUNTIME_IMAGE_ID,
        "verifier_code_digest": VERIFIER_RUNTIME_CODE_DIGEST,
        "new_local_databases": 0 if resume else 3,
        "resume_existing_stores": resume,
        "continue_after_failed": continue_after_failed,
        "batch_deadline_seconds_after_confirmation": MAX_R5_BATCH_SECONDS,
        "available_disk_bytes": available_bytes,
        "limits": {
            "model_requests_max": len(selected),
            "retry_or_replacement": False,
            "provider_write": False,
        },
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")), file=output)


def _print_result(
    output: TextIO,
    result: R5BatchResult,
    *,
    deadline_expired: bool = False,
    selected_attempts: tuple[R5SelectedAttempt, ...] | None = None,
) -> None:
    from scripts.run_r5_preregistered_batch import R5BatchRecord

    selected = (
        select_first_five_attempts()
        if selected_attempts is None
        else selected_attempts
    )
    expected_ids = tuple(item.attempt_id for item in selected)
    if (
        type(result.status) is not str
        or result.status not in {
            "complete", "complete-with-failures", "stopped-failed",
            "stopped-unknown", "stopped-preflight"
        }
        or type(result.records) is not tuple
        or len(result.records) > len(expected_ids)
        or type(deadline_expired) is not bool
        or (
            result.status in {"complete", "complete-with-failures"}
            and len(result.records) != len(expected_ids)
        )
    ):
        raise R5BatchCLIError("R5 batch: result rejected")
    safe_attempts = []
    seen: set[str] = set()
    for index, record in enumerate(result.records):
        if (
            type(record) is not R5BatchRecord
            or record.attempt_id != expected_ids[index]
            or record.attempt_id in seen
            or record.state not in {"PENDING", "CLAIMED", "COMPLETED", "UNKNOWN"}
            or type(record.input_digest) is not str
            or _IMAGE_DIGEST.fullmatch(record.input_digest) is None
            or (
                record.result_digest is not None
                and (
                    type(record.result_digest) is not str
                    or _IMAGE_DIGEST.fullmatch(record.result_digest) is None
                )
            )
            or record.outcome not in {
                None, "verified", "failed", "needs_input", "blocked", "denied"
            }
            or record.reason_code not in {
                None, "none", "execution-failed", "worker-clarification",
                "worker-blocked", "worker-denied", "worker-error", "pipeline-error",
                "interrupted", "result-unavailable",
            } | R5_EXECUTION_FAILURE_REASONS | R5_UNKNOWN_PHASE_CODES
            or (
                record.state == "COMPLETED"
                and (
                    record.result_digest is None
                    or record.outcome is None
                    or record.reason_code is None
                )
            )
            or (
                record.state != "COMPLETED"
                and (
                    record.result_digest is not None
                    or record.outcome is not None
                )
            )
        ):
            raise R5BatchCLIError("R5 batch: result rejected")
        seen.add(record.attempt_id)
        safe_attempts.append(
            {
                "attempt_id": record.attempt_id,
                "state": record.state,
                "input_digest": record.input_digest,
                "result_digest": record.result_digest,
                "outcome": record.outcome,
                "reason_code": record.reason_code,
            }
        )
    contains_failure = any(item["outcome"] == "failed" for item in safe_attempts)
    if result.status in {"complete", "complete-with-failures"} and (
        (result.status == "complete-with-failures") != contains_failure
    ):
        raise R5BatchCLIError("R5 batch: result rejected")
    report = {
        "status": result.status,
        "deadline_expired": deadline_expired,
        "batch_deadline_seconds": MAX_R5_BATCH_SECONDS,
        "attempts": safe_attempts,
        "limitations": [
            "same-host Docker verifier and host/kernel are trusted",
            "GitHub REST snapshot is an API claim; commit bytes are hash-checked",
            "no approval or external publication is performed",
        ],
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")), file=output)


def main() -> int:
    return run_r5_batch_cli()


def _validate_snapshot(snapshot: object) -> None:
    from app_contracts.brainbooster_target_profile import (
        PINNED_CONTENT_DIGEST,
        PINNED_FILE_COUNT,
        PINNED_TREE,
    )

    try:
        if type(snapshot) is not GitHubSnapshotContents:
            raise ValueError
        claim = snapshot.claim
        proof = snapshot.verified_commit_object
        if (
            claim.owner != PINNED_OWNER
            or claim.repository != PINNED_REPOSITORY
            or claim.commit_oid != PINNED_COMMIT
            or claim.tree_oid != PINNED_TREE
            or claim.content_digest != PINNED_CONTENT_DIGEST
            or claim.evidence_origin != "github_codeload_archive"
            or not claim.full_snapshot
            or len(snapshot.files) != PINNED_FILE_COUNT
            or type(proof) is not GitCommitObject
            or proof.commit_oid != PINNED_COMMIT
            or proof.tree_oid != PINNED_TREE
        ):
            raise ValueError
    except Exception:
        raise R5BatchCLIError("R5 batch: pinned snapshot rejected") from None


if __name__ == "__main__":
    raise SystemExit(main())
