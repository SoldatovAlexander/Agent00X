from __future__ import annotations

from collections.abc import Mapping
import io
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_pinned_deepseek_worker as cli
from app_contracts.credential_source import (
    ProcessEnvironmentCredentialSource,
    TerminalPromptCredentialSource,
)
from app_contracts.github_http_transport import GitHubRateLimitEvidence


SECRET = "synthetic-live-token-never-output"


class RecordingEnvironment(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookups: list[str] = []

    def __getitem__(self, name):
        self.lookups.append(name)
        return super().__getitem__(name)


class ValidReadinessTransport:
    def __init__(self, evidence):
        self.evidence = evidence
        self.calls = 0

    def read_rate_limit(self):
        self.calls += 1
        return self.evidence


def fresh_readiness():
    return GitHubRateLimitEvidence(
        status=200,
        remaining=50,
        reset_unix=int(time.time()) + 3600,
        observed_monotonic=time.monotonic(),
    )


class PinnedDeepSeekWorkerCliTests(unittest.TestCase):
    def test_docker_preflight_uses_only_pinned_images(self):
        calls: list[list[str]] = []

        def run(argv, **kwargs):
            calls.append(argv)
            self.assertTrue(kwargs["check"])
            self.assertEqual(kwargs["timeout"], 10)
            return SimpleNamespace(stdout=argv[-1] + "\n")

        cli._preflight_docker_images("/usr/bin/docker", run=run)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [call[-1] for call in calls],
            [cli.TARGET_RUNTIME_IMAGE_ID, cli.VERIFIER_RUNTIME_IMAGE_ID],
        )
        self.assertTrue(all(call[1:3] == ["image", "inspect"] for call in calls))

    def test_invalid_stage_path_stops_before_prompt_readiness_and_runtime(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        events: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-cli-") as temporary:
            root = Path(temporary)
            existing = root / "exists.sqlite3"
            existing.touch()
            target = root / "target.sqlite3"
            link = root / "linked.sqlite3"
            link.symlink_to(target)
            invalid_paths = (
                "relative-stage.sqlite3",
                str(root / ".." / "traversal.sqlite3"),
                str(existing),
                str(link),
                str(root / "missing-parent" / "stage.sqlite3"),
            )
            for invalid_path in invalid_paths:
                with self.subTest(path=invalid_path):
                    output, errors = io.StringIO(), io.StringIO()
                    code = cli.main(
                        [invalid_path],
                        environ=env,
                        input_fn=lambda _prompt: events.append("prompt") or cli.CONFIRMATION_PHRASE,
                        stdout=output,
                        stderr=errors,
                        readiness_transport_factory=lambda: events.append("readiness") or None,
                        runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                        docker_which=lambda _name: events.append("docker") or "/usr/bin/docker",
                        docker_inspect=lambda _path: events.append("inspect"),
                    )
                    self.assertEqual(code, 2)
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(
                        errors.getvalue(),
                        "pinned Worker CLI: stage path is unavailable\n",
                    )
        self.assertEqual(events, [])
        self.assertEqual(env.lookups, [])

    def test_cancel_happens_before_readiness_secret_lookup_or_stage_creation(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        events: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-cli-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(stage_path)],
                environ=env,
                input_fn=lambda prompt: events.append(prompt) or "no",
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness") or None,
                runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("inspect"),
            )
            self.assertEqual(code, 3)
            self.assertFalse(stage_path.exists())
        self.assertEqual(events, ["inspect", f"Type {cli.CONFIRMATION_PHRASE} to continue: "])
        self.assertEqual(env.lookups, [])
        self.assertIn('"provider_attempts":0', output.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_confirmed_run_issues_one_permit_and_forwards_fixed_profile(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET, "OTHER": "other-secret"})
        events: list[str] = []
        transport = ValidReadinessTransport(fresh_readiness())
        captured: dict[str, object] = {}
        with tempfile.TemporaryDirectory(prefix="pinned-worker-cli-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()

            def run_runtime(**kwargs):
                events.append("runtime")
                captured.update(kwargs)
                return 0

            code = cli.main(
                [str(stage_path)],
                environ=env,
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: transport,
                runtime_runner=run_runtime,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("inspect"),
            )
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(transport.calls, 1)
        self.assertEqual(events, ["inspect", "runtime"])
        self.assertEqual(env.lookups, [])
        self.assertEqual(captured["stage_database_path"], stage_path)
        self.assertEqual(captured["process_id"], cli.PROCESS_ID)
        self.assertEqual(captured["task_id"], cli.TASK_ID)
        self.assertEqual(captured["declared_change_paths"], ("backend/routes.py",))
        self.assertEqual(captured["allowed_commands"], frozenset({"python3"}))
        self.assertEqual(captured["execution_image"], cli.TARGET_RUNTIME_IMAGE_ID)
        self.assertEqual(captured["execution_permit"].card_id, "EXP-566")
        source = captured["credential_source"]
        self.assertIsInstance(source, ProcessEnvironmentCredentialSource)
        self.assertEqual(
            repr(source), "ProcessEnvironmentCredentialSource(value='opaque')"
        )
        diagnostic = output.getvalue() + errors.getvalue()
        self.assertIn("api.deepseek.com/chat/completions", diagnostic)
        self.assertIn(cli.CONFIRMATION_PHRASE, diagnostic)
        self.assertNotIn(SECRET, diagnostic)
        self.assertNotIn("other-secret", diagnostic)

    def test_unready_public_api_stops_before_runtime_and_credential_lookup(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        transport = ValidReadinessTransport(
            GitHubRateLimitEvidence(
                status=200,
                remaining=2,
                reset_unix=int(time.time()) + 3600,
                observed_monotonic=time.monotonic(),
            )
        )
        runtime_calls: list[bool] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-cli-") as temporary:
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(Path(temporary) / "stage.sqlite3")],
                environ=env,
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: transport,
                runtime_runner=lambda **_kwargs: runtime_calls.append(True) or 0,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: None,
            )
        self.assertEqual(code, 2)
        self.assertEqual(transport.calls, 1)
        self.assertEqual(runtime_calls, [])
        self.assertEqual(env.lookups, [])
        self.assertIn("pinned-worker-runtime-failed", errors.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_default_cli_wires_hidden_terminal_source_without_reading_environment(self):
        captured: dict[str, object] = {}
        with tempfile.TemporaryDirectory(prefix="pinned-worker-cli-") as temporary:
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(Path(temporary) / "stage.sqlite3")],
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: ValidReadinessTransport(
                    fresh_readiness()
                ),
                runtime_runner=lambda **kwargs: captured.update(kwargs) or 0,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: None,
            )
        self.assertEqual(code, 0, errors.getvalue())
        source = captured["credential_source"]
        self.assertIsInstance(source, TerminalPromptCredentialSource)
        self.assertEqual(
            repr(source), "TerminalPromptCredentialSource(value='opaque')"
        )
        self.assertIn('"credential_input":"hidden_terminal_prompt"', output.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())


if __name__ == "__main__":
    unittest.main()
