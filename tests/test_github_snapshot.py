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
    GitHubTreeClaim,
    GitHubTreeEntry,
    parse_github_commit,
    parse_github_tree,
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


def valid_tree_response(**overrides):
    response = {
        "sha": VALID_TREE_OID,
        "truncated": False,
        "tree": [
            {
                "path": "calculator.py",
                "mode": "100644",
                "type": "blob",
                "sha": "c" * 40,
                "size": 128,
                "url": "https://api.github.com/placeholder",
            },
            {
                "path": "tests",
                "mode": "040000",
                "type": "tree",
                "sha": "d" * 40,
                "url": "https://api.github.com/placeholder",
            },
            {
                "path": "tests/test_calculator.py",
                "mode": "100755",
                "type": "blob",
                "sha": "e" * 40,
            },
        ],
        "url": "https://api.github.com/placeholder",
    }
    response.update(overrides)
    return response


class TreeResponseBindingTests(unittest.TestCase):
    def test_complete_response_binds_exact_tree_claim(self):
        claim = parse_github_tree(valid_claim(), valid_tree_response())
        self.assertEqual(claim.owner, VALID_OWNER)
        self.assertEqual(claim.tree_oid, VALID_TREE_OID)
        self.assertEqual(claim.evidence_origin, "github_rest_api_claim")
        self.assertEqual(
            claim.entries,
            (
                GitHubTreeEntry(path="calculator.py", mode="100644", entry_type="blob", sha="c" * 40),
                GitHubTreeEntry(path="tests", mode="040000", entry_type="tree", sha="d" * 40),
                GitHubTreeEntry(
                    path="tests/test_calculator.py", mode="100755",
                    entry_type="blob", sha="e" * 40,
                ),
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            claim.entries = ()  # type: ignore[misc]

    def test_truncated_or_sha_mismatched_response_fails_closed(self):
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: tree response is incomplete$"
        ):
            parse_github_tree(valid_claim(), valid_tree_response(truncated=True))
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: tree response is incomplete$"
        ):
            parse_github_tree(
                valid_claim(),
                {key: value for key, value in valid_tree_response().items()
                 if key != "truncated"},
            )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: tree OID mismatch$"
        ) as raised:
            parse_github_tree(valid_claim(), valid_tree_response(sha="f" * 40))
        self.assertNotIn("f" * 40, str(raised.exception))

    def test_malformed_response_shape_fails_closed(self):
        for response in (None, [], "tree", {}, {"sha": VALID_TREE_OID}):
            with self.subTest(response=repr(response)[:40]):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: tree response is invalid$",
                ):
                    parse_github_tree(valid_claim(), response)
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: commit claim is invalid$"
        ):
            parse_github_tree({"tree_oid": VALID_TREE_OID}, valid_tree_response())

    def test_unsafe_or_unsupported_entries_fail_closed_without_echo(self):
        canary = "TREE-CANARY-SECRET"
        base_entry = {"path": "ok.py", "mode": "100644", "type": "blob", "sha": "c" * 40}
        malformed_entries = [
            None, "entry", {},
            {**base_entry, "mode": "120000"},
            {**base_entry, "mode": "160000"},
            {**base_entry, "mode": "040755"},
            {**base_entry, "mode": "644"},
            {**base_entry, "mode": None},
            {**base_entry, "type": "commit"},
            {**base_entry, "type": "symlink"},
            {**base_entry, "mode": "040000", "type": "blob"},
            {**base_entry, "mode": "100644", "type": "tree"},
            {**base_entry, "sha": "C" * 40},
            {**base_entry, "sha": "short"},
            {**base_entry, "path": ""},
            {**base_entry, "path": "/absolute.py"},
            {**base_entry, "path": "../escape.py"},
            {**base_entry, "path": "a//b.py"},
            {**base_entry, "path": "a/./b.py"},
            {**base_entry, "path": "a\\b.py"},
            {**base_entry, "path": "p" * 238 + ".py"},
            {**base_entry, "size": -1},
            {**base_entry, "size": 100_001},
            {**base_entry, "size": "128"},
            {**base_entry, "size": True},
            {**base_entry, "path": f"../{canary}.py"},
        ]
        for entry in malformed_entries:
            with self.subTest(entry=repr(entry)[:50]):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: tree entry is invalid$",
                ) as raised:
                    parse_github_tree(valid_claim(), valid_tree_response(tree=[entry]))
                self.assertNotIn(canary, str(raised.exception))

    def test_duplicate_paths_are_rejected(self):
        base_entry = {"path": "dup.py", "mode": "100644", "type": "blob", "sha": "c" * 40}
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: tree entry is invalid$"
        ):
            parse_github_tree(
                valid_claim(), valid_tree_response(tree=[base_entry, dict(base_entry)])
            )

    def test_entry_count_boundary(self):
        entries = [
            {"path": f"file-{index:05d}.py", "mode": "100644", "type": "blob",
             "sha": "c" * 40}
            for index in range(10_000)
        ]
        claim = parse_github_tree(valid_claim(), valid_tree_response(tree=entries))
        self.assertEqual(len(claim.entries), 10_000)
        entries.append(
            {"path": "file-10000.py", "mode": "100644", "type": "blob", "sha": "c" * 40}
        )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: tree response is invalid$"
        ):
            parse_github_tree(valid_claim(), valid_tree_response(tree=entries))


if __name__ == "__main__":
    unittest.main()
