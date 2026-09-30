"""Bounded records for an experimental local verifier process handoff.

The records make the intended JSON boundary explicit. They do not provide
process isolation, verifier identity, or independent trust by themselves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import re
import selectors
import subprocess
import time

from .digests import sha256_bytes
from .executor import (
    MAX_VERIFIER_BLOCKER_CODES,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    validate_verifier_result,
)


VERIFIER_PROCESS_SCHEMA_VERSION = 1

MAX_VERIFIER_REQUEST_FILES = 20
MAX_VERIFIER_REQUEST_PATH_BYTES = 240
MAX_VERIFIER_REQUEST_CONTENT_BYTES = 100_000
MAX_VERIFIER_REQUEST_CONTENTS_BYTES = 1_000_000
MAX_VERIFIER_REQUEST_BYTES = 2_000_000
MAX_VERIFIER_REQUEST_COMMAND_ARGS = 64
MAX_VERIFIER_COMMAND_TIMEOUT_SECONDS = 86_400
MAX_VERIFIER_RESPONSE_BYTES = 2_000_000

_REQUEST_FIELDS = frozenset({"schema_version", "verifier_input"})

_RESPONSE_FIELDS = frozenset({"schema_version", "request_digest", "verifier_result"})

_VERIFIER_RESULT_FIELDS = frozenset(
    {
        "process_id",
        "base_commit",
        "snapshot_tree_digest",
        "replay_result_digest",
        "verifier_id",
        "patch_digest",
        "evidence_digest",
        "verification_digest",
        "verified_contents_digest",
        "verdict",
        "blocker_codes",
        "evidence_origin",
    }
)

_RESULT_STR_FIELDS = frozenset(
    {
        "process_id",
        "base_commit",
        "verifier_id",
        "patch_digest",
        "evidence_digest",
        "verification_digest",
        "verified_contents_digest",
        "evidence_origin",
    }
)

_RESULT_OPTIONAL_STR_FIELDS = frozenset({"snapshot_tree_digest", "replay_result_digest"})

_VERDICTS = frozenset({"pass", "fail", "blocked"})

_BLOCKER_CODE_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_REQUEST_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")

_VERIFIER_INPUT_FIELDS = frozenset(
    {
        "process_id",
        "repository_id",
        "base_commit",
        "snapshot_tree_digest",
        "declared_change_paths",
        "verified_contents",
        "test_command",
        "test_timeout_seconds",
        "patch_digest",
        "evidence_digest",
        "verification_digest",
        "verified_contents_digest",
        "evidence_origin",
        "replay_result_digest",
    }
)

_STR_FIELDS = frozenset(
    {
        "process_id",
        "repository_id",
        "base_commit",
        "patch_digest",
        "evidence_digest",
        "verification_digest",
        "verified_contents_digest",
        "evidence_origin",
    }
)

_OPTIONAL_STR_FIELDS = frozenset({"snapshot_tree_digest", "replay_result_digest"})

_STR_LIST_FIELDS = frozenset({"declared_change_paths", "test_command"})


class VerifierProcessError(ValueError):
    """A verifier process record is malformed or unsupported."""


class SubprocessVerifier:
    """An ``IndependentVerifier`` carried out by one bounded local child.

    The prepared input crosses the process boundary only as canonical bytes;
    the returned result is freshly parsed from child output and bound to the
    exact request. Process failures propagate as stable errors for the
    orchestration to map fail-closed; they are never converted into allow
    results here, and in-process verifier semantics are untouched.
    """

    def __init__(self, config: object, *, environ: object = None) -> None:
        if type(config) is not VerifierProcessConfig:
            raise VerifierProcessError("verifier process: command config is invalid")
        self._config = config
        self._child_environ = verifier_child_environ(environ)

    def verify(self, prepared: VerifierInput) -> VerifierResult:
        request = VerifierProcessRequest.from_verifier_input(prepared)
        response = run_verifier_command(
            self._config, request, environ=self._child_environ
        )
        return bind_verifier_response(request, response)


def verifier_child_environ(extra: object = None) -> dict[str, str]:
    """Build the minimal explicit environment for one verifier child.

    The host environment is never inherited: the child receives exactly the
    explicitly provided mapping and nothing else, so credentials and
    host-specific variables cannot become verifier input by default.
    """

    if extra is None:
        return {}
    if type(extra) is not dict:
        raise VerifierProcessError("verifier process: child environment is invalid")
    for key, value in extra.items():
        if type(key) is not str or not key or type(value) is not str:
            raise VerifierProcessError("verifier process: child environment is invalid")
    return dict(extra)


@dataclass(frozen=True)
class VerifierProcessOutcome:
    """Raw completion record of one bounded child invocation.

    The exit code, stdout and stderr are reported as observed, without any
    output size caps or verdict interpretation; those belong to later stages.
    """

    exit_code: int
    stdout: bytes
    stderr: bytes

    def __post_init__(self) -> None:
        if type(self.exit_code) is not int:
            raise VerifierProcessError("verifier process: child outcome is invalid")
        if type(self.stdout) is not bytes or type(self.stderr) is not bytes:
            raise VerifierProcessError("verifier process: child outcome is invalid")


def run_verifier_command(
    config: object,
    request: object,
    *,
    environ: object = None,
) -> VerifierProcessResponse:
    """Run the configured command once with the canonical request on stdin.

    The argument vector is passed without a shell, stdin carries only the
    canonical request bytes, and the child environment is minimal and
    explicit. Stdout and stderr are collected incrementally under the
    configured per-stream caps: an over-limit stream terminates the child
    and fails closed. Stderr is drained to avoid pipe deadlock but never
    returned to the caller. Stdout is accepted only as exactly one strictly
    parsed response record. The child is started at most once: malformed
    inputs fail before any spawn, and a timeout kills the child, reaps it
    and raises a stable error without retry.
    """

    if type(config) is not VerifierProcessConfig:
        raise VerifierProcessError("verifier process: command config is invalid")
    if type(request) is not VerifierProcessRequest:
        raise VerifierProcessError("verifier process: request shape is invalid")
    child_environ = verifier_child_environ(environ)
    stdin_bytes = serialize_verifier_request(request)
    try:
        process = subprocess.Popen(
            list(config.argv),
            executable=config.executable,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_environ,
            shell=False,
        )
    except Exception:
        raise VerifierProcessError("verifier process: child launch failed") from None
    try:
        stdout, stderr, exit_code = _collect_bounded_output(
            process,
            stdin_bytes,
            stdout_cap=config.max_stdout_bytes,
            stderr_cap=config.max_stderr_bytes,
            timeout_seconds=config.timeout_seconds,
        )
    except VerifierProcessError:
        raise
    except Exception:
        _quietly_reap(process)
        raise VerifierProcessError("verifier process: child launch failed") from None
    return classify_verifier_outcome(VerifierProcessOutcome(exit_code, stdout, stderr))


def classify_verifier_outcome(outcome: object) -> VerifierProcessResponse:
    """Normalize one raw child outcome into a stable verifier failure or response.

    A nonzero exit, an empty response and a malformed response each become a
    stable bounded error. A well-formed response is returned as parsed: process
    diagnostics never alter the child verdict and raw child bytes, streams or
    arguments never enter messages or results.
    """

    if type(outcome) is not VerifierProcessOutcome:
        raise VerifierProcessError("verifier process: child outcome is invalid")
    if outcome.exit_code != 0:
        raise VerifierProcessError("verifier process: child exit failed")
    if outcome.stdout == b"":
        raise VerifierProcessError("verifier process: child response is empty")
    try:
        return parse_verifier_response(outcome.stdout)
    except VerifierProcessError:
        raise VerifierProcessError("verifier process: child response is malformed")


def _quietly_reap(process: subprocess.Popen) -> None:
    try:
        process.kill()
    except Exception:
        pass
    try:
        process.wait()
    except Exception:
        pass


def _collect_bounded_output(
    process: subprocess.Popen,
    stdin_bytes: bytes,
    *,
    stdout_cap: int,
    stderr_cap: int,
    timeout_seconds: int,
) -> tuple[bytes, bytes, int]:
    """Stream one child within per-stream caps and an overall deadline.

    Returns ``(stdout, stderr, exit_code)``. An over-limit stream kills the
    child and fails closed; an expired deadline kills, reaps and reports a
    timeout. File descriptors are always closed and the child reaped.
    """

    deadline = time.monotonic() + timeout_seconds
    pending = memoryview(stdin_bytes)
    stdout_chunks = bytearray()
    stderr_chunks = bytearray()
    for stream in (process.stdin, process.stdout, process.stderr):
        os.set_blocking(stream.fileno(), False)
    try:
        with selectors.DefaultSelector() as selector:
            if pending:
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stderr, selectors.EVENT_READ)
            stdin_open = bool(pending)
            stdout_open = True
            stderr_open = True
            while stdin_open or stdout_open or stderr_open:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _quietly_reap(process)
                    raise VerifierProcessError("verifier process: child timed out")
                for key, mask in selector.select(timeout=remaining):
                    if key.fileobj is process.stdin and mask & selectors.EVENT_WRITE:
                        try:
                            written = os.write(process.stdin.fileno(), pending)
                        except BlockingIOError:
                            continue
                        except OSError:
                            pending = memoryview(b"")
                        else:
                            pending = pending[written:]
                        if not pending and stdin_open:
                            stdin_open = False
                            selector.unregister(process.stdin)
                            process.stdin.close()
                    if key.fileobj is process.stdout and mask & selectors.EVENT_READ:
                        try:
                            chunk = os.read(process.stdout.fileno(), 65536)
                        except BlockingIOError:
                            continue
                        except OSError:
                            chunk = b""
                        if chunk == b"":
                            stdout_open = False
                            selector.unregister(process.stdout)
                        else:
                            stdout_chunks += chunk
                            if len(stdout_chunks) > stdout_cap:
                                _quietly_reap(process)
                                raise VerifierProcessError(
                                    "verifier process: child output exceeds limit"
                                )
                    if key.fileobj is process.stderr and mask & selectors.EVENT_READ:
                        try:
                            chunk = os.read(process.stderr.fileno(), 65536)
                        except BlockingIOError:
                            continue
                        except OSError:
                            chunk = b""
                        if chunk == b"":
                            stderr_open = False
                            selector.unregister(process.stderr)
                        else:
                            stderr_chunks += chunk
                            if len(stderr_chunks) > stderr_cap:
                                _quietly_reap(process)
                                raise VerifierProcessError(
                                    "verifier process: child output exceeds limit"
                                )
            try:
                remaining = deadline - time.monotonic()
                process.wait(timeout=max(remaining, 0))
            except subprocess.TimeoutExpired:
                _quietly_reap(process)
                raise VerifierProcessError("verifier process: child timed out") from None
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except Exception:
                pass
    return bytes(stdout_chunks), bytes(stderr_chunks), process.returncode


@dataclass(frozen=True)
class VerifierProcessConfig:
    """Fixed adapter config for one local verifier child command.

    The executable and argument vector are explicitly configured and never
    derived from the task payload. Only shape is validated here; existence
    of the executable is a launch-time concern handled separately.
    """

    executable: str
    argv: tuple[str, ...]
    timeout_seconds: int
    max_stdout_bytes: int
    max_stderr_bytes: int

    def __post_init__(self) -> None:
        executable = self.executable
        if (
            type(executable) is not str
            or not executable
            or executable != executable.strip()
            or not executable.startswith("/")
            or any(character.isspace() for character in executable)
            or any(ord(character) < 32 or ord(character) == 127 for character in executable)
        ):
            raise VerifierProcessError("verifier process: command executable is invalid")
        argv = self.argv
        if (
            type(argv) is not tuple
            or not argv
            or any(type(argument) is not str or not argument for argument in argv)
        ):
            raise VerifierProcessError("verifier process: command arguments are invalid")
        if (
            type(self.timeout_seconds) is not int
            or not 1 <= self.timeout_seconds <= MAX_VERIFIER_COMMAND_TIMEOUT_SECONDS
        ):
            raise VerifierProcessError("verifier process: command timeout is invalid")
        for limit in (self.max_stdout_bytes, self.max_stderr_bytes):
            if (
                type(limit) is not int
                or not 1 <= limit <= MAX_VERIFIER_RESPONSE_BYTES
            ):
                raise VerifierProcessError("verifier process: response limits are invalid")


@dataclass(frozen=True)
class VerifierProcessRequest:
    """Versioned handoff containing only the existing bounded verifier input."""

    schema_version: int
    verifier_input: VerifierInput

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != VERIFIER_PROCESS_SCHEMA_VERSION:
            raise VerifierProcessError("verifier process: request version is invalid")
        if type(self.verifier_input) is not VerifierInput:
            raise VerifierProcessError("verifier process: request shape is invalid")
        if self.verifier_input.evidence_origin != "local_test":
            raise VerifierProcessError("verifier process: request fields are invalid")

    @classmethod
    def from_verifier_input(cls, value: object) -> "VerifierProcessRequest":
        if type(value) is not VerifierInput:
            raise VerifierProcessError("verifier process: request shape is invalid")
        return cls(VERIFIER_PROCESS_SCHEMA_VERSION, value)


@dataclass(frozen=True)
class VerifierProcessResponse:
    """Versioned handoff containing one bounded typed verifier result."""

    schema_version: int
    request_digest: str
    verifier_result: VerifierResult

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != VERIFIER_PROCESS_SCHEMA_VERSION:
            raise VerifierProcessError("verifier process: response version is invalid")
        if (
            type(self.request_digest) is not str
            or _REQUEST_DIGEST_PATTERN.fullmatch(self.request_digest) is None
        ):
            raise VerifierProcessError("verifier process: response fields are invalid")
        if type(self.verifier_result) is not VerifierResult:
            raise VerifierProcessError("verifier process: response shape is invalid")

    @classmethod
    def from_verifier_result(
        cls, value: object, request_digest: object
    ) -> "VerifierProcessResponse":
        if type(value) is not VerifierResult:
            raise VerifierProcessError("verifier process: response shape is invalid")
        if (
            type(request_digest) is not str
            or _REQUEST_DIGEST_PATTERN.fullmatch(request_digest) is None
        ):
            raise VerifierProcessError("verifier process: response fields are invalid")
        return cls(VERIFIER_PROCESS_SCHEMA_VERSION, request_digest, value)


def serialize_verifier_request(value: object) -> bytes:
    """Serialize one request to canonical UTF-8 JSON without mutating it.

    Resource bounds are enforced before serialization so caller-controlled
    payloads cannot cause unbounded encoding work; the encoded size is
    enforced before the bytes are handed to any child launch.
    """

    if type(value) is not VerifierProcessRequest:
        raise VerifierProcessError("verifier process: request shape is invalid")
    try:
        _check_verifier_request_bounds(value.verifier_input)
    except VerifierProcessError:
        raise
    except Exception:
        raise VerifierProcessError("verifier process: request serialization failed") from None
    try:
        encoded = json.dumps(
            asdict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except Exception:
        raise VerifierProcessError("verifier process: request serialization failed") from None
    if len(encoded) > MAX_VERIFIER_REQUEST_BYTES:
        raise VerifierProcessError("verifier process: request size exceeds limit")
    return encoded


def _check_verifier_request_bounds(verifier_input: VerifierInput) -> None:
    total_text_bytes = 0

    def bounded_text(value: object) -> int:
        nonlocal total_text_bytes
        if type(value) is not str:
            raise VerifierProcessError("verifier process: request fields are invalid")
        # Check character count first: UTF-8 encoding can use at most four bytes
        # per code point, and must never be attempted on an unbounded string.
        if len(value) > MAX_VERIFIER_REQUEST_BYTES:
            raise VerifierProcessError("verifier process: request size exceeds limit")
        byte_count = len(value.encode("utf-8"))
        total_text_bytes += byte_count
        if total_text_bytes > MAX_VERIFIER_REQUEST_BYTES:
            raise VerifierProcessError("verifier process: request size exceeds limit")
        return byte_count

    for field in _STR_FIELDS:
        bounded_text(getattr(verifier_input, field))
    for field in _OPTIONAL_STR_FIELDS:
        value = getattr(verifier_input, field)
        if value is not None:
            bounded_text(value)
    if verifier_input.evidence_origin != "local_test":
        raise VerifierProcessError("verifier process: request fields are invalid")
    if (
        type(verifier_input.test_timeout_seconds) is not int
        or not 1 <= verifier_input.test_timeout_seconds <= 86_400
    ):
        raise VerifierProcessError("verifier process: request fields are invalid")

    paths = verifier_input.declared_change_paths
    if type(paths) is not tuple or len(paths) > MAX_VERIFIER_REQUEST_FILES:
        raise VerifierProcessError("verifier process: request size exceeds limit")
    for path in paths:
        if type(path) is not str or len(path) > MAX_VERIFIER_REQUEST_PATH_BYTES:
            raise VerifierProcessError("verifier process: request path exceeds limit")
        if bounded_text(path) > MAX_VERIFIER_REQUEST_PATH_BYTES:
            raise VerifierProcessError("verifier process: request path exceeds limit")

    command = verifier_input.test_command
    if type(command) is not tuple or len(command) > MAX_VERIFIER_REQUEST_COMMAND_ARGS:
        raise VerifierProcessError("verifier process: request size exceeds limit")
    for argument in command:
        bounded_text(argument)

    contents = verifier_input.verified_contents
    if type(contents) is not tuple:
        raise VerifierProcessError("verifier process: request fields are invalid")
    if len(contents) > MAX_VERIFIER_REQUEST_FILES:
        raise VerifierProcessError("verifier process: request file count exceeds limit")
    total_content_bytes = 0
    for entry in contents:
        if type(entry) is not tuple or len(entry) != 2:
            raise VerifierProcessError("verifier process: request fields are invalid")
        path, content = entry
        if type(path) is not str or len(path) > MAX_VERIFIER_REQUEST_PATH_BYTES:
            raise VerifierProcessError("verifier process: request path exceeds limit")
        if type(content) is not str or len(content) > MAX_VERIFIER_REQUEST_CONTENT_BYTES:
            raise VerifierProcessError("verifier process: request content exceeds limit")
        path_bytes = bounded_text(path)
        content_bytes = bounded_text(content)
        if path_bytes > MAX_VERIFIER_REQUEST_PATH_BYTES:
            raise VerifierProcessError("verifier process: request path exceeds limit")
        if content_bytes > MAX_VERIFIER_REQUEST_CONTENT_BYTES:
            raise VerifierProcessError("verifier process: request content exceeds limit")
        total_content_bytes += content_bytes
        if total_content_bytes > MAX_VERIFIER_REQUEST_CONTENTS_BYTES:
            raise VerifierProcessError("verifier process: request contents exceed limit")


def parse_verifier_request(data: object) -> VerifierProcessRequest:
    """Parse canonical request bytes back into a bounded request record.

    Only the stated schema version and the exact verifier-input field set are
    accepted. Malformed encoding, JSON shape, duplicate keys and scalar types
    fail closed without echoing the payload or field values.
    """

    if type(data) is not bytes:
        raise VerifierProcessError("verifier process: request encoding is invalid")
    if len(data) > MAX_VERIFIER_REQUEST_BYTES:
        raise VerifierProcessError("verifier process: request size exceeds limit")
    try:
        text = data.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise VerifierProcessError("verifier process: request encoding is invalid") from None
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except Exception:
        raise VerifierProcessError("verifier process: request payload is invalid") from None
    if type(payload) is not dict:
        raise VerifierProcessError("verifier process: request payload is invalid")
    version = payload.get("schema_version")
    if type(version) is not int or version != VERIFIER_PROCESS_SCHEMA_VERSION:
        raise VerifierProcessError("verifier process: request version is invalid")
    if set(payload) != _REQUEST_FIELDS:
        raise VerifierProcessError("verifier process: request fields are invalid")
    raw_input = payload["verifier_input"]
    if type(raw_input) is not dict or set(raw_input) != _VERIFIER_INPUT_FIELDS:
        raise VerifierProcessError("verifier process: request fields are invalid")
    _validate_verifier_input_shape(raw_input)
    verifier_input = VerifierInput(
        process_id=raw_input["process_id"],
        repository_id=raw_input["repository_id"],
        base_commit=raw_input["base_commit"],
        snapshot_tree_digest=raw_input["snapshot_tree_digest"],
        declared_change_paths=tuple(raw_input["declared_change_paths"]),
        verified_contents=tuple(
            (entry[0], entry[1]) for entry in raw_input["verified_contents"]
        ),
        test_command=tuple(raw_input["test_command"]),
        test_timeout_seconds=raw_input["test_timeout_seconds"],
        patch_digest=raw_input["patch_digest"],
        evidence_digest=raw_input["evidence_digest"],
        verification_digest=raw_input["verification_digest"],
        verified_contents_digest=raw_input["verified_contents_digest"],
        evidence_origin=raw_input["evidence_origin"],
        replay_result_digest=raw_input["replay_result_digest"],
    )
    _check_verifier_request_bounds(verifier_input)
    return VerifierProcessRequest(version, verifier_input)


def digest_verifier_request(value: object) -> str:
    """Return the canonical digest of one request's exact wire payload.

    The digest covers the same deterministic bytes the child would receive,
    so any field change between serialization and launch changes the digest.
    It is only a change-detection binding, not authentication of the child.
    """

    return sha256_bytes(serialize_verifier_request(value))


def parse_verifier_response(data: object) -> VerifierProcessResponse:
    """Parse child output bytes back into a bounded response record.

    Only the stated schema version, the exact result field set, the known
    verdict labels and well-formed blocker codes are accepted. The restored
    record carries a typed ``VerifierResult`` with a real verdict enum.
    Malformed encoding, JSON shape, duplicate keys and values fail closed
    without echoing the output or field values.
    """

    if type(data) is not bytes:
        raise VerifierProcessError("verifier process: response encoding is invalid")
    try:
        text = data.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise VerifierProcessError("verifier process: response encoding is invalid") from None
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except Exception:
        raise VerifierProcessError("verifier process: response payload is invalid") from None
    if type(payload) is not dict:
        raise VerifierProcessError("verifier process: response payload is invalid")
    version = payload.get("schema_version")
    if type(version) is not int or version != VERIFIER_PROCESS_SCHEMA_VERSION:
        raise VerifierProcessError("verifier process: response version is invalid")
    if set(payload) != _RESPONSE_FIELDS:
        raise VerifierProcessError("verifier process: response fields are invalid")
    request_digest = payload["request_digest"]
    if (
        type(request_digest) is not str
        or _REQUEST_DIGEST_PATTERN.fullmatch(request_digest) is None
    ):
        raise VerifierProcessError("verifier process: response fields are invalid")
    raw_result = payload["verifier_result"]
    if type(raw_result) is not dict or set(raw_result) != _VERIFIER_RESULT_FIELDS:
        raise VerifierProcessError("verifier process: response fields are invalid")
    _validate_verifier_result_shape(raw_result)
    try:
        verdict = VerifierVerdict(raw_result["verdict"])
    except ValueError:
        raise VerifierProcessError("verifier process: response fields are invalid") from None
    verifier_result = VerifierResult(
        process_id=raw_result["process_id"],
        base_commit=raw_result["base_commit"],
        snapshot_tree_digest=raw_result["snapshot_tree_digest"],
        replay_result_digest=raw_result["replay_result_digest"],
        verifier_id=raw_result["verifier_id"],
        patch_digest=raw_result["patch_digest"],
        evidence_digest=raw_result["evidence_digest"],
        verification_digest=raw_result["verification_digest"],
        verified_contents_digest=raw_result["verified_contents_digest"],
        verdict=verdict,
        blocker_codes=tuple(raw_result["blocker_codes"]),
        evidence_origin=raw_result["evidence_origin"],
    )
    return VerifierProcessResponse(version, request_digest, verifier_result)


def bind_verifier_response(
    request: VerifierProcessRequest,
    response: VerifierProcessResponse,
) -> VerifierResult:
    """Bind a parsed response to its exact source request.

    The response's request digest must equal the freshly recomputed digest of
    the source request, and the response must satisfy every existing
    ``validate_verifier_result`` binding against that same request. Any
    substitution is rejected before the typed result is returned; the
    existing executor bindings are reused unchanged, never reimplemented.
    """

    if type(request) is not VerifierProcessRequest:
        raise VerifierProcessError("verifier process: request shape is invalid")
    if type(response) is not VerifierProcessResponse:
        raise VerifierProcessError("verifier process: response shape is invalid")
    if response.request_digest != digest_verifier_request(request):
        raise VerifierProcessError("verifier process: request digest mismatch")
    return validate_verifier_result(response.verifier_result, request.verifier_input)


def _validate_verifier_result_shape(raw_result: dict[str, object]) -> None:
    for field in _RESULT_STR_FIELDS:
        if type(raw_result[field]) is not str:
            raise VerifierProcessError("verifier process: response fields are invalid")
    for field in _RESULT_OPTIONAL_STR_FIELDS:
        value = raw_result[field]
        if value is not None and type(value) is not str:
            raise VerifierProcessError("verifier process: response fields are invalid")
    if type(raw_result["verdict"]) is not str or raw_result["verdict"] not in _VERDICTS:
        raise VerifierProcessError("verifier process: response fields are invalid")
    blocker_codes = raw_result["blocker_codes"]
    if (
        type(blocker_codes) is not list
        or len(blocker_codes) > MAX_VERIFIER_BLOCKER_CODES
        or any(
            type(code) is not str or _BLOCKER_CODE_PATTERN.fullmatch(code) is None
            for code in blocker_codes
        )
    ):
        raise VerifierProcessError("verifier process: response fields are invalid")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError("non-standard JSON constant")


def _validate_verifier_input_shape(raw_input: dict[str, object]) -> None:
    for field in _STR_FIELDS:
        if type(raw_input[field]) is not str:
            raise VerifierProcessError("verifier process: request fields are invalid")
    for field in _OPTIONAL_STR_FIELDS:
        value = raw_input[field]
        if value is not None and type(value) is not str:
            raise VerifierProcessError("verifier process: request fields are invalid")
    if type(raw_input["test_timeout_seconds"]) is not int:
        raise VerifierProcessError("verifier process: request fields are invalid")
    if raw_input["evidence_origin"] != "local_test":
        raise VerifierProcessError("verifier process: request fields are invalid")
    for field in _STR_LIST_FIELDS:
        values = raw_input[field]
        if type(values) is not list or any(type(item) is not str for item in values):
            raise VerifierProcessError("verifier process: request fields are invalid")
    contents = raw_input["verified_contents"]
    if type(contents) is not list:
        raise VerifierProcessError("verifier process: request fields are invalid")
    for entry in contents:
        if (
            type(entry) is not list
            or len(entry) != 2
            or type(entry[0]) is not str
            or type(entry[1]) is not str
        ):
            raise VerifierProcessError("verifier process: request fields are invalid")
