from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitHubCommitClaim,
    GitCommitObject,
    GitHubSnapshotClaim,
    GitHubSnapshotContents,
    GitHubSnapshotError,
    GitHubSnapshotRequest,
    GitHubTreeClaim,
    GitHubTreeEntry,
    parse_github_blob,
    parse_github_commit,
    parse_git_commit_object,
    parse_github_tree,
    read_github_snapshot,
    read_github_snapshot_contents,
    read_github_snapshot_metadata,
)
import app_contracts.github_snapshot as snapshot_module
from app_contracts.pinned_snapshot import MAX_SNAPSHOT_FILE_BYTES, MAX_SNAPSHOT_TOTAL_BYTES


VALID_OWNER = "octo-org"
VALID_REPOSITORY = "hello-world_2.0"
VALID_COMMIT_OID = "a" * 40


def git_tree_oid(entries):
    import hashlib

    payload = b"".join(
        entry["mode"].encode("ascii") + b" " + entry["path"].encode("utf-8")
        + b"\0" + bytes.fromhex(entry["sha"])
        for entry in sorted(
            entries,
            key=lambda entry: entry["path"].encode("utf-8")
            + (b"/" if entry["type"] == "tree" else b""),
        )
    )
    return hashlib.sha1(
        b"tree " + str(len(payload)).encode("ascii") + b"\0" + payload
    ).hexdigest()


def complete_tree_listing(blob_entries):
    entries = {entry["path"]: dict(entry) for entry in blob_entries}
    directories = {
        "/".join(parts[:index])
        for entry in blob_entries
        for parts in [entry["path"].split("/")]
        for index in range(1, len(parts))
    }
    for directory in sorted(directories, key=lambda path: path.count("/"), reverse=True):
        prefix = directory + "/"
        children = []
        for path, entry in entries.items():
            if path.startswith(prefix):
                name = path[len(prefix):]
                if "/" not in name:
                    children.append({
                        **entry, "path": name,
                        "mode": "40000" if entry["type"] == "tree" else entry["mode"],
                    })
        entries[directory] = {
            "path": directory, "mode": "040000", "type": "tree",
            "sha": git_tree_oid(children),
        }
    root_children = [
        {**entry, "mode": "40000" if entry["type"] == "tree" else entry["mode"]}
        for path, entry in entries.items() if "/" not in path
    ]
    return sorted(entries.values(), key=lambda entry: entry["path"]), git_tree_oid(root_children)


def _valid_tree_listing():
    nested_oid = git_tree_oid([
        {"path": "test_calculator.py", "mode": "100755", "type": "blob", "sha": "e" * 40}
    ])
    entries = [
        {"path": "calculator.py", "mode": "100644", "type": "blob", "sha": "c" * 40, "size": 128},
        {"path": "tests", "mode": "040000", "type": "tree", "sha": nested_oid},
        {"path": "tests/test_calculator.py", "mode": "100755", "type": "blob", "sha": "e" * 40},
    ]
    return entries, git_tree_oid([
        {**entry, "mode": "40000"} if entry["type"] == "tree" else entry
        for entry in entries if "/" not in entry["path"]
    ])


VALID_TREE_ENTRIES, VALID_TREE_OID = _valid_tree_listing()


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
            {"owner", "repository", "commit_oid", "include_paths", "evidence_origin"},
        )
        self.assertEqual(
            set(GitHubCommitClaim.__dataclass_fields__),
            {"owner", "repository", "commit_oid", "tree_oid", "evidence_origin"},
        )
        self.assertEqual(request.evidence_origin, "github_rest_api_claim")
        self.assertEqual(claim.evidence_origin, "github_rest_api_claim")
        self.assertIsNone(request.include_paths)
        self.assertEqual(
            set(GitHubSnapshotClaim.__dataclass_fields__),
            {
                "owner", "repository", "commit_oid", "tree_oid",
                "content_digest", "selected_paths", "evidence_origin",
            },
        )
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
        self.assertEqual(source.count("https://"), 1)
        self.assertIn('_GITHUB_API_BASE = "https://api.github.com"', source)
        self.assertNotIn("http://", source)

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
            None, 42, "", ".", "..", "has space", "has/slash", "x" * 101,
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

    def test_dot_segment_slugs_are_rejected_without_over_blocking(self):
        for slug in (".", ".."):
            with self.subTest(slug=slug):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: repository identity is invalid$",
                ):
                    valid_request(repository=slug)
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: repository identity is invalid$",
                ):
                    valid_request(owner=slug)
        dotted = valid_request(repository="...")
        self.assertEqual(dotted.repository, "...")
        claim = parse_github_commit(dotted, valid_commit_response())
        self.assertEqual(claim.repository, "...")

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


