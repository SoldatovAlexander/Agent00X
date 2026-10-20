from __future__ import annotations

import io
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest import mock

from scripts import serve_pinned_verifier_image_exp1653 as serve
from scripts import stream_pinned_verifier_image as pinned


def completed(stdout=b"", returncode=0, stderr=b""):
    return subprocess.CompletedProcess(args=(), returncode=returncode, stdout=stdout, stderr=stderr)


class _TTYInput(io.StringIO):
    def isatty(self):
        return True


class _FakeServer:
    def __init__(self, address, archive):
        self.archive = archive
        self.server_address = (address[0], 49237)
        self.request_consumed = False
        self.archive_served = False
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *_args):
        self.exited = True

    def handle_request(self):
        self.request_consumed = True
        self.archive_served = True


class ServePinnedVerifierImageExp1653Tests(unittest.TestCase):
    @staticmethod
    def _valid_archive_audit(_archive, **kwargs):
        kwargs["output"].write(
        f"ARCHIVE_CONFIRMED|{pinned.REMOTE_CONFIG_IMAGE_ID}|{pinned.STREAM_SIZE}|"
            f"{len(pinned.DIFF_IDS)}|ok\n"
        )
        return 0

    def _run_remote_command_stubbed(
        self,
        *,
        archive: bytes,
        expected_digest: str,
        load_returncode: int = 0,
        inspect_tuple: str | None = None,
    ):
        tempdir = tempfile.TemporaryDirectory()
        root = Path(tempdir.name)
        bindir = root / "bin"
        bindir.mkdir()
        archive_path = root / "source-archive.tar"
        archive_path.write_bytes(archive)
        path_log = root / "temporary-archive-path"
        docker_log = root / "docker-load-called"
        curl_stub = bindir / "curl"
        curl_stub.write_text(
            "#!/bin/sh\n"
            "out=\nurl=\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  case \"$1\" in\n"
            "    --output) out=$2; shift 2 ;;\n"
            "    --max-time) shift 2 ;;\n"
            "    -fsS) shift ;;\n"
            "    *) url=$1; shift ;;\n"
            "  esac\n"
            "done\n"
            "[ \"$url\" = \"$TEST_EXPECTED_URL\" ] || exit 8\n"
            "printf '%s\\n' \"$out\" > \"$TEST_ARCHIVE_PATH_LOG\"\n"
            "cp \"$TEST_ARCHIVE_SOURCE\" \"$out\"\n",
            encoding="utf-8",
        )
        hash_stub = bindir / "sha256sum"
        hash_stub.write_text(
            "#!/bin/sh\n"
            "python3 -c 'import hashlib,sys; p=sys.argv[1]; "
            "print(hashlib.sha256(open(p, \"rb\").read()).hexdigest(), p)' \"$1\"\n",
            encoding="utf-8",
        )
        actual_tuple = inspect_tuple or pinned._EXPECTED_REMOTE_INSPECT
        docker_stub = bindir / "docker"
        docker_stub.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = image ] && [ \"$2\" = load ]; then\n"
            "  [ \"$3\" = --input ] || exit 21\n"
            "  printf '%s\\n' \"$4\" > \"$TEST_DOCKER_LOAD_MARKER\"\n"
            "  cmp \"$4\" \"$TEST_ARCHIVE_SOURCE\" || exit 22\n"
            "  exit \"$TEST_DOCKER_LOAD_RC\"\n"
            "fi\n"
            "if [ \"$1\" = image ] && [ \"$2\" = inspect ]; then\n"
            "  printf '%s\\n' \"$TEST_INSPECT_TUPLE\"\n"
            "  exit 0\n"
            "fi\n"
            "exit 23\n",
            encoding="utf-8",
        )
        for stub in (curl_stub, hash_stub, docker_stub):
            stub.chmod(0o700)

        bind_address, port = "192.168.88.5", 49237
        command = serve.remote_import_command(
            bind_address, port, expected_digest
        )
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{bindir}:/usr/bin:/bin",
                "TEST_ARCHIVE_SOURCE": str(archive_path),
                "TEST_ARCHIVE_PATH_LOG": str(path_log),
                "TEST_DOCKER_LOAD_MARKER": str(docker_log),
                "TEST_EXPECTED_URL": (
                    f"http://{bind_address}:{port}{serve.REQUEST_PATH}"
                ),
                "TEST_EXPECTED_TUPLE": actual_tuple,
                "TEST_DOCKER_LOAD_RC": str(load_returncode),
                "TEST_INSPECT_TUPLE": actual_tuple,
            }
        )
        completed_command = subprocess.run(
            ("/bin/bash", "-c", command),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env=environment,
        )
        temp_archive = (
            Path(path_log.read_text(encoding="utf-8").strip())
            if path_log.exists()
            else None
        )
        docker_called = docker_log.exists()
        docker_input = docker_log.read_text(encoding="utf-8").strip() if docker_called else None
        if temp_archive is not None:
            self.assertFalse(temp_archive.exists(), "EXIT trap must remove temp archive")
        tempdir.cleanup()
        return completed_command, docker_called, docker_input

    def test_bind_address_requires_explicit_private_unicast_ipv4(self):
        for value in (
            "0.0.0.0",
            "127.0.0.1",
            "169.254.1.2",
            "224.0.0.1",
            "2001:db8::1",
            "example.local",
            "192.168.1.1;touch /tmp/x",
            None,
        ):
            with self.subTest(value=value):
                self.assertIsNone(serve.validate_bind_address(value))
        self.assertEqual(serve.validate_bind_address("192.168.88.24"), "192.168.88.24")

    def test_archive_preparation_inspects_saves_and_validates_exact_image_once(self):
        archive = b"synthetic-image-archive"
        runner = mock.Mock(
            side_effect=(
                completed((pinned._EXPECTED_INSPECT + "\n").encode("ascii")),
                completed(archive),
            )
        )
        validation_output = io.StringIO()
        with mock.patch.object(
            serve.archive_audit,
            "inspect_archive",
            side_effect=self._valid_archive_audit,
        ) as audit:
            result = serve.prepare_archive(runner, output=validation_output)
        self.assertEqual(result, archive)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(
            runner.call_args_list[0].args[0][-1], pinned.IMAGE_ID
        )
        self.assertEqual(
            runner.call_args_list[1].args[0],
            ("/usr/local/bin/docker", "image", "save", pinned.IMAGE_ID),
        )
        audit.assert_called_once()
        self.assertEqual(audit.call_args.args[0], archive)
        self.assertEqual(
            audit.call_args.kwargs["image_id"], pinned.REMOTE_CONFIG_IMAGE_ID
        )
        self.assertEqual(audit.call_args.kwargs["diff_ids"], pinned.DIFF_IDS)
        self.assertEqual(audit.call_args.kwargs["stream_size"], pinned.STREAM_SIZE)
        self.assertEqual(validation_output.getvalue(), "")

    def test_archive_preparation_refuses_identity_or_archive_mismatch_before_listener(self):
        mismatch_runner = mock.Mock(return_value=completed(b"wrong\n"))
        output = io.StringIO()
        self.assertIsNone(serve.prepare_archive(mismatch_runner, output=output))
        self.assertEqual(output.getvalue(), "LOCAL_IMAGE_IDENTITY_MISMATCH\n")
        mismatch_runner.assert_called_once()

        exact_inspect = completed((pinned._EXPECTED_INSPECT + "\n").encode("ascii"))
        bad_archive_runner = mock.Mock(side_effect=(exact_inspect, completed(b"bad")))
        output = io.StringIO()
        with mock.patch.object(
            serve.archive_audit,
            "inspect_archive",
            side_effect=lambda _archive, **kwargs: kwargs["output"].write("ARCHIVE_INVALID\n") or 14,
        ):
            self.assertIsNone(serve.prepare_archive(bad_archive_runner, output=output))
        self.assertEqual(output.getvalue(), "LOCAL_ARCHIVE_INVALID\n")
        self.assertEqual(bad_archive_runner.call_count, 2)

    def test_remote_command_is_exactly_pinned_and_does_not_use_ssh_or_credentials(self):
        archive_digest = "a" * 64
        command = serve.remote_import_command("192.168.88.24", 49237, archive_digest)
        self.assertIn("http://192.168.88.24:49237" + serve.REQUEST_PATH, command)
        self.assertIn(pinned.REMOTE_CONFIG_IMAGE_ID, command)
        self.assertIn(pinned._REMOTE_INSPECT_FORMAT, command)
        self.assertIn(serve._REMOTE_EXPECTED_TUPLE, command)
        self.assertIn(f"sha256sum", command)
        self.assertIn(archive_digest, command)
        self.assertIn("docker image load --input", command)
        self.assertIn(f"--max-time {serve.TRANSFER_TIMEOUT_SECONDS}", command)
        self.assertLess(command.index("ARCHIVE_DIGEST_MISMATCH"), command.index("docker image load"))
        self.assertIn("trap 'rm -f", command)
        self.assertNotIn("ssh ", command)
        self.assertNotIn("password", command.lower())
        self.assertIn("IMAGE_IMPORT_CONFIRMED", command)
        self.assertIn("IMAGE_IDENTITY_MISMATCH", command)
        with self.assertRaises(ValueError):
            serve.remote_import_command("192.168.88.24", 49237, "not-a-digest")

    def test_generated_remote_command_checks_digest_before_one_import_and_cleans_temp(self):
        archive = b"verified-public-image-archive"
        digest = hashlib.sha256(archive).hexdigest()
        result, docker_called, docker_input = self._run_remote_command_stubbed(
            archive=archive,
            expected_digest=digest,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "IMAGE_IMPORT_CONFIRMED\n")
        self.assertTrue(docker_called)
        self.assertTrue(docker_input.startswith("/tmp/agent00x-exp1654."))

    def test_generated_remote_command_blocks_bad_digest_before_docker_load(self):
        archive = b"tampered-or-wrong-archive"
        wrong_digest = "0" * 64
        result, docker_called, docker_input = self._run_remote_command_stubbed(
            archive=archive,
            expected_digest=wrong_digest,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "ARCHIVE_DIGEST_MISMATCH\n")
        self.assertFalse(docker_called)
        self.assertIsNone(docker_input)

    def test_generated_remote_command_cleans_temp_after_import_failure(self):
        archive = b"verified-public-image-archive"
        digest = hashlib.sha256(archive).hexdigest()
        result, docker_called, docker_input = self._run_remote_command_stubbed(
            archive=archive,
            expected_digest=digest,
            load_returncode=9,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "IMAGE_IMPORT_FAILED\n")
        self.assertTrue(docker_called)
        self.assertTrue(docker_input.startswith("/tmp/agent00x-exp1654."))

    def test_generated_remote_command_rejects_wrong_post_import_image_tuple(self):
        archive = b"verified-public-image-archive"
        digest = hashlib.sha256(archive).hexdigest()
        result, docker_called, docker_input = self._run_remote_command_stubbed(
            archive=archive,
            expected_digest=digest,
            inspect_tuple="wrong|linux|amd64|[]|[]",
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "IMAGE_IDENTITY_MISMATCH\n")
        self.assertTrue(docker_called)
        self.assertTrue(docker_input.startswith("/tmp/agent00x-exp1654."))

    def test_serve_once_prints_only_ephemeral_endpoint_and_user_command(self):
        output = io.StringIO()
        instances = []

        def factory(address, archive):
            instance = _FakeServer(address, archive)
            instances.append(instance)
            return instance

        archive = b"public-pinned-archive"
        with mock.patch.object(pinned, "STREAM_SIZE", len(archive)):
            result = serve.serve_once(
                archive,
                bind_address="192.168.88.24",
                port=0,
                output=output,
                server_factory=factory,
            )
        self.assertEqual(result, 0)
        self.assertEqual(len(instances), 1)
        self.assertTrue(instances[0].entered)
        self.assertTrue(instances[0].exited)
        self.assertIn("IMAGE_READY|url=http://192.168.88.24:49237", output.getvalue())
        expected_archive_digest = hashlib.sha256(archive).hexdigest()
        self.assertIn(f"archive_sha256={expected_archive_digest}", output.getvalue())
        self.assertIn("On the testdev console run exactly this one-shot command:", output.getvalue())
        self.assertIn("IMAGE_IMPORT_CONFIRMED", output.getvalue())
        self.assertIn(expected_archive_digest, output.getvalue())
        self.assertTrue(output.getvalue().endswith("ARCHIVE_SERVED\n"))

    def test_timeout_is_bounded_and_reports_no_import_claim(self):
        output = io.StringIO()

        class TimeoutServer(_FakeServer):
            def handle_request(self):
                return

        with mock.patch.object(pinned, "STREAM_SIZE", len(b"archive")):
            result = serve.serve_once(
                b"archive",
                bind_address="192.168.88.24",
                port=49237,
                output=output,
                server_factory=TimeoutServer,
            )
        self.assertEqual(result, serve._MARKER_CODES["TRANSFER_TIMEOUT"])
        self.assertTrue(output.getvalue().endswith("TRANSFER_TIMEOUT\n"))
        self.assertNotIn("IMAGE_IMPORT_CONFIRMED\n", output.getvalue())

    def test_http_handler_serves_one_exact_body_only_to_allowlisted_peer(self):
        archive = b"loopback-test-public-image"
        with (
            mock.patch.object(serve, "TARGET_ADDRESS", "127.0.0.1"),
            mock.patch.object(pinned, "STREAM_SIZE", len(archive)),
        ):
            server = serve._OneShotServer(("127.0.0.1", 0), archive)
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            try:
                with urlopen(
                    f"http://127.0.0.1:{server.server_address[1]}{serve.REQUEST_PATH}",
                    timeout=2,
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(response.read(), archive)
            finally:
                thread.join(timeout=2)
                server.server_close()
            self.assertFalse(thread.is_alive())
            self.assertTrue(server.request_consumed)
            self.assertTrue(server.archive_served)

    def test_http_handler_refuses_non_allowlisted_peer_without_sending_archive(self):
        archive = b"do-not-serve-to-this-peer"
        with (
            mock.patch.object(serve, "TARGET_ADDRESS", "192.168.88.101"),
            mock.patch.object(pinned, "STREAM_SIZE", len(archive)),
        ):
            server = serve._OneShotServer(("127.0.0.1", 0), archive)
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            try:
                with self.assertRaises(HTTPError) as raised:
                    urlopen(
                        f"http://127.0.0.1:{server.server_address[1]}{serve.REQUEST_PATH}",
                        timeout=2,
                    )
                self.assertEqual(raised.exception.code, 403)
            finally:
                thread.join(timeout=2)
                server.server_close()
            self.assertFalse(thread.is_alive())
            self.assertTrue(server.request_consumed)
            self.assertFalse(server.archive_served)

    def test_tty_gate_and_exact_phrase_precede_docker_and_listener(self):
        runner = mock.Mock(side_effect=AssertionError("must not run"))
        factory = mock.Mock(side_effect=AssertionError("must not listen"))
        output = io.StringIO()
        self.assertEqual(
            serve.run_once(
                bind_address="192.168.88.24",
                port=49237,
                stdin=io.StringIO("RUN EXP-1653 ONCE\n"),
                stdout=output,
                stderr=io.StringIO(),
                runner=runner,
                server_factory=factory,
            ),
            serve._MARKER_CODES["RUN_NOT_CONFIRMED"],
        )
        self.assertEqual(output.getvalue(), "RUN_NOT_CONFIRMED\n")

        output = io.StringIO()
        self.assertEqual(
            serve.run_once(
                bind_address="192.168.88.24",
                port=49237,
                stdin=_TTYInput("RUN EXP-1653 ONCE\n"),
                stdout=output,
                stderr=io.StringIO(),
                runner=runner,
                server_factory=factory,
            ),
            serve._MARKER_CODES["RUN_NOT_CONFIRMED"],
        )
        runner.assert_not_called()
        factory.assert_not_called()

    def test_expired_one_shot_gate_refuses_before_docker_or_listener(self):
        runner = mock.Mock(side_effect=AssertionError("must not run"))
        factory = mock.Mock(side_effect=AssertionError("must not listen"))
        output = io.StringIO()
        self.assertEqual(
            serve.run_once(
                bind_address="192.168.88.24",
                port=49237,
                stdin=_TTYInput("RUN EXP-1654 ONCE\n"),
                stdout=output,
                stderr=io.StringIO(),
                runner=runner,
                server_factory=factory,
                now=serve.AUTHORIZATION_EXPIRES_AT,
            ),
            serve._MARKER_CODES["AUTHORIZATION_EXPIRED"],
        )
        self.assertEqual(output.getvalue(), "AUTHORIZATION_EXPIRED\n")
        runner.assert_not_called()
        factory.assert_not_called()

    def test_successful_gate_creates_listener_only_after_archive_validation(self):
        archive = b"synthetic-image-archive"
        runner = mock.Mock(
            side_effect=(
                completed((pinned._EXPECTED_INSPECT + "\n").encode("ascii")),
                completed(archive),
            )
        )
        factory = mock.Mock(side_effect=lambda address, body: _FakeServer(address, body))
        output = io.StringIO()
        with (
            mock.patch.object(pinned, "STREAM_SIZE", len(archive)),
            mock.patch.object(
                serve.archive_audit,
                "inspect_archive",
                side_effect=self._valid_archive_audit,
            ),
        ):
            result = serve.run_once(
                bind_address="192.168.88.24",
                port=49237,
                stdin=_TTYInput("RUN EXP-1654 ONCE\n"),
                stdout=output,
                stderr=io.StringIO(),
                runner=runner,
                server_factory=factory,
                now=datetime(2026, 10, 20, 15, tzinfo=timezone.utc),
            )
        self.assertEqual(result, 0)
        self.assertEqual(runner.call_count, 2)
        factory.assert_called_once_with(("192.168.88.24", 49237), archive)
        self.assertTrue(output.getvalue().endswith("ARCHIVE_SERVED\n"))


if __name__ == "__main__":
    unittest.main()
