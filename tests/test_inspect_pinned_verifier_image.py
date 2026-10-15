from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import inspect_pinned_verifier_image as inspector
from scripts import stream_pinned_verifier_image as pinned


def completed(stdout=b"", returncode=0, stderr=b""):
    return subprocess.CompletedProcess(args=(), returncode=returncode, stdout=stdout, stderr=stderr)


class PinnedVerifierImageInspectionTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()

    def test_exact_tuple_confirms_with_one_read_only_ssh_call(self):
        runner = mock.Mock(
            return_value=completed((pinned._EXPECTED_REMOTE_INSPECT + "\n").encode("ascii"))
        )
        result = inspector.inspect_remote_image(runner, self.output)

        self.assertEqual(result, 0)
        self.assertEqual(self.output.getvalue(), "REMOTE_IMAGE_CONFIRMED\n")
        runner.assert_called_once()
        command = runner.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/ssh")
        self.assertEqual(command[-2], "alex@192.168.88.101")
        self.assertEqual(command[-1], inspector._REMOTE_COMMAND)
        self.assertIn("docker image inspect", command[-1])
        self.assertNotIn("docker image load", command[-1])
        self.assertNotIn("docker image tag", command[-1])
        self.assertEqual(runner.call_args.kwargs, {
            "capture_output": True,
            "timeout": 15,
            "check": False,
        })
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("PasswordAuthentication=no", command)

    def test_nonexact_tuple_is_bounded_mismatch(self):
        for remote_output in (
            b"PRIVATE_RAW_OUTPUT\n",
            (pinned._EXPECTED_INSPECT + "\n").encode("ascii"),
            (pinned._EXPECTED_REMOTE_INSPECT.replace("|[]", "|[\\\"unexpected:tag\\\"]") + "\n").encode("ascii"),
            (pinned._EXPECTED_REMOTE_INSPECT + "\nextra\n").encode("ascii"),
            b"\xff\n",
        ):
            with self.subTest(remote_output=remote_output[:24]):
                self.output = io.StringIO()
                runner = mock.Mock(return_value=completed(remote_output))
                result = inspector.inspect_remote_image(runner, self.output)
                self.assertEqual(result, 10)
                self.assertEqual(self.output.getvalue(), "REMOTE_IMAGE_IDENTITY_MISMATCH\n")
                self.assertNotIn("PRIVATE_RAW_OUTPUT", self.output.getvalue())
                runner.assert_called_once()

    def test_transport_remote_command_and_launch_failures_are_separated(self):
        scenarios = (
            (mock.Mock(return_value=completed(b"PRIVATE_STDOUT", 255, b"SECRET_STDERR")), 13, "SSH_CLIENT_EXIT_255"),
            (mock.Mock(return_value=completed(b"PRIVATE_STDOUT", 1, b"SECRET_STDERR")), 11, "REMOTE_INSPECT_FAILED"),
            (mock.Mock(side_effect=RuntimeError("SECRET_EXCEPTION")), 12, "SSH_CLIENT_LAUNCH_FAILED"),
        )
        for runner, expected_code, expected_marker in scenarios:
            with self.subTest(runner=runner):
                self.output = io.StringIO()
                result = inspector.inspect_remote_image(runner, self.output)
                self.assertEqual(result, expected_code)
                self.assertEqual(self.output.getvalue(), expected_marker + "\n")
                self.assertNotIn("SECRET", self.output.getvalue())
                runner.assert_called_once()

    def test_exact_gate_is_required_before_remote_dispatch(self):
        for supplied in (
            "RUN EXP-1265 ONCE",
            "RUN EXP-1272 ONCE",
            "RUN EXP-1274 ONCE",
            "RUN EXP-1297 ONCE",
            "",
        ):
            with self.subTest(supplied=supplied):
                stdout = io.StringIO()
                stderr = io.StringIO()
                inspect_call = mock.Mock(return_value=0)
                with (
                    mock.patch.object(inspector.sys, "stdin", io.StringIO(supplied + "\n")),
                    mock.patch.object(inspector.sys, "stdout", stdout),
                    mock.patch.object(inspector.sys, "stderr", stderr),
                    mock.patch.object(inspector, "inspect_remote_image", inspect_call),
                ):
                    result = inspector.main()
                self.assertEqual(result, 19)
                self.assertEqual(stdout.getvalue(), "RUN_NOT_CONFIRMED\n")
                self.assertEqual(stderr.getvalue(), "Type RUN EXP-1315 ONCE to continue: ")
                inspect_call.assert_not_called()

    def test_fresh_exact_gate_dispatches_one_inspection(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        inspect_call = mock.Mock(return_value=0)
        with (
            mock.patch.object(inspector.sys, "stdin", io.StringIO("RUN EXP-1315 ONCE\n")),
            mock.patch.object(inspector.sys, "stdout", stdout),
            mock.patch.object(inspector.sys, "stderr", stderr),
            mock.patch.object(inspector, "inspect_remote_image", inspect_call),
        ):
            result = inspector.main()
        self.assertEqual(result, 0)
        self.assertEqual(stderr.getvalue(), "Type RUN EXP-1315 ONCE to continue: ")
        inspect_call.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
