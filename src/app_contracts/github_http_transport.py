"""Anonymous, bounded HTTPS transport for the fixed GitHub snapshot GET API."""

from __future__ import annotations

import http.client
import math
import re
import ssl
import threading
import time
from dataclasses import dataclass
import certifi
from urllib.parse import parse_qsl, urlsplit
from typing import Callable


class GitHubHTTPTransportError(ValueError):
    """A fixed-host GitHub read request could not be completed safely."""


@dataclass(frozen=True)
class GitHubRateLimitEvidence:
    """Bounded header-only evidence from one anonymous rate-limit response."""

    status: int
    remaining: int | None
    reset_unix: int | None
    observed_monotonic: float

    def __post_init__(self) -> None:
        if type(self.status) is not int or not 100 <= self.status <= 599:
            raise GitHubHTTPTransportError("github http transport: response is invalid")
        if self.remaining is not None and (
            type(self.remaining) is not int or not 0 <= self.remaining <= 1_000_000
        ):
            raise GitHubHTTPTransportError("github http transport: response is invalid")
        if self.reset_unix is not None and (
            type(self.reset_unix) is not int or not 0 <= self.reset_unix <= 9_999_999_999_999
        ):
            raise GitHubHTTPTransportError("github http transport: response is invalid")
        if (
            isinstance(self.observed_monotonic, bool)
            or not isinstance(self.observed_monotonic, (int, float))
            or not math.isfinite(float(self.observed_monotonic))
            or self.observed_monotonic < 0
        ):
            raise GitHubHTTPTransportError("github http transport: response is invalid")


_API_HOST = "api.github.com"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2026-03-10"
_USER_AGENT = "Agent00X-ReadOnly-Snapshot/1"
_MAX_RESPONSE_BYTES = 8_000_000
_MAX_TIMEOUT_SECONDS = 30.0
_ALLOWED_GIT_PATH = re.compile(
    r"/repos/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"([A-Za-z0-9_.-]{1,100})/(commits|git/trees|git/blobs)/([0-9a-f]{40})\Z"
)


def _create_verified_ssl_context() -> ssl.SSLContext:
    """Use Python defaults plus the declared Mozilla CA bundle, fail closed."""

    try:
        context = ssl.create_default_context()
        ca_file = certifi.where()
        if type(ca_file) is not str or not ca_file:
            raise ValueError()
        context.load_verify_locations(cafile=ca_file)
        if (
            not context.check_hostname
            or context.verify_mode != ssl.CERT_REQUIRED
            or context.cert_store_stats().get("x509_ca", 0) < 1
        ):
            raise ValueError()
        return context
    except Exception:
        raise GitHubHTTPTransportError(
            "github http transport: tls trust configuration is invalid"
        ) from None


