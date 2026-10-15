from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import check_local_verifier_image_id_exp1342 as check
from scripts import stream_pinned_verifier_image as pinned


class LocalVerifierImageIdTests(unittest.TestCase):
    def test_exact_id_is_confirmed_without_returning_value(self):
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(
                (), 0, (pinned.IMAGE_ID + "\n").encode(), b""
            )
        )
        output = io.StringIO()
        self.assertEqual(check.check_local_image_id(runner, output), 0)
        self.assertEqual(output.getvalue(), "LOCAL_IMAGE_ID_CONFIRMED\n")
        runner.assert_called_once_with(
            (
                "/usr/local/bin/docker",
                "image",
                "inspect",
                "--format",
                "{{.Id}}",
                pinned.IMAGE_ID,
            ),
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertNotIn(pinned.IMAGE_ID, output.getvalue())

    def test_absence_and_other_failures_are_fixed_markers(self):
        cases = (
            (
                subprocess.CompletedProcess((), 1, b"", b"No such image: PRIVATE"),
                "LOCAL_IMAGE_NOT_FOUND\n",
            ),
            (
                subprocess.CompletedProcess((), 1, b"PRIVATE", b"daemon error"),
                "LOCAL_IMAGE_INSPECT_FAILED\n",
            ),
        )
        for result, expected in cases:
            with self.subTest(expected=expected):
                runner = mock.Mock(return_value=result)
                output = io.StringIO()
                check.check_local_image_id(runner, output)
                self.assertEqual(output.getvalue(), expected)
                self.assertNotIn("PRIVATE", output.getvalue())
                runner.assert_called_once()

    def test_mismatch_and_malformed_output_do_not_leak(self):
        for raw in (b"sha256:" + b"0" * 64 + b"\n", b"PRIVATE\nextra\n"):
            runner = mock.Mock(
                return_value=subprocess.CompletedProcess((), 0, raw, b"")
            )
            output = io.StringIO()
            check.check_local_image_id(runner, output)
            self.assertEqual(output.getvalue(), "LOCAL_IMAGE_ID_MISMATCH\n")
            self.assertNotIn("PRIVATE", output.getvalue())


if __name__ == "__main__":
    unittest.main()