class GitCommitObjectTests(unittest.TestCase):
    @staticmethod
    def make_object(tree_oid: str, headers: bytes | None = None):
        object_headers = headers or (
            b"tree " + tree_oid.encode("ascii")
            + b"\nauthor Fixture <fixture@example.invalid> 1 +0000"
            + b"\ncommitter Fixture <fixture@example.invalid> 1 +0000"
        )
        raw = object_headers + b"\n\nfixture commit message\n"
        object_oid = hashlib.sha1(
            b"commit " + str(len(raw)).encode("ascii") + b"\0" + raw
        ).hexdigest()
        claim = GitHubCommitClaim(
            owner=VALID_OWNER,
            repository=VALID_REPOSITORY,
            commit_oid=object_oid,
            tree_oid=tree_oid,
        )
        return claim, raw

    def test_exact_git_object_hash_and_root_tree_are_verified(self):
        claim, raw = self.make_object(VALID_TREE_OID)

        parsed = parse_git_commit_object(claim, raw)

        self.assertEqual(
            parsed,
            GitCommitObject(commit_oid=claim.commit_oid, tree_oid=VALID_TREE_OID),
        )

    def test_hash_tree_and_header_mutations_fail_closed(self):
        claim, raw = self.make_object(VALID_TREE_OID)
        other_tree_claim = GitHubCommitClaim(
            owner=claim.owner,
            repository=claim.repository,
            commit_oid=claim.commit_oid,
            tree_oid="f" * 40,
        )
        malformed_claims_and_objects = (
            (claim, raw + b"mutation"),
            (other_tree_claim, raw),
            self.make_object(VALID_TREE_OID, b"author Fixture <fixture@example.invalid> 1 +0000"),
            self.make_object(
                VALID_TREE_OID,
                b"tree " + VALID_TREE_OID.encode() + b"\ntree " + VALID_TREE_OID.encode(),
            ),
            self.make_object("f" * 40, b"tree " + b"g" * 40),
        )
        for malformed_claim, malformed_raw in malformed_claims_and_objects:
            with self.subTest(size=len(malformed_raw)):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: commit object is invalid$",
                ):
                    parse_git_commit_object(malformed_claim, malformed_raw)

    def test_invalid_types_empty_and_over_limit_objects_are_rejected(self):
        claim, _raw = self.make_object(VALID_TREE_OID)
        for malformed in (None, bytearray(b"tree"), b"", b"x" * 1_000_001):
            with self.subTest(type=type(malformed).__name__, size=len(malformed or b"")):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: commit object is invalid$",
                ):
                    parse_git_commit_object(claim, malformed)


def valid_tree_response(**overrides):
    response = {
        "sha": VALID_TREE_OID,
        "truncated": False,
        "tree": [dict(entry) for entry in VALID_TREE_ENTRIES],
        "url": "https://api.github.com/placeholder",
    }
    response.update(overrides)
    if "tree" in overrides and "sha" not in overrides:
        try:
            raw = response["tree"]
            tree_entries = [entry for entry in raw if isinstance(entry, dict)]
            # Test fixture helper: infer directory object IDs from flat entries.
            for entry in sorted(tree_entries, key=lambda item: item.get("path", "").count("/"), reverse=True):
                if entry.get("type") != "tree" or not isinstance(entry.get("path"), str):
                    continue
                prefix = entry["path"] + "/"
                children = []
                for child in tree_entries:
                    if not child.get("path", "").startswith(prefix):
                        continue
                    remainder = child["path"][len(prefix):]
                    if "/" not in remainder:
                        children.append({**child, "path": remainder, "mode": "40000" if child.get("type") == "tree" else child.get("mode")})
                entry["sha"] = git_tree_oid(children)
            top = []
            for entry in tree_entries:
                path = entry.get("path", "")
                if isinstance(path, str) and "/" not in path:
                    top.append({**entry, "mode": "40000" if entry.get("type") == "tree" else entry.get("mode")})
            response["sha"] = git_tree_oid(top)
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
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
                GitHubTreeEntry(
                    path="calculator.py", mode="100644", entry_type="blob",
                    sha="c" * 40, size=128,
                ),
                GitHubTreeEntry(path="tests", mode="040000", entry_type="tree", sha=VALID_TREE_ENTRIES[1]["sha"]),
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

    def test_recursive_listing_recomputes_subtree_and_root_merkle_ids(self):
        response = valid_tree_response()
        claim = parse_github_tree(valid_claim(), response)
        # These fixed vectors were checked with Git's own hash-object encoder.
        self.assertEqual(
            VALID_TREE_ENTRIES[1]["sha"],
            "335d0fac008aa7ef093a25acfb77c30397e83d77",
        )
        self.assertEqual(VALID_TREE_OID, "05b1661e1312fd033a154412441e3d217aa0ac11")
        self.assertEqual(claim.tree_oid, VALID_TREE_OID)
        self.assertEqual(claim.evidence_origin, "github_rest_api_claim")

        mutations = (
            ("path", lambda entries: entries[2].update(path="tests/renamed.py")),
            ("mode", lambda entries: entries[2].update(mode="100644")),
            ("blob-oid", lambda entries: entries[2].update(sha="f" * 40)),
            ("missing-entry", lambda entries: entries.pop()),
            ("missing-tree", lambda entries: entries.pop(1)),
            ("subtree-oid", lambda entries: entries[1].update(sha="f" * 40)),
        )
        for label, mutate in mutations:
            with self.subTest(mutation=label):
                altered = valid_tree_response()
                altered_entries = [dict(entry) for entry in altered["tree"]]
                mutate(altered_entries)
                altered["tree"] = altered_entries
                with self.assertRaises(GitHubSnapshotError):
                    parse_github_tree(valid_claim(), altered)

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
            {**base_entry, "size": "128"},
            {**base_entry, "size": True},
            {**base_entry, "path": f"../{canary}.py"},
        ]
        for entry in malformed_entries:
            with self.subTest(entry=repr(entry)[:50]):
                response = valid_tree_response(tree=[entry])
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: tree entry is invalid$",
                ) as raised:
                    parse_github_tree(valid_claim(tree_oid=response["sha"]), response)
                self.assertNotIn(canary, str(raised.exception))

    def test_large_blob_size_is_preserved_as_tree_metadata(self):
        entry = {
            "path": "large.bin", "mode": "100644", "type": "blob",
            "sha": "c" * 40, "size": 100_001,
        }
        response = valid_tree_response(tree=[entry])
        claim = parse_github_tree(valid_claim(tree_oid=response["sha"]), response)
        self.assertEqual(claim.entries[0].size, 100_001)
        self.assertEqual(claim.entries[0].path, "large.bin")

    def test_duplicate_paths_are_rejected(self):
        base_entry = {"path": "dup.py", "mode": "100644", "type": "blob", "sha": "c" * 40}
        response = valid_tree_response(tree=[base_entry, dict(base_entry)])
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: tree entry is invalid$"
        ):
            parse_github_tree(valid_claim(tree_oid=response["sha"]), response)

    def test_entry_count_boundary(self):
        entries = [
            {"path": f"file-{index:05d}.py", "mode": "100644", "type": "blob",
             "sha": "c" * 40}
            for index in range(10_000)
        ]
        response = valid_tree_response(tree=entries)
        claim = parse_github_tree(valid_claim(tree_oid=response["sha"]), response)
        self.assertEqual(len(claim.entries), 10_000)
        entries.append(
            {"path": "file-10000.py", "mode": "100644", "type": "blob", "sha": "c" * 40}
        )
        response = valid_tree_response(tree=entries)
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: tree response is invalid$"
        ):
            parse_github_tree(valid_claim(tree_oid=response["sha"]), response)


