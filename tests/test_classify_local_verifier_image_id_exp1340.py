from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import audit_pinned_verifier_save_archive as audit
from scripts import classify_local_verifier_image_id_exp1340 as classify
from scripts import stream_pinned_verifier_image as pinned


class LocalVerifierImageIdClassificationTests(unittest.TestCase):
    def test_identity_parser_accepts_only_one_bounded_digest_pair(self):
        digest = "sha256:" + "a" * 64
        self.assertEqual(
            classify._parse_identity_line(f"{pinned.IMAGE_ID}|{digest}\n".encode()),
            (pinned.IMAGE_ID, digest),
        )
        for value in (
            b"secret-output",
            f"{pinned.IMAGE_ID}|none\n".encode(),
            f"{pinned.IMAGE_ID}|{digest}\nextra\n".encode(),
        ):
            with self.subTest(value=value[:30]):
                parsed = classify._parse_identity_line(value)
                if value.endswith(b"|none\n"):
                    self.assertEqual(parsed, (pinned.IMAGE_ID, "none"))
                else:
                    self.assertIsNone(parsed)

    def test_inspect_failure_and_absent_descriptor_stop_before_save(self):
        for result, expected in (
            (
                subprocess.CompletedProcess((), 1, b"SECRET", b"SECRET"),
                "LOCAL_INSPECT_FAILED\n",
            ),
            (
                subprocess.CompletedProcess(
                    (), 0, f"{pinned.IMAGE_ID}|none\n".encode(), b""
                ),
                "LOCAL_IMAGE_DESCRIPTOR_UNAVAILABLE\n",
            ),
        ):
            runner = mock.Mock(return_value=result)
            output = io.StringIO()
            classify.run_once(runner, output)
            self.assertEqual(output.getvalue(), expected)
            self.assertNotIn("SECRET", output.getvalue())
            runner.assert_called_once()

    def test_mismatch_markers_are_fixed_and_no_save_occurs(self):
        bad_lines = (
            b"secret output\n",
            f"sha256:{'0' * 64}|sha256:{'1' * 64}\n".encode(),
        )
        expected = (
            "LOCAL_IDENTITY_FIELDS_INVALID\n",
            "LOCAL_IMAGE_ID_MISMATCH\n",
        )
        for line, marker in zip(bad_lines, expected, strict=True):
            runner = mock.Mock(
                return_value=subprocess.CompletedProcess((), 0, line, b"")
            )
            output = io.StringIO()
            classify.run_once(runner, output)
            self.assertEqual(output.getvalue(), marker)
            runner.assert_called_once()

    def test_save_uses_exact_id_and_passes_descriptor_digest_to_archive_audit(self):
        descriptor = "sha256:" + pinned.IMAGE_ID.split(":", 1)[1]
        runner = mock.Mock(
            side_effect=(
                subprocess.CompletedProcess(
                    (), 0, f"{pinned.IMAGE_ID}|{descriptor}\n".encode(), b""
                ),
                subprocess.CompletedProcess((), 0, b"ARCHIVE", b""),
            )
        )
        output = io.StringIO()
        with mock.patch.object(audit, "inspect_archive", return_value=23) as inspect:
            result = classify.run_once(runner, output)
        self.assertEqual(result, 23)
        self.assertEqual(
            output.getvalue(),
            "LOCAL_IMAGE_ID_MODEL|image_id_matches_pin=true|"
            "id_equals_descriptor_digest=true\n",
        )
        inspect.assert_called_once_with(
            b"ARCHIVE", descriptor_digest=descriptor, output=output
        )
        self.assertEqual(runner.call_count, 2)


if __name__ == "__main__":
    unittest.main()
