from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts import stage_copy as stage_copy_module
from app_contracts.stage_copy import StageCopyError, copy_staged_evidence, main
from test_durable_stage import get_verified_artifact


class StageCopyTests(unittest.TestCase):
    def _source(self, path: Path):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        with SQLiteStagedArtifactStore(path) as store:
            store.save(artifact)
        return artifact

    def test_copy_is_byte_identical_no_overwrite_and_exact_digest_readback(self):
        with tempfile.TemporaryDirectory(prefix="stage-copy-success-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "copy.sqlite3"
            artifact = self._source(source)
            original = source.read_bytes()

            evidence = copy_staged_evidence(
                source, artifact.staged_change_digest, destination
            )

            copied = destination.read_bytes()
            self.assertEqual(copied, original)
            self.assertEqual(evidence["status"], "copied")
            self.assertEqual(evidence["staged_change_digest"], artifact.staged_change_digest)
            self.assertEqual(evidence["artifact_digest"], artifact.artifact_digest)
            self.assertEqual(
                evidence["database_file_sha256"], hashlib.sha256(copied).hexdigest()
            )
            self.assertFalse(evidence["overwrite"])
            self.assertEqual(source.read_bytes(), original)
            with SQLiteStagedArtifactStore(destination, read_only=True) as store:
                self.assertEqual(store.load(artifact.staged_change_digest), artifact)

    def test_invalid_digest_and_existing_destination_fail_without_mutation(self):
        with tempfile.TemporaryDirectory(prefix="stage-copy-invalid-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "existing.sqlite3"
            artifact = self._source(source)
            source_bytes = source.read_bytes()
            destination.write_bytes(b"preserve")
            with self.assertRaisesRegex(StageCopyError, "staged digest is invalid"):
                copy_staged_evidence(source, "invalid", root / "bad.sqlite3")
            with self.assertRaisesRegex(StageCopyError, "destination is unavailable"):
                copy_staged_evidence(source, artifact.staged_change_digest, destination)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(destination.read_bytes(), b"preserve")
            alias = root / "alias.sqlite3"
            alias.symlink_to(destination)
            with self.assertRaisesRegex(StageCopyError, "destination is unavailable"):
                copy_staged_evidence(source, artifact.staged_change_digest, alias)
            self.assertEqual(destination.read_bytes(), b"preserve")

    def test_wrong_stage_digest_and_wal_sidecar_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="stage-copy-sidecar-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            artifact = self._source(source)
            destination = root / "copy.sqlite3"
            wrong = "sha256:" + "0" * 64
            with self.assertRaisesRegex(StageCopyError, "source stage is invalid"):
                copy_staged_evidence(source, wrong, destination)
            self.assertFalse(destination.exists())
            wal = source.with_name(source.name + "-wal")
            wal.write_bytes(b"untrusted active wal marker")
            with self.assertRaisesRegex(StageCopyError, "source is unavailable"):
                copy_staged_evidence(source, artifact.staged_change_digest, destination)
            self.assertEqual(wal.read_bytes(), b"untrusted active wal marker")
            self.assertFalse(destination.exists())

    def test_copy_failure_redacts_exception_text_and_leaves_no_output(self):
        with tempfile.TemporaryDirectory(prefix="stage-copy-redaction-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "copy.sqlite3"
            artifact = self._source(source)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch(
                "app_contracts.stage_copy.shutil.copyfile",
                side_effect=OSError("token=PRIVATE-CANARY"),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(
                    [str(source), artifact.staged_change_digest, str(destination)]
                )
            self.assertEqual(status, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "stage copy: operation failed\n")
            self.assertNotIn("PRIVATE-CANARY", stderr.getvalue())
            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".agent00x-stage-copy-*.sqlite3")), [])

    def test_sidecar_appearing_during_copy_stops_before_destination_link(self):
        with tempfile.TemporaryDirectory(prefix="stage-copy-concurrent-sidecar-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "copy.sqlite3"
            artifact = self._source(source)
            source_bytes = source.read_bytes()
            original_copy = shutil.copyfile

            def copy_then_add_wal(src, dst):
                result = original_copy(src, dst)
                source.with_name(source.name + "-wal").write_bytes(b"concurrent wal")
                return result

            with patch("app_contracts.stage_copy.shutil.copyfile", side_effect=copy_then_add_wal):
                with self.assertRaisesRegex(StageCopyError, "source changed during copy"):
                    copy_staged_evidence(source, artifact.staged_change_digest, destination)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertFalse(destination.exists())
            self.assertFalse(list(root.glob(".agent00x-stage-copy-*.sqlite3")))

    def test_changed_source_hash_stops_before_destination_link(self):
        with tempfile.TemporaryDirectory(prefix="stage-copy-concurrent-change-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "copy.sqlite3"
            artifact = self._source(source)
            source_bytes = source.read_bytes()
            original_hash = stage_copy_module._file_sha256
            source_hash_calls = 0

            def change_hash_for_prelink_check(path):
                nonlocal source_hash_calls
                if path == source:
                    source_hash_calls += 1
                    if source_hash_calls == 2:
                        return "0" * 64
                return original_hash(path)

            with patch(
                "app_contracts.stage_copy._file_sha256",
                side_effect=change_hash_for_prelink_check,
            ):
                with self.assertRaisesRegex(StageCopyError, "source changed during copy"):
                    copy_staged_evidence(source, artifact.staged_change_digest, destination)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertFalse(destination.exists())
            self.assertFalse(list(root.glob(".agent00x-stage-copy-*.sqlite3")))

    def test_cli_only_emits_fixed_metadata_on_success(self):
        with tempfile.TemporaryDirectory(prefix="stage-copy-cli-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "copy.sqlite3"
            artifact = self._source(source)
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(
                    [str(source), artifact.staged_change_digest, str(destination)]
                )
            self.assertEqual(status, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertNotIn(str(source), stdout.getvalue())
            self.assertNotIn("calculator.py", stdout.getvalue())
            self.assertEqual(
                json.loads(stdout.getvalue())["status"], "copied"
            )


if __name__ == "__main__":
    unittest.main()