def git_blob_sha(content: bytes) -> str:
    import hashlib as hashlib_module

    return hashlib_module.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()


def valid_blob_entry(content: bytes = b"print('ok')\n"):
    return GitHubTreeEntry(
        path="calculator.py", mode="100644", entry_type="blob",
        sha=git_blob_sha(content),
    )


def valid_blob_response(content: bytes = b"print('ok')\n", **overrides):
    import base64 as base64_module

    response = {
        "sha": git_blob_sha(content),
        "size": len(content),
        "encoding": "base64",
        "content": base64_module.b64encode(content).decode("ascii"),
    }
    response.update(overrides)
    return response, content


class BlobDecodeVerificationTests(unittest.TestCase):
    def test_bounded_single_blob_limit_supports_256_kib_with_aggregate_unchanged(self):
        import base64 as base64_module

        self.assertEqual(MAX_SNAPSHOT_FILE_BYTES, 262_144)
        self.assertEqual(MAX_SNAPSHOT_TOTAL_BYTES, 1_000_000)
        at_limit = b"a" * MAX_SNAPSHOT_FILE_BYTES
        response, _ = valid_blob_response(at_limit)
        entry = GitHubTreeEntry(
            path="asset.bin", mode="100644", entry_type="blob",
            sha=git_blob_sha(at_limit), size=len(at_limit),
        )
        accepted = parse_github_blob(entry, response)
        self.assertEqual(accepted.size, MAX_SNAPSHOT_FILE_BYTES)

        over_limit = b"a" * (MAX_SNAPSHOT_FILE_BYTES + 1)
        rejected_response, _ = valid_blob_response(over_limit)
        rejected_entry = GitHubTreeEntry(
            path="asset.bin", mode="100644", entry_type="blob",
            sha=git_blob_sha(over_limit), size=len(over_limit),
        )
        rejected_response["content"] = base64_module.b64encode(over_limit).decode("ascii")
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob size exceeds limit$"
        ):
            parse_github_blob(rejected_entry, rejected_response)

    def test_valid_text_and_binary_blobs_verify(self):
        for content in (b"print('ok')\n", bytes(range(256))):
            with self.subTest(size=len(content)):
                response, _ = valid_blob_response(content)
                claim = parse_github_blob(valid_blob_entry(content), response)
                self.assertEqual(claim.sha, git_blob_sha(content))
                self.assertEqual(claim.size, len(content))
                self.assertEqual(claim.content, content)
                self.assertEqual(claim.path, "calculator.py")
                self.assertEqual(claim.evidence_origin, "github_rest_api_claim")
                self.assertNotIn("content=", repr(claim))
                self.assertNotIn(repr(content), repr(claim))

    def test_invalid_encoding_or_base64_fails_closed(self):
        response, content = valid_blob_response()
        entry = valid_blob_entry(content)
        for override in (
            {"encoding": "utf-8"},
            {"encoding": None},
            {"content": "not base64!!!"},
            {"content": "aGVs bG8="},
            {"content": "aGVsbG8=\t"},
            {"content": 42},
            {"content": None},
        ):
            with self.subTest(override=repr(override)[:40]):
                tampered = dict(response, **override)
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: blob response is invalid$",
                ):
                    parse_github_blob(entry, tampered)
        for response in (None, [], "blob"):
            with self.subTest(response=repr(response)[:20]):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: blob response is invalid$",
                ):
                    parse_github_blob(entry, response)

    def test_lf_and_crlf_wrapped_base64_preserve_canonical_raw_bytes(self):
        import base64 as base64_module

        content = bytes(range(128))
        response, _ = valid_blob_response(content)
        encoded = response["content"]
        wrapped = encoded[:64] + "\n" + encoded[64:128] + "\r\n" + encoded[128:] + "\n"
        parsed = parse_github_blob(
            valid_blob_entry(content), dict(response, content=wrapped)
        )
        compact = parse_github_blob(valid_blob_entry(content), response)
        self.assertEqual(parsed.content, content)
        self.assertEqual(parsed.content_digest, compact.content_digest)
        self.assertEqual(parsed.sha, git_blob_sha(content))
        self.assertNotIn(base64_module.b64encode(content).decode("ascii"), repr(parsed))
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob entry is invalid$"
        ):
            parse_github_blob("not-an-entry", response)

    def test_size_and_sha_mismatch_fail_closed_without_echo(self):
        canary = "BLOB-CANARY-SECRET"
        content = f"payload with {canary} inside\n".encode("utf-8")
        response, _ = valid_blob_response(content)
        entry = valid_blob_entry(content)
        mismatched = [
            (dict(response, size=len(content) + 1),
             "^github snapshot: blob size mismatch$"),
            (dict(response, size="12"),
             "^github snapshot: blob size mismatch$"),
            (dict(response, sha="f" * 40),
             "^github snapshot: blob OID mismatch$"),
        ]
        for tampered, message in mismatched:
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                    GitHubSnapshotError, message
                ) as raised:
                    parse_github_blob(entry, tampered)
                self.assertNotIn(canary, str(raised.exception))
                self.assertNotIn("f" * 40, str(raised.exception))
        wrong_tree_size = GitHubTreeEntry(
            path=entry.path, mode=entry.mode, entry_type=entry.entry_type,
            sha=entry.sha, size=len(content) + 1,
        )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob size mismatch$"
        ):
            parse_github_blob(wrong_tree_size, response)

    def test_oversized_payload_fails_closed_before_full_decode(self):
        import base64 as base64_module

        wire_huge = {
            "sha": "f" * 40,
            "size": 1,
            "encoding": "base64",
            "content": "A" * (MAX_SNAPSHOT_FILE_BYTES * 2 + 1),
        }
        entry = valid_blob_entry()
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob size exceeds limit$"
        ):
            parse_github_blob(entry, wire_huge)
        big = b"Q" * (MAX_SNAPSHOT_FILE_BYTES + 1)
        oversized = {
            "sha": git_blob_sha(big),
            "size": len(big),
            "encoding": "base64",
            "content": base64_module.b64encode(big).decode("ascii"),
        }
        entry = GitHubTreeEntry(
            path="big.py", mode="100644", entry_type="blob",
            sha=git_blob_sha(big), size=len(big),
        )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob size exceeds limit$"
        ):
            parse_github_blob(entry, oversized)
        medium = b"M" * 60_000
        total_response, _ = valid_blob_response(medium)
        medium_entry = valid_blob_entry(medium)
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob contents exceed limit$"
        ):
            parse_github_blob(
                medium_entry, total_response, content_bytes_used=950_001
            )
        ok_claim = parse_github_blob(
            medium_entry, total_response, content_bytes_used=940_000
        )
        self.assertEqual(ok_claim.size, 60_000)


