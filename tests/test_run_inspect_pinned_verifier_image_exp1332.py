from __future__ import annotations

import io
import unittest
from unittest import mock

from scripts import run_inspect_pinned_verifier_image_exp1332 as gated_inspect


class Exp1332FreshGateTests(unittest.TestCase):
    def test_stale_or_inexact_gates_never_dispatch(self):
        for supplied in (
            "RUN EXP-1315 ONCE",
            "RUN EXP-1320 ONCE",
            "RUN EXP-1332 ONCE extra",
            "",
        ):
            with self.subTest(supplied=supplied):
                stdout = io.StringIO()
                stderr = io.StringIO()
                inspect = mock.Mock(return_value=0)

                result = gated_inspect.main(
                    inspect=inspect,
                    stdin=io.StringIO(supplied + "\n"),
                    stdout=stdout,
                    stderr=stderr,
                )

                self.assertEqual(result, 19)
                self.assertEqual(stdout.getvalue(), "RUN_NOT_CONFIRMED\n")
                self.assertEqual(
                    stderr.getvalue(), "Type RUN EXP-1332 ONCE to continue: "
                )
                inspect.assert_not_called()

    def test_exact_fresh_gate_dispatches_inspection_once(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        inspect = mock.Mock(return_value=11)

        result = gated_inspect.main(
            inspect=inspect,
            stdin=io.StringIO("RUN EXP-1332 ONCE\n"),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(result, 11)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "Type RUN EXP-1332 ONCE to continue: ")
        inspect.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
