from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.github_snapshot import (
    GitHubCommitClaim,
    GitHubSnapshotError,
    GitHubSnapshotRequest,
    parse_github_commit,
)
import app_contracts.github_snapshot as snapshot_module


VALID_OWNER = "octo-org"
VALID_REPOSITORY = "hello-world_2.0"
VALID_COMMIT_OID = "a" * 40
VALID_TREE_OID = "b" * 40


def valid_request(**overrides):
    fields = {
        "owner": VALID_OWNER,
        "repository": VALID_REPOSITORY,
        "commit_oid": VALID_COMMIT_OID,
    }
    fields.update(overrides)
    return GitHubSnapshotRequest(**fields)


def valid_claim(**overrides):
    fields = {
        "owner": VALID_OWNER,
        "repository": VALID_REPOSITORY,
        "commit_oid": VALID_COMMIT_OID,
        "tree_oid": VALID_TREE_OID,
    }
    fields.update(overrides)
    return GitHubCommitClaim(**fields)


class SnapshotClaimRecordTests(unittest.TestCase):
    def test_records_carry_only_bounded_claim_fields(self):
        request = valid_request()
        claim = valid_claim()
        self.assertEqual(
            set(GitHubSnapshotRequest.__dataclass_fields__),
            {"owner", "repository", "commit_oid", "evidence_origin"},
        )
        self.assertEqual(
            set(GitHubCommitClaim.__dataclass_fields__),
            {"owner", "repository", "commit_oid", "tree_oid", "evidence_origin"},
        )
        self.assertEqual(request.evidence_origin, "github_rest_api_claim")
        self.assertEqual(claim.evidence_origin, "github_rest_api_claim")
        with self.assertRaises(FrozenInstanceError):
            request.commit_oid = "c" * 40  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            claim.tree_oid = "d" * 40  # type: ignore[misc]

    def test_repr_names_no_trust_and_holds_no_secrets_or_payloads(self):
        serialized = repr((valid_request(), valid_claim()))
        for forbidden in (
            "verified", "trusted", "http", "token", "credential", "secret",
            "raw", "BEGIN", "stdout",
        ):
            self.assertNotIn(forbidden, serialized)
        source = Path(snapshot_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("http", source.lower())
        self.assertNotIn("://", source)

    def test_malformed_repository_identities_fail_closed_without_echo(self):
        canary = "REPO-CANARY-SECRET"
        malformed_owners = (
            None, 42, "", " leading", "trailing ", "-leading", "trailing-",
            "has space", "has/slash", "under_score", "toolong" + "x" * 40,
            f"evil {canary}",
        )
        for owner in malformed_owners:
            with self.subTest(owner=repr(owner)[:40]):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: repository identity is invalid$",
                ) as raised:
                    valid_request(owner=owner)
                self.assertNotIn(canary, str(raised.exception))
        malformed_repositories = (
            None, 42, "", "has space", "has/slash", "x" * 101,
            f"repo/{canary}",
        )
        for repository in malformed_repositories:
            with self.subTest(repository=repr(repository)[:40]):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: repository identity is invalid$",
                ) as raised:
                    valid_request(repository=repository)
                self.assertNotIn(canary, str(raised.exception))

    def test_malformed_oids_fail_closed_without_echo(self):
        canary = "OID-CANARY-SECRET"
        malformed = (
            None, 42, "", "a" * 39, "a" * 41, "A" * 40, "g" * 40,
            "a" * 64, " not-hex" + "a" * 33, f"{canary}",
        )
        for oid in malformed:
            with self.subTest(oid=repr(oid)[:40]):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: commit OID is invalid$",
                ) as raised:
                    valid_request(commit_oid=oid)
                self.assertNotIn(canary, str(raised.exception))
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: tree OID is invalid$",
                ) as raised:
                    valid_claim(tree_oid=oid)
                self.assertNotIn(canary, str(raised.exception))

    def test_evidence_origin_is_fixed(self):
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: evidence origin is invalid$"
        ):
            GitHubSnapshotRequest(
                owner=VALID_OWNER, repository=VALID_REPOSITORY,
                commit_oid=VALID_COMMIT_OID, evidence_origin="local_test",
            )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: evidence origin is invalid$"
        ):
            GitHubCommitClaim(
                owner=VALID_OWNER, repository=VALID_REPOSITORY,
                commit_oid=VALID_COMMIT_OID, tree_oid=VALID_TREE_OID,
                evidence_origin="local_test",
            )


