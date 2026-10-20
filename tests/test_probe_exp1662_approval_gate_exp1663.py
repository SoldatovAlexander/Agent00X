from __future__ import annotations

import io
import json
import unittest
from unittest.mock import Mock

from scripts import probe_exp1662_approval_gate_exp1663 as probe


class ProbeExp1662ApprovalGateExp1663Tests(unittest.TestCase):
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
        self.assertEqual(error.getvalue(), "Type RUN EXP-1663 ONCE to continue: ")
        cli_main.assert_not_called()

    def test_current_stage_trust_refusal_maps_to_fixed_marker(self):
        stdin = io.StringIO("RUN EXP-1663 ONCE\n")
        stdin.isatty = lambda: True
        output, error = io.StringIO(), io.StringIO()

        def refuse(*_args, **_kwargs):
            print(
                "approval request: verifier provenance trust is unavailable",
                file=__import__("sys").stderr,
            )
            return 2

        cli_main = Mock(side_effect=refuse)
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

    def test_untrusted_cli_output_is_never_emitted(self):
        stdin = io.StringIO("RUN EXP-1663 ONCE\n")
        stdin.isatty = lambda: True
        output, error = io.StringIO(), io.StringIO()

        def unexpected(*_args, **_kwargs):
            print("SYNTHETIC-PRIVATE-CANARY")
            return 0

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

    def test_unsigned_request_classification_does_not_render_patch(self):
        stdin = io.StringIO("RUN EXP-1663 ONCE\n")
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
