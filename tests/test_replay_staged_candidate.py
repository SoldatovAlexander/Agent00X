from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import replay_staged_candidate as replay
from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts.sandbox import LocalProcessSandboxBackend
from test_durable_stage import AcceptingVerifier, get_verified_artifact
from test_durable_stage import make_snapshot


class FakeTransport:
    def __init__(self, remaining=60):
        self.remaining = remaining
        self.calls = 0

    def read_rate_limit(self):
        self.calls += 1
        return SimpleNamespace(
            status=200,
            remaining=self.remaining,
            reset_unix=int(time.time()) + 3600,
        )


class RecordingSandbox(LocalProcessSandboxBackend):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def create(self, snapshot, allowed_commands):
        self.calls += 1
        return super().create(snapshot, allowed_commands)


class RecordingVerifier(AcceptingVerifier):
    def __init__(self):
        self.calls = 0

    def verify(self, prepared):
        self.calls += 1
        return super().verify(prepared)


class ReplayStagedCandidateTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(replay, "REMOTE_REPOSITORY_OWNER", "FixtureOwner"),
            patch.object(replay, "REMOTE_REPOSITORY_NAME", "stage-fixture"),
            patch.object(replay, "REMOTE_REPOSITORY_COMMIT", "a" * 40),
            patch.object(replay, "REMOTE_REPOSITORY_TREE", "b" * 40),
            patch.object(replay, "REMOTE_REPOSITORY_FILE_COUNT", 1),
            patch.object(replay, "REMOTE_REPOSITORY_CONTENT_DIGEST", None),
            patch.object(replay, "ALLOWED_CHANGE_PATH", "calculator.py"),
            patch.object(replay, "_VERIFIER_ID", "stage-test-verifier-v1"),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self._stop_patches)

    def _stop_patches(self):
        for item in reversed(self.patches):
            item.stop()

    def _source_database(self, path: Path):
        request, prepared, result, _ = get_verified_artifact()
        artifact = build_staged_artifact(request, prepared, result)
        with SQLiteStagedArtifactStore(path) as store:
            store.save(artifact)
        return artifact

    def _snapshot(self):
        snapshot = make_snapshot()
        replay.REMOTE_REPOSITORY_CONTENT_DIGEST = snapshot.claim.content_digest
        replay.REMOTE_REPOSITORY_TREE = snapshot.claim.tree_oid
        replay.REMOTE_REPOSITORY_FILE_COUNT = len(snapshot.files)
        return snapshot

    def _run(self, source, artifact, output, *, transport=None, snapshot=None, snapshot_reader=None):
        transport = transport or FakeTransport()
        snapshot = snapshot or self._snapshot()
        return replay.replay_staged_candidate(
            source,
            artifact.staged_change_digest,
            output,
            transport=transport,
            sandbox_backend=RecordingSandbox(),
            verifier=RecordingVerifier(),
            test_command=("python3", "-c", "pass"),
            snapshot_reader=snapshot_reader or (lambda _request, _transport: snapshot),
        )

    def test_replays_only_stored_verified_content_and_reopens_exact_output(self):
        with tempfile.TemporaryDirectory(prefix="replay-staged-candidate-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            output = root / "output.sqlite3"
            artifact = self._source_database(source)
            source_bytes = source.read_bytes()
            evidence = self._run(source, artifact, output)

            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertTrue(output.is_file())
            self.assertEqual(evidence["status"], "verified")
            self.assertEqual(evidence["source_stage_digest"], artifact.staged_change_digest)
            self.assertEqual(evidence["approval"], "not_created")
            self.assertEqual(evidence["publication"], "not_attempted")
            self.assertFalse(evidence["external_write"])
            self.assertIn("replayed-not-live-worker", evidence["limitations"])
            with SQLiteStagedArtifactStore(output, read_only=True) as store:
                replayed = store.load(evidence["staged_change_digest"])
            payload = replayed.payload_copy()
            source_content = artifact.payload_copy()["verified_contents"]
            self.assertEqual(payload["verified_contents"], source_content)
            self.assertEqual(payload["declared_change_paths"], ["calculator.py"])

    def test_bad_source_binding_fails_before_readiness_or_sandbox(self):
        with tempfile.TemporaryDirectory(prefix="replay-staged-invalid-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            output = root / "output.sqlite3"
            artifact = self._source_database(source)
            for attribute, invalid_value in (
                ("REMOTE_REPOSITORY_OWNER", "OtherOwner"),
                ("REMOTE_REPOSITORY_COMMIT", "f" * 40),
                ("ALLOWED_CHANGE_PATH", "other.py"),
            ):
                with self.subTest(binding=attribute):
                    transport = FakeTransport()
                    sandbox = RecordingSandbox()
                    with patch.object(replay, attribute, invalid_value):
                        with self.assertRaisesRegex(
                            replay.ReplayError, "source stage is invalid"
                        ):
                            replay.replay_staged_candidate(
                                source,
                                artifact.staged_change_digest,
                                output,
                                transport=transport,
                                sandbox_backend=sandbox,
                                verifier=RecordingVerifier(),
                                test_command=("python3", "-c", "pass"),
                                snapshot_reader=lambda *_args: self.fail(
                                    "snapshot must not be read"
                                ),
                            )
                    self.assertEqual(transport.calls, 0)
                    self.assertEqual(sandbox.calls, 0)
                    self.assertFalse(output.exists())

    def test_low_readiness_stops_before_snapshot_and_target_execution(self):
        with tempfile.TemporaryDirectory(prefix="replay-staged-readiness-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            output = root / "output.sqlite3"
            artifact = self._source_database(source)
            transport = FakeTransport(remaining=24)
            sandbox = RecordingSandbox()
            with self.assertRaisesRegex(replay.ReplayError, "readiness gate failed"):
                replay.replay_staged_candidate(
                    source,
                    artifact.staged_change_digest,
                    output,
                    transport=transport,
                    sandbox_backend=sandbox,
                    verifier=RecordingVerifier(),
                    test_command=("python3", "-c", "pass"),
                    snapshot_reader=lambda *_args: self.fail("snapshot must not be read"),
                )
            self.assertEqual(transport.calls, 1)
            self.assertEqual(sandbox.calls, 0)
            self.assertFalse(output.exists())

    def test_snapshot_mismatch_stops_before_sandbox_or_output(self):
        with tempfile.TemporaryDirectory(prefix="replay-staged-pin-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            output = root / "output.sqlite3"
            artifact = self._source_database(source)
            transport = FakeTransport()
            sandbox = RecordingSandbox()
            with self.assertRaisesRegex(replay.ReplayError, "pinned snapshot mismatch"):
                replay.replay_staged_candidate(
                    source,
                    artifact.staged_change_digest,
                    output,
                    transport=transport,
                    sandbox_backend=sandbox,
                    verifier=RecordingVerifier(),
                    test_command=("python3", "-c", "pass"),
                    snapshot_reader=lambda *_args: object(),
                )
            self.assertEqual(transport.calls, 1)
            self.assertEqual(sandbox.calls, 0)
            self.assertFalse(output.exists())

    def test_alias_existing_and_symlink_outputs_are_rejected_before_transport(self):
        with tempfile.TemporaryDirectory(prefix="replay-staged-paths-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            artifact = self._source_database(source)
            transport = FakeTransport()
            sandbox = RecordingSandbox()
            kwargs = dict(
                transport=transport,
                sandbox_backend=sandbox,
                verifier=RecordingVerifier(),
                test_command=("python3", "-c", "pass"),
                snapshot_reader=lambda *_args: self.fail("no remote fetch expected"),
            )
            with self.assertRaisesRegex(replay.ReplayError, "output database path is unavailable"):
                replay.replay_staged_candidate(
                    source, artifact.staged_change_digest, source, **kwargs
                )
            existing = root / "existing.sqlite3"
            existing.write_bytes(b"preserve")
            with self.assertRaisesRegex(replay.ReplayError, "output database path is unavailable"):
                replay.replay_staged_candidate(
                    source, artifact.staged_change_digest, existing, **kwargs
                )
            alias = root / "alias.sqlite3"
            alias.symlink_to(source)
            with self.assertRaisesRegex(replay.ReplayError, "output database path is unavailable"):
                replay.replay_staged_candidate(
                    source, artifact.staged_change_digest, alias, **kwargs
                )
            self.assertEqual(transport.calls, 0)
            self.assertEqual(sandbox.calls, 0)
            self.assertEqual(existing.read_bytes(), b"preserve")

    def test_cli_requires_explicit_docker_opt_in_before_runtime_creation(self):
        stderr = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "0"}):
            with patch.object(replay, "_production_runtime", side_effect=AssertionError):
                with redirect_stderr(stderr):
                    result = replay.main(["source.sqlite3", "sha256:" + "a" * 64, "out.sqlite3"])
        self.assertEqual(result, 2)
        self.assertIn("explicit Docker opt-in is required", stderr.getvalue())

    def test_clean_cli_import_does_not_load_worker_credentials_or_publication_adapters(self):
        probe = (
            "import json, sys; "
            f"sys.path.insert(0, {str(ROOT / 'src')!r}); "
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r}); "
            "import replay_staged_candidate; "
            "forbidden = ('app_contracts.deepseek_worker', 'app_contracts.deepseek_http_channel', "
            "'app_contracts.openai_worker', 'app_contracts.credential_source', "
            "'app_contracts.stage_approval', 'app_contracts.controlled_publication', "
            "'app_contracts.github_app'); "
            "print(json.dumps([name for name in forbidden if name in sys.modules]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main()
