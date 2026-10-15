from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts.wal_stage_snapshot import (
    WalStageSnapshotError,
    main,
    snapshot_wal_stage,
)
from test_durable_stage import get_verified_artifact


class WalStageSnapshotTests(unittest.TestCase):
    def _artifact(self):
        request, prepared, result, _ = get_verified_artifact()
        return build_staged_artifact(request, prepared, result)

    def _manifest(self, source: Path):
        result = {}
        for suffix in ("", "-wal", "-shm"):
            path = source if not suffix else source.with_name(source.name + suffix)
            if path.exists():
                result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    def test_wal_snapshot_is_standalone_exact_and_does_not_mutate_source(self):
        with tempfile.TemporaryDirectory(prefix="wal-stage-snapshot-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "review.sqlite3"
            artifact = self._artifact()

            with SQLiteStagedArtifactStore(source) as store:
                store.save(artifact)
                self.assertTrue(source.with_name(source.name + "-wal").is_file())
                self.assertTrue(source.with_name(source.name + "-shm").is_file())
                source_before = self._manifest(source)
                evidence = snapshot_wal_stage(
                    source, artifact.staged_change_digest, destination
                )
                self.assertEqual(self._manifest(source), source_before)

            self.assertEqual(evidence["status"], "snapshotted")
            self.assertEqual(evidence["staged_change_digest"], artifact.staged_change_digest)
            self.assertEqual(evidence["artifact_digest"], artifact.artifact_digest)
            self.assertTrue(evidence["source_unchanged"])
            self.assertFalse(evidence["overwrite"])
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            self.assertFalse(destination.with_name(destination.name + "-wal").exists())
            self.assertFalse(destination.with_name(destination.name + "-shm").exists())
            self.assertEqual(
                evidence["destination_sha256"],
                hashlib.sha256(destination.read_bytes()).hexdigest(),
            )
            with SQLiteStagedArtifactStore(destination, read_only=True) as store:
                self.assertEqual(store.load(artifact.staged_change_digest), artifact)

    def test_existing_destination_and_bad_digest_fail_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="wal-stage-no-overwrite-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "review.sqlite3"
            artifact = self._artifact()
            with SQLiteStagedArtifactStore(source) as store:
                store.save(artifact)
                destination.write_bytes(b"preserve")
                with self.assertRaisesRegex(
                    WalStageSnapshotError, "destination is unavailable"
                ):
                    snapshot_wal_stage(source, artifact.staged_change_digest, destination)
                destination.unlink()
                with self.assertRaisesRegex(
                    WalStageSnapshotError, "staged digest is invalid"
                ):
                    snapshot_wal_stage(source, "invalid", destination)
            self.assertFalse(destination.exists())

    def test_source_mutation_during_snapshot_aborts_before_publish(self):
        with tempfile.TemporaryDirectory(prefix="wal-stage-mutation-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "review.sqlite3"
            artifact = self._artifact()
            import app_contracts.wal_stage_snapshot as module

            with SQLiteStagedArtifactStore(source) as store:
                store.save(artifact)
                original_copy = module._copy_exact
                mutated = False

                def copy_then_mutate(src: Path, dst: Path) -> None:
                    nonlocal mutated
                    original_copy(src, dst)
                    if not mutated and src == source:
                        wal = source.with_name(source.name + "-wal")
                        with wal.open("ab") as stream:
                            stream.write(b"changed")
                        mutated = True

                with patch.object(module, "_copy_exact", side_effect=copy_then_mutate):
                    with self.assertRaisesRegex(
                        WalStageSnapshotError, "source changed during copy"
                    ):
                        snapshot_wal_stage(
                            source, artifact.staged_change_digest, destination
                        )
            self.assertTrue(mutated)
            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".agent00x-wal-stage-*")), [])

    def test_invalid_source_paths_and_oversize_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="wal-stage-inputs-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "review.sqlite3"
            artifact = self._artifact()
            with SQLiteStagedArtifactStore(source) as store:
                store.save(artifact)
                alias = root / "alias.sqlite3"
                alias.symlink_to(source)
                with self.assertRaisesRegex(WalStageSnapshotError, "source is unavailable"):
                    snapshot_wal_stage(alias, artifact.staged_change_digest, destination)
                with patch("app_contracts.wal_stage_snapshot._MAX_SOURCE_BYTES", 8):
                    with self.assertRaisesRegex(
                        WalStageSnapshotError, "source is unavailable"
                    ):
                        snapshot_wal_stage(
                            source, artifact.staged_change_digest, destination
                        )
            self.assertFalse(destination.exists())

    def test_wrong_database_schema_fails_without_publishing_output(self):
        with tempfile.TemporaryDirectory(prefix="wal-stage-schema-") as temporary:
            root = Path(temporary).resolve()
            source = root / "not-a-stage.sqlite3"
            destination = root / "review.sqlite3"
            connection = sqlite3.connect(source)
            try:
                connection.execute("CREATE TABLE unrelated (value TEXT)")
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(
                WalStageSnapshotError, "staged artifact validation failed"
            ):
                snapshot_wal_stage(
                    source,
                    "sha256:" + "a" * 64,
                    destination,
                )
            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".agent00x-wal-stage-*")), [])

    def test_cli_redacts_unexpected_errors_and_only_emits_bounded_metadata(self):
        with tempfile.TemporaryDirectory(prefix="wal-stage-cli-") as temporary:
            root = Path(temporary).resolve()
            source = root / "source.sqlite3"
            destination = root / "review.sqlite3"
            artifact = self._artifact()
            with SQLiteStagedArtifactStore(source) as store:
                store.save(artifact)
                stdout, stderr = io.StringIO(), io.StringIO()
                with (
                    patch(
                        "app_contracts.wal_stage_snapshot._copy_exact",
                        side_effect=OSError("PRIVATE-CANARY"),
                    ),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    status = main(
                        [str(source), artifact.staged_change_digest, str(destination)]
                    )
                self.assertEqual(status, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(stderr.getvalue(), "wal stage snapshot: operation failed\n")
                self.assertNotIn("PRIVATE-CANARY", stderr.getvalue())
                self.assertFalse(destination.exists())
                self.assertEqual(list(root.glob(".agent00x-wal-stage-*")), [])

                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    status = main(
                        [str(source), artifact.staged_change_digest, str(destination)]
                    )
                self.assertEqual(status, 0)
                self.assertEqual(stderr.getvalue(), "")
                evidence = json.loads(stdout.getvalue())
                self.assertEqual(evidence["status"], "snapshotted")
                self.assertNotIn("canonical_payload", evidence)
                self.assertNotIn("backend/routes.py", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
