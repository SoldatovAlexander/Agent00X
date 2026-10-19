from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from scripts import capture_pinned_verifier_bootstrap as capture


class _FakeProcess:
    def __init__(self, stdout, *, poll_code=None):
        self.stdout = stdout
        self.poll_code = poll_code
        self.terminated = False
        self.killed = False
        self.wait_calls = []

    def poll(self):
        return self.poll_code

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if self.poll_code is None:
            self.poll_code = -15 if self.terminated else 0
        return self.poll_code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.poll_code = -9


class CapturePinnedVerifierBootstrapTests(unittest.TestCase):
    def _stream(self, raw: bytes):
        read_fd, write_fd = os.pipe()
        try:
            view = memoryview(raw)
            while view:
                count = os.write(write_fd, view)
                view = view[count:]
        finally:
            os.close(write_fd)
        return os.fdopen(read_fd, "rb", buffering=0)

    def _bound(self, **changes):
        fields = {
            "bootstrap_sha256": "sha256:" + "1" * 64,
            "connect_port": 49231,
            "tls_ca_sha256": "sha256:" + "2" * 64,
            "verifier_public_key_sha256": "sha256:" + "3" * 64,
            "trust_established": False,
        }
        fields.update(changes)
        return SimpleNamespace(**fields)

    def _start(self, directory, raw=b'{"public":"bootstrap"}\n', *, parser=None):
        output_path = Path(directory) / "bootstrap.json"
        stream = self._stream(raw)
        process = _FakeProcess(stream)
        popen = Mock(return_value=process)
        output = io.StringIO()
        parser_fn = parser or Mock(return_value=self._bound())
        session = capture.start_pinned_verifier_session(
            str(output_path), popen_factory=popen, output=output, parser=parser_fn
        )
        return output_path, stream, process, popen, output, parser_fn, session

    def test_exact_command_and_full_line_are_captured_without_raw_output(self):
        raw = b'{"public":"bootstrap","ca":"never print me"}\n'
        with tempfile.TemporaryDirectory() as directory:
            path, stream, process, popen, output, parser, session = self._start(
                directory, raw
            )
            try:
                command = popen.call_args.args[0]
                kwargs = popen.call_args.kwargs
                self.assertEqual(command, list(capture._ssh_command()))
                self.assertEqual(
                    capture.REMOTE_LAUNCHER,
                    "/home/alex/.local/share/agent00x/verifier-host/exp-1491/scripts/"
                    "serve_ephemeral_signed_verifier_https.py",
                )
                self.assertEqual(kwargs["executable"], "/usr/bin/ssh")
                self.assertFalse(kwargs["shell"])
                self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
                self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
                self.assertEqual(session.bootstrap, raw)
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                expected = "sha256:" + hashlib.sha256(raw).hexdigest()
                parser.assert_called_once_with(raw, expected_sha256=expected)
                self.assertEqual(
                    output.getvalue(),
                    f"BOOTSTRAP_CAPTURED|{expected}|port=49231|trust=unestablished\n",
                )
                self.assertNotIn("never print me", output.getvalue())
                self.assertEqual(session.wait(), 0)
            finally:
                stream.close()
                process.stdout.close()

    def test_existing_and_symlink_outputs_fail_before_ssh(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "existing.json"
            existing.write_bytes(b"keep")
            symlink = Path(directory) / "link.json"
            symlink.symlink_to(existing)
            for target in (existing, symlink):
                popen = Mock()
                output = io.StringIO()
                with self.subTest(target=target.name), self.assertRaises(
                    capture.VerifierBootstrapCaptureError
                ):
                    capture.start_pinned_verifier_session(
                        str(target), popen_factory=popen, output=output
                    )
                popen.assert_not_called()
                self.assertEqual(output.getvalue(), "BOOTSTRAP_CAPTURE_REJECTED\n")
            self.assertEqual(existing.read_bytes(), b"keep")

    def test_parser_rejection_stops_and_reaps_only_the_started_child(self):
        with tempfile.TemporaryDirectory() as directory:
            stream = self._stream(b"not validated\n")
            process = _FakeProcess(stream)
            popen = Mock(return_value=process)
            output = io.StringIO()
            parser = Mock(side_effect=ValueError("sensitive detail"))
            with self.assertRaises(capture.VerifierBootstrapCaptureError):
                capture.start_pinned_verifier_session(
                    str(Path(directory) / "bootstrap.json"),
                    popen_factory=popen,
                    output=output,
                    parser=parser,
                )
            self.assertEqual(popen.call_count, 1)
            self.assertTrue(process.terminated)
            self.assertEqual(process.wait_calls, [capture.STOP_TIMEOUT_SECONDS])
            self.assertEqual(output.getvalue(), "BOOTSTRAP_CAPTURE_REJECTED\n")
            self.assertFalse((Path(directory) / "bootstrap.json").exists())
            stream.close()

    def test_wrong_port_or_trust_promotion_is_rejected(self):
        for bound in (self._bound(connect_port=49232), self._bound(trust_established=True)):
            with tempfile.TemporaryDirectory() as directory:
                stream = self._stream(b"public\n")
                process = _FakeProcess(stream)
                popen = Mock(return_value=process)
                output = io.StringIO()
                with self.subTest(bound=bound.connect_port, trusted=bound.trust_established):
                    with self.assertRaises(capture.VerifierBootstrapCaptureError):
                        capture.start_pinned_verifier_session(
                            str(Path(directory) / "bootstrap.json"),
                            popen_factory=popen,
                            output=output,
                            parser=Mock(return_value=bound),
                        )
                    self.assertTrue(process.terminated)
                    self.assertEqual(output.getvalue(), "BOOTSTRAP_CAPTURE_REJECTED\n")
                stream.close()

    def test_bounded_reader_rejects_missing_oversized_and_multiple_lines(self):
        for raw in (b"no newline", b"x" * (capture.MAX_BOOTSTRAP_BYTES + 1) + b"\n", b"a\nb\n"):
            stream = self._stream(raw)
            process = _FakeProcess(stream)
            with self.subTest(size=len(raw)), self.assertRaises(
                capture.VerifierBootstrapCaptureError
            ):
                capture._read_bootstrap_line(stream, process)
            stream.close()

    def test_bounded_reader_rejects_timeout_and_early_process_exit(self):
        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, "rb", buffering=0)
        process = _FakeProcess(stream)
        try:
            with self.assertRaises(capture.VerifierBootstrapCaptureError):
                capture._read_bootstrap_line(stream, process, timeout_seconds=0.01)
        finally:
            stream.close()
            os.close(write_fd)

        stream = self._stream(b"")
        process = _FakeProcess(stream, poll_code=2)
        try:
            with self.assertRaises(capture.VerifierBootstrapCaptureError):
                capture._read_bootstrap_line(stream, process)
        finally:
            stream.close()

    def test_session_stop_terminates_and_reaps_child_once(self):
        process = _FakeProcess(None)
        session = capture.ActiveVerifierSession(
            process=process,
            bootstrap=b"public\n",
            bound=self._bound(),
        )
        session.stop()
        self.assertTrue(process.terminated)
        self.assertEqual(process.wait_calls, [capture.STOP_TIMEOUT_SECONDS])


if __name__ == "__main__":
    unittest.main()
