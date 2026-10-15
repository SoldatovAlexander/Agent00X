from __future__ import annotations

from io import StringIO
import importlib
import unittest
from unittest.mock import patch

from scripts import run_r5_batch_cli as cli_module
from scripts.run_r5_batch_cli import (
    R5BatchDeadlineExceeded,
    _Dependencies,
    run_r5_batch_cli,
)
from app_contracts.r5_local_model_preflight import R5LocalModelPreflightError


def _fixture_type():
    return importlib.import_module("tests.test_r5_batch_cli").R5BatchCLITests


class R5BatchCLIDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.fixture = _fixture_type()()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.doCleanups()

    def _run(self, dependencies, *, input_fn=None):
        return run_r5_batch_cli(
            self.fixture._args(),
            input_fn=input_fn or (lambda _prompt: "RUN EXP-1070 ONCE"),
            stdout=StringIO(),
            stderr=(errors := StringIO()),
            interactive=lambda: True,
            dependencies=dependencies,
        ), errors.getvalue()

    def test_generic_preflight_failures_report_only_fixed_phase(self):
        cases = (
            ("snapshot", "snapshot"),
            ("model", "model_metadata"),
            ("image", "target_image"),
            ("stores", "stores"),
        )
        for failure, expected_phase in cases:
            with self.subTest(phase=expected_phase):
                self.fixture.events.clear()
                self.fixture.stores = self.fixture.stores.__class__()
                dependencies = self.fixture._dependencies(failure=failure)
                result, errors = self._run(dependencies)
                self.assertEqual(result, 2)
                self.assertEqual(errors.strip(), f"R5 batch: {expected_phase} failed")
                self.assertNotIn("secret-payload", errors)
                self.assertNotIn("local path details", errors)
                self.assertNotIn("must not be exposed", errors)
                self.assertNotIn("runner", self.fixture.events)

    def test_model_preflight_reports_only_its_enumerated_reason_code(self):
        base = self.fixture._dependencies()

        class _BadModelPreflight:
            def inspect(self, *, expected_model_digest):
                raise R5LocalModelPreflightError("model_digest_mismatch")

        dependencies = _Dependencies(
            **{**base.__dict__, "model_preflight_factory": _BadModelPreflight}
        )
        result, errors = self._run(dependencies)
        self.assertEqual(result, 2)
        self.assertEqual(
            errors.strip(), "R5 batch: model_metadata failed (model_digest_mismatch)"
        )
        self.assertNotIn("secret-payload", errors)
        self.assertNotIn("digest_value", errors)

    def test_docker_discovery_failure_has_its_own_fixed_phase(self):
        base = self.fixture._dependencies()

        def fail_with_details():
            raise RuntimeError("local executable path must not leak")

        dependencies = _Dependencies(
            **{**base.__dict__, "docker_discover": fail_with_details}
        )
        result, errors = self._run(dependencies)
        self.assertEqual(result, 2)
        self.assertEqual(errors.strip(), "R5 batch: docker_discovery failed")
        self.assertNotIn("local executable path", errors)
        self.assertNotIn("runner", self.fixture.events)

    def test_default_docker_discovery_supplies_the_executable_name(self):
        with patch.object(cli_module.shutil, "which", return_value="/usr/local/bin/docker") as which:
            dependencies = _Dependencies()
            self.assertEqual(dependencies.docker_discover(), "/usr/local/bin/docker")
        which.assert_called_once_with("docker")

    def test_missing_docker_executable_fails_before_store_creation(self):
        base = self.fixture._dependencies()
        dependencies = _Dependencies(
            **{**base.__dict__, "docker_discover": lambda: None}
        )
        result, errors = self._run(dependencies)
        self.assertEqual(result, 2)
        self.assertEqual(errors.strip(), "R5 batch: Docker executable unavailable")
        self.assertNotIn("open-stores", self.fixture.events)
        self.assertNotIn("runner", self.fixture.events)

    def test_unexpected_confirmation_exception_is_redacted(self):
        dependencies = self.fixture._dependencies()

        def fail_with_payload(_prompt):
            raise RuntimeError("secret-payload-at-confirmation")

        result, errors = self._run(dependencies, input_fn=fail_with_payload)
        self.assertEqual(result, 2)
        self.assertEqual(errors.strip(), "R5 batch: confirmation failed")
        self.assertNotIn("secret-payload-at-confirmation", errors)
        self.assertFalse(self.fixture.stores.preserved)
        self.assertTrue(self.fixture.stores.closed)
        self.assertNotIn("runner", self.fixture.events)

    def test_unexpected_execution_exception_is_redacted_and_stores_preserved(self):
        base = self.fixture._dependencies()
        dependencies = _Dependencies(
            **{
                **base.__dict__,
                "batch_runner": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("secret-payload-in-execution")
                ),
            }
        )
        result, errors = self._run(dependencies)
        self.assertEqual(result, 2)
        self.assertEqual(errors.strip(), "R5 batch: execution failed")
        self.assertNotIn("secret-payload-in-execution", errors)
        self.assertTrue(self.fixture.stores.preserved)
        self.assertTrue(self.fixture.stores.closed)

    def test_deadline_after_gate_preserves_recovery_stores_and_stops(self):
        dependencies = self.fixture._dependencies()

        class _ExpiredDeadline:
            def __enter__(self):
                raise R5BatchDeadlineExceeded("fixed deadline")

            def __exit__(self, *_args):
                return False

        with patch.object(cli_module, "_batch_deadline", return_value=_ExpiredDeadline()):
            result, errors = self._run(dependencies)
        self.assertEqual(result, 2)
        self.assertIn("deadline expired", errors)
        self.assertTrue(self.fixture.stores.preserved)
        self.assertTrue(self.fixture.stores.closed)
        self.assertNotIn("runner", self.fixture.events)

    def test_wrong_gate_closes_owned_stores_without_preserving_them(self):
        dependencies = self.fixture._dependencies()
        result, errors = self._run(dependencies, input_fn=lambda _prompt: "WRONG")
        self.assertEqual(result, 2)
        self.assertIn("confirmation did not match", errors)
        self.assertFalse(self.fixture.stores.preserved)
        self.assertTrue(self.fixture.stores.closed)
        self.assertNotIn("runner", self.fixture.events)
        self.assertNotIn("secret-payload", errors)


if __name__ == "__main__":
    unittest.main()
