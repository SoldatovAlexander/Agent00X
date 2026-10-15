from __future__ import annotations

import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TEST_RUNTIME_IMAGE_ID = "sha256:" + "a" * 64
TEST_VERIFIER_CODE_DIGEST = "sha256:" + "b" * 64
# Fixed-shape fixture only; real invocation nonces are random per container run.
TEST_NONCE = "c" * 64
STALE_NONCE = "e" * 64
NONCE_ARGUMENT = "--invocation-nonce="
_SAFE_STARTUP_STDERR_MARKERS = (
    (b"Cannot connect to the Docker daemon", "daemon-connect"),
    (b"error during connect", "daemon-connect"),
    (b"Error response from daemon:", "daemon-rejected"),
    (b"OCI runtime create failed", "oci-runtime"),
    (b"failed to create shim task", "oci-runtime"),
    (b"No such image:", "image-unavailable"),
    (b"pull access denied for", "image-unavailable"),
    (b"ModuleNotFoundError:", "python-import"),
    (b"ImportError:", "python-import"),
    (b"Traceback (most recent call last):", "python-traceback"),
)


def safe_startup_stderr_category(stderr: bytes) -> str:
    if type(stderr) is not bytes:
        return "unclassified"
    for marker, category in _SAFE_STARTUP_STDERR_MARKERS:
        if marker in stderr:
            return category
    return "unclassified"


def nonce_arguments(argv: list[str]) -> list[str]:
    return [argument for argument in argv if argument.startswith(NONCE_ARGUMENT)]

from app_contracts.executor import (
    VerifierInput,
    VerifierVerdict,
    verifier_snapshot_tree_digest,
)
from app_contracts.verifier_container import (
    DEFAULT_CONTAINER_TIMEOUT_SECONDS,
    MAX_CONTAINER_TIMEOUT_SECONDS,
    MAX_CONTAINER_OUTPUT_BYTES,
    VERIFIER_BASE_IMAGE,
    DockerContainerVerifier,
    VerifierContainerConfig,
)
from app_contracts.verifier_container_entrypoint import main, run_verifier_request
from app_contracts.digests import sha256_digest
from app_contracts.verifier_process import (
    _collect_bounded_output,
    VerifierProcessError,
    VerifierProcessRequest,
    parse_verifier_response,
    serialize_verifier_request,
)


def valid_input(**overrides) -> VerifierInput:
    snapshot_files = (("calculator.py", "100644", b"def add(a, b): return 0\n"),)
    fields = {
        "process_id": "container-test-001",
        "repository_id": "fixture-repository",
        "base_commit": "a" * 40,
        "snapshot_tree_digest": verifier_snapshot_tree_digest(snapshot_files),
        "declared_change_paths": ("calculator.py",),
        "verified_contents": (("calculator.py", "def add(a, b): return a + b\n"),),
        "test_command": (
            sys.executable,
            "-c",
            "import calculator; print('OUTPUT-CANARY'); assert calculator.add(2, 3) == 5",
        ),
        "test_timeout_seconds": 10,
        "patch_digest": "sha256:" + "1" * 64,
        "evidence_digest": "sha256:" + "2" * 64,
        "verification_digest": "sha256:" + "3" * 64,
        "verified_contents_digest": sha256_digest(
            (("calculator.py", "def add(a, b): return a + b\n"),)
        ),
        "replay_result_digest": "sha256:" + "5" * 64,
        "snapshot_files": snapshot_files,
    }
    fields.update(overrides)
    if "verified_contents" in overrides and "verified_contents_digest" not in overrides:
        fields["verified_contents_digest"] = sha256_digest(fields["verified_contents"])
    return VerifierInput(**fields)


