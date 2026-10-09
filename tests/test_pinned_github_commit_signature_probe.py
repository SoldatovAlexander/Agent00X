from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_pinned_github_commit_signature as probe  # noqa: E402
from app_contracts.brainbooster_target_profile import (  # noqa: E402
    PINNED_COMMIT,
    PINNED_OWNER,
    PINNED_REPOSITORY,
    PINNED_TREE,
)
from app_contracts.github_commit_signature import (  # noqa: E402
    GitCommitSignatureError,
    GitCommitSignatureProof,
)
from app_contracts.github_http_transport import (  # noqa: E402
    GitHubRateLimitEvidence,
)


FINGERPRINT = "A" * 40
ARMOR = (
    b"-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
    b"synthetic public key\n"
    b"-----END PGP PUBLIC KEY BLOCK-----\n"
)
COMMIT_URL = (
    "https://api.github.com/repos/"
    f"{PINNED_OWNER}/{PINNED_REPOSITORY}/commits/{PINNED_COMMIT}"
)
KEYS_URL = "https://api.github.com/users/web-flow/gpg_keys"


class FakeTransport:
    def __init__(self, *, remaining=8, key_body=None, commit=None):
        self.remaining = remaining
        self.key_body = key_body or json.dumps(
            [{"public_key": ARMOR.decode("ascii")}]
        ).encode("utf-8")
        self.commit = commit or {
            "sha": PINNED_COMMIT,
            "commit": {"tree": {"sha": PINNED_TREE}},
            "committer": {"login": "web-flow"},
            "verification": {"verified": True, "reason": "valid"},
        }
        self.readiness_calls = 0
        self.requests = []

    def read_rate_limit(self):
        self.readiness_calls += 1
        return GitHubRateLimitEvidence(
            status=200,
            remaining=self.remaining,
            reset_unix=1_900_000_000,
            observed_monotonic=1.0,
        )

    def __call__(self, method, url, headers, max_bytes, *, allow_redirects):
        self.requests.append((method, url, headers, max_bytes, allow_redirects))
        if method != "GET" or allow_redirects is not False:
            return {"status": 405, "body": b""}
        if url == COMMIT_URL:
            return {"status": 200, "body": json.dumps(self.commit).encode("utf-8")}
        if url == KEYS_URL:
            return {"status": 200, "body": self.key_body}
        return {"status": 404, "body": b""}


class FakeRawCommitSource:
    instances = []

    def __init__(self, git_executable, *, timeout_seconds):
        self.git_executable = git_executable
        self.timeout_seconds = timeout_seconds
        self.claim = None
        self.__class__.instances.append(self)

    def __call__(self, claim):
        self.claim = claim
        return b"synthetic raw commit bytes"


def _proof():
    return GitCommitSignatureProof(
        commit_oid=PINNED_COMMIT,
        tree_oid=PINNED_TREE,
        primary_fingerprint=FINGERPRINT,
    )


class PinnedGitHubCommitSignatureProbeTests(unittest.TestCase):
    def setUp(self):
        FakeRawCommitSource.instances.clear()
        self.transport = FakeTransport()
        self.transport_context = patch.object(
            probe, "GitHubAnonymousSnapshotTransport", return_value=self.transport
        )
        self.raw_context = patch.object(
            probe, "GitHubRawCommitObjectSource", FakeRawCommitSource
        )
        self.which_context = patch.object(
            probe.shutil, "which", side_effect=("/usr/bin/git", "/usr/bin/gpg")
        )
        self.fingerprint_context = patch.object(
            probe,
            "primary_fingerprint_from_armored_public_key",
            return_value=FINGERPRINT,
        )
        self.proof_context = patch.object(
            probe, "verify_git_commit_signature", return_value=_proof()
        )
        for context in (
            self.transport_context,
            self.raw_context,
            self.which_context,
            self.fingerprint_context,
            self.proof_context,
        ):
            context.start()
            self.addCleanup(context.stop)

    def test_happy_path_makes_exact_anonymous_reads_then_checks_one_object(self):
        result = probe.run_probe()

        self.assertEqual(
            result,
            {
                "status": "signature-valid",
                "commit_oid": PINNED_COMMIT,
                "tree_oid": PINNED_TREE,
                "primary_fingerprint": FINGERPRINT,
                "identity_authenticated": False,
                "independent_transport_trust_established": False,
            },
        )
        self.assertEqual(self.transport.readiness_calls, 1)
        self.assertEqual(
            [request[1] for request in self.transport.requests],
            [COMMIT_URL, KEYS_URL],
        )
        self.assertTrue(
            all(request[0] == "GET" and request[4] is False for request in self.transport.requests)
        )
        self.assertTrue(
            all("Authorization" not in request[2] for request in self.transport.requests)
        )
        self.assertEqual(len(FakeRawCommitSource.instances), 1)
        self.assertEqual(FakeRawCommitSource.instances[0].claim.commit_oid, PINNED_COMMIT)

    def test_low_rate_budget_stops_before_any_commit_or_key_read(self):
        self.transport.remaining = 1

        with self.assertRaisesRegex(probe.ProbeStopped, "rate-limit-unavailable"):
            probe.run_probe()

        self.assertEqual(self.transport.readiness_calls, 1)
        self.assertEqual(self.transport.requests, [])
        self.assertEqual(FakeRawCommitSource.instances, [])

    def test_unapproved_signer_stops_before_key_fetch_or_git_fetch(self):
        self.transport.commit["committer"] = {"login": "other-account"}

        with self.assertRaisesRegex(probe.ProbeStopped, "signer-not-allowlisted"):
            probe.run_probe()

        self.assertEqual([request[1] for request in self.transport.requests], [COMMIT_URL])
        self.assertEqual(FakeRawCommitSource.instances, [])

    def test_malformed_public_key_list_stops_before_raw_commit_fetch(self):
        self.transport.key_body = b'{"not":"an array"}'

        with self.assertRaisesRegex(probe.ProbeStopped, "public-key-response-rejected"):
            probe.run_probe()

        self.assertEqual([request[1] for request in self.transport.requests], [COMMIT_URL, KEYS_URL])
        self.assertEqual(FakeRawCommitSource.instances, [])

    def test_signature_mismatch_returns_only_a_fixed_failure(self):
        self.proof_context.stop()
        self.proof_context = patch.object(
            probe,
            "verify_git_commit_signature",
            side_effect=GitCommitSignatureError("do not expose this detail"),
        )
        self.proof_context.start()
        self.addCleanup(self.proof_context.stop)

        with self.assertRaises(probe.ProbeStopped) as raised:
            probe.run_probe()

        self.assertEqual(raised.exception.reason, "signature-not-verified")
        self.assertNotIn("detail", str(raised.exception))

    def test_rate_budget_and_api_body_size_are_fixed(self):
        probe.run_probe()

        self.assertEqual(self.transport.requests[0][3], 1_000_000)
        self.assertEqual(self.transport.requests[1][3], 1_000_000)
        self.assertEqual(self.transport.requests[0][2], self.transport.requests[1][2])


if __name__ == "__main__":
    unittest.main()