API_BASE = "https://api.github.com"
EXPECTED_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
}
READER_COMMIT_OID = "a" * 40
READER_TREE_OID = "b" * 40


class FakeTransport:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers, max_bytes, allow_redirects=False):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "max_bytes": max_bytes,
                "allow_redirects": allow_redirects,
            }
        )
        if (method, url) in self.routes:
            status, body = self.routes[(method, url)]
            return {"status": status, "body": body}
        return {"status": 404, "body": b"{}"}


def reader_fixture_routes(files, commit_oid=READER_COMMIT_OID, tree_oid=None):
    import base64 as base64_module
    import json as json_module

    owner, repository = VALID_OWNER, VALID_REPOSITORY
    entries = []
    blobs = {}
    for path, content, mode in files:
        blob_sha = git_blob_sha(content)
        if mode is not None:
            entries.append(
                {
                    "path": path, "mode": mode,
                    "type": "blob" if mode != "040000" else "tree",
                    "sha": blob_sha, "size": len(content),
                }
            )
        if mode != "040000":
            blobs[blob_sha] = {
                "sha": blob_sha, "size": len(content), "encoding": "base64",
                "content": base64_module.b64encode(content).decode("ascii"),
            }
    entries, computed_tree_oid = complete_tree_listing(entries)
    tree_oid = computed_tree_oid if tree_oid is None else tree_oid
    routes = {
        ("GET", f"{API_BASE}/repos/{owner}/{repository}/commits/{commit_oid}"): (
            200,
            json_module.dumps(
                {"sha": commit_oid, "commit": {"tree": {"sha": tree_oid}}}
            ).encode("utf-8"),
        ),
        ("GET", f"{API_BASE}/repos/{owner}/{repository}/git/trees/{tree_oid}?recursive=1"): (
            200,
            json_module.dumps(
                {"sha": tree_oid, "truncated": False, "tree": entries}
            ).encode("utf-8"),
        ),
    }
    for blob_sha, payload in blobs.items():
        routes[
            ("GET", f"{API_BASE}/repos/{owner}/{repository}/git/blobs/{blob_sha}")
        ] = (200, json_module.dumps(payload).encode("utf-8"))
    return routes


