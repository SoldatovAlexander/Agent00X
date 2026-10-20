from __future__ import annotations

import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from scripts import probe_local_ollama_readiness_exp1644 as probe


class ProbeLocalOllamaReadinessExp1644Tests(unittest.TestCase):
    def test_requires_tty_before_constructing_preflight(self):
        output = io.StringIO()
        factory = Mock()
        self.assertEqual(
            probe.run_once(stdin=io.StringIO(""), stdout=output, preflight_factory=factory),
            2,
        )
        self.assertEqual(output.getvalue(), "OLLAMA_PROBE_REQUIRES_TTY\n")
        factory.assert_not_called()

    def test_wrong_phrase_does_not_open_local_metadata_transport(self):
        stdin = io.StringIO("not the gate\n")
        stdin.isatty = lambda: True
        output, error = io.StringIO(), io.StringIO()
        factory = Mock()
        self.assertEqual(
            probe.run_once(
                stdin=stdin,
                stdout=output,
                stderr=error,
                preflight_factory=factory,
            ),
            3,
        )
        self.assertEqual(output.getvalue(), "RUN_NOT_CONFIRMED\n")
        self.assertEqual(error.getvalue(), "Type RUN EXP-1644 ONCE to continue: ")
        factory.assert_not_called()

    def test_exact_gate_runs_one_fixed_digest_preflight(self):
        stdin = io.StringIO("RUN EXP-1644 ONCE\n")
        stdin.isatty = lambda: True
        output, error = io.StringIO(), io.StringIO()
        preflight = Mock()
        preflight.inspect.return_value = SimpleNamespace(
            version="0.40.3", model_digest=probe.EXPECTED_MODEL_DIGEST
        )
        factory = Mock(return_value=preflight)
        self.assertEqual(
            probe.run_once(
                stdin=stdin,
                stdout=output,
                stderr=error,
                preflight_factory=factory,
            ),
            0,
        )
        factory.assert_called_once_with()
        preflight.inspect.assert_called_once_with(
            expected_model_digest=probe.EXPECTED_MODEL_DIGEST
        )
        self.assertEqual(error.getvalue(), "Type RUN EXP-1644 ONCE to continue: ")
        self.assertEqual(output.getvalue(), "OLLAMA_PREFLIGHT_MATCHED\n")

    def test_failure_emits_only_fixed_reason_and_never_retries(self):
        from app_contracts.r5_local_model_preflight import R5LocalModelPreflightError

        stdin = io.StringIO("RUN EXP-1644 ONCE\n")
        stdin.isatty = lambda: True
        output, error = io.StringIO(), io.StringIO()
        preflight = Mock()
        preflight.inspect.side_effect = R5LocalModelPreflightError(
            "version_request_failed"
        )
        factory = Mock(return_value=preflight)
        self.assertEqual(
            probe.run_once(
                stdin=stdin,
                stdout=output,
                stderr=error,
                preflight_factory=factory,
            ),
            10,
        )
        self.assertEqual(
            output.getvalue(),
            "OLLAMA_PREFLIGHT_FAILED|reason=version_request_failed\n",
        )
        self.assertEqual(error.getvalue(), "Type RUN EXP-1644 ONCE to continue: ")
        preflight.inspect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
