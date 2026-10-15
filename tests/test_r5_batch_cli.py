from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from app_contracts.brainbooster_target_profile import (
    PINNED_COMMIT,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
    PINNED_CONTENT_DIGEST,
    PINNED_FILE_COUNT,
    TARGET_RUNTIME_IMAGE_ID,
)
from app_contracts.verifier_image_pin import (
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.github_snapshot import GitCommitObject
from app_contracts.local_ollama_channel import LOCAL_OLLAMA_MODEL
from app_contracts.r5_local_model_preflight import (
    EXPECTED_OLLAMA_VERSION,
    R5LocalModelMetadata,
)
from scripts import run_r5_batch_cli as cli_module
from scripts.run_r5_batch_cli import (
    R5BatchCLIError,
    _Dependencies,
    R5OutputPaths,
    _print_result,
    _validate_absent_path,
    _validate_snapshot,
    _open_stores,
    run_r5_batch_cli,
)
from scripts.run_r5_preregistered_batch import R5BatchRecord, R5BatchResult
from scripts.r5_batch_selection import select_r5_attempts
from app_contracts.r5_attempt_ledger import SQLiteR5AttemptLedger


MODEL_DIGEST = "a" * 64
CARD_ID = "EXP-1070"


class _Stores:
    def __init__(self):
        self.ledger = object()
        self.stage = SimpleNamespace(save=lambda _artifact: None, load=lambda _digest: None)
        self.observer = object()
        self.preserved = False
        self.closed = False

    def preserve(self):
        self.preserved = True

    def close(self):
        self.closed = True


def _snapshot():
    claim = SimpleNamespace(
        owner=PINNED_OWNER,
        repository=PINNED_REPOSITORY,
        commit_oid=PINNED_COMMIT,
        tree_oid=PINNED_TREE,
        content_digest=PINNED_CONTENT_DIGEST,
        evidence_origin="github_codeload_archive",
        full_snapshot=True,
    )
    snapshot = object.__new__(cli_module.GitHubSnapshotContents)
    object.__setattr__(snapshot, "claim", claim)
    object.__setattr__(snapshot, "files", tuple(object() for _ in range(PINNED_FILE_COUNT)))
    object.__setattr__(
        snapshot,
        "verified_commit_object",
        GitCommitObject(PINNED_COMMIT, PINNED_TREE),
    )
    return snapshot


class _Preflight:
    def __init__(self, events, *, fail=False, model=None):
        self.events = events
        self.fail = fail
        self.model = model or R5LocalModelMetadata(
            EXPECTED_OLLAMA_VERSION, LOCAL_OLLAMA_MODEL, MODEL_DIGEST, 1
        )

    def inspect(self, *, expected_model_digest):
        self.events.append(("model", expected_model_digest))
        if self.fail:
            raise RuntimeError("must not be exposed")
        return self.model


class R5BatchCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.paths = (
            root / "ledger.sqlite3",
            root / "stage.sqlite3",
            root / "observer.sqlite3",
        )
        self.events = []
        self.stores = _Stores()
        self.dependencies = self._dependencies()

    def _dependencies(self, *, failure=None):
        events = self.events

        def snapshot_loader(**_kwargs):
            events.append("snapshot")
            if failure == "snapshot":
                raise RuntimeError("secret-payload-must-not-leak")
            return _snapshot()

        def preflight_factory():
            return _Preflight(events, fail=failure == "model")

        def image_inspect(_docker, image):
            events.append(("image", image))
            if failure == "image":
                raise RuntimeError("local path details must not leak")

        def open_stores(_paths, **_kwargs):
            events.append("open-stores")
            if failure == "stores":
                raise RuntimeError
            return self.stores

        def build_adapters(*, docker_executable, stage_store, observation_store, selected_attempts):
            events.append("adapters")
            self.assertEqual(docker_executable, "/fake/docker")
            self.assertEqual(tuple(item.attempt_id for item in selected_attempts),
                             ("R5-001", "R5-002", "R5-003", "R5-004", "R5-005"))
            return SimpleNamespace(
                worker_factory=lambda _attempt: object(),
                verifier=SimpleNamespace(verify=lambda _value: None),
                sandbox_backend=SimpleNamespace(create=lambda *_args: None),
                stage_sink=stage_store,
                observation_store=observation_store,
            )

        def runner(*_args, **_kwargs):
            events.append("runner")
            return R5BatchResult(
                "complete",
                tuple(
                    R5BatchRecord(
                        attempt_id,
                        "COMPLETED",
                        "sha256:" + f"{index:064x}",
                        "sha256:" + f"{index + 5:064x}",
                        "verified",
                        "none",
                    )
                    for index, attempt_id in enumerate(
                        ("R5-001", "R5-002", "R5-003", "R5-004", "R5-005"),
                        start=1,
                    )
                ),
            )

        return _Dependencies(
            disk_usage=lambda path: events.append("disk")
            or SimpleNamespace(free=1024 * 1024 * 1024),
            transport_factory=lambda: events.append("transport") or object(),
            commit_source_factory=lambda git: events.append(("commit-source", git)) or object(),
            snapshot_loader=snapshot_loader,
            model_preflight_factory=preflight_factory,
            docker_discover=lambda: "/fake/docker",
            git_discover=lambda: "/fake/git",
            docker_inspect=image_inspect,
            open_stores=open_stores,
            adapter_builder=build_adapters,
            batch_runner=runner,
        )

    def _args(self):
        ledger, stage, observer = self.paths
        return [
            "--ledger-db", str(ledger),
            "--stage-db", str(stage),
            "--observer-db", str(observer),
            "--model-digest", MODEL_DIGEST,
            "--execution-card-id", CARD_ID,
        ]

    def test_orders_all_preflight_before_stores_then_gate_then_dispatch(self):
        output, errors = StringIO(), StringIO()

        def confirm(prompt):
            self.events.append(("gate", prompt))
            return f"RUN {CARD_ID} ONCE"

        result = run_r5_batch_cli(
            self._args(),
            input_fn=confirm,
            stdout=output,
            stderr=errors,
            interactive=lambda: True,
            dependencies=self.dependencies,
        )

        self.assertEqual(result, 0, errors.getvalue() + repr(self.events))
        self.assertEqual(
            self.events,
            [
                "disk",
                "transport",
                ("commit-source", "/fake/git"),
                "snapshot",
                ("model", MODEL_DIGEST),
                ("image", TARGET_RUNTIME_IMAGE_ID),
                ("image", VERIFIER_RUNTIME_IMAGE_ID),
                "open-stores",
                ("gate", f"Type RUN {CARD_ID} ONCE to continue: "),
                "adapters",
                "runner",
            ],
        )
        lines = output.getvalue().splitlines()
        summary = json.loads(lines[0])
        report = json.loads(lines[1])
        self.assertEqual(summary["attempt_ids"], ["R5-001", "R5-002", "R5-003", "R5-004", "R5-005"])
        self.assertEqual(summary["limits"]["model_requests_max"], 5)
        self.assertEqual(summary["new_local_databases"], 3)
        self.assertEqual(summary["available_disk_bytes"], 1024 * 1024 * 1024)
        self.assertEqual(summary["snapshot_origin"], "github_codeload_archive")
        self.assertEqual(summary["tree"], PINNED_TREE)
        self.assertEqual(summary["snapshot_content_digest"], PINNED_CONTENT_DIGEST)
        self.assertEqual(summary["target_image_id"], TARGET_RUNTIME_IMAGE_ID)
        self.assertEqual(summary["verifier_code_digest"], VERIFIER_RUNTIME_CODE_DIGEST)
        self.assertEqual(report["attempts"][0]["outcome"], "verified")
        self.assertTrue(self.stores.preserved)
        self.assertTrue(self.stores.closed)
        self.assertEqual(errors.getvalue(), "")

    def test_wrong_gate_never_dispatches_and_cleans_new_stores(self):
        output, errors = StringIO(), StringIO()
        result = run_r5_batch_cli(
            self._args(),
            input_fn=lambda _prompt: f"RUN {CARD_ID} twice",
            stdout=output,
            stderr=errors,
            interactive=lambda: True,
            dependencies=self.dependencies,
        )
        self.assertEqual(result, 2)
        self.assertNotIn("runner", self.events)
        self.assertFalse(self.stores.preserved)
        self.assertTrue(self.stores.closed)
        self.assertIn("confirmation did not match", errors.getvalue())

    def test_preflight_failure_does_not_open_local_stores(self):
        for failure in ("snapshot", "model", "image"):
            with self.subTest(failure=failure):
                self.events.clear()
                self.stores = _Stores()
                deps = self._dependencies(failure=failure)
                result = run_r5_batch_cli(
                    self._args(),
                    input_fn=lambda _prompt: f"RUN {CARD_ID} ONCE",
                    stdout=StringIO(),
                    stderr=(error := StringIO()),
                    interactive=lambda: True,
                    dependencies=deps,
                )
                self.assertEqual(result, 2)
                self.assertNotIn("open-stores", self.events)
                self.assertNotIn("runner", self.events)
                self.assertNotIn("secret-payload", error.getvalue())

    def test_low_disk_headroom_stops_before_any_external_preflight(self):
        deps = self._dependencies()
        deps = _Dependencies(
            **{
                **deps.__dict__,
                "disk_usage": lambda _path: SimpleNamespace(free=1),
            }
        )
        result = run_r5_batch_cli(
            self._args(),
            stdout=StringIO(),
            stderr=(errors := StringIO()),
            interactive=lambda: True,
            dependencies=deps,
        )
        self.assertEqual(result, 2)
        self.assertEqual(self.events, [])
        self.assertIn("disk headroom unavailable", errors.getvalue())
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_requires_interactive_exact_gate_and_valid_card_id(self):
        output, errors = StringIO(), StringIO()
        result = run_r5_batch_cli(
            self._args(),
            input_fn=lambda _prompt: self.fail("must not prompt outside a TTY"),
            stdout=output,
            stderr=errors,
            interactive=lambda: False,
            dependencies=self.dependencies,
        )
        self.assertEqual(result, 2)
        self.assertNotIn("runner", self.events)
        self.assertIn("interactive confirmation required", errors.getvalue())

        self.events.clear()
        args = self._args()
        args[-1] = "not-an-experiment"
        self.assertEqual(
            run_r5_batch_cli(
                args,
                stdout=StringIO(),
                stderr=(error := StringIO()),
                interactive=lambda: True,
                dependencies=self.dependencies,
            ),
            2,
        )
        self.assertEqual(self.events, [])
        self.assertNotIn("not-an-experiment", error.getvalue())

    def test_rejects_occupied_relative_duplicate_and_symlink_paths(self):
        with self.assertRaises(R5BatchCLIError):
            _validate_absent_path("relative.sqlite3")
        occupied = self.paths[0]
        occupied.write_bytes(b"occupied")
        with self.assertRaises(R5BatchCLIError):
            _validate_absent_path(str(occupied))

        target = self.paths[0].with_name("target")
        target.write_bytes(b"target")
        link = self.paths[0].with_name("link")
        link.symlink_to(target)
        with self.assertRaises(R5BatchCLIError):
            _validate_absent_path(str(link))

        args = self._args()
        args[3] = args[1]
        self.events.clear()
        result = run_r5_batch_cli(
            args,
            stdout=StringIO(),
            stderr=StringIO(),
            dependencies=self.dependencies,
        )
        self.assertEqual(result, 2)
        self.assertEqual(self.events, [])

    def test_rejects_bad_snapshot_and_bad_runtime_metadata_before_open(self):
        bad_snapshot = _snapshot()
        object.__setattr__(bad_snapshot, "claim", SimpleNamespace(owner="other"))
        with self.assertRaises(R5BatchCLIError):
            _validate_snapshot(bad_snapshot)

        self.events.clear()
        deps = self._dependencies()
        deps = _Dependencies(
            **{
                **deps.__dict__,
                "model_preflight_factory": lambda: _Preflight(
                    self.events,
                    model=R5LocalModelMetadata("wrong", LOCAL_OLLAMA_MODEL, MODEL_DIGEST, 1),
                ),
            }
        )
        result = run_r5_batch_cli(
            self._args(),
            stdout=StringIO(),
            stderr=StringIO(),
            dependencies=deps,
        )
        self.assertEqual(result, 2)
        self.assertNotIn("open-stores", self.events)

    def test_result_renderer_rejects_unbounded_or_payload_bearing_values(self):
        output = StringIO()
        bad = R5BatchResult(
            "complete",
            (
                R5BatchRecord(
                    "R5-001", "COMPLETED", "secret-payload", None, "verified", "none"
                ),
            ),
        )
        with self.assertRaises(R5BatchCLIError):
            _print_result(output, bad)
        self.assertEqual(output.getvalue(), "")

    def test_result_renderer_labels_a_fully_dispatched_failed_sample(self):
        output = StringIO()
        selected = select_r5_attempts(("R5-001",))
        result = R5BatchResult(
            "complete-with-failures",
            (
                R5BatchRecord(
                    "R5-001",
                    "COMPLETED",
                    selected[0].input_digest,
                    "sha256:" + "b" * 64,
                    "failed",
                    "target-test-sqlite-range-status",
                ),
            ),
        )

        _print_result(output, result, selected_attempts=selected)

        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "complete-with-failures")
        self.assertEqual(
            report["attempts"][0]["reason_code"], "target-test-sqlite-range-status"
        )

    def test_result_renderer_accepts_only_fixed_unknown_phase_codes(self):
        selected = select_r5_attempts(("R5-001",))
        for reason_code in (
            "pipeline-error",
            "input-validation-error",
            "executor-uncaught-error",
            "result-validation-error",
            "executor-request-rejected",
            "executor-worker-rejected",
            "executor-sandbox-rejected",
            "executor-snapshot-rejected",
            "executor-preparation-rejected",
            "executor-verifier-rejected",
            "executor-stage-rejected",
            "executor-marker-unmapped",
            "executor-value-error",
            "executor-type-error",
            "executor-os-error",
            "executor-runtime-error",
            "executor-key-error",
            "executor-attribute-error",
            "executor-workspace-error",
            "executor-contract-invalid",
            "executor-test-result-malformed",
        ):
            with self.subTest(reason_code=reason_code):
                output = StringIO()
                result = R5BatchResult(
                    "stopped-unknown",
                    (
                        R5BatchRecord(
                            "R5-001", "UNKNOWN", selected[0].input_digest,
                            None, None, reason_code,
                        ),
                    ),
                )

                _print_result(output, result, selected_attempts=selected)

                report = json.loads(output.getvalue())
                self.assertEqual(
                    report["attempts"][0]["reason_code"], reason_code
                )
                self.assertEqual(report["attempts"][0]["state"], "UNKNOWN")

        output = StringIO()
        invalid = R5BatchResult(
            "stopped-unknown",
            (
                R5BatchRecord(
                    "R5-001", "UNKNOWN", selected[0].input_digest,
                    None, None, "private exception text",
                ),
            ),
        )
        with self.assertRaises(R5BatchCLIError):
            _print_result(output, invalid, selected_attempts=selected)
        self.assertEqual(output.getvalue(), "")

    def test_continue_after_failed_requires_resume_and_explicit_attempt_ids(self):
        for extra_args in (
            ["--continue-after-failed"],
            ["--resume-existing-stores", "--continue-after-failed"],
        ):
            with self.subTest(extra_args=extra_args):
                output, errors = StringIO(), StringIO()
                result = run_r5_batch_cli(
                    self._args() + extra_args,
                    stdout=output,
                    stderr=errors,
                    interactive=lambda: True,
                    dependencies=self.dependencies,
                )
                self.assertEqual(result, 2)
                self.assertEqual(output.getvalue(), "")
                self.assertIn("request paths or pins rejected", errors.getvalue())
                self.assertEqual(self.events, [])

    def test_resume_reopens_existing_stores_read_only_until_activation(self):
        paths = R5OutputPaths(*self.paths)
        initial = _open_stores(paths)
        initial.ledger.claim("R5-001", "sha256:" + "a" * 64)
        initial.ledger.mark_unknown("R5-001", reason_code="pipeline-error")
        initial.preserve()
        initial.close()
        before = tuple(path.read_bytes() for path in self.paths)

        resumed = _open_stores(
            paths,
            resume_existing=True,
            selected_attempts=select_r5_attempts(("R5-002", "R5-003")),
        )
        self.assertEqual(tuple(path.read_bytes() for path in self.paths), before)
        self.assertEqual(resumed.ledger.get("R5-001").state, "UNKNOWN")
        self.assertEqual(resumed.ledger.get("R5-002").state, "PENDING")
        self.assertTrue(resumed.stage._read_only)
        resumed.activate()
        self.assertFalse(resumed.stage._read_only)
        resumed.close()
        self.assertTrue(all(path.is_file() for path in self.paths))
        reopened = SQLiteR5AttemptLedger.open_existing(paths.ledger)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get("R5-001").state, "UNKNOWN")

    def test_resume_extension_is_read_only_until_activation_and_appends_next_range(self):
        paths = R5OutputPaths(*self.paths)
        initial = _open_stores(paths)
        initial.ledger.claim("R5-001", "sha256:" + "a" * 64)
        initial.ledger.mark_unknown("R5-001", reason_code="pipeline-error")
        initial.preserve()
        initial.close()
        before = tuple(path.read_bytes() for path in self.paths)
        selected = select_r5_attempts(
            ("R5-006", "R5-007", "R5-008", "R5-009", "R5-010")
        )

        resumed = _open_stores(
            paths,
            resume_existing=True,
            selected_attempts=selected,
            allow_extension=True,
        )
        self.assertEqual(
            resumed.pending_extension_ids,
            ("R5-006", "R5-007", "R5-008", "R5-009", "R5-010"),
        )
        self.assertEqual(tuple(path.read_bytes() for path in self.paths), before)
        self.assertEqual(
            {record.attempt_id for record in resumed.ledger.records()},
            {f"R5-{number:03d}" for number in range(1, 6)},
        )

        resumed.activate()
        self.assertEqual(resumed.pending_extension_ids, ())
        for attempt_id in ("R5-006", "R5-007", "R5-008", "R5-009", "R5-010"):
            self.assertEqual(resumed.ledger.get(attempt_id).state, "PENDING")
        self.assertEqual(resumed.ledger.get("R5-001").state, "UNKNOWN")
        resumed.close()

    def test_resume_extension_appends_only_new_suffix_after_existing_pending_ids(self):
        paths = R5OutputPaths(*self.paths)
        initial = _open_stores(paths)
        initial.preserve()
        initial.close()

        first_extension = _open_stores(
            paths,
            resume_existing=True,
            selected_attempts=select_r5_attempts(
                ("R5-006", "R5-007", "R5-008", "R5-009", "R5-010")
            ),
            allow_extension=True,
        )
        first_extension.activate()
        first_extension.ledger.claim(
            "R5-006", select_r5_attempts(("R5-006",))[0].input_digest
        )
        first_extension.ledger.complete(
            "R5-006",
            result_digest="sha256:" + "c" * 64,
            outcome="failed",
            reason_code="execution-failed",
        )
        first_extension.preserve()
        first_extension.close()

        selected = select_r5_attempts(
            ("R5-007", "R5-008", "R5-009", "R5-010", "R5-011")
        )
        before = tuple(path.read_bytes() for path in self.paths)
        resumed = _open_stores(
            paths,
            resume_existing=True,
            selected_attempts=selected,
            allow_extension=True,
        )
        self.assertEqual(resumed.pending_extension_ids, ("R5-011",))
        self.assertEqual(tuple(path.read_bytes() for path in self.paths), before)
        self.assertEqual(resumed.ledger.get("R5-006").outcome, "failed")
        self.assertTrue(
            all(resumed.ledger.get(f"R5-{number:03d}").state == "PENDING"
                for number in range(7, 11))
        )
        resumed.activate()
        self.assertEqual(resumed.ledger.get("R5-011").state, "PENDING")
        resumed.close()

    def test_resume_extension_rejects_gaps_before_gate_without_mutation(self):
        paths = R5OutputPaths(*self.paths)
        initial = _open_stores(paths)
        initial.preserve()
        initial.close()
        before = tuple(path.read_bytes() for path in self.paths)
        with self.assertRaises(R5BatchCLIError):
            _open_stores(
                paths,
                resume_existing=True,
                selected_attempts=select_r5_attempts(("R5-006", "R5-008")),
                allow_extension=True,
            )
        with self.assertRaises(R5BatchCLIError):
            _open_stores(
                paths,
                resume_existing=True,
                selected_attempts=select_r5_attempts(("R5-006",)),
                allow_extension=False,
            )
        self.assertEqual(tuple(path.read_bytes() for path in self.paths), before)

    def test_resume_rejects_missing_path_and_sidecar_without_mutation(self):
        paths = R5OutputPaths(*self.paths)
        created = _open_stores(paths)
        created.preserve()
        created.close()
        self.paths[2].unlink()
        with self.assertRaises(R5BatchCLIError):
            cli_module._validate_resume_paths(paths)

    def test_resume_rejects_malformed_observer_and_sidecar(self):
        paths = R5OutputPaths(*self.paths)
        created = _open_stores(paths)
        created.preserve()
        created.close()
        self.paths[2].write_bytes(b"not a database")
        sidecar = Path(f"{self.paths[1]}-wal")
        sidecar.write_bytes(b"unexpected")
        with self.assertRaises(R5BatchCLIError):
            cli_module._validate_resume_paths(paths)

    def test_resume_cli_binds_selected_pending_ids_to_exact_one_shot_gate(self):
        paths = R5OutputPaths(*self.paths)
        initial = _open_stores(paths)
        initial.ledger.claim("R5-001", "sha256:" + "a" * 64)
        initial.ledger.mark_unknown("R5-001", reason_code="pipeline-error")
        initial.preserve()
        initial.close()
        self.events.clear()
        args = self._args() + [
            "--resume-existing-stores", "--attempt-ids", "R5-002,R5-003",
            "--continue-after-failed",
        ]

        def open_stores(requested_paths, **kwargs):
            self.events.append("open-resume-stores")
            return _open_stores(requested_paths, **kwargs)

        def build_adapters(*, docker_executable, stage_store, observation_store, selected_attempts):
            self.events.append(("adapters", tuple(item.attempt_id for item in selected_attempts)))
            return SimpleNamespace(
                worker_factory=lambda attempt: self.fail("runner not expected to dispatch"),
                verifier=SimpleNamespace(verify=lambda _value: None),
                sandbox_backend=SimpleNamespace(create=lambda *_args: None),
                stage_sink=stage_store,
                observation_store=observation_store,
            )

        def runner(
            _snapshot, ledger, *, selected_attempts, continue_after_failed, **_kwargs
        ):
            self.events.append(("runner", tuple(item.attempt_id for item in selected_attempts)))
            self.assertEqual(ledger.get("R5-001").state, "UNKNOWN")
            self.assertTrue(continue_after_failed)
            return R5BatchResult(
                "complete",
                tuple(
                    R5BatchRecord(
                        item.attempt_id, "COMPLETED", item.input_digest,
                        "sha256:" + "b" * 64, "verified", "none",
                    )
                    for item in selected_attempts
                ),
            )

        deps = _Dependencies(
            **{
                **self.dependencies.__dict__,
                "open_stores": open_stores,
                "adapter_builder": build_adapters,
                "batch_runner": runner,
            }
        )
        output, errors = StringIO(), StringIO()
        result = run_r5_batch_cli(
            args,
            input_fn=lambda prompt: self.events.append(("gate", prompt))
            or "RUN EXP-1070 ONCE",
            stdout=output,
            stderr=errors,
            interactive=lambda: True,
            dependencies=deps,
        )
        self.assertEqual(result, 0, errors.getvalue())
        summary = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(summary["attempt_ids"], ["R5-002", "R5-003"])
        self.assertEqual(summary["limits"]["model_requests_max"], 2)
        self.assertTrue(summary["resume_existing_stores"])
        self.assertTrue(summary["continue_after_failed"])
        self.assertEqual(summary["new_local_databases"], 0)
        self.assertEqual(
            self.events[-3:],
            [
                ("gate", "Type RUN EXP-1070 ONCE to continue: "),
                ("adapters", ("R5-002", "R5-003")),
                ("runner", ("R5-002", "R5-003")),
            ],
        )
        reopened = SQLiteR5AttemptLedger.open_existing(paths.ledger)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get("R5-001").state, "UNKNOWN")

    def test_resume_cli_refuses_unknown_selected_id_before_gate_and_worker(self):
        paths = R5OutputPaths(*self.paths)
        initial = _open_stores(paths)
        initial.ledger.claim("R5-001", "sha256:" + "a" * 64)
        initial.ledger.mark_unknown("R5-001", reason_code="pipeline-error")
        initial.preserve()
        initial.close()
        before = tuple(path.read_bytes() for path in self.paths)
        args = self._args() + [
            "--resume-existing-stores", "--attempt-ids", "R5-001"
        ]
        deps = _Dependencies(
            **{
                **self.dependencies.__dict__,
                "open_stores": _open_stores,
            }
        )
        output, errors = StringIO(), StringIO()
        result = run_r5_batch_cli(
            args,
            input_fn=lambda _prompt: self.fail("must reject before confirmation"),
            stdout=output,
            stderr=errors,
            interactive=lambda: True,
            dependencies=deps,
        )
        self.assertEqual(result, 2)
        self.assertIn("selected attempt is not pending", errors.getvalue())
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("runner", self.events)
        self.assertEqual(tuple(path.read_bytes() for path in self.paths), before)

    def test_wrong_extension_gate_leaves_all_existing_store_bytes_unchanged(self):
        paths = R5OutputPaths(*self.paths)
        initial = _open_stores(paths)
        initial.preserve()
        initial.close()
        before = tuple(path.read_bytes() for path in self.paths)
        selected_ids = ("R5-006", "R5-007", "R5-008", "R5-009", "R5-010")
        args = self._args() + [
            "--resume-existing-stores",
            "--attempt-ids",
            ",".join(selected_ids),
            "--extend-allowed-attempts",
        ]
        deps = _Dependencies(
            **{
                **self.dependencies.__dict__,
                "open_stores": _open_stores,
                "adapter_builder": lambda **_kwargs: self.fail("must not build adapters"),
                "batch_runner": lambda *_args, **_kwargs: self.fail("must not run batch"),
            }
        )
        output, errors = StringIO(), StringIO()
        result = run_r5_batch_cli(
            args,
            input_fn=lambda _prompt: "RUN EXP-1070 twice",
            stdout=output,
            stderr=errors,
            interactive=lambda: True,
            dependencies=deps,
        )
        self.assertEqual(result, 2)
        self.assertIn("one-shot confirmation did not match", errors.getvalue())
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(tuple(path.read_bytes() for path in self.paths), before)

    def test_cli_extends_after_gate_then_stops_after_first_failed_new_id(self):
        paths = R5OutputPaths(*self.paths)
        initial = _open_stores(paths)
        initial.preserve()
        initial.close()
        selected_ids = ("R5-006", "R5-007", "R5-008", "R5-009", "R5-010")
        selected = select_r5_attempts(selected_ids)
        args = self._args() + [
            "--resume-existing-stores",
            "--attempt-ids",
            ",".join(selected_ids),
            "--extend-allowed-attempts",
        ]
        opened = []
        events = self.events
        events.clear()

        def open_stores(requested_paths, **kwargs):
            events.append("open-stores")
            stores = _open_stores(requested_paths, **kwargs)
            opened.append(stores)
            return stores

        def build_adapters(*, docker_executable, stage_store, observation_store, selected_attempts):
            events.append("adapters")
            self.assertEqual(
                tuple(item.attempt_id for item in selected_attempts), selected_ids
            )
            return SimpleNamespace(
                worker_factory=lambda _attempt: self.fail("fake runner must not dispatch"),
                verifier=SimpleNamespace(verify=lambda _value: None),
                sandbox_backend=SimpleNamespace(create=lambda *_args: None),
                stage_sink=stage_store,
                observation_store=observation_store,
            )

        def runner(_snapshot, ledger, *, selected_attempts, **_kwargs):
            events.append("runner")
            self.assertEqual(tuple(item.attempt_id for item in selected_attempts), selected_ids)
            self.assertEqual(ledger.get("R5-006").state, "PENDING")
            self.assertTrue(
                all(ledger.get(attempt_id).state == "PENDING" for attempt_id in selected_ids[1:])
            )
            first = selected_attempts[0]
            result_digest = "sha256:" + "f" * 64
            ledger.claim(first.attempt_id, first.input_digest)
            ledger.complete(
                first.attempt_id,
                result_digest=result_digest,
                outcome="failed",
                reason_code="execution-failed",
            )
            self.assertTrue(
                all(ledger.get(attempt_id).state == "PENDING" for attempt_id in selected_ids[1:])
            )
            return R5BatchResult(
                "stopped-failed",
                (
                    R5BatchRecord(
                        first.attempt_id,
                        "COMPLETED",
                        first.input_digest,
                        result_digest,
                        "failed",
                        "execution-failed",
                    ),
                ),
            )

        dependencies = _Dependencies(
            **{
                **self.dependencies.__dict__,
                "open_stores": open_stores,
                "adapter_builder": build_adapters,
                "batch_runner": runner,
            }
        )
        output, errors = StringIO(), StringIO()

        def confirm(prompt):
            events.append(("gate", prompt))
            self.assertEqual(opened[0].pending_extension_ids, selected_ids)
            self.assertNotIn(
                "R5-006", {record.attempt_id for record in opened[0].ledger.records()}
            )
            summary = json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(summary["attempt_ids"], list(selected_ids))
            self.assertEqual(
                summary["append_attempt_ids_after_confirmation"], list(selected_ids)
            )
            return f"RUN {CARD_ID} ONCE"

        result = run_r5_batch_cli(
            args,
            input_fn=confirm,
            stdout=output,
            stderr=errors,
            interactive=lambda: True,
            dependencies=dependencies,
        )
        self.assertEqual(result, 2, errors.getvalue())
        self.assertEqual(events[-3:], [("gate", f"Type RUN {CARD_ID} ONCE to continue: "), "adapters", "runner"])
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        report = json.loads(lines[1])
        self.assertEqual(report["status"], "stopped-failed")
        self.assertEqual([row["attempt_id"] for row in report["attempts"]], ["R5-006"])
        reopened = SQLiteR5AttemptLedger.open_existing(paths.ledger)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get("R5-006").outcome, "failed")
        for attempt_id in selected_ids[1:]:
            self.assertEqual(reopened.get(attempt_id).state, "PENDING")

        before_replay = tuple(path.read_bytes() for path in self.paths)
        events.clear()
        replay_output, replay_errors = StringIO(), StringIO()
        replay_result = run_r5_batch_cli(
            args[:-1],
            input_fn=lambda _prompt: self.fail("terminal R5-006 must stop before gate"),
            stdout=replay_output,
            stderr=replay_errors,
            interactive=lambda: True,
            dependencies=dependencies,
        )
        self.assertEqual(replay_result, 2)
        self.assertIn("selected attempt is not pending", replay_errors.getvalue())
        self.assertEqual(replay_output.getvalue(), "")
        self.assertNotIn("adapters", events)
        self.assertNotIn("runner", events)
        self.assertEqual(tuple(path.read_bytes() for path in self.paths), before_replay)


if __name__ == "__main__":
    unittest.main()