class SnapshotReaderCompositionTests(unittest.TestCase):
    def test_metadata_reader_uses_only_commit_and_complete_tree_gets(self):
        transport = FakeTransport(
            reader_fixture_routes(
                [
                    ("README.md", b"metadata only\n", "100644"),
                    ("scripts/run.sh", b"#!/bin/sh\n", "100755"),
                ]
            )
        )
        tree = read_github_snapshot_metadata(
            GitHubSnapshotRequest(
                owner=VALID_OWNER,
                repository=VALID_REPOSITORY,
                commit_oid=READER_COMMIT_OID,
            ),
            transport,
        )
        import json

        tree_body = next(
            body for (method, url), (_status, body) in transport.routes.items()
            if method == "GET" and "/git/trees/" in url
        )
        self.assertEqual(tree.tree_oid, json.loads(tree_body)["sha"])
        self.assertEqual(
            tuple((entry.path, entry.mode, entry.size) for entry in tree.entries if entry.entry_type == "blob"),
            (("README.md", "100644", len(b"metadata only\n")),
             ("scripts/run.sh", "100755", len(b"#!/bin/sh\n"))),
        )
        self.assertEqual(len(transport.calls), 2)
        self.assertTrue(all("/commits/" in call["url"] or "/git/trees/" in call["url"] for call in transport.calls))
        self.assertFalse(any("/git/blobs/" in call["url"] for call in transport.calls))
        self.assertTrue(all(call["method"] == "GET" for call in transport.calls))
        self.assertTrue(all(call["allow_redirects"] is False for call in transport.calls))

    def test_mock_transport_digest_matches_local_fixture_digest(self):
        import tempfile

        from app_contracts.pinned_snapshot import compute_snapshot_tree_digest

        calculator = b"print('ok')\n"
        readme = b"# Fixture\n"
        notes = b"nested notes\n"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "calculator.py").write_bytes(calculator)
            (root / "calculator.py").chmod(0o755)
            (root / "README.md").write_bytes(readme)
            (root / "docs").mkdir()
            (root / "docs" / "notes.txt").write_bytes(notes)
            expected = compute_snapshot_tree_digest(root)
            transport = FakeTransport(
                reader_fixture_routes(
                    [
                        ("README.md", readme, "100644"),
                        ("docs", b"", "040000"),
                        ("calculator.py", calculator, "100755"),
                        ("docs/notes.txt", notes, "100644"),
                    ]
                )
            )
            request = GitHubSnapshotRequest(
                owner=VALID_OWNER, repository=VALID_REPOSITORY,
                commit_oid=READER_COMMIT_OID,
            )
            claim = read_github_snapshot(request, transport)
            self.assertEqual(
                claim,
                GitHubSnapshotClaim(
                    owner=VALID_OWNER, repository=VALID_REPOSITORY,
                    commit_oid=READER_COMMIT_OID,
                    tree_oid=claim.tree_oid,
                    content_digest=expected,
                ),
            )
            self.assertEqual(claim.evidence_origin, "github_rest_api_claim")
            self.assertEqual(len(transport.calls), 5)
            for call in transport.calls:
                self.assertEqual(call["method"], "GET")
                self.assertIs(call["allow_redirects"], False)
                self.assertEqual(call["headers"], EXPECTED_HEADERS)
                self.assertTrue(call["url"].startswith(API_BASE + "/repos/"))
                self.assertIsInstance(call["max_bytes"], int)
                self.assertGreater(call["max_bytes"], 0)
            for header_key in transport.calls[0]["headers"]:
                self.assertNotIn("authoriz", header_key.lower())

    def test_contents_reader_retains_bounded_bytes_without_repr_leak(self):
        marker = b"snapshot-content-marker"
        transport = FakeTransport(
            reader_fixture_routes(
                [("README.md", marker, "100644"), ("run.sh", b"echo ok\n", "100755")]
            )
        )
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER,
            repository=VALID_REPOSITORY,
            commit_oid=READER_COMMIT_OID,
        )

        snapshot = read_github_snapshot_contents(request, transport)

        self.assertIsInstance(snapshot, GitHubSnapshotContents)
        self.assertEqual(snapshot.claim.evidence_origin, "github_rest_api_claim")
        self.assertEqual(
            [(blob.path, blob.mode, blob.content) for blob in snapshot.files],
            [("README.md", "100644", marker), ("run.sh", "100755", b"echo ok\n")],
        )
        self.assertEqual(
            snapshot.claim,
            read_github_snapshot(
                request,
                FakeTransport(
                    reader_fixture_routes(
                        [("README.md", marker, "100644"), ("run.sh", b"echo ok\n", "100755")]
                    )
                ),
            ),
        )
        self.assertNotIn(marker.decode(), repr(snapshot))
        self.assertNotIn("verified", repr(snapshot).lower())
        self.assertEqual(len(transport.calls), 4)
        for call in transport.calls:
            self.assertEqual(call["method"], "GET")
            self.assertIs(call["allow_redirects"], False)
            self.assertEqual(call["headers"], EXPECTED_HEADERS)

    def test_contents_reader_binds_raw_commit_object_before_tree_reads(self):
        import json

        content = b"print('synthetic snapshot')\n"
        files = [("src.py", content, "100644")]
        initial_routes = reader_fixture_routes(files, commit_oid="0" * 40)
        tree_url = next(
            url for method, url in initial_routes
            if method == "GET" and "/git/trees/" in url
        )
        tree_oid = json.loads(initial_routes[("GET", tree_url)][1])["sha"]
        raw_commit = (
            b"tree " + tree_oid.encode("ascii")
            + b"\nauthor Fixture <fixture@example.invalid> 1 +0000"
            + b"\ncommitter Fixture <fixture@example.invalid> 1 +0000"
            + b"\n\nsynthetic commit\n"
        )
        commit_oid = hashlib.sha1(
            b"commit " + str(len(raw_commit)).encode("ascii") + b"\0" + raw_commit
        ).hexdigest()
        transport = FakeTransport(
            reader_fixture_routes(files, commit_oid=commit_oid, tree_oid=tree_oid)
        )
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER,
            repository=VALID_REPOSITORY,
            commit_oid=commit_oid,
        )
        source_calls = []

        snapshot = read_github_snapshot_contents(
            request,
            transport,
            commit_object_source=lambda claim: source_calls.append(claim) or raw_commit,
        )

        self.assertEqual(len(source_calls), 1)
        self.assertEqual(snapshot.verified_commit_object.commit_oid, commit_oid)
        self.assertEqual(snapshot.verified_commit_object.tree_oid, tree_oid)
        self.assertEqual(len(transport.calls), 3)
        self.assertNotIn("synthetic commit", repr(snapshot))

    def test_invalid_raw_commit_object_stops_before_tree_and_blob_reads(self):
        content = b"print('synthetic snapshot')\n"
        transport = FakeTransport(reader_fixture_routes([("src.py", content, "100644")]))
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER,
            repository=VALID_REPOSITORY,
            commit_oid=READER_COMMIT_OID,
        )

        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: commit object is invalid$"
        ):
            read_github_snapshot_contents(
                request,
                transport,
                commit_object_source=lambda _claim: b"invalid commit bytes",
            )

        self.assertEqual(len(transport.calls), 1)

    def test_selected_paths_only_request_matching_blobs_and_remain_partial(self):
        secret_canary = b"SYNTHETIC-ENV-CANARY"
        files = [
            (".env", secret_canary, "100644"),
            ("backend/main.py", b"def main(): pass\n", "100644"),
            ("backend/routes.py", b"def routes(): pass\n", "100644"),
        ]
        transport = FakeTransport(reader_fixture_routes(files))
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER,
            repository=VALID_REPOSITORY,
            commit_oid=READER_COMMIT_OID,
            include_paths=("backend/main.py",),
        )

        snapshot = read_github_snapshot_contents(request, transport)

        self.assertFalse(snapshot.claim.full_snapshot)
        self.assertEqual(snapshot.claim.selected_paths, ("backend/main.py",))
        self.assertEqual(tuple(blob.path for blob in snapshot.files), ("backend/main.py",))
        self.assertEqual(
            snapshot.files[0].content,
            b"def main(): pass\n",
        )
        requested_urls = tuple(call["url"] for call in transport.calls)
        self.assertEqual(len(requested_urls), 3)
        self.assertTrue(any("/git/blobs/" in url for url in requested_urls))
        self.assertFalse(
            any(git_blob_sha(secret_canary) in url for url in requested_urls)
        )
        self.assertNotIn(secret_canary.decode(), repr(snapshot))
        self.assertEqual(
            read_github_snapshot(
                request,
                FakeTransport(reader_fixture_routes(files)),
            ).selected_paths,
            ("backend/main.py",),
        )

    def test_snapshot_contents_reject_credential_shaped_bytes_without_leak(self):
        secret_canary = b'password = "synthetic-password-value"\n'
        transport = FakeTransport(
            reader_fixture_routes([("backend/config.py", secret_canary, "100644")])
        )
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER,
            repository=VALID_REPOSITORY,
            commit_oid=READER_COMMIT_OID,
            include_paths=("backend/config.py",),
        )

        with self.assertRaisesRegex(
            GitHubSnapshotError,
            "^github snapshot: credential-shaped content detected$",
        ) as raised:
            read_github_snapshot_contents(request, transport)
        self.assertNotIn(secret_canary.decode().strip(), str(raised.exception))
        self.assertNotIn(secret_canary.decode().strip(), repr(transport))

    def test_selected_path_request_and_content_binding_reject_bad_sets(self):
        for include_paths in (
            (),
            ("../escape.py",),
            ("b.py", "a.py"),
            ("a.py", "a.py"),
            (["a.py"],),
        ):
            with self.subTest(include_paths=repr(include_paths)):
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: selected paths are invalid$",
                ):
                    GitHubSnapshotRequest(
                        owner=VALID_OWNER,
                        repository=VALID_REPOSITORY,
                        commit_oid=READER_COMMIT_OID,
                        include_paths=include_paths,
                    )

        files = [("a.py", b"print('a')\n", "100644")]
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: selected path is missing$"
        ):
            read_github_snapshot_contents(
                GitHubSnapshotRequest(
                    owner=VALID_OWNER,
                    repository=VALID_REPOSITORY,
                    commit_oid=READER_COMMIT_OID,
                    include_paths=("b.py",),
                ),
                FakeTransport(reader_fixture_routes(files)),
            )

        selected = read_github_snapshot_contents(
            GitHubSnapshotRequest(
                owner=VALID_OWNER,
                repository=VALID_REPOSITORY,
                commit_oid=READER_COMMIT_OID,
                include_paths=("a.py",),
            ),
            FakeTransport(reader_fixture_routes(files)),
        )
        inconsistent_claim = GitHubSnapshotClaim(
            owner=selected.claim.owner,
            repository=selected.claim.repository,
            commit_oid=selected.claim.commit_oid,
            tree_oid=selected.claim.tree_oid,
            content_digest=selected.claim.content_digest,
            selected_paths=("b.py",),
        )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: content selection mismatch$"
        ):
            GitHubSnapshotContents(inconsistent_claim, selected.files)

    def test_mutated_request_is_revalidated_before_transport(self):
        transport = FakeTransport({})
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER,
            repository=VALID_REPOSITORY,
            commit_oid=READER_COMMIT_OID,
            include_paths=("safe.py",),
        )
        object.__setattr__(request, "include_paths", ("../outside.py",))

        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: request shape is invalid$"
        ):
            read_github_snapshot_contents(request, transport)
        self.assertEqual(transport.calls, [])

    def test_contents_record_rejects_duplicate_unsorted_and_unbound_files(self):
        transport = FakeTransport(
            reader_fixture_routes(
                [("a.txt", b"a\n", "100644"), ("b.txt", b"b\n", "100644")]
            )
        )
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER,
            repository=VALID_REPOSITORY,
            commit_oid=READER_COMMIT_OID,
        )
        snapshot = read_github_snapshot_contents(request, transport)
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob OID mismatch$"
        ):
            GitHubBlobClaim(
                path=snapshot.files[0].path,
                mode=snapshot.files[0].mode,
                sha="0" * 40,
                size=snapshot.files[0].size,
                content=snapshot.files[0].content,
                content_digest=snapshot.files[0].content_digest,
            )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: content files are invalid$"
        ):
            GitHubSnapshotContents(snapshot.claim, tuple(reversed(snapshot.files)))
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: content files are invalid$"
        ):
            GitHubSnapshotContents(snapshot.claim, (snapshot.files[0], snapshot.files[0]))
        unbound = GitHubSnapshotClaim(
            owner=snapshot.claim.owner,
            repository=snapshot.claim.repository,
            commit_oid=snapshot.claim.commit_oid,
            tree_oid=snapshot.claim.tree_oid,
            content_digest="sha256:" + "0" * 64,
        )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: content digest mismatch$"
        ):
            GitHubSnapshotContents(unbound, snapshot.files)

    def test_declared_oversized_blob_stops_before_any_blob_request(self):
        small_content = b"small\n"
        large_content = b"L" * (MAX_SNAPSHOT_FILE_BYTES + 1)
        routes = reader_fixture_routes(
            [
                ("small.txt", small_content, "100644"),
                ("large.bin", large_content, "100644"),
            ]
        )
        transport = FakeTransport(routes)
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER, repository=VALID_REPOSITORY,
            commit_oid=READER_COMMIT_OID,
        )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob size exceeds limit$"
        ):
            read_github_snapshot(request, transport)
        self.assertEqual(len(transport.calls), 2)
        self.assertTrue(
            all("/git/blobs/" not in call["url"] for call in transport.calls)
        )

    def test_declared_oversized_blob_is_rejected_before_blob_decode(self):
        entry = GitHubTreeEntry(
            path="large.bin", mode="100644", entry_type="blob",
            sha="c" * 40, size=MAX_SNAPSHOT_FILE_BYTES + 1,
        )
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob size exceeds limit$"
        ):
            parse_github_blob(entry, None)

    def test_mismatch_and_incomplete_chain_yield_no_claim(self):
        import base64 as base64_module
        import json as json_module

        files = [("calculator.py", b"print('ok')\n", "100644")]
        tampered_content = b"print('forged')\n"
        tampered_blob = {
            "sha": git_blob_sha(files[0][1]),
            "size": len(tampered_content),
            "encoding": "base64",
            "content": base64_module.b64encode(tampered_content).decode("ascii"),
        }
        owner_url = f"{API_BASE}/repos/{VALID_OWNER}/{VALID_REPOSITORY}"
        blob_url = f"{owner_url}/git/blobs/{git_blob_sha(files[0][1])}"
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER, repository=VALID_REPOSITORY, commit_oid=READER_COMMIT_OID
        )
        base_routes = reader_fixture_routes(files)
        tampered_routes = dict(base_routes)
        tampered_routes[("GET", blob_url)] = (
            200, json_module.dumps(tampered_blob).encode("utf-8"),
        )
        tree_key = next(
            key for key in base_routes
            if key[0] == "GET" and "/git/trees/" in key[1]
        )
        tree_oid = tree_key[1].split("/git/trees/")[1].split("?")[0]
        truncated_payload = json_module.dumps(
            {"sha": tree_oid, "truncated": True, "tree": []}
        ).encode("utf-8")
        truncated_routes = dict(base_routes)
        truncated_routes[tree_key] = (200, truncated_payload)
        mismatched_payload = json_module.dumps(
            {"sha": "f" * 40, "commit": {"tree": {"sha": tree_oid}}}
        ).encode("utf-8")
        mismatched_routes = dict(base_routes)
        mismatched_routes[
            ("GET", f"{owner_url}/commits/{READER_COMMIT_OID}")
        ] = (200, mismatched_payload)
        for label, routes in (
            ("tampered-blob", tampered_routes),
            ("truncated-tree", truncated_routes),
            ("commit-mismatch", mismatched_routes),
        ):
            with self.subTest(chain=label):
                with self.assertRaises(GitHubSnapshotError):
                    read_github_snapshot(request, FakeTransport(routes))

    def test_transport_json_and_http_failures_are_sanitized(self):
        canary = "TRANSPORT-CANARY-SECRET"

        class ExplodingTransport:
            def __init__(self):
                self.calls = 0

            def __call__(self, *args, **kwargs):
                self.calls += 1
                raise RuntimeError(f"connection blew up: {canary}")

        request = GitHubSnapshotRequest(
            owner=VALID_OWNER, repository=VALID_REPOSITORY, commit_oid=READER_COMMIT_OID
        )
        exploding = ExplodingTransport()
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: snapshot transport failed$"
        ) as raised:
            read_github_snapshot(request, exploding)
        self.assertNotIn(canary, str(raised.exception))
        self.assertEqual(exploding.calls, 1)
        bad_results = (
            ["not-a-mapping"],
            {"status": "200", "body": b"{}"},
            {"status": 200, "body": {"already": "parsed"}},
            {"status": 99, "body": b"{}"},
            {"status": 600, "body": b"{}"},
            {"status": 200, "body": b"not json{{{"},
            {"status": 200, "body": b'{"a": 1, "a": 2}'},
        )
        for result in bad_results:
            with self.subTest(result=repr(result)[:30]):

                class FixedTransport:
                    def __init__(self):
                        self.calls = 0

                    def __call__(self, *args, **kwargs):
                        self.calls += 1
                        return result

                with self.assertRaises(GitHubSnapshotError):
                    read_github_snapshot(request, FixedTransport())

        for status in (403, 404, 429, 500):
            with self.subTest(http_status=status):
                body_canary = f"response-body-canary-{status}"

                class StatusTransport:
                    def __init__(self):
                        self.calls = 0

                    def __call__(self, *args, **kwargs):
                        self.calls += 1
                        return {"status": status, "body": body_canary.encode()}

                transport = StatusTransport()
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    rf"^github snapshot: snapshot response failed \(HTTP {status}\)$",
                ) as raised:
                    read_github_snapshot(request, transport)
                self.assertEqual(transport.calls, 1)
                self.assertNotIn(body_canary, str(raised.exception))

    def test_invalid_request_makes_zero_transport_calls(self):
        class CountingTransport:
            def __init__(self):
                self.calls = 0

            def __call__(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("transport must not be called")

        counting = CountingTransport()
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: request shape is invalid$"
        ):
            read_github_snapshot("not-a-request", counting)
        self.assertEqual(counting.calls, 0)
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: transport is invalid$"
        ):
            read_github_snapshot(
                GitHubSnapshotRequest(
                    owner=VALID_OWNER, repository=VALID_REPOSITORY,
                    commit_oid=READER_COMMIT_OID,
                ),
                None,
            )

    def test_oversized_bodies_fail_closed_before_decode_per_limit(self):
        files = [("calculator.py", b"print('ok')\n", "100644")]
        owner_url = f"{API_BASE}/repos/{VALID_OWNER}/{VALID_REPOSITORY}"
        commit_url = f"{owner_url}/commits/{READER_COMMIT_OID}"
        blob_sha = git_blob_sha(files[0][1])
        blob_url = f"{owner_url}/git/blobs/{blob_sha}"
        request = GitHubSnapshotRequest(
            owner=VALID_OWNER, repository=VALID_REPOSITORY, commit_oid=READER_COMMIT_OID
        )
        oversized = b"x" * 10_000_001
        for label in ("commit-limit", "tree-limit", "blob-limit"):
            with self.subTest(limit=label):
                routes = reader_fixture_routes(files)
                tree_url = next(
                    url for (method, url) in routes
                    if method == "GET" and "/git/trees/" in url
                )
                target_url = {
                    "commit-limit": commit_url,
                    "tree-limit": tree_url,
                    "blob-limit": blob_url,
                }[label]
                routes[("GET", target_url)] = (200, oversized)
                with self.assertRaisesRegex(
                    GitHubSnapshotError,
                    "^github snapshot: snapshot response exceeds limit$",
                ):
                    read_github_snapshot(request, FakeTransport(routes))
        oversized_error = dict(reader_fixture_routes(files))
        oversized_error[("GET", commit_url)] = (404, oversized)
        with self.subTest(limit="error-status-still-size-gated"):
            with self.assertRaisesRegex(
                GitHubSnapshotError,
                "^github snapshot: snapshot response exceeds limit$",
            ):
                read_github_snapshot(request, FakeTransport(oversized_error))

    def test_reader_uses_no_live_network_or_default_transport(self):
        import ast

        source = Path(snapshot_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = set()
        called_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add((node.module or "").lower())
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id.lower())
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr.lower())
        for forbidden in ("urllib", "requests", "http", "socket", "ssl"):
            self.assertTrue(
                all(forbidden not in module for module in imported_modules),
                forbidden,
            )
        self.assertTrue(
            {
                "urlopen", "urlretrieve", "create_connection", "getaddrinfo",
                "socket", "request",
            }.isdisjoint(called_names)
        )


if __name__ == "__main__":
    unittest.main()
