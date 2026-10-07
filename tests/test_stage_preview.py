from __future__ import annotations

import ast
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.durable_stage import (
    DurableStageNotFound,
    DurableStageStoreError,
    SQLiteStagedArtifactStore,
    build_staged_artifact,
)
from app_contracts.stage_preview import (
    StagePreviewError,
    build_stage_preview,
    load_stage_preview,
    main,
    render_stage_preview,
)
from test_durable_stage import get_verified_artifact


class StagePreviewTests(unittest.TestCase):
    def get_artifact(self):
        request, prepared, result, _ = get_verified_artifact()
        return build_staged_artifact(request, prepared, result)

    def test_preview_is_deterministic_digest_bound_and_excludes_prompts_evidence(self):
        artifact = self.get_artifact()
        preview = build_stage_preview(artifact)
        rendered = render_stage_preview(artifact)
        self.assertEqual(json.loads(rendered), preview)
        self.assertEqual(rendered, render_stage_preview(artifact))
        self.assertEqual(preview["schema"], "stage-preview/v1")
        self.assertEqual(preview["stage"]["staged_change_digest"], artifact.staged_change_digest)
        self.assertEqual(preview["stage"]["artifact_digest"], artifact.artifact_digest)
        self.assertEqual(
            preview["stage"]["verified_contents_digest"], artifact.verified_contents_digest
        )
        self.assertEqual(preview["change"]["repository_id"], "FixtureOwner/stage-fixture")
        self.assertEqual(preview["change"]["process_id"], "process-durable-stage-001")
        self.assertEqual(preview["change"]["declared_change_paths"], ["calculator.py"])
        self.assertIn("--- a/calculator.py", preview["change"]["patch"])
        self.assertEqual(preview["verification"]["verdict"], "pass")
        self.assertEqual(preview["approval"], "not_created")
        self.assertEqual(preview["publication"], "not_attempted")
        self.assertNotIn("evidence_bundle", rendered)
        self.assertNotIn("task_instruction", rendered)
        self.assertNotIn("Add a harmless synthetic comment", rendered)

    def test_read_only_database_preview_does_not_change_database_or_allow_save(self):
        artifact = self.get_artifact()
        with tempfile.TemporaryDirectory(prefix="stage-preview-ro-") as temporary:
            path = Path(temporary) / "stages.sqlite3"
            with SQLiteStagedArtifactStore(path) as writable:
                writable.save(artifact)
            before = path.read_bytes()
            entries_before = {item.name for item in path.parent.iterdir()}
            rendered = load_stage_preview(path, artifact.staged_change_digest)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual({item.name for item in path.parent.iterdir()}, entries_before)
            self.assertIn(artifact.staged_change_digest, rendered)
            with SQLiteStagedArtifactStore(path, read_only=True) as readonly:
                self.assertEqual(readonly.load(artifact.staged_change_digest), artifact)
                with self.assertRaisesRegex(
                    DurableStageStoreError, "^durable stage store: store is read-only$"
                ):
                    readonly.save(artifact)
            self.assertEqual(path.read_bytes(), before)

    def test_missing_symlink_and_bad_database_paths_fail_without_creating(self):
        artifact = self.get_artifact()
        with tempfile.TemporaryDirectory(prefix="stage-preview-path-") as temporary:
            missing = Path(temporary) / "missing.sqlite3"
            with self.assertRaisesRegex(StagePreviewError, "^stage preview: database unavailable$"):
                load_stage_preview(missing, artifact.staged_change_digest)
            self.assertFalse(missing.exists())
            real = Path(temporary) / "real.sqlite3"
            with SQLiteStagedArtifactStore(real) as store:
                store.save(artifact)
            alias = Path(temporary) / "alias.sqlite3"
            alias.symlink_to(real)
            with self.assertRaisesRegex(StagePreviewError, "^stage preview: database unavailable$"):
                load_stage_preview(alias, artifact.staged_change_digest)
            with self.assertRaisesRegex(DurableStageStoreError, "^durable stage store: digest is invalid$"):
                load_stage_preview(real, "wrong-digest")
            wal = real.with_name(real.name + "-wal")
            wal.write_bytes(b"synthetic active WAL marker")
            with self.assertRaisesRegex(
                DurableStageStoreError, "^durable stage store: database is unavailable$"
            ):
                load_stage_preview(real, artifact.staged_change_digest)
            self.assertEqual(wal.read_bytes(), b"synthetic active WAL marker")

    def test_missing_digest_and_tampered_artifact_are_refused_without_payload_leak(self):
        artifact = self.get_artifact()
        with tempfile.TemporaryDirectory(prefix="stage-preview-invalid-") as temporary:
            path = Path(temporary) / "stages.sqlite3"
            with SQLiteStagedArtifactStore(path) as store:
                store.save(artifact)
            with self.assertRaises(DurableStageNotFound):
                load_stage_preview(path, "sha256:" + "f" * 64)
            connection = sqlite3.connect(path)
            connection.execute(
                "UPDATE staged_artifacts SET canonical_payload = ? WHERE staged_change_digest = ?",
                (b"{}", artifact.staged_change_digest),
            )
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(
                DurableStageStoreError,
                "^durable stage store: stored artifact is invalid$",
            ) as error:
                load_stage_preview(path, artifact.staged_change_digest)
            self.assertNotIn("calculator.py", str(error.exception))

    def test_cli_prints_preview_or_stable_error_and_module_has_no_publication_imports(self):
        artifact = self.get_artifact()
        with tempfile.TemporaryDirectory(prefix="stage-preview-cli-") as temporary:
            path = Path(temporary) / "stages.sqlite3"
            with SQLiteStagedArtifactStore(path) as store:
                store.save(artifact)
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main([str(path), artifact.staged_change_digest])
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(json.loads(stdout.getvalue())["publication"], "not_attempted")
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main([str(path), "invalid"])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "durable stage store: digest is invalid\n")

        tree = ast.parse((ROOT / "src/app_contracts/stage_preview.py").read_text(encoding="utf-8"))
        forbidden = {"approval", "policy", "gateway", "broker", "github_http_transport"}
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.rsplit(".", 1)[-1] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add((node.module or "").rsplit(".", 1)[-1])
        self.assertFalse(forbidden.intersection(imports))


if __name__ == "__main__":
    unittest.main()
