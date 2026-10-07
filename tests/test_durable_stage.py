from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.digests import canonical_json, sha256_bytes, sha256_digest
from app_contracts.durable_stage import (
    DurableStageError,
    DurableStageConflict,
    DurableStageNotFound,
    DurableStageStoreError,
    MAX_STAGED_ARTIFACT_BYTES,
    SQLiteStagedArtifactStore,
    StagedArtifact,
    build_staged_artifact,
)
from app_contracts.executor import (
    ExecutionRequest,
    ExecutionStatus,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    WorkerInput,
    WorkerProposal,
    run_local_execution,
)
import app_contracts.executor as executor_module
from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
)
from app_contracts.pinned_snapshot import SNAPSHOT_DIGEST_CANONICALIZATION
from app_contracts.remote_snapshot_workspace import materialize_github_snapshot
from app_contracts.sandbox import LocalProcessSandboxBackend


def make_snapshot() -> GitHubSnapshotContents:
    content = (
        b'def add(left: int, right: int) -> int:\n'
        b'    return left + right\n'
    )
    blob = GitHubBlobClaim(
        path="calculator.py",
        mode="100644",
        sha=hashlib.sha1(
            b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        ).hexdigest(),
        size=len(content),
        content=content,
        content_digest=sha256_bytes(content),
    )
    content_digest = sha256_digest(
        {
            "canonicalization": SNAPSHOT_DIGEST_CANONICALIZATION,
            "files": [
                {
                    "path": blob.path,
                    "content_digest": blob.content_digest,
                    "mode": blob.mode,
                }
            ],
        }
    )
    return GitHubSnapshotContents(
        claim=GitHubSnapshotClaim(
            owner="FixtureOwner",
            repository="stage-fixture",
            commit_oid="a" * 40,
            tree_oid="b" * 40,
            content_digest=content_digest,
        ),
        files=(blob,),
    )


class FixedWorker:
    def __init__(self, content: str) -> None:
        self.content = content

    def propose(self, task: WorkerInput) -> WorkerProposal:
        return WorkerProposal((("calculator.py", self.content),))


class AcceptingVerifier:
    def verify(self, prepared: VerifierInput) -> VerifierResult:
        return VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id="stage-test-verifier-v1",
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
        )


def get_verified_artifact(
    proposed_content: str | None = None,
    *,
    stage_sink=None,
    verifier=None,
    worker=None,
    sandbox_backend=None,
    require_durable_stage=False,
):
    snapshot = make_snapshot()
    source = snapshot.files[0].content.decode("utf-8")
    updated = proposed_content or source + "\n# clean synthetic stage\n"
    captured: dict = {}
    with materialize_github_snapshot(snapshot) as workspace:
        request = ExecutionRequest(
            process_id="process-durable-stage-001",
            task_id="task-durable-stage-001",
            repository_id="FixtureOwner/stage-fixture",
            base_commit=snapshot.claim.commit_oid,
            snapshot_path=workspace.path,
            allowed_commands=frozenset({"python3"}),
            declared_change_paths=("calculator.py",),
            test_command=("python3", "-c", "from calculator import add; assert add(1, 1) == 2"),
            task_instruction="Add a harmless synthetic comment",
            context_files=(("calculator.py", source),),
            remote_snapshot=snapshot,
            remote_workspace=workspace,
        )
        prepare = executor_module.prepare_change

        def capture(sandbox, **kwargs):
            prepared = prepare(sandbox, **kwargs)
            captured["prepared"] = prepared
            return prepared

        with patch.object(executor_module, "prepare_change", side_effect=capture):
            result = run_local_execution(
                request,
                worker or FixedWorker(updated),
                verifier=verifier or AcceptingVerifier(),
                sandbox_backend=sandbox_backend or LocalProcessSandboxBackend(),
                stage_sink=stage_sink,
                require_durable_stage=require_durable_stage,
            )
        return request, captured["prepared"], result, getattr(sandbox_backend, "closed", None)


