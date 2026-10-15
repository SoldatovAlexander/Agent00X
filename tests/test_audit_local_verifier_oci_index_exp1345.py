from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import unittest
from unittest import mock

from scripts import audit_local_verifier_oci_index_exp1345 as audit


class LocalVerifierOciIndexAuditTests(unittest.TestCase):
    def make_archive(self, *, image_id=None, corrupt_blob=False, entry_count=1):
        manifest = b'{"schemaVersion":2,"config":{"mediaType":"test"}}'
        digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
        if image_id is None:
            image_id = digest
        descriptors = [
            {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": digest,
             "size": len(manifest)}
            for _ in range(entry_count)
        ]
        index = json.dumps({"schemaVersion": 2, "manifests": descriptors}).encode()
        blob = manifest + (b"x" if corrupt_blob else b"")
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as tar:
            for name, content in (
                ("index.json", index),
                ("blobs/sha256/" + digest.split(":", 1)[1], blob),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
        return output.getvalue(), image_id

    def audit(self, archive, image_id):
        output = io.StringIO()
        result = audit.audit_oci_index(
            archive, image_id=image_id, stream_size=len(archive), output=output
        )
        return result, output.getvalue()

    def test_index_manifest_digest_and_blob_are_both_confirmed(self):
        archive, image_id = self.make_archive()
        result, output = self.audit(archive, image_id)
        self.assertEqual(result, 0)
        self.assertEqual(
            output,
            "OCI_ARCHIVE_FACTS|index_present=true|index_valid=true|entry_count=1|"
            "target_digest_matches_image_id=true|manifest_blob_hash_matches=true\n",
        )

    def test_unmatched_index_target_is_only_a_false_boolean(self):
        archive, _ = self.make_archive(image_id="sha256:" + "0" * 64)
        result, output = self.audit(archive, "sha256:" + "0" * 64)
        self.assertEqual(result, 0)
        self.assertIn("target_digest_matches_image_id=false", output)
        self.assertNotIn("sha256:", output)

    def test_absent_malformed_multiple_and_corrupt_archives_are_fixed(self):
        for archive, expected in (
            (b"not a tar", "OCI_ARCHIVE_INVALID\n"),
            (self._archive_without_index(), "OCI_INDEX_ABSENT\n"),
            (self.make_archive(entry_count=2)[0], "OCI_INDEX_ENTRY_COUNT_MISMATCH\n"),
            (self.make_archive(corrupt_blob=True)[0], "OCI_MANIFEST_BLOB_INVALID\n"),
        ):
            with self.subTest(expected=expected):
                result, output = self.audit(archive, "sha256:" + "0" * 64)
                self.assertNotEqual(result, 0)
                self.assertIn(expected.splitlines()[0], output)
                self.assertNotIn("sha256:", output)

    def _archive_without_index(self):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w"):
            pass
        return output.getvalue()

    def test_runner_saves_exact_image_once_and_suppresses_failure_text(self):
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess((), 1, b"SECRET", b"SECRET")
        )
        output = io.StringIO()
        self.assertEqual(audit.audit_local_archive(runner, output), 10)
        self.assertEqual(output.getvalue(), "LOCAL_IMAGE_SAVE_FAILED\n")
        self.assertNotIn("SECRET", output.getvalue())
        runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
