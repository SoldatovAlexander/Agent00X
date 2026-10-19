from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import verifier_snapshot_tree_digest
from app_contracts.brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID
from app_contracts.sandbox import (
    DockerSandbox,
    DockerSandboxBackend,
    LocalProcessSandboxBackend,
    SandboxError,
)
from app_contracts.docker_endpoint import LOCAL_DOCKER_HOST_ARGUMENT


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.backend = LocalProcessSandboxBackend()
        self.fixture = ROOT / "fixtures" / "repository" / "project"

    def test_fixture_tests_run_in_ephemeral_workspace(self):
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            result = sandbox.run(["python3", "-m", "unittest", "-v"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("test_add", result.stderr)
            self.assertNotEqual(sandbox.workspace.resolve(), self.fixture.resolve())

    def test_empty_snapshot_path_denied_without_workspace(self):
        backend = LocalProcessSandboxBackend()
        with self.assertRaisesRegex(SandboxError, "^snapshot must be a directory$"):
            backend.create(Path(""), {"python3"})
        with backend.create(self.fixture, {"python3"}) as sandbox:
            self.assertTrue((sandbox.workspace / "calculator.py").exists())

    def test_malformed_snapshot_root_denied_without_sandbox(self):
        import tempfile
        backend = LocalProcessSandboxBackend()
        with tempfile.TemporaryDirectory(prefix="app-sandbox-file-") as directory:
            regular_file = Path(directory) / "file.txt"
            regular_file.write_text("data", encoding="utf-8")
            for bad in (None, 123, str(self.fixture), regular_file):
                with self.subTest(root=type(bad).__name__):
                    with self.assertRaisesRegex(SandboxError, "snapshot must be a directory"):
                        backend.create(bad, {"python3"})

    def test_snapshot_symlink_escape_is_denied_before_copy(self):
        import tempfile
        backend = LocalProcessSandboxBackend()
        with tempfile.TemporaryDirectory(prefix="app-sandbox-fixture-") as fixture_dir, \
                tempfile.TemporaryDirectory(prefix="app-sandbox-outside-") as outside_dir:
            fixture = Path(fixture_dir)
            (fixture / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            secret = Path(outside_dir) / "secret.txt"
            secret.write_text("outside-canary-value", encoding="utf-8")
            (fixture / "linked.py").symlink_to(secret)
            with self.assertRaisesRegex(SandboxError, "must not contain symlinks"):
                backend.create(fixture, {"python3"})
            self.assertEqual(secret.read_text(encoding="utf-8"), "outside-canary-value")

    def test_malformed_allowlist_denied_before_copy_or_execution(self):
        backend = LocalProcessSandboxBackend()
        for bad in (None, 123, "python3", ["python3"], {"python3", ""}, {123}, {None}):
            with self.subTest(allowlist=bad):
                with self.assertRaisesRegex(
                    SandboxError, "allowed commands must be a set of non-empty names"
                ):
                    backend.create(self.fixture, bad)
        with backend.create(self.fixture, {"python3"}) as sandbox:
            result = sandbox.run(["python3", "-m", "unittest", "-q"])
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_invocation_denied_without_execution(self):
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            for bad_argv in (None, 123, "python3 -m unittest", b"python3", [], [None], ["python3", 42], [""]):
                with self.subTest(argv=type(bad_argv).__name__):
                    with self.assertRaisesRegex(SandboxError, "command invocation is malformed"):
                        sandbox.run(bad_argv)
            for bad_timeout in (True, "30", -1, 0, None):
                with self.subTest(timeout=bad_timeout):
                    with self.assertRaisesRegex(SandboxError, "command timeout is invalid"):
                        sandbox.run(["python3", "--version"], timeout_seconds=bad_timeout)
            result = sandbox.run(["python3", "--version"])
            self.assertEqual(result.returncode, 0)

    def test_close_is_idempotent_without_raw_errors(self):
        import shutil
        from app_contracts.sandbox import _make_tree_owner_writable
        sandbox = self.backend.create(self.fixture, {"python3"})
        root = sandbox._root
        sandbox.close()
        self.assertTrue(sandbox._closed)
        sandbox.close()
        sandbox.close()
        self.assertFalse(root.exists())
        sandbox = self.backend.create(self.fixture, {"python3"})
        root = sandbox._root
        _make_tree_owner_writable(root)
        shutil.rmtree(root)
        sandbox.close()
        self.assertTrue(sandbox._closed)

    def test_non_allowlisted_command_is_rejected(self):
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            with self.assertRaisesRegex(SandboxError, "not allowlisted"):
                sandbox.run(["curl", "https://example.com"])

    def test_host_environment_is_not_inherited(self):
        with self.backend.create(self.fixture, {"env"}) as sandbox:
            result = sandbox.run(["env"])
            self.assertEqual(result.returncode, 0)
            self.assertNotIn("HOME=", result.stdout)
            self.assertNotIn("TOKEN=", result.stdout.upper())

    def test_named_api_credential_is_not_inherited_by_sandbox_child(self):
        synthetic_canary = "SYNTHETIC-API-CREDENTIAL-CANARY-SANDBOX"
        script = (
            "from pathlib import Path; import sys; "
            "from app_contracts.sandbox import LocalProcessSandboxBackend; "
            "backend = LocalProcessSandboxBackend(); "
            "sandbox = backend.create(Path(sys.argv[1]), {Path(sys.executable).name}); "
            "result = sandbox.run((sys.executable, '-c', "
            "'import os; print(\"AI_PROCESS_API\" in os.environ)')); "
            "print(result.stdout, end=''); sandbox.close()"
        )
        child_environment = {
            "PATH": os.defpath,
            "PYTHONPATH": str(ROOT / "src"),
            "AI_PROCESS_API": synthetic_canary,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.fixture)],
            env=child_environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "False")
        self.assertNotIn(synthetic_canary, completed.stdout + completed.stderr)

    def test_docker_exec_passes_only_fixed_container_environment(self):
        with tempfile.TemporaryDirectory(prefix="docker-sandbox-env-allowlist-") as temporary:
            root = Path(temporary)
            sandbox = DockerSandbox(root, root, root, "synthetic-container", {"python"})
            with patch(
                "app_contracts.sandbox.subprocess.run",
                return_value=subprocess.CompletedProcess(["docker"], 0, "ok\n", ""),
            ) as run:
                result = sandbox.run(("python", "-c", "pass"))
                self.assertEqual(result.returncode, 0)
                argv = run.call_args.args[0]
                self.assertEqual(argv[:3], ["docker", LOCAL_DOCKER_HOST_ARGUMENT, "exec"])
                env_values = [argv[index + 1] for index, part in enumerate(argv[:-1]) if part == "--env"]
                self.assertEqual(
                    env_values,
                    [
                        "PATH=/usr/local/bin:/usr/bin:/bin",
                        "PYTHONDONTWRITEBYTECODE=1",
                        "LANG=C.UTF-8",
                    ],
                )
                self.assertNotIn("AI_PROCESS_API", "\x00".join(argv))
                sandbox.close()
                self.assertEqual(
                    run.call_args_list[1].args[0][:4],
                    ["docker", LOCAL_DOCKER_HOST_ARGUMENT, "rm", "--force"],
                )

    def test_snapshot_and_workspace_are_separate(self):
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            workspace_file = sandbox.workspace / "generated.txt"
            workspace_file.write_text("artifact", encoding="utf-8")
            self.assertFalse((sandbox.snapshot / "generated.txt").exists())

    def test_read_only_input_snapshot_produces_read_only_baseline_and_writable_workspace(self):
        with tempfile.TemporaryDirectory(prefix="app-sandbox-readonly-input-") as temporary_directory:
            snapshot = Path(temporary_directory) / "snapshot"
            nested = snapshot / "nested"
            nested.mkdir(parents=True)
            source_file = nested / "source.txt"
            source_file.write_text("pinned input\n", encoding="utf-8")
            source_file.chmod(0o444)
            nested.chmod(0o555)
            snapshot.chmod(0o555)
            try:
                with self.backend.create(snapshot, {"python3"}) as sandbox:
                    readonly_copy = sandbox.snapshot / "nested" / "source.txt"
                    workspace_copy = sandbox.workspace / "nested" / "source.txt"
                    self.assertFalse(readonly_copy.stat().st_mode & 0o222)
                    self.assertTrue(workspace_copy.stat().st_mode & 0o200)
                    workspace_copy.write_text("workspace update\n", encoding="utf-8")
                    self.assertEqual(readonly_copy.read_text(encoding="utf-8"), "pinned input\n")
                    self.assertEqual(source_file.read_text(encoding="utf-8"), "pinned input\n")
            finally:
                source_file.chmod(0o600)
                nested.chmod(0o700)
                snapshot.chmod(0o700)

    def test_docker_copy_of_read_only_input_keeps_writable_workspace(self):
        with tempfile.TemporaryDirectory(prefix="app-docker-readonly-input-") as temporary_directory:
            snapshot = Path(temporary_directory) / "snapshot"
            snapshot.mkdir()
            source_file = snapshot / "source.txt"
            source_file.write_text("pinned input\n", encoding="utf-8")
            source_file.chmod(0o444)
            snapshot.chmod(0o555)
            backend = DockerSandboxBackend("local-test-image")
            backend._assert_image_available = lambda: None
            try:
                with patch(
                    "app_contracts.sandbox.subprocess.run",
                    return_value=subprocess.CompletedProcess(
                        ["docker"], 0, "container-id\n", ""
                    ),
                ):
                    sandbox = backend.create(snapshot, {"python3"})
                    workspace_copy = sandbox.workspace / "source.txt"
                    self.assertTrue(workspace_copy.stat().st_mode & 0o200)
                    self.assertFalse((sandbox.snapshot / "source.txt").stat().st_mode & 0o222)
                    sandbox.close()
            finally:
                source_file.chmod(0o600)
                snapshot.chmod(0o700)

    def test_docker_read_only_snapshot_copy_preserves_git_executable_mode_digest(self):
        with tempfile.TemporaryDirectory(prefix="app-docker-executable-mode-") as temporary_directory:
            snapshot = Path(temporary_directory) / "snapshot"
            snapshot.mkdir()
            executable = snapshot / "scripts" / "probe.sh"
            executable.parent.mkdir()
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            regular = snapshot / "data.txt"
            regular.write_bytes(b"pinned data\n")
            regular.chmod(0o644)
            expected_files = (
                ("data.txt", "100644", b"pinned data\n"),
                ("scripts/probe.sh", "100755", b"#!/bin/sh\nexit 0\n"),
            )
            expected_digest = verifier_snapshot_tree_digest(expected_files)

            backend = DockerSandboxBackend("local-test-image")
            backend._assert_image_available = lambda: None
            with patch(
                "app_contracts.sandbox.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    ["docker"], 0, "container-id\n", ""
                ),
            ):
                sandbox = backend.create(snapshot, {"python3"})
                try:
                    copied_files = []
                    for path in sandbox.snapshot.rglob("*"):
                        if not path.is_file():
                            continue
                        mode = "100755" if path.stat().st_mode & 0o111 else "100644"
                        copied_files.append(
                            (path.relative_to(sandbox.snapshot).as_posix(), mode, path.read_bytes())
                        )
                        self.assertFalse(path.stat().st_mode & 0o222)
                    copied_files.sort(key=lambda entry: entry[0])
                    self.assertEqual(tuple(copied_files), expected_files)
                    self.assertEqual(verifier_snapshot_tree_digest(tuple(copied_files)), expected_digest)
                    self.assertTrue(sandbox.workspace.joinpath("scripts", "probe.sh").stat().st_mode & 0o200)
                finally:
                    sandbox.close()

    def test_backend_does_not_claim_network_isolation(self):
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            self.assertFalse(sandbox.network_isolated)
            self.assertEqual(sandbox.security_profile, "development-process-only")

    def test_docker_profile_disables_network_and_limits_container(self):
        backend = DockerSandboxBackend("python:3.12-alpine")
        command = backend.build_run_command(Path("/tmp/snapshot"), Path("/tmp/workspace"))
        self.assertEqual(command[:3], ["docker", LOCAL_DOCKER_HOST_ARGUMENT, "run"])
        self.assertIn("--network", command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("ALL", command)
        self.assertIn("--user", command)
        self.assertEqual(command[command.index("--user") + 1], f"{os.getuid()}:{os.getgid()}")
        self.assertIn("--pids-limit", command)
        self.assertIn("--memory", command)
        self.assertIn("--cpus", command)

    def test_docker_backend_refuses_unavailable_daemon_or_image(self):
        backend = DockerSandboxBackend("agent-process-image-that-is-not-present")
        with patch(
            "app_contracts.sandbox.subprocess.run",
            return_value=subprocess.CompletedProcess(["docker"], 1, "", "hidden"),
        ) as run, self.assertRaisesRegex(SandboxError, "not automatic"):
            backend._assert_image_available()
        self.assertEqual(
            run.call_args.args[0][:4],
            ["docker", LOCAL_DOCKER_HOST_ARGUMENT, "image", "inspect"],
        )

    @unittest.skipUnless(os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1", "Docker integration test is opt-in")
    def test_docker_backend_enforces_network_mount_and_workspace_profile(self):
        backend = DockerSandboxBackend(TARGET_RUNTIME_IMAGE_ID)
        snapshot = ROOT / "fixtures" / "repository" / "project"
        # The exact task command supplies only a synthetic value. Check the
        # variable name, never read or print its value.
        self.assertIn("AI_PROCESS_API", os.environ)
        original_canary = os.environ.get("AGENT_PROCESS_HOST_CANARY")
        os.environ["AGENT_PROCESS_HOST_CANARY"] = "host-only-value"
        try:
            with backend.create(snapshot, {"python", "env"}) as sandbox:
                self.assertTrue(sandbox.network_isolated)
                self.assertEqual(sandbox.run(("python", "--version")).returncode, 0)
                network = sandbox.run(("python", "-c", "import socket; socket.create_connection(('1.1.1.1', 53), timeout=1)"))
                self.assertNotEqual(network.returncode, 0)
                dns = sandbox.run(("python", "-c", "import socket; socket.gethostbyname('example.com')"))
                self.assertNotEqual(dns.returncode, 0)
                capabilities = sandbox.run(("python", "-c", "status=open('/proc/self/status').read(); assert 'CapEff:\\t0000000000000000' in status"))
                self.assertEqual(capabilities.returncode, 0, capabilities.stderr)
                snapshot_write = sandbox.run(("python", "-c", "from pathlib import Path; Path('/snapshot/blocked').write_text('x')"))
                self.assertNotEqual(snapshot_write.returncode, 0)
                rootfs_write = sandbox.run(("python", "-c", "from pathlib import Path; Path('/root/blocked').write_text('x')"))
                self.assertNotEqual(rootfs_write.returncode, 0)
                environment = sandbox.run(("env",))
                self.assertNotIn("AGENT_PROCESS_HOST_CANARY=host-only-value", environment.stdout)
                self.assertNotIn("AI_PROCESS_API=", environment.stdout)
                inspection = subprocess.run(
                    ["docker", "inspect", sandbox._container_id],
                    capture_output=True, text=True, check=True,
                )
                configuration = json.loads(inspection.stdout)[0]
                host_config = configuration["HostConfig"]
                self.assertFalse(
                    any(
                        item.startswith("AI_PROCESS_API=")
                        for item in configuration["Config"].get("Env", [])
                    )
                )
                self.assertEqual(host_config["NetworkMode"], "none")
                self.assertTrue(host_config["ReadonlyRootfs"])
                self.assertEqual(host_config["PidsLimit"], 64)
                self.assertEqual(host_config["Memory"], 512 * 1024 * 1024)
                self.assertEqual(host_config["NanoCpus"], 1_000_000_000)
                self.assertEqual(host_config["CapDrop"], ["ALL"])
                self.assertIn("no-new-privileges", host_config["SecurityOpt"])
                self.assertEqual(configuration["Config"]["User"], backend.user)
                pid_limit = sandbox.run(("python", "-c", "import subprocess\nchildren=[]\nexhausted=False\ntry:\n    for _ in range(128):\n        children.append(subprocess.Popen(['sleep', '5']))\nexcept OSError:\n    exhausted=True\nfinally:\n    for child in children:\n        child.terminate()\n    for child in children:\n        child.wait(timeout=2)\nassert exhausted\nassert len(children) < 64"))
                self.assertEqual(pid_limit.returncode, 0, pid_limit.stderr)
                workspace_write = sandbox.run(("python", "-c", "from pathlib import Path; Path('created-in-container').write_text('ok')"))
                self.assertEqual(workspace_write.returncode, 0)
                self.assertTrue((sandbox.workspace / "created-in-container").exists())
        finally:
            if original_canary is None:
                os.environ.pop("AGENT_PROCESS_HOST_CANARY", None)
            else:
                os.environ["AGENT_PROCESS_HOST_CANARY"] = original_canary


if __name__ == "__main__":
    unittest.main()
