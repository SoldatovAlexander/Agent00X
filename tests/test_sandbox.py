from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.sandbox import LocalProcessSandboxBackend, SandboxError


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


if __name__ == "__main__":
    unittest.main()
