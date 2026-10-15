from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import probe_local_verifier_descriptor_exp1343 as probe
from scripts import stream_pinned_verifier_image as pinned


class LocalVerifierDescriptorProbeTests(unittest.TestCase):
    def test_exact_descriptor_is_compared_without_disclosing_digest(self):
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(
                (), 0, f'{{"digest":"{pinned.IMAGE_ID}"}}\n'.encode(), b""
            )
        )
        output = io.StringIO()
        self.assertEqual(probe.probe_descriptor(runner, output), 0)
        self.assertEqual(
            output.getvalue(),
            "LOCAL_DESCRIPTOR|present=true|digest_matches_pinned_id=true\n",
        )
        self.assertNotIn(pinned.IMAGE_ID, output.getvalue())
        runner.assert_called_once_with(
            (
                "/usr/local/bin/docker",
                "image",
                "inspect",
                "--format",
                "{{json .Descriptor}}",
                pinned.IMAGE_ID,
            ),
            capture_output=True,
            timeout=15,
            check=False,
        )

    def test_absent_malformed_and_failed_descriptor_are_terminal(self):
        cases = (
            (subprocess.CompletedProcess((), 0, b"null\n", b""), "LOCAL_DESCRIPTOR_ABSENT\n"),
            (subprocess.CompletedProcess((), 0, b"SECRET\n", b""), "LOCAL_DESCRIPTOR_OUTPUT_INVALID\n"),
            (subprocess.CompletedProcess((), 1, b"SECRET", b"SECRET"), "LOCAL_DESCRIPTOR_INSPECT_FAILED\n"),
        )
        for result, expected in cases:
            with self.subTest(expected=expected):
                runner = mock.Mock(return_value=result)
                output = io.StringIO()
                probe.probe_descriptor(runner, output)
                self.assertEqual(output.getvalue(), expected)
                self.assertNotIn("SECRET", output.getvalue())
                runner.assert_called_once()

    def test_valid_different_digest_is_reported_only_as_false(self):
        other = "sha256:" + "0" * 64
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(
                (), 0, f'{{"digest":"{other}"}}\n'.encode(), b""
            )
        )
        output = io.StringIO()
        self.assertEqual(probe.probe_descriptor(runner, output), 0)
        self.assertEqual(
            output.getvalue(),
            "LOCAL_DESCRIPTOR|present=true|digest_matches_pinned_id=false\n",
        )
        self.assertNotIn(other, output.getvalue())


if __name__ == "__main__":
    unittest.main()
