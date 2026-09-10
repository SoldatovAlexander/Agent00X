from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.mock_github import MockGitHubEndpoint, MockPullRequest
from app_contracts.publication import (
    PublicationJournal,
    PublicationRecoveryRequired,
    SimulatedCrash,
    execute_publication,
    recover_publication,
)


class PublicationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="app-publication-test-")
        self.database = Path(self.temporary_directory.name) / "publication.sqlite3"
        self.endpoint = MockGitHubEndpoint()
        self.request = {
            "process_id": "process-publication-001",
            "operation": "publish_pull_request",
            "repository_id": "github-installation/42/repository/1001",
            "branch": "agent/process-publication-001",
            "staged_change_digest": "sha256:" + "a" * 64,
            "idempotency_key": "publish/process-publication-001/sha256:" + "a" * 64,
            "policy_effect": "allow",
            "approval_valid": True,
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _prepare(self, journal: PublicationJournal) -> None:
        journal.prepare(
            self.request["process_id"],
            idempotency_key=self.request["idempotency_key"],
            request_digest="sha256:" + "b" * 64,
        )

    def test_conflict_errors_carry_no_injected_values(self):
        with PublicationJournal(self.database) as journal:
            journal.prepare(
                "process-evil-caller-secret-001",
                idempotency_key="publish/evil-caller-secret-002/sha256:" + "d" * 64,
                request_digest="sha256:" + "e" * 64,
            )
            with self.assertRaisesRegex(ValueError, "^publication payload conflict$") as first:
                journal.prepare(
                    "process-evil-caller-secret-001",
                    idempotency_key="publish/evil-caller-secret-002/sha256:" + "d" * 64,
                    request_digest="sha256:" + "f" * 64,
                )
            self.assertNotIn("caller-secret", str(first.exception))
            with self.assertRaisesRegex(ValueError, "^publication payload conflict$") as second:
                journal.prepare(
                    "process-other-003",
                    idempotency_key="publish/evil-caller-secret-002/sha256:" + "d" * 64,
                    request_digest="sha256:" + "e" * 64,
                )
            self.assertNotIn("caller-secret", str(second.exception))

    def test_identical_prepare_replay_returns_existing_record(self):
        with PublicationJournal(self.database) as journal:
            self._prepare(journal)
            replayed = journal.prepare(
                self.request["process_id"],
                idempotency_key=self.request["idempotency_key"],
                request_digest="sha256:" + "b" * 64,
            )
            self.assertEqual(replayed.status, "prepared")
            self.assertEqual(replayed.request_digest, "sha256:" + "b" * 64)

    def test_conflicting_digest_prepare_is_rejected_without_second_record(self):
        with PublicationJournal(self.database) as journal:
            self._prepare(journal)
            with self.assertRaisesRegex(ValueError, "payload conflict"):
                journal.prepare(
                    self.request["process_id"],
                    idempotency_key=self.request["idempotency_key"],
                    request_digest="sha256:" + "c" * 64,
                )
            record = journal.get(self.request["process_id"])
            self.assertEqual(record.request_digest, "sha256:" + "b" * 64)
            self.assertEqual(record.status, "prepared")
            self.assertIsNone(self.endpoint.find_by_idempotency_key(self.request["idempotency_key"]))

    def test_invalid_status_transitions_change_nothing(self):
        with PublicationJournal(self.database) as journal:
            self._prepare(journal)
            before = journal.get(self.request["process_id"])
            with self.assertRaises(ValueError) as first:
                journal.mark_completed(
                    self.request["process_id"],
                    MockPullRequest(
                        9, self.request["repository_id"], self.request["branch"],
                        self.request["staged_change_digest"], self.request["idempotency_key"],
                    ),
                )
            self.assertIn("not attempting", str(first.exception))
            with self.assertRaises(ValueError):
                journal.mark_reconciliation_required(self.request["process_id"])
            self.assertEqual(journal.get(self.request["process_id"]), before)
            journal.mark_attempting(self.request["process_id"])
            mid = journal.get(self.request["process_id"])
            with self.assertRaises(ValueError):
                journal.mark_attempting(self.request["process_id"])
            self.assertEqual(journal.get(self.request["process_id"]), mid)
            leaked = str(first.exception)
            self.assertNotIn(self.request["idempotency_key"], leaked)
            self.assertNotIn(self.request["staged_change_digest"], leaked)

    def test_crash_before_external_call_remains_explicitly_retryable(self):
        with PublicationJournal(self.database) as journal:
            self._prepare(journal)
            recovered = recover_publication(journal, self.endpoint, self.request["process_id"])
            self.assertEqual(recovered.status, "prepared")
            self.assertIsNone(self.endpoint.find_by_idempotency_key(self.request["idempotency_key"]))

    def test_crash_after_external_effect_recovers_without_second_publish(self):
        journal = PublicationJournal(self.database)
        self._prepare(journal)
        with self.assertRaises(SimulatedCrash):
            execute_publication(journal, self.endpoint, self.request, crash_after_external_effect=True)
        journal.close()

        with PublicationJournal(self.database) as reopened:
            recovered = recover_publication(reopened, self.endpoint, self.request["process_id"])
            self.assertEqual(recovered.status, "completed")
            self.assertEqual(recovered.pull_request_id, 1)
            self.assertEqual(self.endpoint.find_by_idempotency_key(self.request["idempotency_key"]).pull_request_id, 1)

    def test_repeated_unknown_recovery_creates_no_side_effect_and_leaks_nothing(self):
        with PublicationJournal(self.database) as journal:
            self._prepare(journal)
            journal.mark_attempting(self.request["process_id"])
            with self.assertRaises(PublicationRecoveryRequired) as first:
                recover_publication(journal, self.endpoint, self.request["process_id"])
            self.assertEqual(first.exception.args, (self.request["process_id"],))
            for _ in range(2):
                with self.assertRaises(PublicationRecoveryRequired):
                    recover_publication(journal, self.endpoint, self.request["process_id"])
            self.assertEqual(journal.get(self.request["process_id"]).status, "reconciliation_required")
            self.assertIsNone(self.endpoint.find_by_idempotency_key(self.request["idempotency_key"]))

    def test_unknown_attempt_requires_reconciliation_without_retry(self):
        with PublicationJournal(self.database) as journal:
            self._prepare(journal)
            journal.mark_attempting(self.request["process_id"])
            with self.assertRaises(PublicationRecoveryRequired):
                recover_publication(journal, self.endpoint, self.request["process_id"])
            self.assertEqual(journal.get(self.request["process_id"]).status, "reconciliation_required")
            self.assertIsNone(self.endpoint.find_by_idempotency_key(self.request["idempotency_key"]))


if __name__ == "__main__":
    unittest.main()
