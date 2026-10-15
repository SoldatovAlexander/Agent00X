from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import audit_pinned_verifier_save_archive as audit
from scripts import emit_local_verifier_config_digest_exp1344 as emit
from scripts import stream_pinned_verifier_image as pinned


class LocalVerifierConfigDigestTests(unittest.TestCase):
    def make_archive(self):
        from tests.test_audit_pinned_verifier_save_archive import (
            PinnedVerifierArchiveAuditTests,
        )

        return PinnedVerifierArchiveAuditTests().make_archive()

    def test_config_digest_is_emitted_only_when_explicitly_enabled(self):
        archive, local_id, diff_ids = self.make_archive()
        hidden = io.StringIO()
        audit.inspect_archive(
            archive,
            image_id=pinned.IMAGE_ID,
            descriptor_digest=pinned.IMAGE_ID,
            diff_ids=diff_ids,
            stream_size=len(archive),
            output=hidden,
        )
        self.assertNotIn("archive_config_digest=", hidden.getvalue())

        visible = io.StringIO()
        audit.inspect_archive(
            archive,
            image_id=pinned.IMAGE_ID,
            descriptor_digest=pinned.IMAGE_ID,
            diff_ids=diff_ids,
            emit_config_digest=True,
            stream_size=len(archive),
            output=visible,
        )
        expected = "sha256:" + local_id.split(":", 1)[1]
        self.assertIn("archive_config_digest=" + expected, visible.getvalue())
        self.assertIn("diff_ids_match_pin=true", visible.getvalue())
        self.assertIn("uncompressed_layers_match_diff_ids=true", visible.getvalue())
        self.assertEqual(len(diff_ids), 2)

    def test_exactly_one_save_uses_pin_and_redacts_command_output(self):
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess((), 1, b"SECRET", b"SECRET")
        )
        output = io.StringIO()
        self.assertEqual(emit.emit_config_digest(runner, output), 10)
        self.assertEqual(output.getvalue(), "LOCAL_IMAGE_SAVE_FAILED\n")
        self.assertNotIn("SECRET", output.getvalue())
        runner.assert_called_once_with(
            ("/usr/local/bin/docker", "image", "save", pinned.IMAGE_ID),
            capture_output=True,
            timeout=60,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