def valid_commit_response(**overrides):
    response = {
        "sha": VALID_COMMIT_OID,
        "commit": {
            "message": "fixture commit",
            "tree": {"sha": VALID_TREE_OID},
            "author": {"name": "Fixture Author", "email": "author@example.invalid"},
            "committer": {"name": "Fixture Committer", "email": "committer@example.invalid"},
            "verification": {"verified": True, "reason": "valid", "signature": "fixture-sig"},
        },
        "parents": [{"sha": "c" * 40}],
    }
    response.update(overrides)
    return response


class CommitResponseBindingTests(unittest.TestCase):
    def test_matching_response_binds_exact_claim(self):
        claim = parse_github_commit(valid_request(), valid_commit_response())
        self.assertEqual(
            claim,
            GitHubCommitClaim(
                owner=VALID_OWNER, repository=VALID_REPOSITORY,
                commit_oid=VALID_COMMIT_OID, tree_oid=VALID_TREE_OID,
            ),
        )
        self.assertEqual(claim.evidence_origin, "github_rest_api_claim")

    def test_missing_or_malformed_fields_fail_closed(self):
        malformed = (
            None, [], "response",
            {},
            {"sha": VALID_COMMIT_OID},
            {"sha": None, "commit": {"tree": {"sha": VALID_TREE_OID}}},
            {"sha": "short", "commit": {"tree": {"sha": VALID_TREE_OID}}},
            {"sha": "A" * 40, "commit": {"tree": {"sha": VALID_TREE_OID}}},
            {"sha": VALID_COMMIT_OID, "commit": None},
            {"sha": VALID_COMMIT_OID, "commit": {"tree": None}},
            {"sha": VALID_COMMIT_OID, "commit": {"tree": {"sha": "xyz"}}},
            {"sha": VALID_COMMIT_OID, "commit": {"tree": {}}},
        )
        for response in malformed:
            with self.subTest(response=repr(response)[:50]):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: commit response is invalid$",
                ):
                    parse_github_commit(valid_request(), response)

    def test_mismatched_commit_oid_is_rejected_without_echo(self):
        canary = "COMMIT-CANARY-SECRET"
        foreign = dict(
            valid_commit_response(),
            sha="f" * 40,
            commit={
                "message": canary,
                "tree": {"sha": VALID_TREE_OID},
            },
        )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: commit OID mismatch$"
        ) as raised:
            parse_github_commit(valid_request(), foreign)
        self.assertNotIn(canary, str(raised.exception))
        self.assertNotIn("f" * 40, str(raised.exception))

    def test_signature_metadata_never_elevates_the_claim(self):
        for verification in (
            {"verified": True, "reason": "valid", "signature": "fixture-valid-sig"},
            {"verified": False, "reason": "unsigned", "signature": None},
            {"verified": "yes", "reason": 42},
        ):
            with self.subTest(verification=repr(verification)[:40]):
                response = dict(
                    valid_commit_response(),
                    commit={**valid_commit_response()["commit"], "verification": verification},
                )
                claim = parse_github_commit(valid_request(), response)
                self.assertEqual(claim.tree_oid, VALID_TREE_OID)
                self.assertNotIn("verification", GitHubCommitClaim.__dataclass_fields__)
                self.assertNotIn("author", GitHubCommitClaim.__dataclass_fields__)

    def test_non_request_input_is_rejected(self):
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: request shape is invalid$"
        ):
            parse_github_commit({"commit_oid": VALID_COMMIT_OID}, valid_commit_response())


if __name__ == "__main__":
    unittest.main()
