from __future__ import annotations

from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.durable_stage import SQLiteStagedArtifactStore, build_staged_artifact
from app_contracts.digests import sha256_digest
from app_contracts.operator_confirmation import (
    OperatorConfirmationStoreError,
    SQLiteOperatorConfirmationStore,
)
from app_contracts.stage_approval import (
    StageApprovalError,
    main,
    run_local_mock_publication,
)
from test_durable_stage import get_verified_artifact


class StageApprovalTests(unittest.TestCase):
    def get_artifact(self):
        request, prepared, result, _ = get_verified_artifact()
        return build_staged_artifact(request, prepared, result)

    def cli_args(self, database, confirmation_database, artifact, branch):
        return [
            str(database),
            artifact.staged_change_digest,
            branch,
            "master",
            "--confirmation-db",
            str(confirmation_database),
        ]

    def test_exact_digest_confirmation_creates_matching_mock_receipt_only(self):
        artifact = self.get_artifact()
        receipt = run_local_mock_publication(
            artifact,
            artifact.staged_change_digest,
            "agent/local-mock-review",
            "master",
            now=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(receipt.staged_change_digest, artifact.staged_change_digest)
        self.assertEqual(receipt.repository_id, "FixtureOwner/stage-fixture")
        self.assertEqual(receipt.branch, "agent/local-mock-review")
        self.assertEqual(receipt.pull_request_id, 1)

    def test_ephemeral_approval_binds_exact_engine_intent_and_five_minute_ttl(self):
        artifact = self.get_artifact()
        now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
        from app_contracts.stage_approval import run_controlled_local_publication

        with patch(
            "app_contracts.stage_approval.run_controlled_local_publication",
            wraps=run_controlled_local_publication,
        ) as controlled:
            receipt = run_local_mock_publication(
                artifact,
                artifact.staged_change_digest,
                "agent/local-mock-review",
                "master",
                now=now,
            )
        approval = controlled.call_args.args[2]
        engine_intent = controlled.call_args.args[4]
        self.assertEqual(receipt.staged_change_digest, artifact.staged_change_digest)
        self.assertEqual(
            approval["staged_change_digest"], artifact.staged_change_digest
        )
        self.assertEqual(approval["approved_intent_digest"], sha256_digest(engine_intent))
        self.assertEqual(
            (datetime.fromisoformat(approval["expires_at"]) - now).total_seconds(),
            300,
        )

    def test_wrong_digest_or_branch_refuses_before_mock_publication_gate(self):
        artifact = self.get_artifact()
        now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
        for digest, branch, message in (
            ("sha256:" + "0" * 64, "agent/safe", "stage approval: digest confirmation mismatch"),
            (artifact.staged_change_digest, "external/unsafe", "stage approval: verified stage or intent is invalid"),
        ):
            with self.subTest(branch=branch), patch(
                "app_contracts.stage_approval.run_controlled_local_publication"
            ) as controlled:
                with self.assertRaisesRegex(StageApprovalError, f"^{message}$"):
                    run_local_mock_publication(artifact, digest, branch, "master", now=now)
                controlled.assert_not_called()

        tampered = self.get_artifact()
        object.__setattr__(tampered, "canonical_payload", "{}")
        with patch("app_contracts.stage_approval.run_controlled_local_publication") as controlled:
            with self.assertRaisesRegex(
                StageApprovalError, "^stage approval: verified stage or intent is invalid$"
            ):
                run_local_mock_publication(
                    tampered,
                    tampered.staged_change_digest,
                    "agent/safe",
                    "master",
                    now=now,
                )
            controlled.assert_not_called()

    def test_cli_persists_exact_typed_confirmation_and_mock_receipt_only(self):
        artifact = self.get_artifact()
        with tempfile.TemporaryDirectory(prefix="stage-approval-cli-") as temporary:
            database = Path(temporary) / "stage.sqlite3"
            confirmation_database = Path(temporary) / "confirmation.sqlite3"
            with SQLiteStagedArtifactStore(database) as store:
                store.save(artifact)
            db_before = database.read_bytes()
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("builtins.input", return_value=artifact.staged_change_digest):
                real_mock = run_local_mock_publication

                def invoke_mock(*args, **kwargs):
                    with closing(sqlite3.connect(confirmation_database)) as connection:
                        rows = connection.execute(
                            "SELECT status, staged_change_digest, intent_digest "
                            "FROM operator_confirmations"
                        ).fetchall()
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0][0], "confirmed")
                    self.assertEqual(rows[0][1], artifact.staged_change_digest)
                    self.assertRegex(rows[0][2], r"^sha256:[0-9a-f]{64}$")
                    return real_mock(*args, **kwargs)

                with patch(
                    "app_contracts.stage_approval.run_local_mock_publication",
                    side_effect=invoke_mock,
                ):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = main(self.cli_args(
                            database,
                            confirmation_database,
                            artifact,
                            "agent/cli-mock-review",
                        ))
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            lines = stdout.getvalue().splitlines()
            preview = json.loads("\n".join(lines[:-1]))
            receipt = json.loads(lines[-1])
            self.assertEqual(preview["stage"]["staged_change_digest"], artifact.staged_change_digest)
            self.assertEqual(preview["requested_action"]["branch"], "agent/cli-mock-review")
            self.assertEqual(preview["requested_action"]["external_write"], False)
            self.assertEqual(
                preview["requested_action"]["destination"],
                "in-memory MockGitHubEndpoint only",
            )
            self.assertEqual(receipt["staged_change_digest"], artifact.staged_change_digest)
            self.assertEqual(receipt["branch"], "agent/cli-mock-review")
            self.assertEqual(receipt["external_write"], False)
            self.assertEqual(receipt["confirmation_record_persisted"], True)
            self.assertEqual(receipt["authenticated"], False)
            self.assertNotIn("approved_intent_digest", stdout.getvalue())
            self.assertNotIn("approval_id", stdout.getvalue())
            self.assertEqual(database.read_bytes(), db_before)
            self.assertTrue(confirmation_database.is_file())
            with SQLiteOperatorConfirmationStore(confirmation_database) as store:
                record = store.load(receipt["confirmation_record_id"])
                with self.assertRaisesRegex(
                    OperatorConfirmationStoreError,
                    "^operator confirmation: record transition is invalid$",
                ):
                    store.complete_mock(record.confirmation_id, record.mock_receipt_id)
            self.assertEqual(record.status, "mock_completed")
            self.assertEqual(record.mock_receipt_id, receipt["mock_pull_request_id"])
            self.assertEqual(record.staged_change_digest, artifact.staged_change_digest)
            self.assertEqual(record.repository_id, "FixtureOwner/stage-fixture")
            self.assertEqual(record.branch, "agent/cli-mock-review")
            self.assertEqual(record.operation, "publish_pull_request")
            self.assertEqual(record.confirmation_mode, "typed-digest-local-mock")
            self.assertIs(record.authenticated, False)
            self.assertEqual(
                record.intent_digest,
                json.loads("\n".join(lines[:-1]))["requested_action"]["intent_digest"],
            )
            self.assertEqual(
                (datetime.fromisoformat(record.expires_at)
                 - datetime.fromisoformat(record.confirmed_at)).total_seconds(),
                300,
            )

    def test_cli_mismatch_cancellation_and_missing_db_never_start_mock_path(self):
        artifact = self.get_artifact()
        with tempfile.TemporaryDirectory(prefix="stage-approval-refusal-") as temporary:
            database = Path(temporary) / "stage.sqlite3"
            confirmation_database = Path(temporary) / "confirmation.sqlite3"
            with SQLiteStagedArtifactStore(database) as store:
                store.save(artifact)
            with patch("app_contracts.stage_approval.run_controlled_local_publication") as mock_run:
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch("builtins.input", return_value="not-the-digest"):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = main(self.cli_args(
                            database, confirmation_database, artifact, "agent/no-publish"
                        ))
                self.assertEqual(exit_code, 2)
                self.assertIn("stage approval: digest confirmation mismatch", stderr.getvalue())
                mock_run.assert_not_called()
                self.assertFalse(confirmation_database.exists())

                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(
                        self.cli_args(
                            Path(temporary) / "missing.sqlite3",
                            confirmation_database,
                            artifact,
                            "agent/no-publish",
                        )
                    )
                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout.getvalue(), "")
                mock_run.assert_not_called()

                stdout, stderr = io.StringIO(), io.StringIO()
                with patch("builtins.input", side_effect=EOFError):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = main(self.cli_args(
                            database, confirmation_database, artifact, "agent/no-publish"
                        ))
                self.assertEqual(exit_code, 2)
                self.assertIn("stage approval: confirmation cancelled", stderr.getvalue())
                mock_run.assert_not_called()
                self.assertFalse(confirmation_database.exists())

    def test_cli_rejects_same_database_for_stage_and_confirmation(self):
        artifact = self.get_artifact()
        with tempfile.TemporaryDirectory(prefix="stage-approval-alias-") as temporary:
            database = Path(temporary) / "stage.sqlite3"
            with SQLiteStagedArtifactStore(database) as store:
                store.save(artifact)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("builtins.input") as prompt:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(self.cli_args(
                        database, database, artifact, "agent/no-alias"
                    ))
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("confirmation database must be separate", stderr.getvalue())
            prompt.assert_not_called()

    def test_cli_rejects_invalid_intent_and_corrupt_confirmation_store(self):
        artifact = self.get_artifact()
        with tempfile.TemporaryDirectory(prefix="stage-approval-corrupt-") as temporary:
            stage_database = Path(temporary) / "stage.sqlite3"
            with SQLiteStagedArtifactStore(stage_database) as store:
                store.save(artifact)

            confirmation_database = Path(temporary) / "confirmation.sqlite3"
            with closing(sqlite3.connect(confirmation_database)) as connection, connection:
                connection.execute("CREATE TABLE operator_confirmations (wrong TEXT)")

            with patch("app_contracts.stage_approval.run_local_mock_publication") as mock_run:
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch("builtins.input", return_value=artifact.staged_change_digest):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = main(self.cli_args(
                            stage_database,
                            confirmation_database,
                            artifact,
                            "agent/corrupt-store",
                        ))
                self.assertEqual(exit_code, 2)
                self.assertIn("operator confirmation: schema is malformed", stderr.getvalue())
                mock_run.assert_not_called()
                with closing(sqlite3.connect(confirmation_database)) as connection:
                    self.assertEqual(
                        connection.execute("PRAGMA user_version").fetchone()[0], 0
                    )

                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(self.cli_args(
                        stage_database,
                        Path(temporary) / "invalid-intent.sqlite3",
                        artifact,
                        "unsafe/branch",
                    ))
                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout.getvalue(), "")
                mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
