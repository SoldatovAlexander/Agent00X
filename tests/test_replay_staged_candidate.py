from __future__ import annotations

from contextlib import redirect_stderr
from dataclasses import replace
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
from app_contracts.github_snapshot import GitCommitObject
from app_contracts.observation_store import SQLiteObservationStore
from app_contracts.observer_report import report_from_sqlite
from app_contracts.sandbox import LocalProcessSandboxBackend
from app_contracts.validator import ContractValidationError
from test_durable_stage import AcceptingVerifier, get_verified_artifact
from test_durable_stage import make_snapshot


class FakeTransport:
    def __init__(self, remaining=60, status=200, reset_unix=None):
        self.remaining = remaining
        self.status = status
        self.reset_unix = reset_unix
        self.calls = 0

    def read_rate_limit(self):
        self.calls += 1
        return SimpleNamespace(
            status=self.status,
            remaining=self.remaining,
            reset_unix=self.reset_unix or int(time.time()) + 3600,
        )

    def __call__(self, _method, _url, _headers, _max_bytes, *, allow_redirects):
        return SimpleNamespace(status=200, body=b"{}", allow_redirects=allow_redirects)


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


class FakeCommitObjectSource:
    def __call__(self, _claim):
        return b"synthetic raw commit object source"


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
        return replace(
            snapshot,
            verified_commit_object=GitCommitObject(
                snapshot.claim.commit_oid,
                snapshot.claim.tree_oid,
            ),
        )

    def _run(
        self,
        source,
        artifact,
        output,
        *,
        transport=None,
        snapshot=None,
        snapshot_reader=None,
        commit_object_source=None,
        sandbox=None,
        verifier=None,
        observation_store=None,
        record_snapshot_sources=False,
    ):
        transport = transport or FakeTransport()
        snapshot = snapshot or self._snapshot()
        commit_object_source = commit_object_source or FakeCommitObjectSource()
        sandbox = sandbox or RecordingSandbox()
        verifier = verifier or RecordingVerifier()
        if snapshot_reader is None and record_snapshot_sources:
            def reader(_request, observed_transport, *, commit_object_source):
                observed_transport(
                    "GET",
                    "https://api.github.com/repos/FixtureOwner/stage-fixture/commits/"
                    + "a" * 40,
                    {
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2026-03-10",
                    },
                    10000,
                    allow_redirects=False,
                )
                commit_object_source(snapshot.claim)
                return snapshot
        else:
            reader = snapshot_reader or (
                lambda _request, _transport, *, commit_object_source: snapshot
            )
        return replay.replay_staged_candidate(
            source,
            artifact.staged_change_digest,
            output,
            transport=transport,
            sandbox_backend=sandbox,
            verifier=verifier,
            commit_object_source=commit_object_source,
            test_command=("python3", "-c", "pass"),
            snapshot_reader=reader,
            observation_store=observation_store,
        )

    def test_optional_observer_carries_replay_from_readiness_through_stage(self):
        with tempfile.TemporaryDirectory(prefix="replay-observer-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            output = root / "output.sqlite3"
            journal = root / "observer.sqlite3"
            artifact = self._source_database(source)
            snapshot = self._snapshot()
            with SQLiteObservationStore(journal) as store:
                evidence = self._run(
                    source,
                    artifact,
                    output,
                    snapshot=snapshot,
                    observation_store=store,
                    record_snapshot_sources=True,
                )
                events = store.events()

            self.assertEqual(evidence["status"], "verified")
            self.assertEqual(evidence["observer"]["completeness"], "partial")
            self.assertEqual(
                evidence["observer"]["run_id"], events[0]["run_id"]
            )
            self.assertEqual(
                [event["sequence"] for event in events], list(range(len(events)))
            )
            tools = [event.get("decision_or_tool") for event in events]
            self.assertLess(
                tools.index("GitHubReadiness.fetch"),
                tools.index("GitHubSnapshot.GET.commit"),
            )
            self.assertLess(
                tools.index("GitHubSnapshot.GET.commit"),
                tools.index("ProposalWorker.propose"),
            )
            self.assertLess(
                tools.index("IndependentVerifier.verify"),
                tools.index("StagedArtifactStore.save"),
            )
            report = report_from_sqlite(journal, run_id=evidence["observer"]["run_id"])
            self.assertEqual(report["snapshot"]["event_count"], len(events))
            self.assertEqual(report["source"]["trust"], "local_unattested")
            self.assertEqual(report["snapshot"]["completeness"], "partial")

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
            self.assertEqual(
                evidence["raw_commit_object"],
                {
                    "status": "verified-by-object-hash",
                    "commit_oid": "a" * 40,
                    "root_tree_oid": "b" * 40,
                },
            )
            self.assertIn("replayed-not-live-worker", evidence["limitations"])
            self.assertIn(
                "raw-commit-object-and-content-hashes-verified",
                evidence["limitations"],
            )
            self.assertIn(
                "github-tls-transport-provenance-not-independent",
                evidence["limitations"],
            )
            self.assertIn(
                "human-authorship-not-independently-verified",
                evidence["limitations"],
            )
            with SQLiteStagedArtifactStore(output, read_only=True) as store:
                replayed = store.load(evidence["staged_change_digest"])
            payload = replayed.payload_copy()
            source_content = artifact.payload_copy()["verified_contents"]
            self.assertEqual(payload["verified_contents"], source_content)
            self.assertEqual(payload["declared_change_paths"], ["calculator.py"])

    def test_safe_failure_marker_reports_only_allowlisted_phase(self):
        marker = replay._safe_failure_marker(
            replay.ReplayError("replay: readiness request failed")
        )
        self.assertEqual(
            marker,
            "replay: operation failed closed [readiness-request-failed]",
        )

    def test_safe_failure_marker_distinguishes_readiness_gate_categories(self):
        cases = (
            ("replay: readiness HTTP status failed", "readiness-http-status-failed"),
            ("replay: readiness metadata is invalid", "readiness-metadata-invalid"),
            ("replay: readiness quota is insufficient", "readiness-quota-low"),
        )
        for message, code in cases:
            with self.subTest(code=code):
                self.assertEqual(
                    replay._safe_failure_marker(replay.ReplayError(message)),
                    f"replay: operation failed closed [{code}]",
                )

    def test_safe_failure_marker_redacts_unknown_exception_text(self):
        secret_like = "token=DO_NOT_PRINT"
        marker = replay._safe_failure_marker(RuntimeError(secret_like))
        self.assertEqual(marker, "replay: operation failed closed [operation-failed]")
        self.assertNotIn(secret_like, marker)

    def test_safe_failure_marker_maps_unknown_replay_message_to_generic(self):
        marker = replay._safe_failure_marker(
            replay.ReplayError("private path and response body")
        )
        self.assertEqual(marker, "replay: operation failed closed [operation-failed]")

    def test_safe_failure_marker_projects_only_known_target_test_categories(self):
        for category in ("sqlite-range-status", "sqlite-range-no-write"):
            with self.subTest(category=category):
                error = ContractValidationError(
                    "verification failed; staged change was not created: " + category
                )
                self.assertEqual(
                    replay._safe_failure_marker(error),
                    "replay: operation failed closed [target-test-" + category + "]",
                )

    def test_safe_failure_marker_hides_unknown_or_embedded_target_text(self):
        for message in (
            "verification failed; staged change was not created: private-token",
            "prefix verification failed; staged change was not created: sqlite-range-status",
            "verification failed; staged change was not created: sqlite-range-status token=SECRET",
        ):
            with self.subTest(message=message):
                marker = replay._safe_failure_marker(ContractValidationError(message))
                self.assertEqual(
                    marker, "replay: operation failed closed [operation-failed]"
                )
                self.assertNotIn("SECRET", marker)

    def test_production_reader_receives_commit_source_and_proof_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="replay-staged-commit-source-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            output = root / "output.sqlite3"
            artifact = self._source_database(source)
            commit_source = FakeCommitObjectSource()
            snapshot = self._snapshot()
            observed = []

            def reader(_request, _transport, *, commit_object_source):
                observed.append(commit_object_source)
                return snapshot

            evidence = self._run(
                source,
                artifact,
                output,
                snapshot_reader=reader,
                commit_object_source=commit_source,
            )

            self.assertEqual(observed, [commit_source])
            self.assertEqual(
                evidence["raw_commit_object"]["status"],
                "verified-by-object-hash",
            )

    def test_absent_malformed_or_mismatched_raw_proof_stops_before_execution(self):
        with tempfile.TemporaryDirectory(prefix="replay-staged-commit-proof-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            artifact = self._source_database(source)
            original_source_bytes = source.read_bytes()

            for proof_case in ("absent", "malformed", "mismatched"):
                with self.subTest(proof=proof_case):
                    output = root / f"{proof_case}.sqlite3"
                    snapshot = self._snapshot()
                    if proof_case == "absent":
                        snapshot = replace(snapshot, verified_commit_object=None)
                    elif proof_case == "mismatched":
                        snapshot = SimpleNamespace(
                            claim=snapshot.claim,
                            files=snapshot.files,
                            verified_commit_object=GitCommitObject(
                                "c" * 40,
                                snapshot.claim.tree_oid,
                            ),
                        )
                    else:
                        snapshot = SimpleNamespace(
                            claim=snapshot.claim,
                            files=snapshot.files,
                            verified_commit_object="not-a-git-commit-object",
                        )
                    sandbox = RecordingSandbox()
                    verifier = RecordingVerifier()

                    with self.assertRaisesRegex(
                        replay.ReplayError, "raw commit proof mismatch"
                    ):
                        self._run(
                            source,
                            artifact,
                            output,
                            snapshot=snapshot,
                            sandbox=sandbox,
                            verifier=verifier,
                        )

                    self.assertEqual(sandbox.calls, 0)
                    self.assertEqual(verifier.calls, 0)
                    self.assertFalse(output.exists())
                    self.assertEqual(source.read_bytes(), original_source_bytes)

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
                                commit_object_source=FakeCommitObjectSource(),
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
            with self.assertRaisesRegex(
                replay.ReplayError, "readiness quota is insufficient"
            ):
                replay.replay_staged_candidate(
                    source,
                    artifact.staged_change_digest,
                    output,
                    transport=transport,
                    sandbox_backend=sandbox,
                    verifier=RecordingVerifier(),
                    commit_object_source=FakeCommitObjectSource(),
                    test_command=("python3", "-c", "pass"),
                    snapshot_reader=lambda *_args: self.fail("snapshot must not be read"),
                )
            self.assertEqual(transport.calls, 1)
            self.assertEqual(sandbox.calls, 0)
            self.assertFalse(output.exists())

    def test_bad_readiness_status_or_metadata_stops_before_snapshot_and_sandbox(self):
        for transport, expected in (
            (FakeTransport(status=503), "readiness HTTP status failed"),
            (FakeTransport(remaining=True), "readiness metadata is invalid"),
            (FakeTransport(reset_unix=-1), "readiness metadata is invalid"),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory(
                prefix="replay-staged-bad-readiness-"
            ) as directory:
                root = Path(directory)
                source = root / "source.sqlite3"
                output = root / "output.sqlite3"
                artifact = self._source_database(source)
                sandbox = RecordingSandbox()
                with self.assertRaisesRegex(replay.ReplayError, expected):
                    replay.replay_staged_candidate(
                        source,
                        artifact.staged_change_digest,
                        output,
                        transport=transport,
                        sandbox_backend=sandbox,
                        verifier=RecordingVerifier(),
                        commit_object_source=FakeCommitObjectSource(),
                        test_command=("python3", "-c", "pass"),
                        snapshot_reader=lambda *_args: self.fail(
                            "snapshot must not be read"
                        ),
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
                    commit_object_source=FakeCommitObjectSource(),
                    test_command=("python3", "-c", "pass"),
                    snapshot_reader=lambda *_args, **_kwargs: object(),
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
                commit_object_source=FakeCommitObjectSource(),
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

    def test_cli_rejects_observer_stage_database_alias_before_runtime(self):
        with tempfile.TemporaryDirectory(prefix="replay-observer-paths-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            shared_output = root / "shared.sqlite3"
            artifact = self._source_database(source)
            stderr = io.StringIO()
            with (
                patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}),
                patch.object(replay, "_production_runtime", side_effect=AssertionError),
                redirect_stderr(stderr),
            ):
                result = replay.main(
                    [
                        str(source),
                        artifact.staged_change_digest,
                        str(shared_output),
                        "--observer-database",
                        str(shared_output),
                    ]
                )
            self.assertEqual(result, 2)
            self.assertFalse(shared_output.exists())
            self.assertIn("operation failed closed", stderr.getvalue())

    def test_production_runtime_includes_fixed_raw_commit_source(self):
        with (
            patch.object(replay.shutil, "which", return_value="/usr/bin/docker"),
            patch.object(replay, "GitHubAnonymousSnapshotTransport") as transport,
            patch.object(replay, "DockerSandboxBackend") as sandbox,
            patch.object(replay, "VerifierContainerConfig"),
            patch.object(replay, "DockerContainerVerifier"),
            patch.object(replay, "GitHubRawCommitObjectSource") as commit_source,
        ):
            runtime = replay._production_runtime()

        self.assertEqual(len(runtime), 4)
        commit_source.assert_called_once_with(
            "/usr/bin/git", timeout_seconds=15
        )
        self.assertIs(runtime[0], transport.return_value)
        self.assertIs(runtime[1], sandbox.return_value)
        self.assertIs(runtime[3], commit_source.return_value)

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
