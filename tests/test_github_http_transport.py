from __future__ import annotations

from pathlib import Path
import ssl
import sys
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.github_http_transport import (
    GitHubAnonymousSnapshotTransport,
    GitHubHTTPTransportError,
    GitHubRateLimitEvidence,
)
import app_contracts.github_http_transport as transport_module


VALID_COMMIT_URL = (
    "https://api.github.com/repos/fixture-owner/fixture-repository/"
    "commits/" + "a" * 40
)
VALID_TREE_URL = (
    "https://api.github.com/repos/fixture-owner/fixture-repository/"
    "git/trees/" + "b" * 40 + "?recursive=1"
)
VALID_BLOB_URL = (
    "https://api.github.com/repos/fixture-owner/fixture-repository/"
    "git/blobs/" + "c" * 40
)
VALID_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
}


class FakeResponse:
    status = 200

    def __init__(self, body=b'{"ok":true}'):
        self.body = body
        self.read_limits = []

    def read(self, limit):
        self.read_limits.append(limit)
        return self.body[:limit]


class FakeConnection:
    def __init__(self, response=None):
        self.response = response or FakeResponse()
        self.request_args = None
        self.closed = False

    def request(self, method, target, *, headers):
        self.request_args = (method, target, headers)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class HeaderOnlyRateLimitResponse:
    status = 200

    def __init__(self, headers=None):
        self.headers = headers or {
            "X-RateLimit-Remaining": "37",
            "X-RateLimit-Reset": "1791378648",
        }
        self.closed = False
        self.body_read = False

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, _limit):
        self.body_read = True
        raise AssertionError("rate-limit body must not be read")

    def close(self):
        self.closed = True