class VerifierContainerConfigTests(unittest.TestCase):
    def test_startup_stderr_classifier_emits_only_fixed_categories(self):
        for sample, expected in (
            (b"Cannot connect to the Docker daemon at private-path", "daemon-connect"),
            (b"Error response from daemon: opaque detail", "daemon-rejected"),
            (b"OCI runtime create failed: opaque detail", "oci-runtime"),
            (b"No such image: opaque-reference", "image-unavailable"),
            (b"ModuleNotFoundError: private module name", "python-import"),
            (b"Traceback (most recent call last): private path", "python-traceback"),
            (b"opaque canary private-path", "unclassified"),
            ("not-bytes", "unclassified"),
        ):
            with self.subTest(expected=expected):
                self.assertEqual(safe_startup_stderr_category(sample), expected)

    def test_command_is_a_fixed_no_shell_docker_profile(self):
        config = VerifierContainerConfig(
            "/usr/local/bin/docker", TEST_RUNTIME_IMAGE_ID, TEST_VERIFIER_CODE_DIGEST
        )
        self.assertEqual(config.timeout_seconds, DEFAULT_CONTAINER_TIMEOUT_SECONDS)
        command = config.command_config("agent00x-verifier-test", TEST_NONCE)
        self.assertEqual(command.executable, "/usr/local/bin/docker")
        self.assertEqual(
            command.argv[0:3],
            ("/usr/local/bin/docker", "--host=unix:///var/run/docker.sock", "run"),
        )
        self.assertIn("--pull=never", command.argv)
        self.assertIn("--network=none", command.argv)
        self.assertIn("--name=agent00x-verifier-test", command.argv)
        self.assertIn("--read-only", command.argv)
        self.assertIn("--user=65532:65532", command.argv)
        self.assertIn("--cap-drop=ALL", command.argv)
        self.assertIn("--security-opt=no-new-privileges:true", command.argv)
        self.assertIn("--pids-limit=64", command.argv)
        self.assertIn("--memory=256m", command.argv)
        self.assertIn("--cpus=1.0", command.argv)
        self.assertEqual(command.argv.count("--tmpfs"), 2)
        self.assertIn(TEST_RUNTIME_IMAGE_ID, command.argv)
        self.assertEqual(
            command.argv[-2:],
            (TEST_RUNTIME_IMAGE_ID, NONCE_ARGUMENT + TEST_NONCE),
        )
        self.assertEqual(len(nonce_arguments(list(command.argv))), 1)
        self.assertNotIn("app_contracts.verifier_container_entrypoint", command.argv)
        self.assertFalse(any(
            argument == "--mount" or argument == "--volume" or argument == "-v"
            or argument.startswith("--env") or argument == "--tty"
            for argument in command.argv
        ))

    def test_malformed_invocation_nonce_is_rejected_before_launch(self):
        config = VerifierContainerConfig(
            "/usr/bin/docker", TEST_RUNTIME_IMAGE_ID, TEST_VERIFIER_CODE_DIGEST
        )
        for nonce in (
            "",
            "xyz",
            "C" * 64,
            "c" * 63,
            "c" * 65,
            "c" * 63 + "!",
            True,
            None,
            b"c" * 64,
        ):
            with self.subTest(length=len(nonce) if hasattr(nonce, "__len__") else 0):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier container: invocation nonce is invalid$",
                ):
                    config.command_config("agent00x-verifier-test", nonce)

    def test_invalid_executable_limits_and_timeout_are_rejected(self):
        for executable in ("docker", " /usr/bin/docker", "/bad path/docker"):
            with self.subTest(executable=executable), self.assertRaises(VerifierProcessError):
                VerifierContainerConfig(
                    executable, TEST_RUNTIME_IMAGE_ID, TEST_VERIFIER_CODE_DIGEST
                )
        for timeout in (0, True, MAX_CONTAINER_TIMEOUT_SECONDS + 1):
            with self.subTest(timeout=timeout), self.assertRaises(VerifierProcessError):
                VerifierContainerConfig(
                    "/usr/bin/docker", TEST_RUNTIME_IMAGE_ID,
                    TEST_VERIFIER_CODE_DIGEST, timeout_seconds=timeout
                )
        for image_id in ("local-tag", "python:latest", "sha256:" + "A" * 64):
            with self.subTest(image_id=image_id), self.assertRaisesRegex(
                VerifierProcessError,
                "^verifier container: image identity is invalid$",
            ):
                VerifierContainerConfig(
                    "/usr/bin/docker", image_id, TEST_VERIFIER_CODE_DIGEST
                )
        for code_digest in ("local-tag", "sha256:" + "A" * 64):
            with self.subTest(code_digest=code_digest), self.assertRaisesRegex(
                VerifierProcessError,
                "^verifier container: code identity is invalid$",
            ):
                VerifierContainerConfig(
                    "/usr/bin/docker", TEST_RUNTIME_IMAGE_ID, code_digest
                )
        for field in ("max_stdout_bytes", "max_stderr_bytes"):
            with self.subTest(field=field), self.assertRaisesRegex(
                VerifierProcessError,
                "^verifier container: output limits are invalid$",
            ):
                VerifierContainerConfig(
                    "/usr/bin/docker",
                    TEST_RUNTIME_IMAGE_ID,
                    TEST_VERIFIER_CODE_DIGEST,
                    **{field: MAX_CONTAINER_OUTPUT_BYTES + 1},
                )

    def test_fake_docker_receives_exact_request_and_no_parent_environment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            capture_path = directory / "capture.json"
            docker_script = directory / "docker-fake"
            docker_script.write_text(
                "#!" + sys.executable + "\n"
                "import hashlib, json, os, sys\n"
                "from pathlib import Path\n"
                "raw = sys.stdin.buffer.read()\n"
                "config = Path(os.environ['DOCKER_CONFIG'])\n"
                "request = json.loads(raw)\n"
                "item = request['verifier_input']\n"
                "nonce = next(a.split('=', 1)[1] for a in sys.argv[1:] "
                "if a.startswith('--invocation-nonce='))\n"
                "result = {name: item[name] for name in ("
                "'process_id', 'base_commit', 'snapshot_tree_digest', "
                "'replay_result_digest', 'patch_digest', 'evidence_digest', "
                "'verification_digest', 'verified_contents_digest')}\n"
                "result.update(verifier_id=nonce, verdict='pass', "
                "blocker_codes=[], evidence_origin='local_test')\n"
                "Path(__file__).with_name('capture.json').write_text(json.dumps({"
                "'argv': sys.argv[1:], 'input_sha256': hashlib.sha256(raw).hexdigest(), "
                "'input_size': len(raw), 'canary_present': "
                "'CONTAINER_PARENT_CANARY' in os.environ, "
                "'env_keys': sorted(os.environ), 'docker_config_empty': "
                "not any(config.iterdir())}))\n"
                "sys.stdout.write(json.dumps({'schema_version': 2, "
                "'request_digest': 'sha256:' + hashlib.sha256(raw).hexdigest(), "
                "'verifier_result': result}, sort_keys=True, separators=(',', ':')))\n",
                encoding="utf-8",
            )
            docker_script.chmod(0o755)
            prepared = valid_input()
            request = VerifierProcessRequest.from_verifier_input(prepared)
            request_bytes = serialize_verifier_request(request)
            config = VerifierContainerConfig(
                str(docker_script), TEST_RUNTIME_IMAGE_ID, TEST_VERIFIER_CODE_DIGEST,
                timeout_seconds=60,
                max_stdout_bytes=20_000, max_stderr_bytes=20_000,
            )
            canary_name = "CONTAINER_PARENT_CANARY"
            os.environ[canary_name] = "do-not-inherit"
            try:
                result = DockerContainerVerifier(config).verify(prepared)
            finally:
                os.environ.pop(canary_name, None)

            capture = json.loads(capture_path.read_text(encoding="utf-8"))
            self.assertEqual(capture["input_sha256"], hashlib.sha256(request_bytes).hexdigest())
            self.assertEqual(capture["input_size"], len(request_bytes))
            self.assertFalse(capture["canary_present"])
            self.assertIn("DOCKER_CONFIG", capture["env_keys"])
            self.assertLessEqual(
                set(capture["env_keys"]),
                {"DOCKER_CONFIG", "LC_CTYPE", "__CF_USER_TEXT_ENCODING"},
            )
            self.assertTrue(capture["docker_config_empty"])
            argv = capture["argv"]
            self.assertEqual(argv[0], "--host=unix:///var/run/docker.sock")
            self.assertIn("--network=none", argv)
            self.assertIn("--read-only", argv)
            self.assertIn("--user=65532:65532", argv)
            echoed = nonce_arguments(argv)
            self.assertEqual(len(echoed), 1)
            self.assertTrue(
                re.fullmatch(r"--invocation-nonce=[0-9a-f]{64}", echoed[0]) is not None
            )
            self.assertNotIn(
                "app_contracts.verifier_container_entrypoint", argv
            )
            self.assertEqual(result.verdict, VerifierVerdict.PASS)
            self.assertEqual(
                result.verifier_id,
                f"docker-image:{TEST_RUNTIME_IMAGE_ID}"
                f"/code:{TEST_VERIFIER_CODE_DIGEST}",
            )

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1"
        and re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            os.environ.get("AGENT00X_VERIFIER_IMAGE_ID", ""),
        )
        and re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            os.environ.get("AGENT00X_VERIFIER_CODE_DIGEST", ""),
        )
        and os.path.isabs(os.environ.get("AGENT00X_DOCKER_EXECUTABLE", "")),
        "Docker verifier integration test is opt-in",
    )
    def test_opt_in_real_container_executes_synthetic_request_under_profile(self):
        image_id = os.environ["AGENT00X_VERIFIER_IMAGE_ID"]
        code_digest = os.environ["AGENT00X_VERIFIER_CODE_DIGEST"]
        docker_executable = os.environ["AGENT00X_DOCKER_EXECUTABLE"]
        isolation_probe = (
            "import os\n"
            "assert os.getuid() == 65532\n"
            "assert not os.access('/', os.W_OK)\n"
            "assert not os.path.exists('/var/run/docker.sock')\n"
            "assert set(os.environ) <= {'HOME', 'LANG', 'PATH', "
            "'PYTHONDONTWRITEBYTECODE', 'TMPDIR'}\n"
        )
        prepared = valid_input(
            test_command=("python3", "-c", isolation_probe),
            test_timeout_seconds=20,
        )
        config = VerifierContainerConfig(
            docker_executable,
            image_id,
            code_digest,
            timeout_seconds=60,
            max_stdout_bytes=20_000,
            max_stderr_bytes=20_000,
        )
        result = DockerContainerVerifier(config).verify(prepared)
        self.assertEqual(result.verdict, VerifierVerdict.PASS)
        self.assertEqual(
            result.verifier_id,
            f"docker-image:{image_id}/code:{code_digest}",
        )

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1"
        and re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            os.environ.get("AGENT00X_VERIFIER_IMAGE_ID", ""),
        )
        and re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            os.environ.get("AGENT00X_VERIFIER_CODE_DIGEST", ""),
        )
        and os.path.isabs(os.environ.get("AGENT00X_DOCKER_EXECUTABLE", "")),
        "Docker verifier integration test is opt-in",
    )
    def test_opt_in_real_container_accepts_bounded_large_snapshot(self):
        image_id = os.environ["AGENT00X_VERIFIER_IMAGE_ID"]
        code_digest = os.environ["AGENT00X_VERIFIER_CODE_DIGEST"]
        docker_executable = os.environ["AGENT00X_DOCKER_EXECUTABLE"]
        snapshot_files = (
            ("calculator.py", "100644", b"def add(a, b): return 0\n"),
            ("large.bin", "100644", b"x" * 220_064),
        )
        verified_contents = (("calculator.py", "def add(a, b): return a + b\n"),)
        prepared = valid_input(
            snapshot_files=snapshot_files,
            snapshot_tree_digest=verifier_snapshot_tree_digest(snapshot_files),
            verified_contents=verified_contents,
            test_command=(
                "python3",
                "-c",
                "import calculator; assert calculator.add(2, 3) == 5",
            ),
            test_timeout_seconds=20,
        )
        config = VerifierContainerConfig(
            docker_executable,
            image_id,
            code_digest,
            timeout_seconds=60,
            max_stdout_bytes=20_000,
            max_stderr_bytes=20_000,
        )

        result = DockerContainerVerifier(config).verify(prepared)

        self.assertEqual(result.verdict, VerifierVerdict.PASS)
        self.assertEqual(result.process_id, prepared.process_id)
        self.assertEqual(result.snapshot_tree_digest, prepared.snapshot_tree_digest)
        self.assertEqual(
            result.verifier_id,
            f"docker-image:{image_id}/code:{code_digest}",
        )

    @unittest.skipUnless(
        os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1"
        and re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            os.environ.get("AGENT00X_VERIFIER_IMAGE_ID", ""),
        )
        and re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            os.environ.get("AGENT00X_VERIFIER_CODE_DIGEST", ""),
        )
        and os.path.isabs(os.environ.get("AGENT00X_DOCKER_EXECUTABLE", "")),
        "Docker verifier integration test is opt-in",
    )
    def test_opt_in_real_container_starts_before_request_validation(self):
        config = VerifierContainerConfig(
            os.environ["AGENT00X_DOCKER_EXECUTABLE"],
            os.environ["AGENT00X_VERIFIER_IMAGE_ID"],
            os.environ["AGENT00X_VERIFIER_CODE_DIGEST"],
            timeout_seconds=60,
            max_stdout_bytes=4_096,
            max_stderr_bytes=4_096,
        )
        command = config.command_config(
            "agent00x-verifier-startup-probe", TEST_NONCE
        )
        expected_marker = b"verifier container: rejection:request-payload\n"
        with tempfile.TemporaryDirectory(prefix="agent00x-verifier-config-") as config_dir:
            process = subprocess.Popen(
                list(command.argv),
                executable=command.executable,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"DOCKER_CONFIG": config_dir},
                shell=False,
            )
            stdout, stderr, exit_code = _collect_bounded_output(
                process,
                b"not-json",
                stdout_cap=4_096,
                stderr_cap=4_096,
                timeout_seconds=60,
            )

        evidence = (
            f"status={exit_code}; stdout_bytes={len(stdout)}; "
            f"stderr_bytes={len(stderr)}; marker_match={stderr == expected_marker}; "
            f"stderr_category={safe_startup_stderr_category(stderr)}"
        )
        self.assertEqual(exit_code, 2, evidence)
        self.assertEqual(stdout, b"", evidence)
        self.assertEqual(stderr, expected_marker, evidence)

    def test_failed_docker_run_attempts_bounded_force_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            docker_script = directory / "docker-timeout-fake"
            run_capture = directory / "run-args.json"
            cleanup_capture = directory / "cleanup-args.json"
            docker_script.write_text(
                "#!" + sys.executable + "\n"
                "import json, sys, time\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "if 'run' in args:\n"
                f" Path({str(run_capture)!r}).write_text(json.dumps(args))\n"
                " time.sleep(30)\n"
                "else:\n"
                f" Path({str(cleanup_capture)!r}).write_text(json.dumps(args))\n",
                encoding="utf-8",
            )
            docker_script.chmod(0o755)
            config = VerifierContainerConfig(
                str(docker_script), TEST_RUNTIME_IMAGE_ID, TEST_VERIFIER_CODE_DIGEST,
                timeout_seconds=6,
                max_stdout_bytes=20_000, max_stderr_bytes=20_000,
            )
            with self.assertRaisesRegex(
                VerifierProcessError, "^verifier process: child timed out$"
            ):
                DockerContainerVerifier(config).verify(
                    valid_input(test_timeout_seconds=1)
                )

            run_args = json.loads(run_capture.read_text(encoding="utf-8"))
            cleanup_args = json.loads(cleanup_capture.read_text(encoding="utf-8"))
            name = next(argument.removeprefix("--name=") for argument in run_args
                        if argument.startswith("--name="))
            self.assertEqual(
                cleanup_args,
                ["--host=unix:///var/run/docker.sock", "rm", "--force", name],
            )
            self.assertTrue(name.startswith("agent00x-verifier-"))

    def test_docker_output_overflow_is_bounded_and_triggers_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            docker_script = directory / "docker-output-fake"
            cleanup_capture = directory / "cleanup-args.json"
            docker_script.write_text(
                "#!" + sys.executable + "\n"
                "import json, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "if 'run' in args:\n"
                " sys.stdout.write('OUTPUT-CANARY' * 1000)\n"
                "else:\n"
                f" Path({str(cleanup_capture)!r}).write_text(json.dumps(args))\n",
                encoding="utf-8",
            )
            docker_script.chmod(0o755)
            config = VerifierContainerConfig(
                str(docker_script), TEST_RUNTIME_IMAGE_ID, TEST_VERIFIER_CODE_DIGEST,
                timeout_seconds=60,
                max_stdout_bytes=128, max_stderr_bytes=128,
            )
            with self.assertRaisesRegex(
                VerifierProcessError,
                "^verifier process: child output exceeds limit$",
            ) as raised:
                DockerContainerVerifier(config).verify(valid_input())
            self.assertNotIn("OUTPUT-CANARY", str(raised.exception))
            cleanup_args = json.loads(cleanup_capture.read_text(encoding="utf-8"))
            self.assertEqual(cleanup_args[:3], [
                "--host=unix:///var/run/docker.sock", "rm", "--force"
            ])

    def test_stale_or_foreign_nonce_values_are_rejected_and_cleaned_up(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            canned_path = directory / "canned-id.txt"
            docker_script = directory / "docker-replay-fake"
            run_capture = directory / "run-args.json"
            cleanup_capture = directory / "cleanup-args.json"
            docker_script.write_text(
                "#!" + sys.executable + "\n"
                "import hashlib, json, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "if 'run' in args:\n"
                f" Path({str(run_capture)!r}).write_text(json.dumps(args))\n"
                " raw = sys.stdin.buffer.read()\n"
                " item = json.loads(raw)['verifier_input']\n"
                " result = {name: item[name] for name in ("
                "'process_id', 'base_commit', 'snapshot_tree_digest', "
                "'replay_result_digest', 'patch_digest', 'evidence_digest', "
                "'verification_digest', 'verified_contents_digest')}\n"
                f" canned = Path({str(canned_path)!r}).read_text(encoding='utf-8')\n"
                " result.update(verifier_id=canned, verdict='pass', "
                "blocker_codes=[], evidence_origin='local_test')\n"
                " sys.stdout.write(json.dumps({'schema_version': 2, "
                "'request_digest': 'sha256:' + hashlib.sha256(raw).hexdigest(), "
                "'verifier_result': result}, sort_keys=True, separators=(',', ':')))\n"
                "else:\n"
                f" Path({str(cleanup_capture)!r}).write_text(json.dumps(args))\n",
                encoding="utf-8",
            )
            docker_script.chmod(0o755)
            config = VerifierContainerConfig(
                str(docker_script), TEST_RUNTIME_IMAGE_ID, TEST_VERIFIER_CODE_DIGEST,
                timeout_seconds=60,
                max_stdout_bytes=20_000, max_stderr_bytes=20_000,
            )
            for index, canned in enumerate(
                (STALE_NONCE, "container-fake-v1", "not a nonce!!")
            ):
                with self.subTest(index=index):
                    canned_path.write_text(canned, encoding="utf-8")
                    with self.assertRaisesRegex(
                        VerifierProcessError,
                        "^verifier container: invocation nonce mismatch$",
                    ):
                        DockerContainerVerifier(config).verify(valid_input())

            run_args = json.loads(run_capture.read_text(encoding="utf-8"))
            cleanup_args = json.loads(cleanup_capture.read_text(encoding="utf-8"))
            name = next(argument.removeprefix("--name=") for argument in run_args
                        if argument.startswith("--name="))
            self.assertEqual(
                cleanup_args,
                ["--host=unix:///var/run/docker.sock", "rm", "--force", name],
            )
            self.assertTrue(name.startswith("agent00x-verifier-"))

    def test_each_invocation_uses_a_distinct_nonce(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            nonce_log = directory / "nonces.txt"
            docker_script = directory / "docker-nonce-fake"
            docker_script.write_text(
                "#!" + sys.executable + "\n"
                "import hashlib, json, sys\n"
                "raw = sys.stdin.buffer.read()\n"
                "nonce = next(a.split('=', 1)[1] for a in sys.argv[1:] "
                "if a.startswith('--invocation-nonce='))\n"
                "item = json.loads(raw)['verifier_input']\n"
                "result = {name: item[name] for name in ("
                "'process_id', 'base_commit', 'snapshot_tree_digest', "
                "'replay_result_digest', 'patch_digest', 'evidence_digest', "
                "'verification_digest', 'verified_contents_digest')}\n"
                "result.update(verifier_id=nonce, verdict='pass', "
                "blocker_codes=[], evidence_origin='local_test')\n"
                f"handle = open({str(nonce_log)!r}, 'a', encoding='utf-8')\n"
                "handle.write(nonce + chr(10))\n"
                "handle.close()\n"
                "sys.stdout.write(json.dumps({'schema_version': 2, "
                "'request_digest': 'sha256:' + hashlib.sha256(raw).hexdigest(), "
                "'verifier_result': result}, sort_keys=True, separators=(',', ':')))\n",
                encoding="utf-8",
            )
            docker_script.chmod(0o755)
            config = VerifierContainerConfig(
                str(docker_script), TEST_RUNTIME_IMAGE_ID, TEST_VERIFIER_CODE_DIGEST,
                timeout_seconds=60,
                max_stdout_bytes=20_000, max_stderr_bytes=20_000,
            )
            verifier = DockerContainerVerifier(config)
            first = verifier.verify(valid_input())
            second = verifier.verify(valid_input())
            self.assertEqual(first.verdict, VerifierVerdict.PASS)
            self.assertEqual(second.verdict, VerifierVerdict.PASS)
            logged = nonce_log.read_text(encoding="utf-8").split()
            self.assertEqual(len(logged), 2)
            self.assertTrue(
                re.fullmatch(r"[0-9a-f]{64}", logged[0]) is not None
            )
            self.assertTrue(
                re.fullmatch(r"[0-9a-f]{64}", logged[1]) is not None
            )
            self.assertTrue(logged[0] != logged[1])


class VerifierContainerEntrypointTests(unittest.TestCase):
    def test_main_emits_only_allowlisted_rejection_code(self):
        stdin = SimpleNamespace(buffer=BytesIO(b"not-json"))
        stdout_buffer = BytesIO()
        stdout = SimpleNamespace(buffer=stdout_buffer)
        stderr = StringIO()
        with (
            patch.object(sys, "stdin", stdin),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
            patch.object(sys, "argv", ["verifier", NONCE_ARGUMENT + TEST_NONCE]),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout_buffer.getvalue(), b"")
        self.assertEqual(
            stderr.getvalue(), "verifier container: rejection:request-payload\n"
        )

    def test_entrypoint_materializes_base_overlays_candidate_and_hides_test_output(self):
        response_bytes = run_verifier_request(
            serialize_verifier_request(
                VerifierProcessRequest.from_verifier_input(valid_input())
            ),
            invocation_nonce=TEST_NONCE,
        )
        response = parse_verifier_response(response_bytes)
        self.assertEqual(response.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertNotIn(b"OUTPUT-CANARY", response_bytes)

    def test_malformed_and_noncanonical_requests_fail_without_echo(self):
        for raw in (
            b"not-json-secret-canary",
            serialize_verifier_request(
                VerifierProcessRequest.from_verifier_input(valid_input())
            ) + b" ",
        ):
            with self.subTest(length=len(raw)), self.assertRaises(VerifierProcessError) as raised:
                run_verifier_request(raw, invocation_nonce=TEST_NONCE)
            self.assertNotIn("secret-canary", str(raised.exception))

    def test_entrypoint_echoes_invocation_nonce_in_bounded_result(self):
        response = parse_verifier_response(
            run_verifier_request(
                serialize_verifier_request(
                    VerifierProcessRequest.from_verifier_input(valid_input())
                ),
                invocation_nonce=TEST_NONCE,
            )
        )
        self.assertEqual(response.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertEqual(response.verifier_result.verifier_id, TEST_NONCE)

    def test_malformed_invocation_nonce_is_rejected_without_echo(self):
        request_bytes = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(valid_input())
        )
        for index, nonce in enumerate(
            ("", "xyz", "C" * 64, "c" * 63, "c" * 65, True, None)
        ):
            with self.subTest(index=index):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier container: invocation nonce is invalid$",
                ):
                    run_verifier_request(request_bytes, invocation_nonce=nonce)

    def test_failed_test_is_a_bounded_typed_fail_result(self):
        prepared = valid_input(
            test_command=(sys.executable, "-c", "print('FAIL-CANARY'); raise SystemExit(7)")
        )
        result = parse_verifier_response(
            run_verifier_request(
                serialize_verifier_request(VerifierProcessRequest.from_verifier_input(prepared)),
                invocation_nonce=TEST_NONCE,
            )
        ).verifier_result
        self.assertEqual(result.verdict, VerifierVerdict.FAIL)
        self.assertEqual(result.blocker_codes, ("test-command-failed",))
        self.assertNotIn("FAIL-CANARY", repr(result))

    def test_candidate_paths_must_exactly_match_declared_safe_scope(self):
        unsafe = valid_input(
            declared_change_paths=("../outside.py",),
            verified_contents=(("../outside.py", "x"),),
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier container: candidate scope is invalid$"
        ):
            run_verifier_request(
                serialize_verifier_request(VerifierProcessRequest.from_verifier_input(unsafe)),
                invocation_nonce=TEST_NONCE,
            )

        mismatch = valid_input(declared_change_paths=("other.py",))
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier container: candidate scope is invalid$"
        ):
            run_verifier_request(
                serialize_verifier_request(VerifierProcessRequest.from_verifier_input(mismatch)),
                invocation_nonce=TEST_NONCE,
            )

    def test_candidate_digest_is_recomputed_before_test_execution(self):
        malformed = valid_input(
            verified_contents=(("calculator.py", "def add(a, b): return 99\n"),),
            verified_contents_digest="sha256:" + "4" * 64,
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier container: input binding is invalid$"
        ):
            run_verifier_request(
                serialize_verifier_request(
                    VerifierProcessRequest.from_verifier_input(malformed)
                ),
                invocation_nonce=TEST_NONCE,
            )

    def test_main_returns_only_a_stable_error_for_malformed_stdin(self):
        from io import BytesIO, StringIO
        from types import SimpleNamespace
        from unittest.mock import patch

        stdout_buffer = BytesIO()
        stderr_buffer = StringIO()
        stdin = SimpleNamespace(buffer=BytesIO(b"MALFORMED-PRIVATE-CANARY"))
        stdout = SimpleNamespace(buffer=stdout_buffer)
        argv = ["verifier_container_entrypoint", NONCE_ARGUMENT + TEST_NONCE]
        with patch("sys.stdin", stdin), patch("sys.stdout", stdout), patch(
            "sys.stderr", stderr_buffer
        ), patch("sys.argv", argv):
            exit_code = main()
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout_buffer.getvalue(), b"")
        self.assertNotIn("MALFORMED-PRIVATE-CANARY", stderr_buffer.getvalue())
        self.assertEqual(
            stderr_buffer.getvalue(),
            "verifier container: rejection:request-payload\n",
        )

    def test_main_rejects_nonce_argv_without_echo(self):
        from io import BytesIO, StringIO
        from types import SimpleNamespace
        from unittest.mock import patch

        request_bytes = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(valid_input())
        )
        bad_argvs = (
            ["verifier_container_entrypoint"],
            ["verifier_container_entrypoint", NONCE_ARGUMENT + "xyz"],
            ["verifier_container_entrypoint", NONCE_ARGUMENT + TEST_NONCE, "extra"],
            ["verifier_container_entrypoint", "python3"],
        )
        for index, argv in enumerate(bad_argvs):
            with self.subTest(index=index):
                stdout_buffer = BytesIO()
                stderr_buffer = StringIO()
                stdin = SimpleNamespace(buffer=BytesIO(request_bytes))
                stdout = SimpleNamespace(buffer=stdout_buffer)
                with patch("sys.stdin", stdin), patch("sys.stdout", stdout), patch(
                    "sys.stderr", stderr_buffer
                ), patch("sys.argv", argv):
                    exit_code = main()
                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout_buffer.getvalue(), b"")
                self.assertEqual(
                    stderr_buffer.getvalue(),
                    "verifier container: request or execution rejected\n",
                )

    def test_main_emits_nonce_bound_response_for_valid_argv(self):
        from io import BytesIO, StringIO
        from types import SimpleNamespace
        from unittest.mock import patch

        request_bytes = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(valid_input())
        )
        stdout_buffer = BytesIO()
        stderr_buffer = StringIO()
        stdin = SimpleNamespace(buffer=BytesIO(request_bytes))
        stdout = SimpleNamespace(buffer=stdout_buffer)
        argv = ["verifier_container_entrypoint", NONCE_ARGUMENT + TEST_NONCE]
        with patch("sys.stdin", stdin), patch("sys.stdout", stdout), patch(
            "sys.stderr", stderr_buffer
        ), patch("sys.argv", argv):
            exit_code = main()
        self.assertEqual(exit_code, 0)
        response = parse_verifier_response(stdout_buffer.getvalue())
        self.assertEqual(response.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertEqual(response.verifier_result.verifier_id, TEST_NONCE)
        self.assertNotIn(b"OUTPUT-CANARY", stdout_buffer.getvalue())

    def test_timeout_and_output_overflow_fail_closed_without_echo(self):
        timeout_input = valid_input(
            test_timeout_seconds=1,
            test_command=(sys.executable, "-c", "import time; time.sleep(5)"),
        )
        timeout_result = parse_verifier_response(
            run_verifier_request(
                serialize_verifier_request(
                    VerifierProcessRequest.from_verifier_input(timeout_input)
                ),
                invocation_nonce=TEST_NONCE,
            )
        ).verifier_result
        self.assertEqual(timeout_result.verdict, VerifierVerdict.BLOCKED)
        self.assertEqual(timeout_result.blocker_codes, ("test-command-timeout",))

        overflow_input = valid_input(
            test_command=(sys.executable, "-c", "print('X' * 70000)"),
        )
        overflow_result = parse_verifier_response(
            run_verifier_request(
                serialize_verifier_request(
                    VerifierProcessRequest.from_verifier_input(overflow_input)
                ),
                invocation_nonce=TEST_NONCE,
            )
        ).verifier_result
        self.assertEqual(overflow_result.verdict, VerifierVerdict.BLOCKED)
        self.assertEqual(overflow_result.blocker_codes, ("test-command-output-limit",))


class VerifierContainerImageTests(unittest.TestCase):
    def test_dockerfile_uses_only_pinned_base_and_non_root_numeric_user(self):
        dockerfile = ROOT / "containers/verifier/Dockerfile"
        source = dockerfile.read_text(encoding="utf-8")
        self.assertIn("FROM " + VERIFIER_BASE_IMAGE, source)
        self.assertIn("USER 65532:65532", source)
        self.assertIn("TMPDIR=/work", source)
        self.assertNotIn("ARG ", source)
        self.assertNotIn("ENV TOKEN", source)
        self.assertNotIn("openai_worker.py", source)
        self.assertIn("schemas/checkpoint.schema.json", source)
        self.assertIn("schemas/observation-event.schema.json", source)
        self.assertFalse(Path(str(dockerfile) + ".json").exists())

    def test_verifier_image_includes_target_dependency_payload_without_target_code(self):
        dockerfile = ROOT / "containers/verifier/Dockerfile"
        source = dockerfile.read_text(encoding="utf-8")
        self.assertIn("COPY requirements.lock /opt/agent00x/target-runtime-requirements.lock", source)
        self.assertIn("COPY target-python/ /usr/local/lib/python3.11/site-packages/", source)
        self.assertNotIn("COPY backend/", source)


if __name__ == "__main__":
    unittest.main()
