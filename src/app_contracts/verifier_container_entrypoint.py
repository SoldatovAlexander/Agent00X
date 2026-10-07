"""Untrusted-input verifier entrypoint for one isolated local container.

It replays a supplied argv-only test command over a detached pinned base and
candidate overlay. A passing command is only local test evidence, not proof of
semantic correctness or remote provenance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import posixpath
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time

from .digests import sha256_digest
from .executor import VerifierInput, VerifierResult, VerifierVerdict
from .verifier_process import (
    MAX_VERIFIER_REQUEST_BYTES,
    VerifierProcessError,
    VerifierProcessRequest,
    VerifierProcessResponse,
    digest_verifier_request,
    parse_verifier_request,
    serialize_verifier_request,
)


MAX_TEST_STDOUT_BYTES = 65_536
MAX_TEST_STDERR_BYTES = 65_536
# The only argument the trusted launcher ever passes: the per-invocation
# 256-bit nonce the child must echo in the bounded verifier_id result field.
# The echo only lets the parent reject stale replays; a child-chosen value can
# never select the accepted identity, which the parent derives from its own
# trusted configuration.
_CONTAINER_ENTRYPOINT_ARGUMENT = "--invocation-nonce="
_INVOCATION_NONCE_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_CHILD_ENV = {
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": "/tmp",
}
_SAFE_REJECTION_CODES = {
    "verifier process: request encoding is invalid": "request-encoding",
    "verifier process: request payload is invalid": "request-payload",
    "verifier process: request version is invalid": "request-version",
    "verifier process: request fields are invalid": "request-fields",
    "verifier process: request size exceeds limit": "request-size",
    "verifier process: snapshot file exceeds limit": "snapshot-file-limit",
    "verifier process: snapshot exceeds limit": "snapshot-total-limit",
    "verifier process: snapshot binding is invalid": "snapshot-binding",
    "verifier container: request encoding is invalid": "request-encoding",
    "verifier container: request size exceeds limit": "request-size",
    "verifier container: input binding is invalid": "input-binding",
    "verifier container: candidate scope is invalid": "candidate-scope",
    "verifier container: test command is invalid": "test-command",
    "verifier container: snapshot path is invalid": "snapshot-path",
}


def _invocation_nonce_from_argv(argv: object) -> str:
    if type(argv) is not list or len(argv) != 2:
        raise VerifierProcessError("verifier container: invocation nonce is invalid")
    argument = argv[1]
    if (
        type(argument) is not str
        or not argument.startswith(_CONTAINER_ENTRYPOINT_ARGUMENT)
    ):
        raise VerifierProcessError("verifier container: invocation nonce is invalid")
    nonce = argument[len(_CONTAINER_ENTRYPOINT_ARGUMENT):]
    if _INVOCATION_NONCE_PATTERN.fullmatch(nonce) is None:
        raise VerifierProcessError("verifier container: invocation nonce is invalid")
    return nonce


def run_verifier_request(data: object, *, invocation_nonce: object) -> bytes:
    """Return one canonical response for a canonical bounded request."""

    if (
        type(invocation_nonce) is not str
        or _INVOCATION_NONCE_PATTERN.fullmatch(invocation_nonce) is None
    ):
        raise VerifierProcessError("verifier container: invocation nonce is invalid")
    request = parse_verifier_request(data)
    canonical_request = serialize_verifier_request(request)
    if canonical_request != data:
        raise VerifierProcessError("verifier container: request encoding is invalid")
    prepared = request.verifier_input
    _validate_overlay(prepared)
    try:
        # The image fixes TMPDIR=/work; local unit tests safely use the host temp root.
        with tempfile.TemporaryDirectory(prefix="verifier-") as temporary:
            workspace = Path(temporary)
            _materialize_base(prepared, workspace)
            _apply_candidate(prepared, workspace)
            verdict, blocker_codes = _run_test_command(prepared, workspace)
    except VerifierProcessError:
        raise
    except Exception:
        verdict, blocker_codes = VerifierVerdict.BLOCKED, ("workspace-failed",)

    result = VerifierResult(
        process_id=prepared.process_id,
        base_commit=prepared.base_commit,
        snapshot_tree_digest=prepared.snapshot_tree_digest,
        replay_result_digest=prepared.replay_result_digest,
        verifier_id=invocation_nonce,
        patch_digest=prepared.patch_digest,
        evidence_digest=prepared.evidence_digest,
        verification_digest=prepared.verification_digest,
        verified_contents_digest=prepared.verified_contents_digest,
        verdict=verdict,
        blocker_codes=blocker_codes,
        evidence_origin="local_test",
    )
    response = VerifierProcessResponse.from_verifier_result(
        result, digest_verifier_request(request)
    )
    return _canonical_response_bytes(response)


def main() -> int:
    """Read one bounded stdin record and emit only a typed JSON response."""

    try:
        invocation_nonce = _invocation_nonce_from_argv(sys.argv)
        data = sys.stdin.buffer.read(MAX_VERIFIER_REQUEST_BYTES + 1)
        if len(data) > MAX_VERIFIER_REQUEST_BYTES:
            raise VerifierProcessError("verifier container: request size exceeds limit")
        sys.stdout.buffer.write(
            run_verifier_request(data, invocation_nonce=invocation_nonce)
        )
        sys.stdout.buffer.flush()
        return 0
    except VerifierProcessError as exc:
        # Map only exact fixed internal errors to codes. Never print exception
        # text, which could accidentally include request-controlled material.
        rejection_code = _SAFE_REJECTION_CODES.get(str(exc))
        if rejection_code is None:
            sys.stderr.write("verifier container: request or execution rejected\n")
        else:
            sys.stderr.write(f"verifier container: rejection:{rejection_code}\n")
        sys.stderr.flush()
        return 2
    except Exception:
        # Never print request bytes, test output, exception reprs or paths.
        sys.stderr.write("verifier container: request or execution rejected\n")
        sys.stderr.flush()
        return 2


def _canonical_response_bytes(response: VerifierProcessResponse) -> bytes:
    result = response.verifier_result
    payload = {
        "schema_version": response.schema_version,
        "request_digest": response.request_digest,
        "verifier_result": {
            "process_id": result.process_id,
            "base_commit": result.base_commit,
            "snapshot_tree_digest": result.snapshot_tree_digest,
            "replay_result_digest": result.replay_result_digest,
            "verifier_id": result.verifier_id,
            "patch_digest": result.patch_digest,
            "evidence_digest": result.evidence_digest,
            "verification_digest": result.verification_digest,
            "verified_contents_digest": result.verified_contents_digest,
            "verdict": result.verdict.value,
            "blocker_codes": list(result.blocker_codes),
            "evidence_origin": result.evidence_origin,
        },
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _validate_overlay(prepared: VerifierInput) -> None:
    if (
        prepared.snapshot_tree_digest is None
        or prepared.replay_result_digest is None
        or sha256_digest(prepared.verified_contents)
        != prepared.verified_contents_digest
    ):
        raise VerifierProcessError("verifier container: input binding is invalid")
    declared = prepared.declared_change_paths
    contents = prepared.verified_contents
    if not declared or len(set(declared)) != len(declared):
        raise VerifierProcessError("verifier container: candidate scope is invalid")
    if any(not _is_safe_relative_path(path) for path in declared):
        raise VerifierProcessError("verifier container: candidate scope is invalid")
    content_paths = tuple(path for path, _ in contents)
    if (
        len(set(content_paths)) != len(content_paths)
        or set(content_paths) != set(declared)
        or any(not _is_safe_relative_path(path) for path in content_paths)
    ):
        raise VerifierProcessError("verifier container: candidate scope is invalid")
    if not prepared.test_command or any(
        not isinstance(argument, str) or not argument for argument in prepared.test_command
    ):
        raise VerifierProcessError("verifier container: test command is invalid")


def _is_safe_relative_path(value: str) -> bool:
    return (
        type(value) is str
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and "\x00" not in value
        and posixpath.normpath(value) == value
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _target(root: Path, relative: str) -> Path:
    if not _is_safe_relative_path(relative):
        raise VerifierProcessError("verifier container: snapshot path is invalid")
    return root.joinpath(*relative.split("/"))


def _materialize_base(prepared: VerifierInput, workspace: Path) -> None:
    for relative, mode, content in prepared.snapshot_files:
        destination = _target(workspace, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        destination.chmod(0o755 if mode == "100755" else 0o644)


def _apply_candidate(prepared: VerifierInput, workspace: Path) -> None:
    base_modes = {path: mode for path, mode, _ in prepared.snapshot_files}
    for relative, content in prepared.verified_contents:
        destination = _target(workspace, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        destination.chmod(0o755 if base_modes.get(relative) == "100755" else 0o644)


def _run_test_command(
    prepared: VerifierInput, workspace: Path
) -> tuple[VerifierVerdict, tuple[str, ...]]:
    try:
        process = subprocess.Popen(
            prepared.test_command,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(_CHILD_ENV),
            shell=False,
            start_new_session=True,
        )
    except Exception:
        return VerifierVerdict.BLOCKED, ("test-command-launch-failed",)

    stdout = bytearray()
    stderr = bytearray()
    deadline = time.monotonic() + prepared.test_timeout_seconds
    try:
        assert process.stdout is not None and process.stderr is not None
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _kill_process_group(process)
                    return VerifierVerdict.BLOCKED, ("test-command-timeout",)
                for key, _ in selector.select(timeout=remaining):
                    try:
                        chunk = os.read(key.fileobj.fileno(), 8192)
                    except BlockingIOError:
                        continue
                    except OSError:
                        chunk = b""
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    target = stdout if key.data == "stdout" else stderr
                    target.extend(chunk)
                    cap = MAX_TEST_STDOUT_BYTES if key.data == "stdout" else MAX_TEST_STDERR_BYTES
                    if len(target) > cap:
                        _kill_process_group(process)
                        return VerifierVerdict.BLOCKED, ("test-command-output-limit",)
        remaining = deadline - time.monotonic()
        try:
            exit_code = process.wait(timeout=max(0, remaining))
        except subprocess.TimeoutExpired:
            _kill_process_group(process)
            return VerifierVerdict.BLOCKED, ("test-command-timeout",)
    finally:
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except Exception:
                pass
        if process.poll() is None:
            _kill_process_group(process)
    if exit_code == 0:
        return VerifierVerdict.PASS, ()
    return VerifierVerdict.FAIL, ("test-command-failed",)


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
    try:
        process.wait(timeout=2)
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
