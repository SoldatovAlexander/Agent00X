from __future__ import annotations

import io
import json
import unittest
from unittest.mock import Mock

from scripts import probe_exp1647_approval_gate_exp1651 as probe


class ProbeExp1647ApprovalGateExp1651Tests(unittest.TestCase):
    def test_non_tty_refuses_before_cli_call(self):
        output = io.StringIO()
        cli_main = Mock()
        self.assertEqual(
            probe.run_once(stdin=io.StringIO(""), stdout=output, cli_main=cli_main), 2
        )
        self.assertEqual(output.getvalue(), "APPROVAL_PROBE_REQUIRES_TTY\n")
        cli_main.assert_not_called()

    def test_wrong_gate_refuses_before_cli_call(self):
        stdin = io.StringIO("wrong\n")
        stdin.isatty = lambda: True
        output, error = io.StringIO(), io.StringIO()
        cli_main = Mock()
        self.assertEqual(
            probe.run_once(
                stdin=stdin,
                stdout=output,
                stderr=error,
                cli_main=cli_main,
            ),
            3,
        )
        self.assertEqual(output.getvalue(), "RUN_NOT_CONFIRMED\n")
        self.assertEqual(error.getvalue(), "Type RUN EXP-1651 ONCE to continue: ")
        cli_main.assert_not_called()

    def test_fixed_verifier_refusal_maps_to_one_safe_marker(self):
        stdin = io.StringIO("RUN EXP-1651 ONCE\n")
        stdin.isatty = lambda: True
        output, error = io.StringIO(), io.StringIO()
        cli_main = Mock(return_value=2)
        cli_main.side_effect = lambda *_args, **_kwargs: (
            print(
                "approval request: verifier provenance trust is unavailable",
                file=__import__("sys").stderr,
            )
            or 2
        )
        self.assertEqual(
            probe.run_once(
                stdin=stdin,
                stdout=output,
                stderr=error,
                cli_main=cli_main,
            ),
            0,
        )
        self.assertEqual(
            output.getvalue(),
            "APPROVAL_REFUSED|reason=verifier-provenance-trust-unavailable\n",
        )
        self.assertNotIn("verifier provenance", output.getvalue() + error.getvalue())
        cli_main.assert_called_once()

    def test_untrusted_stderr_is_never_emitted(self):
        stdin = io.StringIO("RUN EXP-1651 ONCE\n")
        stdin.isatty = lambda: True
        output, error = io.StringIO(), io.StringIO()

        def unexpected(*_args, **_kwargs):
            print("SYNTHETIC-PRIVATE-CANARY", file=__import__("sys").stderr)
            return 2

        self.assertEqual(
            probe.run_once(
                stdin=stdin,
                stdout=output,
                stderr=error,
                cli_main=unexpected,
            ),
            10,
        )
        self.assertEqual(output.getvalue(), "APPROVAL_RESULT_UNCLASSIFIED\n")
        self.assertNotIn("SYNTHETIC-PRIVATE-CANARY", output.getvalue() + error.getvalue())

    def test_unsigned_request_is_classified_without_rendering_review(self):
        stdin = io.StringIO("RUN EXP-1651 ONCE\n")
        stdin.isatty = lambda: True
        output = io.StringIO()
        request = {
            "schema": "approval-request/v1",
            "status": "unsigned",
            "approval": "not_created",
            "provider_write": False,
            "stage": {"staged_change_digest": probe.STAGED_CHANGE_DIGEST},
            "review": {"patch": "SYNTHETIC-PATCH-CANARY"},
        }

        def successful(*_args, **_kwargs):
            print(json.dumps(request))
            return 0

        self.assertEqual(
            probe.run_once(
                stdin=stdin,
                stdout=output,
                stderr=io.StringIO(),
                cli_main=successful,
            ),
            0,
        )
        self.assertEqual(output.getvalue(), "UNSIGNED_REQUEST_IN_MEMORY\n")
        self.assertNotIn("SYNTHETIC-PATCH-CANARY", output.getvalue())


if __name__ == "__main__":
    unittest.main()
