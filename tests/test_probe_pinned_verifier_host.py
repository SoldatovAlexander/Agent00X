from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import probe_pinned_verifier_host as probe
from scripts import stream_pinned_verifier_image as pinned


def completed(stdout=b"", returncode=0, stderr=b""):
    return subprocess.CompletedProcess(args=(), returncode=returncode, stdout=stdout, stderr=stderr)


class PinnedVerifierHostProbeTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()

    def test_remote_shell_script_parses_without_execution(self):
        result = subprocess.run(
            ("/bin/sh", "-n", "-c", probe._REMOTE_SCRIPT),
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)

    def test_probe_uses_one_strict_ssh_call_with_exact_read_only_checks(self):
        runner = mock.Mock(return_value=completed(b"REMOTE_IMAGE_CONFIRMED\n"))

        result = probe.probe_remote_host(runner, self.output)

        self.assertEqual(result, 0)
        self.assertEqual(self.output.getvalue(), "REMOTE_IMAGE_CONFIRMED\n")
        runner.assert_called_once()
        command = runner.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/ssh")
        self.assertEqual(command[-2], "alex@192.168.88.101")
        self.assertIn("command -v docker", command[-1])
        self.assertIn("docker info", command[-1])
        self.assertIn("docker info >/dev/null 2>&1", command[-1])
        self.assertIn(f"docker image inspect {pinned.IMAGE_ID}", command[-1])
        self.assertIn(pinned._EXPECTED_REMOTE_INSPECT, command[-1])
        self.assertIn("2>/dev/null", command[-1])
        self.assertNotIn("printf '%s\\n' \"$result\"", command[-1])
        self.assertNotIn("docker image load", command[-1])
        self.assertNotIn("docker image tag", command[-1])
        self.assertNotIn("docker run", command[-1])
        self.assertEqual(runner.call_args.kwargs, {
            "capture_output": True,
            "timeout": 20,
            "check": False,
        })
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("PasswordAuthentication=no", command)

    def test_only_allowlisted_fixed_remote_markers_are_forwarded(self):
        expected = {
            "DOCKER_CLI_UNAVAILABLE": 10,
            "DOCKER_DAEMON_UNAVAILABLE": 11,
            "REMOTE_IMAGE_INSPECT_FAILED": 12,
            "REMOTE_IMAGE_IDENTITY_MISMATCH": 13,
            "REMOTE_IMAGE_CONFIRMED": 0,
        }
        for marker, code in expected.items():
            with self.subTest(marker=marker):
                self.output = io.StringIO()
                runner = mock.Mock(return_value=completed((marker + "\n").encode()))

                result = probe.probe_remote_host(runner, self.output)

                self.assertEqual(result, code)
                self.assertEqual(self.output.getvalue(), marker + "\n")
                runner.assert_called_once()

    def test_transport_and_unexpected_output_are_redacted(self):
        scenarios = (
            (mock.Mock(return_value=completed(b"SECRET", 255, b"SECRET_ERR")), 17, "SSH_CLIENT_EXIT_255"),
            (mock.Mock(return_value=completed(b"SECRET", 2, b"SECRET_ERR")), 14, "REMOTE_PROBE_COMMAND_FAILED"),
            (mock.Mock(side_effect=subprocess.TimeoutExpired("ssh", 20, b"SECRET")), 16, "SSH_CLIENT_TIMEOUT"),
            (mock.Mock(side_effect=OSError("SECRET_EXCEPTION")), 15, "SSH_CLIENT_LAUNCH_FAILED"),
            (mock.Mock(return_value=completed(b"SECRET_RAW_OUTPUT\n")), 18, "REMOTE_PROBE_UNEXPECTED"),
            (mock.Mock(return_value=completed(b"REMOTE_IMAGE_CONFIRMED\nextra\n")), 18, "REMOTE_PROBE_UNEXPECTED"),
        )
        for runner, code, marker in scenarios:
            with self.subTest(marker=marker):
                self.output = io.StringIO()

                result = probe.probe_remote_host(runner, self.output)

                self.assertEqual(result, code)
                self.assertEqual(self.output.getvalue(), marker + "\n")
                self.assertNotIn("SECRET", self.output.getvalue())
                runner.assert_called_once()

    def test_exact_gate_required_and_stale_gates_never_dispatch(self):
        for supplied in ("RUN EXP-1277 ONCE", "RUN EXP-1279 ONCE", "RUN EXP-1315 ONCE", ""):
            with self.subTest(supplied=supplied):
                stdout = io.StringIO()
                stderr = io.StringIO()
                dispatch = mock.Mock(return_value=0)
                with (
                    mock.patch.object(probe.sys, "stdin", io.StringIO(supplied + "\n")),
                    mock.patch.object(probe.sys, "stdout", stdout),
                    mock.patch.object(probe.sys, "stderr", stderr),
                    mock.patch.object(probe, "probe_remote_host", dispatch),
                ):
                    result = probe.main()

                self.assertEqual(result, 19)
                self.assertEqual(stdout.getvalue(), "RUN_NOT_CONFIRMED\n")
                dispatch.assert_not_called()

    def test_fresh_exact_gate_dispatches_one_probe(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        dispatch = mock.Mock(return_value=0)
        with (
            mock.patch.object(probe.sys, "stdin", io.StringIO("RUN EXP-1318 ONCE\n")),
            mock.patch.object(probe.sys, "stdout", stdout),
            mock.patch.object(probe.sys, "stderr", stderr),
            mock.patch.object(probe, "probe_remote_host", dispatch),
        ):
            self.assertEqual(probe.main(), 0)

        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "Type RUN EXP-1318 ONCE to continue: ")
        dispatch.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
