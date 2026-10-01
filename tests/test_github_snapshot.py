from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitHubCommitClaim,
    GitHubSnapshotClaim,
    GitHubSnapshotError,
    GitHubSnapshotRequest,
    GitHubTreeClaim,
    GitHubTreeEntry,
    parse_github_blob,
    parse_github_commit,
    parse_github_tree,
    read_github_snapshot,
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
            {"content": "aGVsbG8\n"},
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

    def test_oversized_payload_fails_closed_before_full_decode(self):
        import base64 as base64_module

        wire_huge = {
            "sha": "f" * 40,
            "size": 1,
            "encoding": "base64",
            "content": "A" * 300_000,
        }
        entry = valid_blob_entry()
        with self.assertRaisesRegex(
            GitHubSnapshotError, "^github snapshot: blob size exceeds limit$"
        ):
            parse_github_blob(entry, wire_huge)
        big = b"Q" * 150_000
        oversized = {
            "sha": git_blob_sha(big),
            "size": len(big),
            "encoding": "base64",
            "content": base64_module.b64encode(big).decode("ascii"),
        }
        entry = GitHubTreeEntry(
            path="big.py", mode="100644", entry_type="blob", sha=git_blob_sha(big)
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


def reader_fixture_routes(files, commit_oid=READER_COMMIT_OID, tree_oid=READER_TREE_OID):
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
    routes = {
        ("GET", f"{API_BASE}/repos/{owner}/{repository}/git/commits/{commit_oid}"): (
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
                    commit_oid=READER_COMMIT_OID, tree_oid=READER_TREE_OID,
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
        truncated_payload = json_module.dumps(
            {"sha": READER_TREE_OID, "truncated": True, "tree": []}
        ).encode("utf-8")
        truncated_routes = dict(base_routes)
        truncated_routes[
            ("GET", f"{owner_url}/git/trees/{READER_TREE_OID}?recursive=1")
        ] = (200, truncated_payload)
        mismatched_payload = json_module.dumps(
            {"sha": "f" * 40, "commit": {"tree": {"sha": READER_TREE_OID}}}
        ).encode("utf-8")
        mismatched_routes = dict(base_routes)
        mismatched_routes[
            ("GET", f"{owner_url}/git/commits/{READER_COMMIT_OID}")
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
            {"status": 404, "body": b"{}"},
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
