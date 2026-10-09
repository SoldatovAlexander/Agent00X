from __future__ import annotations

from collections.abc import Mapping
import getpass
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_pinned_deepseek_worker as cli
from app_contracts.credential_source import (
    ProcessEnvironmentCredentialSource,
    TerminalPromptCredentialSource,
)
from app_contracts.github_http_transport import GitHubRateLimitEvidence
from app_contracts.observer_report import report_from_sqlite
from app_contracts.observation_store import SQLiteObservationStore


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
    def test_observation_database_path_is_new_absolute_and_non_symlink(self):
        with tempfile.TemporaryDirectory(prefix="pinned-worker-observer-path-") as root:
            database = Path(root) / "observations.sqlite3"
            self.assertEqual(cli._validate_new_observation_path(database), database)
            existing = Path(root) / "existing.sqlite3"
            existing.touch()
            link = Path(root) / "observer-link.sqlite3"
            link.symlink_to(existing)
            for invalid in (Path("relative.sqlite3"), Path(root), existing, link):
                with self.subTest(path=str(invalid)):
                    with self.assertRaisesRegex(
                        ValueError,
                        "^pinned Worker CLI: observation journal path is unavailable$",
                    ):
                        cli._validate_new_observation_path(invalid)

    def test_observer_store_is_opened_only_after_confirmation_and_passed_to_runtime(self):
        transport = ValidReadinessTransport(fresh_readiness())
        captured = {}
        with tempfile.TemporaryDirectory(prefix="pinned-worker-observer-") as root:
            stage = Path(root) / "stage.sqlite3"
            observer = Path(root) / "observer.sqlite3"

            def runtime(**kwargs):
                captured.update(kwargs)
                worker = kwargs["execution_worker"]
                permit = kwargs["execution_permit"]
                worker.record_execution_authorization(
                    lambda: permit.consume(
                        process_id=cli.PROCESS_ID,
                        task_id=cli.TASK_ID,
                    )
                )
                worker.record_snapshot_pin_decision(True)
                return 0

            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(stage), "--observation-database", str(observer)],
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: transport,
                runtime_runner=runtime,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: None,
            )

            self.assertEqual(code, 0, errors.getvalue())
            self.assertEqual(transport.calls, 1)
            self.assertIsInstance(captured["observation_store"], SQLiteObservationStore)
            with self.assertRaises(sqlite3.ProgrammingError):
                captured["observation_store"].events()
            self.assertTrue(observer.is_file())
            report = report_from_sqlite(observer)
            self.assertEqual(report["snapshot"]["event_count"], 9)
            self.assertEqual(report["snapshot"]["checkpoint_count"], 4)
            with SQLiteObservationStore(observer) as reopened:
                events = reopened.events()
            self.assertEqual([event["sequence"] for event in events], list(range(9)))
            self.assertEqual(
                [
                    event.get("decision_or_tool")
                    for event in events
                    if event.get("event_type")
                    in {"decision_proposed", "tool_requested"}
                ],
                [
                    "GitHubReadiness.fetch",
                    "RemoteExecutionPermit.issue",
                    "RemoteExecutionPermit.consume",
                    "PinnedSnapshot.validate-fixed-pin",
                ],
            )
            self.assertEqual(len({event["run_id"] for event in events}), 1)
            self.assertEqual(captured["execution_worker"].observer_reference()["run_id"], events[-1]["run_id"])
            self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_observer_database_open_failure_stops_before_readiness_and_runtime(self):
        with tempfile.TemporaryDirectory(prefix="pinned-worker-observer-fail-") as root:
            stage = Path(root) / "stage.sqlite3"
            observer = Path(root) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            readiness = ValidReadinessTransport(fresh_readiness())
            with patch.object(
                cli,
                "SQLiteObservationStore",
                side_effect=OSError("synthetic private failure"),
            ):
                code = cli.main(
                    [str(stage), "--observation-database", str(observer)],
                    input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: readiness,
                    runtime_runner=lambda **_kwargs: self.fail("runtime must not start"),
                    docker_which=lambda _name: "/usr/bin/docker",
                    docker_inspect=lambda _path: None,
                )
            self.assertEqual(code, 2)
            self.assertEqual(readiness.calls, 0)
            self.assertIn('"reason":"observation-journal-unavailable"', output.getvalue())
            self.assertNotIn("synthetic private failure", output.getvalue() + errors.getvalue())

    def test_readiness_transport_failure_is_recorded_and_runtime_is_not_started(self):
        class FailingReadinessTransport:
            calls = 0

            def read_rate_limit(self):
                self.calls += 1
                raise RuntimeError("synthetic readiness transport detail")

        transport = FailingReadinessTransport()
        with tempfile.TemporaryDirectory(prefix="pinned-worker-readiness-fail-") as root:
            stage = Path(root) / "stage.sqlite3"
            observer = Path(root) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(stage), "--observation-database", str(observer)],
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: transport,
                runtime_runner=lambda **_kwargs: self.fail("runtime must not start"),
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: None,
            )
            self.assertEqual(code, 2)
            self.assertEqual(transport.calls, 1)
            self.assertTrue(observer.is_file())
            self.assertNotIn("synthetic readiness transport detail", output.getvalue() + errors.getvalue())
            with SQLiteObservationStore(observer) as reopened:
                events = reopened.events()
            self.assertEqual([event["sequence"] for event in events], [0, 1, 2])
            self.assertEqual(events[0]["event_type"], "agent_started")
            self.assertEqual(events[1]["decision_or_tool"], "GitHubReadiness.fetch")
            self.assertEqual(events[1]["event_type"], "tool_requested")
            self.assertEqual(events[2]["event_type"], "tool_failed")
            self.assertEqual(events[2]["status"], "failed")
            self.assertEqual(events[2]["error_code"], "readiness-fetch-failed")
            self.assertEqual(len({event["run_id"] for event in events}), 1)
            failure = json.loads(errors.getvalue())
            self.assertEqual(failure["observer"]["run_id"], events[-1]["run_id"])
            self.assertEqual(failure["observer"]["as_of_cursor"], 2)
            self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_native_keyring_status_checks_manager_without_looking_up_item(self):
        events = []

        class FakeKeyringSource:
            def manager_available(self):
                events.append("manager")
                return True

            def __call__(self):
                events.append("credential")
                return SECRET

        output, errors = io.StringIO(), io.StringIO()
        code = cli.main(
            ["--check-credential-source", "--credential-source", "native-keyring"],
            stdout=output,
            stderr=errors,
            native_keyring_source_factory=FakeKeyringSource,
            input_fn=lambda _prompt: self.fail("no prompt expected"),
            readiness_transport_factory=lambda: self.fail("no readiness expected"),
            runtime_runner=lambda **_kwargs: self.fail("no runtime expected"),
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "status": "available",
                "credential_source": "native_keyring",
                "credential_item_checked": False,
                "value_read": False,
            },
        )
        self.assertEqual(events, ["manager"])
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_native_keyring_source_is_passed_lazily_to_runtime(self):
        events = []
        captured = {}

        class FakeKeyringSource:
            def manager_available(self):
                events.append("manager")
                return True

            def __call__(self):
                events.append("credential")
                return SECRET

        transport = ValidReadinessTransport(fresh_readiness())
        with tempfile.TemporaryDirectory(prefix="pinned-worker-native-keyring-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()

            def run_runtime(**kwargs):
                events.append("runtime")
                captured.update(kwargs)
                return 0

            code = cli.main(
                ["--credential-source", "native-keyring", str(stage_path)],
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness") or transport,
                runtime_runner=run_runtime,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("images"),
                native_keyring_source_factory=FakeKeyringSource,
            )
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(events, ["images", "manager", "readiness", "runtime"])
        self.assertIsInstance(captured["credential_source"], FakeKeyringSource)
        self.assertNotIn("credential", events)
        self.assertIn("native_keyring:Agent00X/AI_PROCESS_API", output.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_source_status_check_reads_only_name_presence_and_never_starts_runtime(self):
        cases = (
            ("available", {"AI_PROCESS_API": SECRET, "OTHER": "other-secret"}, 0),
            ("unavailable", {"OTHER": "other-secret"}, 3),
        )
        for status, values, expected_code in cases:
            with self.subTest(status=status):
                env = RecordingEnvironment(values)
                events: list[str] = []
                output, errors = io.StringIO(), io.StringIO()
                code = cli.main(
                    ["--check-credential-source", "--credential-source", "process-environment"],
                    environ=env,
                    input_fn=lambda _prompt: events.append("prompt") or cli.CONFIRMATION_PHRASE,
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: events.append("readiness") or None,
                    runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                    docker_which=lambda _name: events.append("docker") or "/usr/bin/docker",
                )

                self.assertEqual(code, expected_code)
                self.assertEqual(
                    json.loads(output.getvalue()),
                    {
                        "status": status,
                        "credential_source": "process_environment",
                        "value_read": False,
                    },
                )
                self.assertEqual(events, [])
                self.assertEqual(env.lookups, [])
                self.assertEqual(errors.getvalue(), "")
                self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())
                self.assertNotIn("other-secret", output.getvalue() + errors.getvalue())

    def test_source_status_check_requires_an_explicit_noninteractive_source(self):
        output, errors = io.StringIO(), io.StringIO()
        code = cli.main(
            ["--check-credential-source"],
            input_fn=lambda _prompt: self.fail("no prompt expected"),
            stdout=output,
            stderr=errors,
        )
        self.assertEqual(code, 2)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "status": "unavailable",
                "credential_source": "invalid-check",
                "value_read": False,
            },
        )
        self.assertEqual(errors.getvalue(), "")

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
            observer_path = Path(temporary) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [
                    "--credential-source",
                    "process-environment",
                    "--observation-database",
                    str(observer_path),
                    str(stage_path),
                ],
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
            self.assertFalse(observer_path.exists())
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
                captured["synthetic_credential_value"] = kwargs[
                    "credential_source"
                ]()
                return 0

            code = cli.main(
                ["--credential-source", "process-environment", str(stage_path)],
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
        self.assertEqual(env.lookups, ["AI_PROCESS_API"])
        self.assertEqual(captured["synthetic_credential_value"], SECRET)
        self.assertEqual(captured["stage_database_path"], stage_path)
        self.assertEqual(captured["process_id"], cli.PROCESS_ID)
        self.assertEqual(captured["task_id"], cli.TASK_ID)
        self.assertEqual(captured["task_id"], "task-exp-634-live-001")
        self.assertEqual(cli.CONFIRMATION_PHRASE, "RUN EXP-634 ONCE")
        instruction = captured["task_instruction"]
        for field in ("level", "correct", "wrong", "total", "time_ms"):
            self.assertIn(field, instruction)
        self.assertIn("signed 64-bit range [-2^63, 2^63-1]", instruction)
        self.assertIn("malformed, non-finite, fractional", instruction)
        self.assertIn("HTTP 422 and zero rows written", instruction)
        self.assertIn("HTTP 200 and exactly one expected row", instruction)
        self.assertEqual(captured["declared_change_paths"], ("backend/routes.py",))
        self.assertEqual(captured["allowed_commands"], frozenset({"python3"}))
        self.assertEqual(captured["execution_image"], cli.TARGET_RUNTIME_IMAGE_ID)
        self.assertEqual(captured["execution_permit"].card_id, "EXP-634")
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

    def test_exp726_profile_binds_confirmation_permit_and_runtime_identities(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        transport = ValidReadinessTransport(fresh_readiness())
        captured: dict[str, object] = {}
        prompts: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-exp726-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()

            def run_runtime(**kwargs):
                captured.update(kwargs)
                return 0

            code = cli.main(
                [
                    "--authorization-card-id",
                    "EXP-726",
                    "--credential-source",
                    "process-environment",
                    str(stage_path),
                ],
                environ=env,
                input_fn=lambda prompt: prompts.append(prompt) or "RUN EXP-726 ONCE",
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: transport,
                runtime_runner=run_runtime,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: None,
            )

        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(transport.calls, 1)
        self.assertEqual(prompts, ["Type RUN EXP-726 ONCE to continue: "])
        self.assertEqual(env.lookups, [])
        self.assertEqual(captured["process_id"], "process-exp-726-live-001")
        self.assertEqual(captured["task_id"], "task-exp-726-live-001")
        self.assertEqual(captured["execution_permit"].card_id, "EXP-726")
        payload = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(payload["authorization_card_id"], "EXP-726")
        self.assertEqual(payload["process_id"], "process-exp-726-live-001")
        self.assertEqual(payload["task_id"], "task-exp-726-live-001")
        self.assertEqual(payload["confirmation_phrase"], "RUN EXP-726 ONCE")
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_exp726_profile_rejects_exp634_confirmation_before_readiness(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        events: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-exp726-cancel-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [
                    "--authorization-card-id",
                    "EXP-726",
                    "--credential-source",
                    "process-environment",
                    str(stage_path),
                ],
                environ=env,
                input_fn=lambda prompt: events.append(prompt) or "RUN EXP-634 ONCE",
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness") or None,
                runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("inspect"),
            )
        self.assertEqual(code, 3)
        self.assertEqual(events, ["inspect", "Type RUN EXP-726 ONCE to continue: "])
        self.assertEqual(env.lookups, [])
        self.assertFalse(stage_path.exists())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())
        self.assertIn('"provider_attempts":0', output.getvalue())

    def test_unknown_authorization_card_id_is_rejected_before_preflight(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        events: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-unknown-card-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            with patch("sys.stderr", errors):
                with self.assertRaises(SystemExit) as raised:
                    cli.main(
                        ["--authorization-card-id", "EXP-999", str(stage_path)],
                        environ=env,
                        stdout=output,
                        stderr=errors,
                        readiness_transport_factory=lambda: events.append("readiness"),
                        runtime_runner=lambda **_kwargs: events.append("runtime"),
                        docker_which=lambda _name: events.append("docker-which"),
                        docker_inspect=lambda _path: events.append("docker-inspect"),
                    )
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(events, [])
        self.assertEqual(env.lookups, [])
        self.assertFalse(stage_path.exists())
        self.assertIn("invalid choice", errors.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_card_without_authorized_snapshot_origin_stops_before_preflight(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        events: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-unmapped-origin-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            with patch.dict(cli.AUTHORIZATION_SNAPSHOT_ORIGINS, {}, clear=True):
                code = cli.main(
                    ["--authorization-card-id", "EXP-634", str(stage_path)],
                    environ=env,
                    input_fn=lambda prompt: events.append(prompt) or cli.CONFIRMATION_PHRASE,
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: events.append("readiness"),
                    runtime_runner=lambda **_kwargs: events.append("runtime"),
                    docker_which=lambda _name: events.append("docker-which"),
                    docker_inspect=lambda _path: events.append("docker-inspect"),
                )
        self.assertEqual(code, 2)
        self.assertEqual(events, [])
        self.assertEqual(env.lookups, [])
        self.assertFalse(stage_path.exists())
        self.assertIn('"reason":"snapshot-source-not-authorized"', output.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_missing_process_variable_stops_before_readiness_and_runtime(self):
        env = RecordingEnvironment({"OTHER": "synthetic-other-secret"})
        events: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-cli-missing-source-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            observer_path = Path(temporary) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [
                    "--credential-source",
                    "process-environment",
                    "--observation-database",
                    str(observer_path),
                    str(stage_path),
                ],
                environ=env,
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness") or None,
                runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("inspect"),
            )
        self.assertEqual(code, 2)
        self.assertEqual(events, ["inspect"])
        self.assertEqual(env.lookups, [])
        self.assertFalse(stage_path.exists())
        self.assertFalse(observer_path.exists())
        self.assertIn('"reason":"credential-source-unavailable"', output.getvalue())
        self.assertNotIn("synthetic-other-secret", output.getvalue() + errors.getvalue())

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
            observer_path = Path(temporary) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [
                    "--credential-source",
                    "process-environment",
                    "--observation-database",
                    str(observer_path),
                    str(Path(temporary) / "stage.sqlite3"),
                ],
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
            with SQLiteObservationStore(observer_path) as reopened:
                events = reopened.events()
        self.assertEqual([event["sequence"] for event in events], list(range(5)))
        self.assertEqual(events[-1]["decision_or_tool"], "RemoteExecutionPermit.issue")
        self.assertEqual(events[-1]["status"], "denied")
        self.assertEqual(events[-1]["error_code"], "readiness-ineligible")

    def test_unready_public_api_stops_before_hidden_terminal_credential_prompt(self):
        transport = ValidReadinessTransport(
            GitHubRateLimitEvidence(
                status=200,
                remaining=10,
                reset_unix=int(time.time()) + 3600,
                observed_monotonic=time.monotonic(),
            )
        )
        runtime_calls: list[bool] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-hidden-unready-") as root:
            stage_path = Path(root) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(getpass, "getpass") as hidden_prompt:
                code = cli.main(
                    [str(stage_path)],
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
        hidden_prompt.assert_not_called()
        self.assertFalse(stage_path.exists())
        self.assertIn('"credential_input":"hidden_terminal_prompt"', output.getvalue())
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
