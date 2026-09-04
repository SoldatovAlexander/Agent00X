from pathlib import Path
import json
import os
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.sandbox import DockerSandboxBackend, LocalProcessSandboxBackend, SandboxError


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

    def test_snapshot_and_workspace_are_separate(self):
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            workspace_file = sandbox.workspace / "generated.txt"
            workspace_file.write_text("artifact", encoding="utf-8")
            self.assertFalse((sandbox.snapshot / "generated.txt").exists())

    def test_backend_does_not_claim_network_isolation(self):
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            self.assertFalse(sandbox.network_isolated)
            self.assertEqual(sandbox.security_profile, "development-process-only")

    def test_docker_profile_disables_network_and_limits_container(self):
        backend = DockerSandboxBackend("python:3.12-alpine")
        command = backend.build_run_command(Path("/tmp/snapshot"), Path("/tmp/workspace"))
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
        with self.assertRaisesRegex(SandboxError, "not automatic"):
            backend._assert_image_available()

    @unittest.skipUnless(os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1", "Docker integration test is opt-in")
    def test_docker_backend_enforces_network_mount_and_workspace_profile(self):
        backend = DockerSandboxBackend("python:3.12-alpine")
        snapshot = ROOT / "fixtures" / "repository" / "project"
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
                inspection = subprocess.run(
                    ["docker", "inspect", sandbox._container_id],
                    capture_output=True, text=True, check=True,
                )
                configuration = json.loads(inspection.stdout)[0]
                host_config = configuration["HostConfig"]
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
