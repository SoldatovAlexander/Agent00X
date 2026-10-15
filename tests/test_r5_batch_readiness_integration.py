from __future__ import annotations

from io import StringIO
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_r5_batch_cli as cli_module
from scripts.run_r5_batch_cli import _Dependencies, run_r5_batch_cli
from scripts.run_r5_preregistered_batch import R5BatchResult


def _cli_fixture_type():
    from tests.test_r5_batch_cli import R5BatchCLITests

    return R5BatchCLITests


class R5BatchReadinessIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = _cli_fixture_type()()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.doCleanups()

    def _dependencies(self, *, disk_free=1024 * 1024 * 1024):
        base = self.fixture._dependencies()
        events = self.fixture.events

        def build_adapters(**kwargs):
            adapters = base.adapter_builder(**kwargs)
            return SimpleNamespace(
                worker_factory=lambda attempt: events.append(("worker", attempt))
                or adapters.worker_factory(attempt),
                verifier=adapters.verifier,
                sandbox_backend=adapters.sandbox_backend,
                stage_sink=adapters.stage_sink,
                observation_store=adapters.observation_store,
            )

        def runner(_snapshot, _ledger, **kwargs):
            events.append("runner")
            kwargs["worker_factory"]("R5-001")
            return R5BatchResult("stopped-preflight", ())

        return _Dependencies(
            **{
                **base.__dict__,
                "disk_usage": lambda _path: events.append("disk")
                or SimpleNamespace(free=disk_free),
                "adapter_builder": build_adapters,
                "batch_runner": runner,
            }
        )

    def _invoke(self, dependencies, confirmation="RUN EXP-1070 ONCE"):
        return run_r5_batch_cli(
            self.fixture._args(),
            input_fn=lambda prompt: self.fixture.events.append(("gate", prompt))
            or confirmation,
            stdout=(output := StringIO()),
            stderr=(errors := StringIO()),
            interactive=lambda: True,
            dependencies=dependencies,
        ), output, errors

    def test_all_readiness_gates_precede_stores_and_worker_dispatch(self):
        dependencies = self._dependencies()
        result, output, errors = self._invoke(dependencies)
        self.assertEqual(result, 2, errors.getvalue())
        self.assertEqual(
            self.fixture.events,
            [
                "disk", "transport", ("commit-source", "/fake/git"), "snapshot",
                ("model", "a" * 64), ("image", cli_module.TARGET_RUNTIME_IMAGE_ID),
                ("image", cli_module.VERIFIER_RUNTIME_IMAGE_ID), "open-stores",
                ("gate", "Type RUN EXP-1070 ONCE to continue: "), "adapters",
                "runner", ("worker", "R5-001"),
            ],
        )
        self.assertTrue(self.fixture.stores.preserved)
        self.assertTrue(self.fixture.stores.closed)
        self.assertIn('"available_disk_bytes":1073741824', output.getvalue())

    def test_each_preflight_failure_stops_before_store_or_worker(self):
        for failed_gate in ("disk", "snapshot", "model", "image", "deadline"):
            with self.subTest(gate=failed_gate):
                self.fixture.events.clear()
                self.fixture.stores = self.fixture.stores.__class__()
                dependencies = self._dependencies(
                    disk_free=1 if failed_gate == "disk" else 1024 * 1024 * 1024
                )
                if failed_gate in {"snapshot", "model", "image"}:
                    dependencies = _Dependencies(
                        **{
                            **dependencies.__dict__,
                            "snapshot_loader": self.fixture._dependencies(
                                failure=failed_gate
                            ).snapshot_loader
                            if failed_gate == "snapshot"
                            else dependencies.snapshot_loader,
                            "model_preflight_factory": self.fixture._dependencies(
                                failure="model"
                            ).model_preflight_factory
                            if failed_gate == "model"
                            else dependencies.model_preflight_factory,
                            "docker_inspect": self.fixture._dependencies(
                                failure="image"
                            ).docker_inspect
                            if failed_gate == "image"
                            else dependencies.docker_inspect,
                        }
                    )
                with patch.object(cli_module, "_require_deadline_support", side_effect=cli_module.R5BatchCLIError("deadline unavailable")) if failed_gate == "deadline" else _null_context():
                    result, _output, errors = self._invoke(dependencies)
                self.assertEqual(result, 2, errors.getvalue())
                self.assertNotIn("open-stores", self.fixture.events)
                self.assertNotIn("runner", self.fixture.events)
                self.assertFalse(self.fixture.stores.preserved)
                self.assertNotIn("secret-payload", errors.getvalue())

    def test_wrong_confirmation_closes_owned_stores_without_worker_dispatch(self):
        result, _output, errors = self._invoke(self._dependencies(), "not the gate")
        self.assertEqual(result, 2)
        self.assertIn("confirmation did not match", errors.getvalue())
        self.assertNotIn("runner", self.fixture.events)
        self.assertNotIn(("worker", "R5-001"), self.fixture.events)
        self.assertFalse(self.fixture.stores.preserved)
        self.assertTrue(self.fixture.stores.closed)


class _null_context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


if __name__ == "__main__":
    unittest.main()