class DurableStageTests(unittest.TestCase):
    def test_builds_canonical_bounded_artifact_from_verified_full_remote_run(self):
        request, prepared, result, _ = get_verified_artifact()
        self.assertIs(result.status, ExecutionStatus.VERIFIED)
        artifact = build_staged_artifact(request, prepared, result)
        payload = artifact.payload_copy()
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["canonicalization"], "durable-staged-artifact/v1")
        self.assertEqual(payload["declared_change_paths"], ["calculator.py"])
        self.assertEqual(payload["seed"]["staged_change_digest"], result.staged_change_digest)
        self.assertEqual(payload["seed"]["verified_contents_digest"], result.verified_contents_digest)
        self.assertEqual(payload["staged_change"]["patch_digest"], result.patch_digest)
        self.assertEqual(payload["verified_contents"], [
            {"path": "calculator.py", "content": dict(prepared.verified_contents)["calculator.py"]}
        ])
        self.assertEqual(artifact.artifact_digest, sha256_bytes(artifact.canonical_payload.encode("utf-8")))
        self.assertEqual(artifact.canonical_payload.encode("utf-8"), canonical_json(payload))
        self.assertNotIn("clean synthetic stage", repr(artifact))
        self.assertNotIn("clean synthetic stage", str(DurableStageError("safe failure")))

    def test_rejects_unverified_or_mismatched_execution(self):
        request, prepared, result, _ = get_verified_artifact()
        for bad_result in (
            result.__class__(status=ExecutionStatus.FAILED),
            result.__class__(
                **{
                    **result.__dict__,
                    "staged_change_digest": "sha256:" + "0" * 64,
                }
            ),
        ):
            with self.subTest(status=bad_result.status.value):
                with self.assertRaises(DurableStageError):
                    build_staged_artifact(request, prepared, bad_result)

    def test_rejects_credential_shaped_proposed_content_before_persistence(self):
        synthetic_token = "ghp_" + "A" * 32
        proposed = (
            "def add(left: int, right: int) -> int:\n"
            "    return left + right\n"
            f'# api_key: "{synthetic_token}"\n'
        )
        request, prepared, result, _ = get_verified_artifact(proposed)
        with self.assertRaisesRegex(
            DurableStageError, "^durable stage: credential-shaped content detected$"
        ):
            build_staged_artifact(request, prepared, result)

    def test_artifact_constructor_rejects_tampered_content_even_with_new_outer_digest(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        changed = artifact.payload_copy()
        changed["verified_contents"][0]["content"] += "# tampered\n"
        raw = canonical_json(changed)
        with self.assertRaisesRegex(DurableStageError, "^durable stage: artifact is invalid$"):
            StagedArtifact(
                staged_change_digest=artifact.staged_change_digest,
                verified_contents_digest=artifact.verified_contents_digest,
                artifact_digest=sha256_bytes(raw),
                canonical_payload=raw.decode("utf-8"),
            )

        changed["seed"]["verified_contents_digest"] = sha256_digest(
            (("calculator.py", changed["verified_contents"][0]["content"]),)
        )
        raw_with_rebound_content_digest = canonical_json(changed)
        with self.assertRaisesRegex(DurableStageError, "^durable stage: artifact is invalid$"):
            StagedArtifact(
                staged_change_digest=artifact.staged_change_digest,
                verified_contents_digest=changed["seed"]["verified_contents_digest"],
                artifact_digest=sha256_bytes(raw_with_rebound_content_digest),
                canonical_payload=raw_with_rebound_content_digest.decode("utf-8"),
            )

    def test_artifact_constructor_rejects_patch_tampering_and_bad_outer_digest(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        with self.assertRaisesRegex(DurableStageError, "^durable stage: artifact is invalid$"):
            StagedArtifact(
                staged_change_digest=artifact.staged_change_digest,
                verified_contents_digest=artifact.verified_contents_digest,
                artifact_digest="sha256:" + "0" * 64,
                canonical_payload=artifact.canonical_payload,
            )
        changed = artifact.payload_copy()
        changed["patch"] += "tampered"
        raw = canonical_json(changed)
        with self.assertRaisesRegex(DurableStageError, "^durable stage: artifact is invalid$"):
            StagedArtifact(
                staged_change_digest=artifact.staged_change_digest,
                verified_contents_digest=artifact.verified_contents_digest,
                artifact_digest=sha256_bytes(raw),
                canonical_payload=raw.decode("utf-8"),
            )

    def test_artifact_constructor_rejects_rebased_source_bytes(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        changed = artifact.payload_copy()
        base_record = changed["base_contents"][0]
        base_record["content"] += "# changed old source\n"
        base_bytes = base_record["content"].encode("utf-8")
        base_record["git_blob_sha"] = hashlib.sha1(
            b"blob " + str(len(base_bytes)).encode("ascii") + b"\0" + base_bytes
        ).hexdigest()
        raw = canonical_json(changed)
        with self.assertRaisesRegex(DurableStageError, "^durable stage: artifact is invalid$"):
            StagedArtifact(
                staged_change_digest=artifact.staged_change_digest,
                verified_contents_digest=artifact.verified_contents_digest,
                artifact_digest=sha256_bytes(raw),
                canonical_payload=raw.decode("utf-8"),
            )

    def test_artifact_constructor_rejects_evidence_verifier_and_binding_tampering(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        mutations = (
            ("evidence_bundle", "evidence_id", "evidence-substitution"),
            ("verification_report", "verdict", "fail"),
            ("verifier_result", "verifier_id", "other-verifier"),
            ("staged_change", "repository_id", "other-repository"),
        )
        for section, field, replacement in mutations:
            with self.subTest(section=section, field=field):
                changed = artifact.payload_copy()
                changed[section][field] = replacement
                raw = canonical_json(changed)
                with self.assertRaisesRegex(
                    DurableStageError, "^durable stage: artifact is invalid$"
                ):
                    StagedArtifact(
                        staged_change_digest=artifact.staged_change_digest,
                        verified_contents_digest=artifact.verified_contents_digest,
                        artifact_digest=sha256_bytes(raw),
                        canonical_payload=raw.decode("utf-8"),
                    )
        changed = artifact.payload_copy()
        changed["verifier_result"]["blocker_codes"] = ["unexpected-blocker"]
        changed["verifier_result"]["extra"] = "unbound field"
        raw = canonical_json(changed)
        with self.assertRaisesRegex(
            DurableStageError, "^durable stage: artifact is invalid$"
        ):
            StagedArtifact(
                staged_change_digest=artifact.staged_change_digest,
                verified_contents_digest=artifact.verified_contents_digest,
                artifact_digest=sha256_bytes(raw),
                canonical_payload=raw.decode("utf-8"),
            )

    def test_payload_copy_is_detached_from_immutable_canonical_record(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        detached = artifact.payload_copy()
        detached["verified_contents"][0]["content"] = "caller mutation"
        self.assertNotIn("caller mutation", artifact.canonical_payload)

    def test_canonical_payload_size_limit_is_enforced_before_parsing(self):
        payload = "x" * (MAX_STAGED_ARTIFACT_BYTES + 1)
        with self.assertRaisesRegex(
            DurableStageError, "^durable stage: artifact exceeds size limit$"
        ):
            StagedArtifact(
                staged_change_digest="sha256:" + "a" * 64,
                verified_contents_digest="sha256:" + "b" * 64,
                artifact_digest=sha256_bytes(payload.encode("utf-8")),
                canonical_payload=payload,
            )

    def test_module_has_no_implicit_network_environment_or_process_access(self):
        source = (ROOT / "src/app_contracts/durable_stage.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_modules = {"http", "urllib", "requests", "httpx", "os", "subprocess"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(forbidden_modules.intersection(alias.name.split(".")[0] for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden_modules)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"open", "exec", "eval", "compile"})
            elif isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"environ", "getenv", "urlopen"})

    def test_sqlite_store_wal_save_idempotency_and_reopen(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        with tempfile.TemporaryDirectory(prefix="durable-stage-") as temporary:
            path = Path(temporary) / "stages.sqlite3"
            with SQLiteStagedArtifactStore(path) as store:
                self.assertEqual(store._connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                self.assertEqual(store._connection.execute("PRAGMA synchronous").fetchone()[0], 2)
                saved = store.save(artifact)
                duplicate = store.save(artifact)
                self.assertEqual(saved.canonical_payload, artifact.canonical_payload)
                self.assertEqual(duplicate.canonical_payload, artifact.canonical_payload)
            with SQLiteStagedArtifactStore(path) as reopened:
                loaded = reopened.load(artifact.staged_change_digest)
                self.assertEqual(loaded, artifact)
                self.assertEqual(loaded.payload_copy(), artifact.payload_copy())
            self.assertTrue(path.exists())

    def test_executor_persists_and_reads_back_exact_verified_stage_before_success(self):
        events = []

        class TrackingBackend:
            closed = False

            def create(self, snapshot_path, allowed_commands):
                session = LocalProcessSandboxBackend().create(snapshot_path, allowed_commands)
                outer = self

                class TrackedSession:
                    snapshot = session.snapshot
                    workspace = session.workspace

                    def run(self, *args, **kwargs):
                        return session.run(*args, **kwargs)

                    def close(self):
                        try:
                            session.close()
                        finally:
                            outer.closed = True

                return TrackedSession()

        class RecordingVerifier(AcceptingVerifier):
            def verify(self, prepared):
                events.append("verify")
                return super().verify(prepared)

        class RecordingStore:
            def __init__(self, store):
                self.store = store

            def save(self, artifact):
                events.append(("save", artifact.staged_change_digest))
                return self.store.save(artifact)

            def load(self, digest):
                events.append(("load", digest))
                return self.store.load(digest)

        class RecordingWorker(FixedWorker):
            def propose(self, task):
                events.append("worker")
                return super().propose(task)

        with tempfile.TemporaryDirectory(prefix="durable-stage-executor-") as temporary:
            path = Path(temporary) / "stages.sqlite3"
            with SQLiteStagedArtifactStore(path) as store:
                request, prepared, result, workspace_cleaned = get_verified_artifact(
                    stage_sink=RecordingStore(store),
                    verifier=RecordingVerifier(),
                    worker=RecordingWorker("def add(left: int, right: int) -> int:\n    return left + right\n\n# staged\n"),
                    sandbox_backend=TrackingBackend(),
                    require_durable_stage=True,
                )
                loaded = store.load(result.staged_change_digest)
        self.assertIs(result.status, ExecutionStatus.VERIFIED)
        self.assertTrue(workspace_cleaned)
        self.assertEqual([event if isinstance(event, str) else event[0] for event in events],
                         ["worker", "verify", "save", "load"])
        self.assertEqual(events[2][1], result.staged_change_digest)
        self.assertEqual(events[3][1], result.staged_change_digest)
        self.assertEqual(loaded.staged_change_digest, result.staged_change_digest)
        self.assertEqual(loaded.verified_contents_digest, result.verified_contents_digest)
        self.assertEqual(loaded.payload_copy()["verified_contents"], [
            {"path": "calculator.py", "content": dict(prepared.verified_contents)["calculator.py"]}
        ])

    def test_executor_stage_save_or_readback_failure_fails_closed_and_cleans_workspace(self):
        class FailedSave:
            saves = 0

            def save(self, artifact):
                self.saves += 1
                raise RuntimeError("synthetic private source must not escape")

            def load(self, digest):
                self.fail("load must not run after save failure")

        class BadReadback:
            saves = 0
            loads = 0

            def save(self, artifact):
                self.saves += 1
                return artifact

            def load(self, digest):
                self.loads += 1
                return None

        class FailedLoad(BadReadback):
            def load(self, digest):
                self.loads += 1
                raise RuntimeError("synthetic private source must not escape")

        class TrackingBackend:
            closed = False

            def create(self, snapshot_path, allowed_commands):
                session = LocalProcessSandboxBackend().create(snapshot_path, allowed_commands)
                outer = self

                class TrackedSession:
                    snapshot = session.snapshot
                    workspace = session.workspace

                    def run(self, *args, **kwargs):
                        return session.run(*args, **kwargs)

                    def close(self):
                        try:
                            session.close()
                        finally:
                            outer.closed = True

                return TrackedSession()

        for sink in (FailedSave(), BadReadback(), FailedLoad()):
            with self.subTest(sink=type(sink).__name__):
                backend = TrackingBackend()
                request, prepared, result, workspace_cleaned = get_verified_artifact(
                    stage_sink=sink,
                    sandbox_backend=backend,
                    require_durable_stage=True,
                )
                self.assertIs(result.status, ExecutionStatus.FAILED)
                self.assertEqual(result.failure_code, "stage-persistence-failed")
                self.assertTrue(workspace_cleaned)
                self.assertNotIn("synthetic private source", repr(result))
                self.assertEqual(sink.saves, 1)
                self.assertEqual(getattr(sink, "loads", 0), 0 if isinstance(sink, FailedSave) else 1)

    def test_store_rejects_conflict_without_overwriting_existing_stage(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        payload = artifact.payload_copy()
        payload["declared_change_paths"].append("unused.py")
        payload["declared_change_paths"].sort()
        raw = canonical_json(payload)
        conflicting = StagedArtifact(
            staged_change_digest=artifact.staged_change_digest,
            verified_contents_digest=artifact.verified_contents_digest,
            artifact_digest=sha256_bytes(raw),
            canonical_payload=raw.decode("utf-8"),
        )
        with tempfile.TemporaryDirectory(prefix="durable-stage-conflict-") as temporary:
            path = Path(temporary) / "stages.sqlite3"
            store = SQLiteStagedArtifactStore(path)
            store.save(artifact)
            with self.assertRaisesRegex(
                DurableStageConflict, "^durable stage store: digest key conflict$"
            ):
                store.save(conflicting)
            self.assertEqual(
                store.load(artifact.staged_change_digest).canonical_payload,
                artifact.canonical_payload,
            )
            store.close()

    def test_store_detects_tampered_digest_and_serialized_payload(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        for column, replacement in (
            ("artifact_digest", "sha256:" + "0" * 64),
            ("canonical_payload", b"{}"),
        ):
            with self.subTest(column=column), tempfile.TemporaryDirectory(prefix="durable-stage-tamper-") as temporary:
                path = Path(temporary) / "stages.sqlite3"
                store = SQLiteStagedArtifactStore(path)
                store.save(artifact)
                store.close()
                db = sqlite3.connect(path)
                db.execute(
                    f"UPDATE staged_artifacts SET {column} = ? WHERE staged_change_digest = ?",
                    (replacement, artifact.staged_change_digest),
                )
                db.commit()
                db.close()
                with SQLiteStagedArtifactStore(path) as reopened:
                    with self.assertRaisesRegex(
                        DurableStageStoreError,
                        "^durable stage store: stored artifact is invalid$",
                    ):
                        reopened.load(artifact.staged_change_digest)

    def test_store_missing_bad_digest_closed_state_and_context_cleanup(self):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        with tempfile.TemporaryDirectory(prefix="durable-stage-state-") as temporary:
            store = SQLiteStagedArtifactStore(Path(temporary) / "stages.sqlite3")
            with self.assertRaisesRegex(DurableStageNotFound, "^durable stage store: stage not found$"):
                store.load("sha256:" + "f" * 64)
            with self.assertRaisesRegex(DurableStageStoreError, "^durable stage store: digest is invalid$"):
                store.load("not-a-digest")
            store.close()
            store.close()
            with self.assertRaisesRegex(DurableStageStoreError, "^durable stage store: store is closed$"):
                store.save(artifact)
            with self.assertRaisesRegex(DurableStageStoreError, "^durable stage store: store is closed$"):
                store.load(artifact.staged_change_digest)
            with SQLiteStagedArtifactStore(Path(temporary) / "context.sqlite3") as scoped:
                scoped.save(artifact)
            with self.assertRaisesRegex(DurableStageStoreError, "^durable stage store: store is closed$"):
                scoped.load(artifact.staged_change_digest)

    def test_store_rejects_corrupt_database_and_invalid_path_without_leakage(self):
        with tempfile.TemporaryDirectory(prefix="durable-stage-corrupt-") as temporary:
            path = Path(temporary) / "corrupt.sqlite3"
            path.write_bytes(b"synthetic corrupt database source sentinel")
            with self.assertRaisesRegex(
                DurableStageStoreError, "^durable stage store: database is unavailable$"
            ) as error:
                SQLiteStagedArtifactStore(path)
            self.assertNotIn("source sentinel", str(error.exception))
            for invalid in (None, "", ":memory:"):
                with self.subTest(invalid=repr(invalid)):
                    with self.assertRaisesRegex(
                        DurableStageStoreError, "^durable stage store: database path is invalid$"
                    ):
                        SQLiteStagedArtifactStore(invalid)


if __name__ == "__main__":
    unittest.main()