class GitHubAnonymousSnapshotTransportTests(unittest.TestCase):
    def test_rate_limit_is_one_verified_tls_header_only_get(self):
        captured = {}
        response = HeaderOnlyRateLimitResponse()
        connection = FakeConnection(response)
        factory_calls = []

        def connection_factory(host, *, timeout, context):
            factory_calls.append(True)
            captured.update(host=host, timeout=timeout, context=context)
            return connection

        transport = GitHubAnonymousSnapshotTransport(
            timeout_seconds=4.5, connection_factory=connection_factory
        )
        with patch.object(transport_module.time, "monotonic", return_value=100.0):
            evidence = transport.read_rate_limit()
        with self.assertRaisesRegex(
            GitHubHTTPTransportError,
            "^github http transport: readiness attempt already used$",
        ):
            transport.read_rate_limit()

        self.assertEqual(
            evidence,
            GitHubRateLimitEvidence(
                status=200,
                remaining=37,
                reset_unix=1791378648,
                observed_monotonic=100.0,
            ),
        )
        self.assertEqual(factory_calls, [True])
        self.assertEqual(captured["host"], "api.github.com")
        self.assertEqual(captured["timeout"], 4.5)
        self.assertTrue(captured["context"].check_hostname)
        self.assertEqual(captured["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(connection.request_args[0:2], ("GET", "/rate_limit"))
        self.assertEqual(
            connection.request_args[2],
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "Agent00X-ReadOnly-Snapshot/1",
            },
        )
        self.assertNotIn("Authorization", connection.request_args[2])
        self.assertFalse(response.body_read)
        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)

    def test_rate_limit_malformed_headers_are_unavailable_without_retry(self):
        response = HeaderOnlyRateLimitResponse(
            {
                "X-RateLimit-Remaining": "37\n",
                "X-RateLimit-Reset": "not-a-number",
            }
        )
        connection = FakeConnection(response)
        factory_calls = []
        transport = GitHubAnonymousSnapshotTransport(
            connection_factory=lambda *_args, **_kwargs: factory_calls.append(True) or connection
        )

        evidence = transport.read_rate_limit()

        self.assertEqual(evidence.status, 200)
        self.assertIsNone(evidence.remaining)
        self.assertIsNone(evidence.reset_unix)
        self.assertEqual(factory_calls, [True])
        self.assertFalse(response.body_read)

    def test_valid_get_uses_fixed_host_verified_tls_bounded_read_and_closes(self):
        captured = {}
        connection = FakeConnection()

        def connection_factory(host, *, timeout, context):
            captured.update(host=host, timeout=timeout, context=context)
            return connection

        transport = GitHubAnonymousSnapshotTransport(
            timeout_seconds=4.5, connection_factory=connection_factory
        )
        result = transport(
            "GET",
            VALID_TREE_URL,
            VALID_HEADERS,
            1024,
            allow_redirects=False,
        )
        self.assertEqual(result, {"status": 200, "body": b'{"ok":true}'})
        self.assertEqual(captured["host"], "api.github.com")
        self.assertEqual(captured["timeout"], 4.5)
        self.assertIsInstance(captured["context"], ssl.SSLContext)
        self.assertTrue(captured["context"].check_hostname)
        self.assertEqual(captured["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertGreater(captured["context"].cert_store_stats()["x509_ca"], 0)
        self.assertEqual(connection.request_args[0], "GET")
        self.assertEqual(connection.request_args[1], "/repos/fixture-owner/fixture-repository/git/trees/" + "b" * 40 + "?recursive=1")
        self.assertEqual(
            connection.request_args[2],
            {
                **VALID_HEADERS,
                "User-Agent": "Agent00X-ReadOnly-Snapshot/1",
            },
        )
        self.assertNotIn("Authorization", connection.request_args[2])
        self.assertEqual(connection.response.read_limits, [1025])
        self.assertTrue(connection.closed)

    def test_only_fixed_get_paths_and_redirect_opt_out_are_accepted(self):
        connection = FakeConnection()
        transport = GitHubAnonymousSnapshotTransport(
            connection_factory=lambda *_args, **_kwargs: connection
        )
        for method, url, headers, max_bytes, allow_redirects in (
            ("POST", VALID_COMMIT_URL, VALID_HEADERS, 1024, False),
            ("GET", "https://api.github.com.evil.invalid/repos/a/b/commits/" + "a" * 40, VALID_HEADERS, 1024, False),
            ("GET", "https://user@api.github.com/repos/a/b/commits/" + "a" * 40, VALID_HEADERS, 1024, False),
            ("GET", "https://api.github.com:443/repos/a/b/commits/" + "a" * 40, VALID_HEADERS, 1024, False),
            ("GET", "http://api.github.com/repos/a/b/commits/" + "a" * 40, VALID_HEADERS, 1024, False),
            ("GET", "https://api.github.com/repos/a/../commits/" + "a" * 40, VALID_HEADERS, 1024, False),
            ("GET", "https://api.github.com/repos/a/b/git/commits/" + "a" * 40, VALID_HEADERS, 1024, False),
            ("GET", VALID_COMMIT_URL + "?recursive=1", VALID_HEADERS, 1024, False),
            ("GET", VALID_TREE_URL + "&per_page=1", VALID_HEADERS, 1024, False),
            ("GET", VALID_BLOB_URL + "?download=1", VALID_HEADERS, 1024, False),
            ("GET", VALID_COMMIT_URL, {**VALID_HEADERS, "Authorization": "canary"}, 1024, False),
            ("GET", VALID_COMMIT_URL, VALID_HEADERS, 0, False),
            ("GET", VALID_COMMIT_URL, VALID_HEADERS, 1024, True),
        ):
            with self.subTest(method=method, url=url[:55]):
                with self.assertRaises(GitHubHTTPTransportError):
                    transport(
                        method,
                        url,
                        headers,
                        max_bytes,
                        allow_redirects=allow_redirects,
                    )
        self.assertIsNone(connection.request_args)

    def test_body_read_is_limited_and_http_redirect_is_not_followed(self):
        redirect_response = FakeResponse(b"redirect-body")
        redirect_response.status = 302
        connection = FakeConnection(redirect_response)
        transport = GitHubAnonymousSnapshotTransport(
            connection_factory=lambda *_args, **_kwargs: connection
        )
        result = transport(
            "GET",
            VALID_COMMIT_URL,
            VALID_HEADERS,
            4,
            allow_redirects=False,
        )
        self.assertEqual(result, {"status": 302, "body": b"redir"})
        self.assertEqual(redirect_response.read_limits, [5])
        self.assertTrue(connection.closed)

    def test_fixed_git_blob_get_is_allowed_and_bounded(self):
        connection = FakeConnection(FakeResponse(b'{"sha":"' + b"c" * 40 + b'"}'))
        transport = GitHubAnonymousSnapshotTransport(
            connection_factory=lambda *_args, **_kwargs: connection
        )
        result = transport(
            "GET",
            VALID_BLOB_URL,
            VALID_HEADERS,
            64,
            allow_redirects=False,
        )
        self.assertEqual(result["status"], 200)
        self.assertEqual(
            connection.request_args[1],
            "/repos/fixture-owner/fixture-repository/git/blobs/" + "c" * 40,
        )
        self.assertEqual(connection.response.read_limits, [65])
        self.assertTrue(connection.closed)

    def test_failure_is_sanitized_and_connection_is_closed(self):
        connection = FakeConnection()

        def fail_request(*_args, **_kwargs):
            raise RuntimeError("HTTP-CANARY-SECRET")

        connection.request = fail_request
        transport = GitHubAnonymousSnapshotTransport(
            connection_factory=lambda *_args, **_kwargs: connection
        )
        with self.assertRaisesRegex(
            GitHubHTTPTransportError,
            "^github http transport: request failed$",
        ) as raised:
            transport(
                "GET",
                VALID_COMMIT_URL,
                VALID_HEADERS,
                1024,
                allow_redirects=False,
            )
        self.assertNotIn("HTTP-CANARY-SECRET", str(raised.exception))
        self.assertTrue(connection.closed)

    def test_invalid_timeout_config_is_rejected(self):
        for timeout in (0, -1, float("inf"), float("nan"), 31, True, 10**10000):
            with self.subTest(timeout_type=type(timeout).__name__):
                with self.assertRaisesRegex(
                    GitHubHTTPTransportError,
                    "^github http transport: config is invalid$",
                ):
                    GitHubAnonymousSnapshotTransport(timeout_seconds=timeout)

    def test_invalid_ca_bundle_fails_closed_before_connection_creation(self):
        factory_calls = []
        transport = GitHubAnonymousSnapshotTransport(
            connection_factory=lambda *_args, **_kwargs: factory_calls.append(True)
        )
        with patch.object(transport_module.certifi, "where", return_value="/missing/ca.pem"):
            with self.assertRaisesRegex(
                GitHubHTTPTransportError,
                "^github http transport: tls trust configuration is invalid$",
            ):
                transport(
                    "GET",
                    VALID_COMMIT_URL,
                    VALID_HEADERS,
                    1024,
                    allow_redirects=False,
                )
        self.assertEqual(factory_calls, [])


if __name__ == "__main__":
    unittest.main()