class GitHubAnonymousSnapshotTransport:
    """Callable transport accepted by ``read_github_snapshot_contents``.

    The connection factory is injectable for offline tests. The production
    default uses ``http.client`` directly, so it never follows HTTP redirects.
    No authentication or caller-controlled host is supported.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        connection_factory: Callable[..., object] | None = None,
    ) -> None:
        try:
            valid_timeout = (
                not isinstance(timeout_seconds, bool)
                and isinstance(timeout_seconds, (int, float))
                and math.isfinite(float(timeout_seconds))
                and 0 < float(timeout_seconds) <= _MAX_TIMEOUT_SECONDS
            )
        except (OverflowError, TypeError, ValueError):
            valid_timeout = False
        if not valid_timeout or (
            connection_factory is not None and not callable(connection_factory)
        ):
            raise GitHubHTTPTransportError("github http transport: config is invalid")
        self._timeout_seconds = float(timeout_seconds)
        self._connection_factory = connection_factory
        self._readiness_lock = threading.Lock()
        self._readiness_attempt_started = False

    def __repr__(self) -> str:
        return "GitHubAnonymousSnapshotTransport(authentication='none')"

    def read_rate_limit(self) -> GitHubRateLimitEvidence:
        """Make one verified-TLS header-only `/rate_limit` GET; never retry/read body."""

        with self._readiness_lock:
            if self._readiness_attempt_started:
                raise GitHubHTTPTransportError(
                    "github http transport: readiness attempt already used"
                )
            self._readiness_attempt_started = True

        connection = None
        response = None
        try:
            context = _create_verified_ssl_context()
            factory = self._connection_factory or http.client.HTTPSConnection
            connection = factory(
                _API_HOST,
                timeout=self._timeout_seconds,
                context=context,
            )
            connection.request(
                "GET",
                "/rate_limit",
                headers={
                    "Accept": _ACCEPT,
                    "X-GitHub-Api-Version": _API_VERSION,
                    "User-Agent": _USER_AGENT,
                },
            )
            response = connection.getresponse()
            status = getattr(response, "status", None)
            if type(status) is not int or not 100 <= status <= 599:
                raise GitHubHTTPTransportError(
                    "github http transport: response is invalid"
                )
            remaining = _numeric_header(response, "X-RateLimit-Remaining", 1_000_000)
            reset_unix = _numeric_header(
                response, "X-RateLimit-Reset", 9_999_999_999_999
            )
            return GitHubRateLimitEvidence(
                status=status,
                remaining=remaining,
                reset_unix=reset_unix,
                observed_monotonic=time.monotonic(),
            )
        except GitHubHTTPTransportError:
            raise
        except Exception:
            raise GitHubHTTPTransportError(
                "github http transport: request failed"
            ) from None
        finally:
            close_response = getattr(response, "close", None)
            if callable(close_response):
                try:
                    close_response()
                except Exception:
                    pass
            close_connection = getattr(connection, "close", None)
            if callable(close_connection):
                try:
                    close_connection()
                except Exception:
                    pass

    def __call__(
        self,
        method: object,
        url: object,
        headers: object,
        max_bytes: object,
        *,
        allow_redirects: object,
    ) -> dict[str, object]:
        if (
            type(method) is not str
            or method != "GET"
            or type(allow_redirects) is not bool
            or allow_redirects is not False
            or type(max_bytes) is not int
            or not 0 < max_bytes <= _MAX_RESPONSE_BYTES
        ):
            raise GitHubHTTPTransportError("github http transport: request is invalid")
        request_target = _validate_url(url)
        if type(headers) is not dict or headers != {
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _API_VERSION,
        }:
            raise GitHubHTTPTransportError("github http transport: request is invalid")

        connection = None
        try:
            context = _create_verified_ssl_context()
            factory = self._connection_factory or http.client.HTTPSConnection
            connection = factory(
                _API_HOST,
                timeout=self._timeout_seconds,
                context=context,
            )
            connection.request(
                "GET",
                request_target,
                headers={
                    "Accept": _ACCEPT,
                    "X-GitHub-Api-Version": _API_VERSION,
                    "User-Agent": _USER_AGENT,
                },
            )
            response = connection.getresponse()
            status = response.status
            body = response.read(max_bytes + 1)
            if type(status) is not int or type(body) is not bytes:
                raise GitHubHTTPTransportError(
                    "github http transport: response is invalid"
                )
            return {"status": status, "body": body}
        except GitHubHTTPTransportError:
            raise
        except Exception:
            raise GitHubHTTPTransportError(
                "github http transport: request failed"
            ) from None
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass


def _validate_url(url: object) -> str:
    try:
        if type(url) is not str or len(url) > 1024:
            raise ValueError()
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != _API_HOST
            or parsed.hostname != _API_HOST
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError()
        match = _ALLOWED_GIT_PATH.fullmatch(parsed.path)
        if match is None:
            raise ValueError()
        if match.group(2) in {".", ".."}:
            raise ValueError()
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        endpoint_kind = match.group(3)
        if endpoint_kind in {"commits", "git/blobs"} and query:
            raise ValueError()
        if endpoint_kind == "git/trees" and query not in ([], [("recursive", "1")]):
            raise ValueError()
        return parsed.path + ("?recursive=1" if query else "")
    except Exception:
        raise GitHubHTTPTransportError("github http transport: request is invalid") from None


def _numeric_header(response: object, name: str, maximum: int) -> int | None:
    try:
        raw = response.getheader(name)
        if type(raw) is not str or len(raw) > 13 or re.fullmatch(r"[0-9]+", raw) is None:
            return None
        value = int(raw)
        return value if value <= maximum else None
    except Exception:
        return None
