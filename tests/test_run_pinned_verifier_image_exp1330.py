from __future__ import annotations

import io
import unittest
from unittest import mock

from scripts import run_pinned_verifier_image_exp1330 as gated_transfer


class Exp1330FreshGateTests(unittest.TestCase):
    def test_stale_or_inexact_gates_never_dispatch(self):
        for supplied in (
            "RUN EXP-1314 ONCE",
            "RUN EXP-1286 ONCE",
            "RUN EXP-1330 ONCE extra",
            "",
        ):
            with self.subTest(supplied=supplied):
                stdout = io.StringIO()
                stderr = io.StringIO()
                transfer = mock.Mock(return_value=0)

                result = gated_transfer.main(
                    transfer=transfer,
                    stdin=io.StringIO(supplied + "\n"),
                    stdout=stdout,
                    stderr=stderr,
                )

                self.assertEqual(result, 19)
                self.assertEqual(stdout.getvalue(), "RUN_NOT_CONFIRMED\n")
                self.assertEqual(
                    stderr.getvalue(), "Type RUN EXP-1330 ONCE to continue: "
                )
                transfer.assert_not_called()

    def test_exact_fresh_gate_dispatches_transfer_once(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        transfer = mock.Mock(return_value=16)

        result = gated_transfer.main(
            transfer=transfer,
            stdin=io.StringIO("RUN EXP-1330 ONCE\n"),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(result, 16)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "Type RUN EXP-1330 ONCE to continue: ")
        transfer.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
