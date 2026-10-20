from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import stream_pinned_verifier_image as transfer


def completed(stdout=b"", returncode=0, stderr=b""):
    return subprocess.CompletedProcess(args=(), returncode=returncode, stdout=stdout, stderr=stderr)


class PinnedVerifierImageTransferTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()

    def run_with_fake_remote(self, load_output, load_rc=0, inspect_rc=0, inspect_output=None):
        if inspect_output is None:
            inspect_output = transfer._EXPECTED_REMOTE_INSPECT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_docker = root / "docker"
            inspect_log = root / "inspect.log"
            fake_docker.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = image ] && [ "$2" = load ]; then\n'
                '  printf "%s" "$FAKE_LOAD_OUTPUT"\n'
                '  exit "$FAKE_LOAD_RC"\n'
                "fi\n"
                'if [ "$1" = image ] && [ "$2" = inspect ]; then\n'
                '  printf "%s\\n" inspect >> "$FAKE_INSPECT_LOG"\n'
                '  if [ "$FAKE_INSPECT_RC" -ne 0 ]; then\n'
                '    printf "%s" PRIVATE_INSPECT_ERROR >&2\n'
                '    exit "$FAKE_INSPECT_RC"\n'
                "  fi\n"
                '  printf "%s\\n" "$FAKE_INSPECT_OUTPUT"\n'
                "  exit 0\n"
                "fi\n"
                "exit 90\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o700)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{directory}:{env.get('PATH', '')}",
                    "FAKE_LOAD_OUTPUT": load_output,
                    "FAKE_LOAD_RC": str(load_rc),
                    "FAKE_INSPECT_RC": str(inspect_rc),
                    "FAKE_INSPECT_OUTPUT": inspect_output,
                    "FAKE_INSPECT_LOG": str(inspect_log),
                }
            )
            calls = []

            def runner(command, **kwargs):
                calls.append(command)
                if command[0] == "/usr/local/bin/docker" and command[2] == "inspect":
                    return completed((transfer._EXPECTED_INSPECT + "\n").encode("ascii"))
                if command[0] == "/usr/local/bin/docker" and command[2] == "save":
                    return completed(b"x" * 8)
                if command[0] == "/usr/bin/ssh":
                    return subprocess.run(
                        ("/bin/sh", "-c", transfer._REMOTE_COMMAND),
                        input=kwargs["input"],
                        capture_output=True,
                        timeout=kwargs["timeout"],
                        check=False,
                        env=env,
                    )
                raise AssertionError("unexpected command")

            with mock.patch.object(transfer, "STREAM_SIZE", 8):
                status = transfer.run_transfer(runner, self.output)
            remote_output = self.output.getvalue()
            inspect_calls = inspect_log.read_text(encoding="utf-8") if inspect_log.exists() else ""
            return status, remote_output, inspect_calls, calls

    def test_pins_and_remote_command_are_exact_and_fixed(self):
        self.assertEqual(transfer.IMAGE_ID, "sha256:228e703737010ccc001b5d784f35711ca49a00e3af4be5f0a8fcdd2fe06350a0")
        self.assertEqual(transfer.REMOTE_CONFIG_IMAGE_ID, "sha256:d65ca82a1d944f76b7c86163f4f3bcd0c4b4e3c603ce5005e510fcb86ee73c42")
        self.assertEqual(transfer.IMAGE_CODE_DIGEST, "sha256:36f4f81cd98355665992fd9feb0f8ac4f3a6807b2ffb1b332956b694e9031d5f")
        self.assertEqual(transfer.IMAGE_TAG, "agent00x-verifier:exp-1658")
        self.assertEqual(transfer.IMAGE_SIZE, 48857457)
        self.assertEqual(transfer.STREAM_SIZE, 48871936)
        self.assertEqual(
            transfer.DIFF_IDS,
            (
                "sha256:a6dc765193a52cbaede3c93a9ff48b9540948dd0774bbe7031fcb5847606f9ac",
                "sha256:a5c84380b3657bb723a1f71fa963f1e3a3f01e2c6bcba12e3b9a0d336158c7a9",
                "sha256:4a01ba3ac604812ef31dab0006efecd1d572676f7a68afa169a9d57883025006",
                "sha256:d190d09d7bd91836f809045799a7024a54026b3da5de1ccb811627fcf9878b92",
                "sha256:beabc7f2b008356b23800eefa4ad544e11ddb9f695c47f9dbd740c59319dc536",
            "sha256:9b57205ce6c7f897a201da5080de50cf0abddf267a68d5d40e65b33860672413",
            "sha256:ce69400711a693d54ad36863e81a61e853a3a72fd063a5c7abe67c5f91ed7736",
            "sha256:eeeece982ad49e8d6decd0e61a2e63a84d79384bcf7ff25222791ad2bb1bb682",
            "sha256:1b25752190e75eef92e61abad741ae09b2d1ce8108f84af7470ecd7fcf3a7e4f",
            ),
        )
        self.assertIn("{{json .RepoTags}}", transfer._INSPECT_FORMAT)
        self.assertTrue(transfer._EXPECTED_INSPECT.endswith(f'|["{transfer.IMAGE_TAG}"]'))
        self.assertTrue(transfer._EXPECTED_REMOTE_INSPECT.endswith("|[]"))
        self.assertNotIn(transfer.IMAGE_TAG, transfer._EXPECTED_REMOTE_INSPECT)
        self.assertTrue(transfer._EXPECTED_INSPECT.startswith(transfer.IMAGE_ID + "|"))
        self.assertTrue(
            transfer._EXPECTED_REMOTE_INSPECT.startswith(
                transfer.REMOTE_CONFIG_IMAGE_ID + "|"
            )
        )
        self.assertIn(transfer.REMOTE_CONFIG_IMAGE_ID, transfer._REMOTE_COMMAND)
        self.assertNotIn("{{.Size}}", transfer._REMOTE_INSPECT_FORMAT)
        self.assertIn("StrictHostKeyChecking=yes", transfer._SSH_OPTIONS)
        self.assertIn("PasswordAuthentication=no", transfer._SSH_OPTIONS)
        self.assertIn(transfer.REMOTE_CONFIG_IMAGE_ID, transfer._REMOTE_COMMAND)
        self.assertIn("docker image load >/dev/null 2>&1", transfer._REMOTE_COMMAND)
        self.assertIn("REMOTE_LOAD_FAILED", transfer._REMOTE_COMMAND)
        self.assertLess(
            transfer._REMOTE_COMMAND.index("REMOTE_LOAD_FAILED"),
            transfer._REMOTE_COMMAND.index("docker image inspect"),
        )
        self.assertNotIn("ProxyCommand", transfer._REMOTE_COMMAND)

    def test_remote_load_output_variants_are_ignored_when_exact_inspect_matches(self):
        wrong_id = "sha256:" + "0" * 64
        load_outputs = (
            "PRIVATE_WRONG_IMAGE_ID\n",
            f"Loaded image: {transfer.IMAGE_TAG}\n",
            f"Loaded image ID: {wrong_id}\n",
            "PRIVATE_LOAD_OUTPUT\nPRIVATE_ADDITIONAL_OUTPUT\n",
            "\n\n",
            "",
        )
        for load_output in load_outputs:
            with self.subTest(load_output=load_output):
                self.output = io.StringIO()
                status, output, inspect_calls, calls = self.run_with_fake_remote(load_output)
                self.assertEqual(status, 0)
                self.assertEqual(output, "IMAGE_IMPORT_CONFIRMED\n")
                if load_output.strip():
                    self.assertNotIn(load_output.strip(), output)
                self.assertEqual(inspect_calls, "inspect\n")
                self.assertEqual(sum(command[0] == "/usr/bin/ssh" for command in calls), 1)

    def test_remote_load_failure_and_inspect_failure_are_redacted_and_not_retried(self):
        status, output, inspect_calls, calls = self.run_with_fake_remote(
            "PRIVATE_LOAD_OUTPUT\n", load_rc=9
        )
        self.assertEqual(status, transfer._MARKER_CODES["REMOTE_LOAD_FAILED"])
        self.assertEqual(output, "REMOTE_LOAD_FAILED\n")
        self.assertEqual(inspect_calls, "")
        self.assertEqual(sum(command[0] == "/usr/bin/ssh" for command in calls), 1)

        self.output = io.StringIO()
        status, output, inspect_calls, calls = self.run_with_fake_remote(
            "PRIVATE_LOAD_OUTPUT\n", inspect_rc=9
        )
        self.assertEqual(status, transfer._MARKER_CODES["REMOTE_INSPECT_FAILED"])
        self.assertEqual(output, "REMOTE_INSPECT_FAILED\n")
        self.assertNotIn("PRIVATE_INSPECT_ERROR", output)
        self.assertEqual(inspect_calls, "inspect\n")
        self.assertEqual(sum(command[0] == "/usr/bin/ssh" for command in calls), 1)

    def test_inspect_mismatch_stops_before_save_and_ssh(self):
        runner = mock.Mock(return_value=completed(b"wrong\n"))
        result = transfer.run_transfer(runner, self.output)
        self.assertEqual(result, 11)
        self.assertEqual(self.output.getvalue(), "LOCAL_IMAGE_IDENTITY_MISMATCH\n")
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args[0][0:3], ("/usr/local/bin/docker", "image", "inspect"))

    def test_inspect_failure_hides_raw_stderr_and_stops(self):
        runner = mock.Mock(return_value=completed(stderr=b"SECRET_RAW_ERROR", returncode=1))
        result = transfer.run_transfer(runner, self.output)
        self.assertEqual(result, 10)
        self.assertEqual(self.output.getvalue(), "LOCAL_IMAGE_INSPECT_FAILED\n")
        self.assertNotIn("SECRET_RAW_ERROR", self.output.getvalue())
        runner.assert_called_once()

    def test_save_failure_and_size_mismatch_never_call_ssh(self):
        exact = (transfer._EXPECTED_INSPECT + "\n").encode("ascii")
        for saved, expected_marker in (
            (completed(stderr=b"private error", returncode=1), "LOCAL_IMAGE_SAVE_FAILED"),
            (completed(b"short"), "LOCAL_IMAGE_STREAM_SIZE_MISMATCH"),
        ):
            with self.subTest(marker=expected_marker):
                self.output = io.StringIO()
                runner = mock.Mock(side_effect=(completed(exact), saved))
                transfer.run_transfer(runner, self.output)
                self.assertEqual(self.output.getvalue(), expected_marker + "\n")
                self.assertEqual(runner.call_count, 2)

    def test_success_uses_exact_commands_once_and_keeps_stream_in_memory(self):
        exact_local = (transfer._EXPECTED_INSPECT + "\n").encode("ascii")
        exact_remote = (transfer._EXPECTED_REMOTE_INSPECT + "\n").encode("ascii")
        stream = b"x" * 8
        runner = mock.Mock(
            side_effect=(completed(exact_local), completed(stream), completed(exact_remote))
        )
        with mock.patch.object(transfer, "STREAM_SIZE", len(stream)):
            result = transfer.run_transfer(runner, self.output)
        self.assertEqual(result, 0)
        self.assertEqual(self.output.getvalue(), "IMAGE_IMPORT_CONFIRMED\n")
        self.assertEqual(runner.call_count, 3)
        ssh_call = runner.call_args_list[2]
        save_call = runner.call_args_list[1]
        self.assertEqual(
            save_call.args[0],
            ("/usr/local/bin/docker", "image", "save", transfer.IMAGE_ID),
        )
        self.assertIn(transfer.IMAGE_ID, save_call.args[0])
        self.assertNotIn(transfer.IMAGE_TAG, save_call.args[0])
        self.assertEqual(ssh_call.args[0][0], "/usr/bin/ssh")
        self.assertEqual(ssh_call.kwargs["input"], stream)
        self.assertNotIn("--output", ssh_call.args[0])
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_save_is_given_the_immutable_id_and_never_the_repo_tag(self):
        exact_local = (transfer._EXPECTED_INSPECT + "\n").encode("ascii")
        exact_remote = (transfer._EXPECTED_REMOTE_INSPECT + "\n").encode("ascii")
        stream = b"x" * 8
        runner = mock.Mock(side_effect=(completed(exact_local), completed(stream), completed(exact_remote)))
        with mock.patch.object(transfer, "STREAM_SIZE", len(stream)):
            status = transfer.run_transfer(runner, self.output)
        self.assertEqual(status, 0)
        save_command = runner.call_args_list[1].args[0]
        self.assertEqual(save_command[-1], transfer.IMAGE_ID)
        self.assertNotIn(transfer.IMAGE_TAG, save_command)
        self.assertEqual(
            runner.call_args_list[0].args[0][-1],
            transfer.IMAGE_ID,
        )
        self.assertEqual(self.output.getvalue(), "IMAGE_IMPORT_CONFIRMED\n")

    def test_remote_inspect_requires_exact_identity_tuple_and_empty_repo_tags(self):
        tagged_local_tuple = transfer._EXPECTED_INSPECT + "\n"
        wrong_id_tuple = (
            transfer._EXPECTED_REMOTE_INSPECT.replace(
                transfer.REMOTE_CONFIG_IMAGE_ID, "sha256:" + "f" * 64
            )
            + "\n"
        )
        for inspect_output, private_text in (
            (tagged_local_tuple, transfer.IMAGE_TAG),
            (wrong_id_tuple, "sha256:" + "f" * 64),
            ("PRIVATE_RAW_INSPECT_OUTPUT\n", "PRIVATE_RAW_INSPECT_OUTPUT"),
        ):
            with self.subTest(private_text=private_text):
                self.output = io.StringIO()
                status, output, inspect_calls, calls = self.run_with_fake_remote(
                    "PRIVATE_LOAD_OUTPUT\n",
                    inspect_output=inspect_output.rstrip("\n"),
                )
                self.assertEqual(
                    status, transfer._MARKER_CODES["REMOTE_IMAGE_IDENTITY_MISMATCH"]
                )
                self.assertEqual(output, "REMOTE_IMAGE_IDENTITY_MISMATCH\n")
                self.assertNotIn(private_text, output)
                self.assertEqual(inspect_calls, "inspect\n")
                self.assertEqual(sum(command[0] == "/usr/bin/ssh" for command in calls), 1)

    def test_ssh_and_remote_failures_are_bounded_and_distinct(self):
        exact = (transfer._EXPECTED_INSPECT + "\n").encode("ascii")
        scenarios = (
            (completed(b"private output", 255, b"SECRET_RAW_ERROR"), "SSH_OR_REMOTE_COMMAND_FAILED"),
            (completed(b"REMOTE_LOAD_FAILED\n", 41), "REMOTE_LOAD_FAILED"),
            (completed(b"REMOTE_INSPECT_FAILED\n", 42), "REMOTE_INSPECT_FAILED"),
            (completed(b"different|image\n"), "REMOTE_IMAGE_IDENTITY_MISMATCH"),
        )
        for ssh_result, expected_marker in scenarios:
            with self.subTest(marker=expected_marker):
                self.output = io.StringIO()
                runner = mock.Mock(side_effect=(completed(exact), completed(b"x" * 8), ssh_result))
                with mock.patch.object(transfer, "STREAM_SIZE", 8):
                    transfer.run_transfer(runner, self.output)
                self.assertEqual(self.output.getvalue(), expected_marker + "\n")
                self.assertNotIn("SECRET_RAW_ERROR", self.output.getvalue())
                self.assertEqual(runner.call_count, 3)

    def test_exceptions_are_hidden_and_do_not_retry(self):
        runner = mock.Mock(side_effect=RuntimeError("SECRET_RAW_ERROR"))
        result = transfer.run_transfer(runner, self.output)
        self.assertEqual(result, 10)
        self.assertEqual(self.output.getvalue(), "LOCAL_IMAGE_INSPECT_FAILED\n")
        self.assertNotIn("SECRET_RAW_ERROR", self.output.getvalue())
        runner.assert_called_once()

    def test_one_shot_main_rejects_stale_gate_without_dispatch(self):
        for supplied in ("RUN EXP-1272 ONCE", "RUN EXP-1261 ONCE", "RUN EXP-1286 ONCE", "RUN EXP-1296 ONCE", "RUN EXP-1494 ONCE", "", "RUN EXP-1494 ONCE extra"):
            with self.subTest(supplied=supplied):
                output = io.StringIO()
                error = io.StringIO()
                transfer_call = mock.Mock(return_value=0)
                with (
                    mock.patch.object(transfer.sys, "stdin", io.StringIO(supplied + "\n")),
                    mock.patch.object(transfer.sys, "stdout", output),
                    mock.patch.object(transfer.sys, "stderr", error),
                    mock.patch.object(transfer, "run_transfer", transfer_call),
                ):
                    result = transfer.main()
                self.assertEqual(result, transfer._MARKER_CODES["RUN_NOT_CONFIRMED"])
                self.assertEqual(output.getvalue(), "RUN_NOT_CONFIRMED\n")
                self.assertEqual(
                    error.getvalue(),
                    "Type RUN EXP-1637 ONCE to continue: ",
                )
                transfer_call.assert_not_called()

                self.assertEqual(output.getvalue(), "RUN_NOT_CONFIRMED\n")

    def test_one_shot_main_dispatches_transfer_once_for_exact_gate(self):
        output = io.StringIO()
        error = io.StringIO()
        transfer_call = mock.Mock(return_value=0)
        with (
            mock.patch.object(transfer.sys, "stdin", io.StringIO("RUN EXP-1637 ONCE\n")),
            mock.patch.object(transfer.sys, "stdout", output),
            mock.patch.object(transfer.sys, "stderr", error),
            mock.patch.object(transfer, "run_transfer", transfer_call),
        ):
            result = transfer.main()
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error.getvalue(), "Type RUN EXP-1637 ONCE to continue: ")
        transfer_call.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
