from __future__ import annotations

from collections.abc import Mapping
from contextlib import redirect_stderr
import getpass
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_pinned_deepseek_worker as cli
from app_contracts.credential_source import (
    ProcessEnvironmentCredentialSource,
    TerminalPromptCredentialSource,
)
from app_contracts.deepseek_http_channel import DeepSeekHTTPChannel
from app_contracts.deepseek_worker import DeepSeekProposalWorker
from app_contracts.local_ollama_channel import LocalOllamaChatCompletionsChannel
from app_contracts.r5_local_model_preflight import EXPECTED_OLLAMA_VERSION
from app_contracts.github_http_transport import GitHubRateLimitEvidence
from app_contracts.digests import sha256_bytes
from app_contracts.observer_report import report_from_sqlite
from app_contracts.observation_store import PreDispatchError, SQLiteObservationStore
from app_contracts.observer_runtime import (
    JournaledModelChannel,
    JournaledProposalWorker,
)
from app_contracts.signed_verifier_client import SignedVerifierHTTPSTransport
from app_contracts.signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE
from app_contracts.verifier_host_trust_decision import (
    build_signed_verifier_host_trust_decision,
)
from app_contracts.verifier_trust_enrollment import (
    build_signed_verifier_trust_enrollment,
)


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
    def setUp(self):
        self._stdin_patch = patch.object(
            cli.sys, "stdin", new=SimpleNamespace(isatty=lambda: True)
        )
        self._stdin_patch.start()
        self.addCleanup(self._stdin_patch.stop)
        # CLI composition tests use a synthetic successful model preflight by
        # default; dedicated tests below assert its order and failure behavior.
        self._model_preflight_patch = patch.object(
            cli,
            "R5LocalOllamaMetadataPreflight",
            return_value=SimpleNamespace(
                inspect=lambda **_kwargs: SimpleNamespace(
                    version=EXPECTED_OLLAMA_VERSION,
                    model=cli.LOCAL_OLLAMA_MODEL,
                    model_digest=cli.LOCAL_OLLAMA_MODEL_DIGEST,
                )
            ),
        )
        self._model_preflight_patch.start()
        self.addCleanup(self._model_preflight_patch.stop)

    def test_non_tty_exact_gate_refuses_before_preflight_or_callbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "stage.sqlite3"
            observer = Path(directory) / "observer.sqlite3"
            events = []

            class TrackingEnvironment(dict):
                reads = []

                def __contains__(self, key):
                    self.reads.append(key)
                    return super().__contains__(key)

            environment = TrackingEnvironment({"AI_PROCESS_API": SECRET})
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(
                cli.sys, "stdin", new=SimpleNamespace(isatty=lambda: False)
            ):
                code = cli.main(
                    [
                        str(stage),
                        "--credential-source", "process-environment",
                        "--observation-database", str(observer),
                    ],
                    environ=environment,
                    input_fn=lambda _prompt: events.append("input") or cli.CONFIRMATION_PHRASE,
                    stdout=output,
                    stderr=errors,
                    docker_which=lambda _name: events.append("docker-which") or self.fail(
                        "Docker discovery must not run"
                    ),
                    docker_inspect=lambda *_args, **_kwargs: events.append("docker-inspect"),
                    readiness_transport_factory=lambda: events.append("readiness"),
                    runtime_runner=lambda **_kwargs: events.append("runtime"),
                    local_model_preflight_factory=lambda: events.append("model-preflight"),
                )

            self.assertEqual(code, 3)
            self.assertEqual(
                output.getvalue(),
                '{"status":"cancelled","reason":"interactive-terminal-required",'
                '"provider_attempts":0}\n',
            )
            self.assertEqual(errors.getvalue(), "")
            self.assertEqual(events, [])
            self.assertEqual(environment.reads, [])
            self.assertFalse(stage.exists())
            self.assertFalse(observer.exists())

    @staticmethod
    def _write_signed_verifier_material(root: Path):
        authority_id = "synthetic-cli-authority-exp798"
        worker_host_id = "synthetic-cli-worker-exp798"
        verifier_host_id = "synthetic-cli-testdev-exp798"
        authority_key = Ed25519PrivateKey.generate()
        verifier_key = Ed25519PrivateKey.generate()
        authority_public_key = authority_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        verifier_public_key = verifier_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        now = datetime.now(timezone.utc).replace(microsecond=0)
        endpoint = cli.PINNED_SIGNED_VERIFIER_ENDPOINT_URL
        profile = BRAINBOOSTER_VERIFIER_PROFILE
        enrollment = build_signed_verifier_trust_enrollment(
            enrollment_id="synthetic-cli-enrollment-exp798",
            authority_key_id=authority_id,
            endpoint_url=endpoint,
            verifier_id=profile.expected_verifier_id,
            verifier_profile_digest=profile.profile_digest,
            verifier_key_id=profile.signer_key_id,
            verifier_public_key=verifier_public_key,
            worker_host_id=worker_host_id,
            verifier_host_id=verifier_host_id,
            host_separation_evidence_digest="sha256:" + "4" * 64,
            signing_key=authority_key,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        decision = build_signed_verifier_host_trust_decision(
            decision_id="synthetic-cli-host-decision-exp798",
            authority_key_id=authority_id,
            enrollment_digest=sha256_bytes(enrollment),
            endpoint_url=endpoint,
            verifier_id=profile.expected_verifier_id,
            verifier_profile_digest=profile.profile_digest,
            verifier_key_id=profile.signer_key_id,
            worker_host_id=worker_host_id,
            verifier_host_id=verifier_host_id,
            host_separation_evidence_digest="sha256:" + "4" * 64,
            signing_key=authority_key,
            issued_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        authority_key_set = json.dumps(
            {
                "schema": "control-plane-authority-key-set/v1",
                "keys": {authority_id: authority_public_key.hex()},
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        paths = {
            "authority": root / "authority-key-set.json",
            "enrollment": root / "enrollment.json",
            "decision": root / "host-decision.json",
            "ca": root / "verifier-ca.pem",
        }
        paths["authority"].write_bytes(authority_key_set)
        paths["enrollment"].write_bytes(enrollment)
        paths["decision"].write_bytes(decision)
        paths["ca"].write_bytes(b"synthetic public CA bundle")

        def pinned_digest(path: Path) -> str:
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

        arguments = [
            "--verifier-backend",
            "trusted-https",
            "--verifier-authority-key-set",
            str(paths["authority"]),
            "--verifier-authority-key-set-sha256",
            pinned_digest(paths["authority"]),
            "--verifier-enrollment",
            str(paths["enrollment"]),
            "--verifier-enrollment-sha256",
            pinned_digest(paths["enrollment"]),
            "--verifier-host-decision",
            str(paths["decision"]),
            "--verifier-host-decision-sha256",
            pinned_digest(paths["decision"]),
            "--verifier-ca-bundle",
            str(paths["ca"]),
            "--verifier-ca-bundle-sha256",
            pinned_digest(paths["ca"]),
            "--expected-worker-host-id",
            worker_host_id,
            "--expected-verifier-host-id",
            verifier_host_id,
        ]
        return arguments, paths, worker_host_id, verifier_host_id

    def test_trusted_https_cli_loads_only_digest_pinned_public_material(self):
        with tempfile.TemporaryDirectory(prefix="pinned-worker-trust-material-") as root:
            arguments, _paths, worker_host_id, verifier_host_id = (
                self._write_signed_verifier_material(Path(root))
            )
            # Exercise the same parser contract as main without invoking readiness,
            # Docker, credentials, or the Worker.
            parsed = cli.argparse.Namespace(
                verifier_authority_key_set=arguments[3],
                verifier_authority_key_set_sha256=arguments[5],
                verifier_enrollment=arguments[7],
                verifier_enrollment_sha256=arguments[9],
                verifier_host_decision=arguments[11],
                verifier_host_decision_sha256=arguments[13],
                verifier_ca_bundle=arguments[15],
                verifier_ca_bundle_sha256=arguments[17],
                expected_worker_host_id=worker_host_id,
                expected_verifier_host_id=verifier_host_id,
                verifier_connect_address="192.168.88.101",
                verifier_connect_port=8443,
            )
            with patch.object(SignedVerifierHTTPSTransport, "validate_configuration") as validate:
                client, worker, verifier, digests = cli._load_signed_verifier_client(parsed)

            validate.assert_called_once_with()
            self.assertEqual(client.endpoint_url, "https://testdev.local/v1/verify")
            self.assertEqual(client.connect_address, "192.168.88.101")
            self.assertEqual(client.connect_port, 8443)
            self.assertTrue(client.has_current_independent_host_trust())
            self.assertEqual((worker, verifier), (worker_host_id, verifier_host_id))
            self.assertEqual(set(digests), {
                "authority_key_set_sha256",
                "enrollment_sha256",
                "host_decision_sha256",
                "ca_bundle_sha256",
            })

    def test_trusted_https_cli_wires_client_without_verifier_docker_preflight(self):
        transport = ValidReadinessTransport(fresh_readiness())
        captured = {}
        events = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-trusted-https-") as root:
            stage = Path(root) / "stage.sqlite3"
            arguments, _paths, worker_host_id, verifier_host_id = (
                self._write_signed_verifier_material(Path(root))
            )
            arguments.extend(
                [
                    "--verifier-connect-address",
                    "127.0.0.1",
                    "--verifier-connect-port",
                    "8443",
                ]
            )

            def runtime(**kwargs):
                captured.update(kwargs)
                events.append("runtime")
                return 0

            output, errors = io.StringIO(), io.StringIO()
            with (
                patch.object(SignedVerifierHTTPSTransport, "validate_configuration"),
                patch.object(cli, "_preflight_target_docker_image", side_effect=lambda _docker: events.append("target-image")),
            ):
                code = cli.main(
                    [str(stage), "--credential-source", "process-environment", *arguments],
                    environ={"AI_PROCESS_API": SECRET},
                    input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: events.append("readiness") or transport,
                    runtime_runner=runtime,
                    docker_which=lambda _name: "/usr/bin/docker",
                    docker_inspect=lambda _path: self.fail("Docker verifier preflight must not run"),
                )

        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(events, ["target-image", "readiness", "runtime"])
        self.assertEqual(transport.calls, 1)
        self.assertEqual(captured["verifier_client"].endpoint_url, "https://testdev.local/v1/verify")
        self.assertEqual(captured["verifier_client"].connect_address, "127.0.0.1")
        self.assertEqual(captured["verifier_client"].connect_port, 8443)
        self.assertEqual(captured["expected_worker_host_id"], worker_host_id)
        self.assertEqual(captured["expected_verifier_host_id"], verifier_host_id)
        self.assertNotIn("verifier_config", captured)
        preview = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(preview["verifier_backend"], "trusted-https")
        self.assertEqual(preview["verifier_endpoint"], "https://testdev.local/v1/verify")
        self.assertEqual(preview["verifier_connect_address"], "127.0.0.1")
        self.assertEqual(preview["verifier_connect_port"], 8443)
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_invalid_verifier_connect_address_stops_before_all_io(self):
        events = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-connect-address-") as root:
            stage = Path(root) / "stage.sqlite3"
            arguments, _paths, _worker_host_id, _verifier_host_id = (
                self._write_signed_verifier_material(Path(root))
            )
            arguments.extend(["--verifier-connect-address", "testdev.local"])
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(stage), *arguments],
                input_fn=lambda _prompt: events.append("prompt") or cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness"),
                runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                docker_which=lambda _name: events.append("docker") or "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("inspect"),
            )

        self.assertEqual(code, 2)
        self.assertEqual(events, [])
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "status": "stopped",
                "reason": "verifier-trust-material-unavailable",
                "provider_attempts": 0,
            },
        )
        self.assertEqual(errors.getvalue(), "")

    def test_verifier_connect_port_without_address_stops_before_all_io(self):
        events = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-connect-port-") as root:
            stage = Path(root) / "stage.sqlite3"
            arguments, _paths, _worker_host_id, _verifier_host_id = (
                self._write_signed_verifier_material(Path(root))
            )
            arguments.extend(["--verifier-connect-port", "8443"])
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(stage), *arguments],
                input_fn=lambda _prompt: events.append("prompt") or cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness"),
                runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                docker_which=lambda _name: events.append("docker") or "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("inspect"),
            )

        self.assertEqual(code, 2)
        self.assertEqual(events, [])
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "status": "stopped",
                "reason": "verifier-trust-material-unavailable",
                "provider_attempts": 0,
            },
        )
        self.assertEqual(errors.getvalue(), "")

    def test_trusted_https_bad_ca_pin_stops_before_preflight_readiness_and_prompt(self):
        events = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-trust-pin-") as root:
            stage = Path(root) / "stage.sqlite3"
            arguments, _paths, _worker_host_id, _verifier_host_id = (
                self._write_signed_verifier_material(Path(root))
            )
            arguments[17] = "sha256:" + "0" * 64
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(stage), *arguments],
                input_fn=lambda _prompt: events.append("prompt") or cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness"),
                runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                docker_which=lambda _name: events.append("docker") or "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("inspect"),
            )
        self.assertEqual(code, 2)
        self.assertEqual(events, [])
        self.assertEqual(
            json.loads(output.getvalue()),
            {"status": "stopped", "reason": "verifier-trust-material-unavailable", "provider_attempts": 0},
        )
        self.assertEqual(errors.getvalue(), "")

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
        _phrase, profile_process_id, profile_task_id = cli.AUTHORIZATION_PROFILES[
            "EXP-851"
        ]
        with tempfile.TemporaryDirectory(prefix="pinned-worker-observer-") as root:
            stage = Path(root) / "stage.sqlite3"
            observer = Path(root) / "observer.sqlite3"

            def runtime(**kwargs):
                captured.update(kwargs)
                worker = kwargs["execution_worker"]
                permit = kwargs["execution_permit"]
                worker.record_execution_authorization(
                    lambda: permit.consume(
                        process_id=profile_process_id,
                        task_id=profile_task_id,
                    )
                )
                worker.record_snapshot_pin_decision(True)
                return 0

            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [
                    str(stage),
                    "--authorization-card-id",
                    "EXP-851",
                    "--model-backend",
                    "local-ollama",
                    "--credential-source",
                    "not-applicable",
                    "--observation-database",
                    str(observer),
                ],
                input_fn=lambda _prompt: cli.AUTHORIZATION_PROFILES["EXP-851"][0],
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
            self.assertEqual(report["snapshot"]["event_count"], 11)
            self.assertEqual(report["snapshot"]["checkpoint_count"], 5)
            with SQLiteObservationStore(observer) as reopened:
                events = reopened.events()
            self.assertEqual([event["sequence"] for event in events], list(range(11)))
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
                    "LocalOllamaMetadataPreflight.inspect",
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
            self.assertIn("github-readiness-fetch-failed", errors.getvalue())
            self.assertNotIn("synthetic readiness transport detail", output.getvalue() + errors.getvalue())
            with SQLiteObservationStore(observer) as reopened:
                events = reopened.events()
            self.assertEqual([event["sequence"] for event in events], [0, 1, 2, 3])
            self.assertEqual(events[0]["event_type"], "agent_started")
            self.assertEqual(events[1]["decision_or_tool"], "GitHubReadiness.fetch")
            self.assertEqual(events[1]["event_type"], "tool_requested")
            self.assertEqual(events[2]["event_type"], "tool_failed")
            self.assertEqual(events[2]["status"], "failed")
            self.assertEqual(events[2]["error_code"], "readiness-fetch-failed")
            self.assertEqual(events[3]["event_type"], "agent_finished")
            self.assertEqual(events[3]["status"], "failed")
            self.assertEqual(events[3]["invocation_id"], events[0]["invocation_id"])
            self.assertEqual(len({event["run_id"] for event in events}), 1)
            failure = json.loads(errors.getvalue())
            self.assertEqual(failure["observer"]["run_id"], events[-1]["run_id"])
            self.assertEqual(failure["observer"]["as_of_cursor"], 3)
            self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_readiness_transport_construction_failure_has_fixed_marker(self):
        with tempfile.TemporaryDirectory(prefix="pinned-worker-readiness-init-fail-") as root:
            stage = Path(root) / "stage.sqlite3"
            observer = Path(root) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()

            def fail_construction():
                raise RuntimeError("synthetic private constructor detail")

            code = cli.main(
                [str(stage), "--observation-database", str(observer)],
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=fail_construction,
                runtime_runner=lambda **_kwargs: self.fail("runtime must not start"),
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: None,
            )
        self.assertEqual(code, 2)
        self.assertIn("github-readiness-transport-init-failed", errors.getvalue())
        self.assertNotIn("synthetic private constructor detail", output.getvalue() + errors.getvalue())
        self.assertFalse(stage.exists())

    def test_observer_predispatch_refusal_is_distinct_and_never_calls_transport(self):
        class NeverCalledReadinessTransport:
            calls = 0

            def read_rate_limit(self):
                self.calls += 1
                return fresh_readiness()

        transport = NeverCalledReadinessTransport()
        with tempfile.TemporaryDirectory(prefix="pinned-worker-readiness-predispatch-") as root:
            stage = Path(root) / "stage.sqlite3"
            observer = Path(root) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            with patch(
                "app_contracts.observer_runtime.run_gated_dispatch",
                side_effect=PreDispatchError("synthetic private gate detail"),
            ):
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
        self.assertEqual(transport.calls, 0)
        self.assertIn("observer-readiness-pre-dispatch-failed", errors.getvalue())
        self.assertNotIn("synthetic private gate detail", output.getvalue() + errors.getvalue())
        self.assertFalse(stage.exists())

    def test_observer_postdispatch_unknown_is_fixed_and_never_retried(self):
        class LoseReadinessTerminalStore(SQLiteObservationStore):
            def append(self, event):
                if (
                    event.get("agent_id") == "service-publication-observer"
                    and event.get("event_type") == "tool_completed"
                ):
                    raise RuntimeError("synthetic private terminal detail")
                return super().append(event)

        class CountingReadinessTransport:
            calls = 0

            def read_rate_limit(self):
                self.calls += 1
                return fresh_readiness()

        transport = CountingReadinessTransport()
        with tempfile.TemporaryDirectory(prefix="pinned-worker-readiness-unknown-") as root:
            stage = Path(root) / "stage.sqlite3"
            observer = Path(root) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(cli, "SQLiteObservationStore", LoseReadinessTerminalStore):
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
        self.assertIn("observer-readiness-outcome-unknown", errors.getvalue())
        self.assertNotIn("synthetic private terminal detail", output.getvalue() + errors.getvalue())
        self.assertFalse(stage.exists())

    def test_readiness_transport_category_is_fixed_and_redacted_in_cli_evidence(self):
        class FailingReadinessTransport:
            calls = 0

            def read_rate_limit(self):
                self.calls += 1
                raise cli.GitHubHTTPTransportError(
                    "github http transport: request failed",
                    failure_code="timeout",
                )

        transport = FailingReadinessTransport()
        with tempfile.TemporaryDirectory(prefix="pinned-worker-readiness-category-") as root:
            stage = Path(root) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(stage)],
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
        self.assertIn('"failure_code":"github-readiness-timeout"', errors.getvalue())
        self.assertNotIn("github http transport:", errors.getvalue())
        self.assertFalse(stage.exists())

    def test_readiness_transport_rejects_mutated_failure_category(self):
        class FailingReadinessTransport:
            def read_rate_limit(self):
                error = cli.GitHubHTTPTransportError(
                    "fixed safe message", failure_code="timeout"
                )
                error.failure_code = "SYNTHETIC-PRIVATE-CATEGORY"
                raise error

        with tempfile.TemporaryDirectory(prefix="pinned-worker-readiness-invalid-category-") as root:
            stage = Path(root) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            code = cli.main(
                [str(stage)],
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=FailingReadinessTransport,
                runtime_runner=lambda **_kwargs: self.fail("runtime must not start"),
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: None,
            )
        self.assertEqual(code, 2)
        self.assertIn('"failure_code":"github-readiness-fetch-failed"', errors.getvalue())
        self.assertNotIn("SYNTHETIC-PRIVATE-CATEGORY", errors.getvalue())
        self.assertFalse(stage.exists())

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
                ["--credential-source", "native-keyring", "--worker-backend", "host-process", str(stage_path)],
                input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness") or transport,
                runtime_runner=run_runtime,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("images"),
                native_keyring_source_factory=FakeKeyringSource,
                local_model_preflight_factory=lambda: self.fail(
                    "DeepSeek path must not preflight local Ollama"
                ),
            )
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(events, ["images", "manager", "readiness", "runtime"])
        self.assertIsInstance(captured["credential_source"], FakeKeyringSource)
        self.assertNotIn("credential", events)
        self.assertIn("native_keyring:Agent00X/AI_PROCESS_API", output.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_restricted_container_worker_is_default_and_stays_credential_lazy(self):
        events = []
        captured = {}
        isolated_worker = SimpleNamespace(propose=lambda _task: None)

        class FakeCredentialSource:
            def manager_available(self):
                return True

            def __call__(self):
                events.append("credential")
                return SECRET

        transport = ValidReadinessTransport(fresh_readiness())
        with tempfile.TemporaryDirectory(prefix="pinned-worker-restricted-default-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()

            def runtime(**kwargs):
                captured.update(kwargs)
                events.append("runtime")
                return 0

            def build_worker(channel, *, docker_executable):
                events.append("worker-construction")
                self.assertEqual(docker_executable, "/usr/bin/docker")
                self.assertIsInstance(channel, DeepSeekHTTPChannel)
                return isolated_worker

            with patch.object(cli, "ContainerProposalWorker", side_effect=build_worker):
                code = cli.main(
                    [str(stage_path), "--credential-source", "native-keyring"],
                    input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: events.append("readiness") or transport,
                    runtime_runner=runtime,
                    docker_which=lambda _name: "/usr/bin/docker",
                    docker_inspect=lambda _path: events.append("images"),
                    native_keyring_source_factory=FakeCredentialSource,
                )

        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(
            events,
            ["images", "worker-construction", "readiness", "runtime"],
        )
        self.assertIs(captured["proposal_worker"], isolated_worker)
        self.assertIsInstance(captured["credential_source"], FakeCredentialSource)
        self.assertEqual(transport.calls, 1)
        self.assertIn('"worker_backend":"restricted-container"', output.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_host_process_worker_requires_explicit_legacy_selection(self):
        captured = {}
        transport = ValidReadinessTransport(fresh_readiness())
        with tempfile.TemporaryDirectory(prefix="pinned-worker-host-legacy-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(
                cli,
                "ContainerProposalWorker",
                side_effect=AssertionError("no fallback to restricted adapter"),
            ):
                code = cli.main(
                    [str(stage_path), "--worker-backend", "host-process"],
                    input_fn=lambda _prompt: cli.CONFIRMATION_PHRASE,
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: transport,
                    runtime_runner=lambda **kwargs: captured.update(kwargs) or 0,
                    docker_which=lambda _name: "/usr/bin/docker",
                    docker_inspect=lambda _path: None,
                )
        self.assertEqual(code, 0, errors.getvalue())
        self.assertIs(type(captured["proposal_worker"]), DeepSeekProposalWorker)
        self.assertIsInstance(captured["proposal_worker"].channel, DeepSeekHTTPChannel)
        self.assertIn('"worker_backend":"host-process"', output.getvalue())

    def test_restricted_worker_construction_failure_stops_before_prompt_and_readiness(self):
        events = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-construction-fail-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(
                cli,
                "ContainerProposalWorker",
                side_effect=RuntimeError("synthetic docker adapter failure"),
            ):
                code = cli.main(
                    [str(stage_path)],
                    input_fn=lambda _prompt: events.append("prompt") or cli.CONFIRMATION_PHRASE,
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: events.append("readiness"),
                    runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                    docker_which=lambda _name: "/usr/bin/docker",
                    docker_inspect=lambda _path: events.append("images"),
                )
        self.assertEqual(code, 2)
        self.assertEqual(events, ["images"])
        self.assertEqual(
            json.loads(output.getvalue()),
            {"status": "stopped", "reason": "worker-runtime-unavailable", "provider_attempts": 0},
        )
        self.assertNotIn("synthetic docker adapter failure", output.getvalue() + errors.getvalue())

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
            [cli.TARGET_RUNTIME_IMAGE_ID, cli.VERIFIER_RUNTIME_CONFIG_IMAGE_ID],
        )
        self.assertTrue(
            all(
                call[1:4] == [cli.LOCAL_DOCKER_HOST_ARGUMENT, "image", "inspect"]
                for call in calls
            )
        )

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
        self.assertIn("change only /save-session", instruction)
        self.assertIn("Preserve its existing defaults", instruction)
        self.assertIn("delete those five coercions", instruction)
        self.assertIn("raw_level = data.get('level', 1)", instruction)
        self.assertIn("raw_correct = data.get('correct', 0)", instruction)
        self.assertIn("raw_wrong = data.get('wrong', 0)", instruction)
        self.assertIn("raw_total = data.get('total', 10)", instruction)
        self.assertIn("raw_time_ms = data.get('time_ms', 0)", instruction)
        self.assertIn("Add/import HTTPException alongside APIRouter", instruction)
        self.assertIn("Before any database/cursor access", instruction)
        self.assertIn("type(value) is not int", instruction)
        self.assertIn("value < -(2**63) or value > 2**63 - 1", instruction)
        self.assertIn("def strict_sqlite_integer(value):\n", instruction)
        self.assertIn("if type(value) is not int:\n", instruction)
        self.assertIn(
            'raise HTTPException(status_code=422, detail="invalid integer")',
            instruction,
        )
        self.assertIn("return value. Call it separately", instruction)
        self.assertIn("Collect all five validated values before the first database call", instruction)
        self.assertIn("Never coerce with int()", instruction)
        self.assertIn("Use FastAPI HTTPException", instruction)
        self.assertIn("target-test-malformed-status-level-bool", instruction)
        self.assertIn("JSON true for level must return HTTP 422", instruction)
        self.assertIn("Python bool is a subclass of int", instruction)
        self.assertIn("isinstance(value, int) incorrectly accepts booleans", instruction)
        self.assertIn("every boolean, float (including non-finite), string", instruction)
        self.assertIn("returns HTTP 422 and writes zero rows", instruction)
        self.assertIn("valid fixture returns HTTP 200 and exactly one expected row", instruction)
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

    def _assert_local_profile_uses_container_without_constructing_credentials(
        self, authorization_card_id
    ):
        confirmation_phrase = f"RUN {authorization_card_id} ONCE"
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        transport = ValidReadinessTransport(fresh_readiness())
        captured: dict[str, object] = {}
        prompts: list[str] = []
        events: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pinned-worker-local-profile-") as temporary:
            stage_path = Path(temporary) / "stage.sqlite3"
            output, errors = io.StringIO(), io.StringIO()

            def build_worker(channel, *, docker_executable, model_timeout_seconds):
                events.append("container-worker")
                self.assertIsInstance(channel, LocalOllamaChatCompletionsChannel)
                self.assertEqual(model_timeout_seconds, 180)
                captured["channel"] = channel
                captured["docker_executable"] = docker_executable
                return object()

            def run_runtime(**kwargs):
                captured.update(kwargs)
                return 0

            with (
                patch.object(cli, "TerminalPromptCredentialSource", side_effect=AssertionError),
                patch.object(cli, "ProcessEnvironmentCredentialSource", side_effect=AssertionError),
                patch.object(cli, "DeepSeekHTTPChannel", side_effect=AssertionError),
                patch.object(cli, "ContainerProposalWorker", side_effect=build_worker),
            ):
                code = cli.main(
                    [
                        "--authorization-card-id",
                        authorization_card_id,
                        "--model-backend",
                        "local-ollama",
                        "--credential-source",
                        "not-applicable",
                        str(stage_path),
                    ],
                    environ=env,
                    input_fn=lambda prompt: prompts.append(prompt) or confirmation_phrase,
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: events.append("readiness") or transport,
                    runtime_runner=run_runtime,
                    docker_which=lambda _name: "/usr/bin/docker",
                    docker_inspect=lambda _path: events.append("inspect"),
                    native_keyring_source_factory=lambda: self.fail("keyring must not be queried"),
                )

        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(events, ["inspect", "container-worker", "readiness"])
        self.assertEqual(transport.calls, 1)
        self.assertEqual(prompts, [f"Type {confirmation_phrase} to continue: "])
        self.assertEqual(env.lookups, [])
        self.assertEqual(captured["execution_permit"].card_id, authorization_card_id)
        self.assertIsNone(captured["credential_source"])
        instruction = captured["task_instruction"]
        for required_clause in (
            "change only /save-session",
            "delete those five coercions",
            "raw_level = data.get('level', 1)",
            "raw_correct = data.get('correct', 0)",
            "raw_wrong = data.get('wrong', 0)",
            "raw_total = data.get('total', 10)",
            "raw_time_ms = data.get('time_ms', 0)",
            "Add/import HTTPException alongside APIRouter",
            "type(value) is not int",
            "value < -(2**63) or value > 2**63 - 1",
            "Collect all five validated values before the first database call",
            "target-test-malformed-status-level-bool",
            "JSON true for level must return HTTP 422",
            "Python bool is a subclass of int",
            "isinstance(value, int) incorrectly accepts booleans",
            "every boolean, float (including non-finite), string",
            "returns HTTP 422 and writes zero rows",
            "valid fixture returns HTTP 200 and exactly one expected row",
        ):
            self.assertIn(required_clause, instruction)
        self.assertEqual(captured["declared_change_paths"], ("backend/routes.py",))
        payload = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(payload["operation"], "one_local_worker_call")
        self.assertEqual(payload["model_backend"], "local-ollama")
        self.assertEqual(payload["model"], "qwen2.5-coder:7b")
        self.assertEqual(payload["model_timeout_seconds"], 180.0)
        self.assertEqual(payload["endpoint"], "http://127.0.0.1:11434/v1/chat/completions")
        self.assertEqual(payload["credential_input"], "none")
        self.assertEqual(payload["external_model_attempts"], 0)
        self.assertEqual(payload["max_provider_attempts"], 0)
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_local_model_preflight_runs_after_readiness_and_before_runtime(self):
        events = []
        profile = cli.AUTHORIZATION_PROFILES["EXP-851"]
        transport = ValidReadinessTransport(fresh_readiness())

        class SyntheticPreflight:
            def inspect(_self, *, expected_model_digest):
                events.append("model-preflight")
                self.assertEqual(
                    expected_model_digest,
                    cli.LOCAL_OLLAMA_MODEL_DIGEST,
                )
                return SimpleNamespace(
                    version=EXPECTED_OLLAMA_VERSION,
                    model=cli.LOCAL_OLLAMA_MODEL,
                    model_digest=cli.LOCAL_OLLAMA_MODEL_DIGEST,
                )

        output, errors = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory(prefix="local-model-preflight-success-") as root:
            stage = Path(root) / "stage.sqlite3"
            code = cli.main(
                [
                    "--authorization-card-id", "EXP-851",
                    "--model-backend", "local-ollama",
                    "--credential-source", "not-applicable",
                    str(stage),
                ],
                input_fn=lambda _prompt: profile[0],
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness") or transport,
                runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("docker-inspect"),
                local_model_preflight_factory=lambda: SyntheticPreflight(),
            )
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(
            events,
            ["docker-inspect", "readiness", "model-preflight", "runtime"],
        )
        self.assertEqual(transport.calls, 1)
        preflight_payload = json.loads(output.getvalue().splitlines()[1])
        self.assertEqual(preflight_payload["local_model_preflight"], "passed")
        self.assertEqual(preflight_payload["model_digest"], cli.LOCAL_OLLAMA_MODEL_DIGEST)
        self.assertEqual(preflight_payload["ollama_version"], EXPECTED_OLLAMA_VERSION)

    def test_local_model_preflight_mismatch_stops_before_snapshot_runtime(self):
        events = []
        profile = cli.AUTHORIZATION_PROFILES["EXP-851"]
        transport = ValidReadinessTransport(fresh_readiness())

        class MismatchingPreflight:
            def inspect(_self, *, expected_model_digest):
                events.append("model-preflight")
                self.assertEqual(expected_model_digest, cli.LOCAL_OLLAMA_MODEL_DIGEST)
                raise cli.R5LocalModelPreflightError("model_digest_mismatch")

        output, errors = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory(prefix="local-model-preflight-mismatch-") as root:
            stage = Path(root) / "stage.sqlite3"
            code = cli.main(
                [
                    "--authorization-card-id", "EXP-851",
                    "--model-backend", "local-ollama",
                    "--credential-source", "not-applicable",
                    str(stage),
                ],
                input_fn=lambda _prompt: profile[0],
                stdout=output,
                stderr=errors,
                readiness_transport_factory=lambda: events.append("readiness") or transport,
                runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                docker_which=lambda _name: "/usr/bin/docker",
                docker_inspect=lambda _path: events.append("docker-inspect"),
                local_model_preflight_factory=lambda: MismatchingPreflight(),
            )
            self.assertFalse(stage.exists())
        self.assertEqual(code, 2)
        self.assertEqual(
            events,
            ["docker-inspect", "readiness", "model-preflight"],
        )
        self.assertIn('"reason":"local-model-preflight-failed"', errors.getvalue())
        self.assertIn('"snapshot_attempts":0', errors.getvalue())
        self.assertIn('"external_model_attempts":0', errors.getvalue())
        self.assertNotIn("model_digest_mismatch", errors.getvalue())
        self.assertNotIn("dae161e", output.getvalue() + errors.getvalue())

    def test_exp843_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-843"
        )

    def test_exp1238_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1238"
        )

    def test_exp1246_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1246"
        )

    def test_exp1250_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1250"
        )

    def test_exp1253_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1253"
        )

    def test_exp1255_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1255"
        )

    def test_exp1257_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1257"
        )

    def test_exp1266_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1266"
        )

    def test_exp1289_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1289"
        )

    def test_exp1293_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1293"
        )

    def test_exp1299_local_profile_uses_container_without_constructing_credentials(self):
        self._assert_local_profile_uses_container_without_constructing_credentials(
            "EXP-1299"
        )

    def test_exp844_has_distinct_local_profile_and_pinned_snapshot_mapping(self):
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-844"],
            (
                "RUN EXP-844 ONCE",
                "process-exp-844-local-001",
                "task-exp-844-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-844"],
            "github_rest_api_claim",
        )
        self.assertEqual(cli.AUTHORIZATION_MODEL_BACKENDS["EXP-844"], "local-ollama")
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-846"],
            (
                "RUN EXP-846 ONCE",
                "process-exp-846-local-001",
                "task-exp-846-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-846"],
            "github_rest_api_claim",
        )
        self.assertEqual(cli.AUTHORIZATION_MODEL_BACKENDS["EXP-846"], "local-ollama")
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-848"],
            (
                "RUN EXP-848 ONCE",
                "process-exp-848-local-001",
                "task-exp-848-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-848"],
            "github_rest_api_claim",
        )
        self.assertEqual(cli.AUTHORIZATION_MODEL_BACKENDS["EXP-848"], "local-ollama")

        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-849"],
            (
                "RUN EXP-849 ONCE",
                "process-exp-849-local-001",
                "task-exp-849-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-849"],
            "github_rest_api_claim",
        )
        self.assertEqual(cli.AUTHORIZATION_MODEL_BACKENDS["EXP-849"], "local-ollama")
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-851"],
            (
                "RUN EXP-851 ONCE",
                "process-exp-851-local-001",
                "task-exp-851-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-851"],
            "github_rest_api_claim",
        )
        self.assertEqual(cli.AUTHORIZATION_MODEL_BACKENDS["EXP-851"], "local-ollama")
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-964"],
            (
                "RUN EXP-964 ONCE",
                "process-exp-964-local-001",
                "task-exp-964-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-964"],
            "github_rest_api_claim",
        )
        self.assertEqual(cli.AUTHORIZATION_MODEL_BACKENDS["EXP-964"], "local-ollama")
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1200"],
            (
                "RUN EXP-1200 ONCE",
                "process-exp-1200-local-001",
                "task-exp-1200-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1200"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1200"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1209"],
            (
                "RUN EXP-1209 ONCE",
                "process-exp-1209-local-001",
                "task-exp-1209-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1209"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1209"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1218"],
            (
                "RUN EXP-1218 ONCE",
                "process-exp-1218-local-001",
                "task-exp-1218-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1218"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1218"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1230"],
            (
                "RUN EXP-1230 ONCE",
                "process-exp-1230-local-001",
                "task-exp-1230-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1230"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1230"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1233"],
            (
                "RUN EXP-1233 ONCE",
                "process-exp-1233-local-001",
                "task-exp-1233-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1233"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1233"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1238"],
            (
                "RUN EXP-1238 ONCE",
                "process-exp-1238-local-001",
                "task-exp-1238-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1238"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1238"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1246"],
            (
                "RUN EXP-1246 ONCE",
                "process-exp-1246-local-001",
                "task-exp-1246-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1246"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1246"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1250"],
            (
                "RUN EXP-1250 ONCE",
                "process-exp-1250-local-001",
                "task-exp-1250-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1250"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1250"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1253"],
            (
                "RUN EXP-1253 ONCE",
                "process-exp-1253-local-001",
                "task-exp-1253-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1253"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1253"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1255"],
            (
                "RUN EXP-1255 ONCE",
                "process-exp-1255-local-001",
                "task-exp-1255-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1255"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1255"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1257"],
            (
                "RUN EXP-1257 ONCE",
                "process-exp-1257-local-001",
                "task-exp-1257-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1257"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1257"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1266"],
            (
                "RUN EXP-1266 ONCE",
                "process-exp-1266-local-001",
                "task-exp-1266-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1266"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1266"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1268"],
            (
                "RUN EXP-1268 ONCE",
                "process-exp-1268-local-001",
                "task-exp-1268-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1268"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1268"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1289"],
            (
                "RUN EXP-1289 ONCE",
                "process-exp-1289-local-001",
                "task-exp-1289-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1289"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1289"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1293"],
            (
                "RUN EXP-1293 ONCE",
                "process-exp-1293-local-001",
                "task-exp-1293-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1293"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1293"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1299"],
            (
                "RUN EXP-1299 ONCE",
                "process-exp-1299-local-001",
                "task-exp-1299-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1299"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1299"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1303"],
            (
                "RUN EXP-1303 ONCE",
                "process-exp-1303-local-001",
                "task-exp-1303-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1303"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1303"], "local-ollama"
        )
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1310"],
            (
                "RUN EXP-1310 ONCE",
                "process-exp-1310-local-001",
                "task-exp-1310-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1310"],
            "github_rest_api_claim",
        )
        self.assertEqual(cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1310"], "local-ollama")
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1312"],
            (
                "RUN EXP-1312 ONCE",
                "process-exp-1312-local-001",
                "task-exp-1312-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1312"],
            "github_rest_api_claim",
        )
        self.assertEqual(cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1312"], "local-ollama")
        self.assertNotIn("EXP-1354", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-1354", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-1354", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-1425", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-1425", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-1425", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-1438", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-1438", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-1438", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-1434", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-1434", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-1434", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-1428", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-1428", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-1428", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-990", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-990", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-990", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-988", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-988", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-988", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-986", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-986", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-986", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-984", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-984", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-984", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-985", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-985", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-985", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-960", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-960", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-960", cli.AUTHORIZATION_MODEL_BACKENDS)

    def test_exp1585_profile_is_exact_local_ollama_one_shot(self):
        self.assertEqual(
            cli.AUTHORIZATION_PROFILES["EXP-1585"],
            (
                "RUN EXP-1585 ONCE",
                "process-exp-1585-local-001",
                "task-exp-1585-local-001",
            ),
        )
        self.assertEqual(
            cli.AUTHORIZATION_SNAPSHOT_ORIGINS["EXP-1585"],
            "github_rest_api_claim",
        )
        self.assertEqual(
            cli.AUTHORIZATION_MODEL_BACKENDS["EXP-1585"], "local-ollama"
        )
        self.assertNotIn("EXP-1601", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-1601", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-1601", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertNotIn("EXP-1448", cli.AUTHORIZATION_PROFILES)
        self.assertNotIn("EXP-1448", cli.AUTHORIZATION_SNAPSHOT_ORIGINS)
        self.assertNotIn("EXP-1448", cli.AUTHORIZATION_MODEL_BACKENDS)
        self.assertEqual(
            set(cli.AUTHORIZATION_PROFILES),
            set(cli.AUTHORIZATION_SNAPSHOT_ORIGINS),
        )
        self.assertEqual(
            set(cli.AUTHORIZATION_PROFILES),
            set(cli.AUTHORIZATION_MODEL_BACKENDS),
        )

    def test_model_backend_card_mismatches_stop_before_all_side_effects(self):
        cases = (
            ["--authorization-card-id", "EXP-842"],
            ["--authorization-card-id", "EXP-843"],
            [
                "--authorization-card-id",
                "EXP-844",
                "--model-backend",
                "deepseek",
            ],
            [
                "--authorization-card-id",
                "EXP-846",
                "--model-backend",
                "deepseek",
            ],
            ["--authorization-card-id", "EXP-634", "--model-backend", "local-ollama"],
            [
                "--authorization-card-id",
                "EXP-842",
                "--model-backend",
                "local-ollama",
                "--worker-backend",
                "host-process",
            ],
            [
                "--authorization-card-id",
                "EXP-842",
                "--model-backend",
                "local-ollama",
                "--credential-source",
                "native-keyring",
            ],
            [
                "--authorization-card-id",
                "EXP-1230",
                "--model-backend",
                "local-ollama",
                "--credential-source",
                "hidden-terminal",
            ],
            [
                "--authorization-card-id",
                "EXP-634",
                "--credential-source",
                "not-applicable",
            ],
        )
        for options in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary:
                events: list[str] = []
                env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
                output, errors = io.StringIO(), io.StringIO()
                stage_path = Path(temporary) / "stage.sqlite3"
                code = cli.main(
                    [*options, str(stage_path)],
                    environ=env,
                    input_fn=lambda _prompt: events.append("prompt") or "RUN EXP-842 ONCE",
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: events.append("readiness"),
                    runtime_runner=lambda **_kwargs: events.append("runtime") or 0,
                    docker_which=lambda _name: events.append("docker-which"),
                    docker_inspect=lambda _path: events.append("docker-inspect"),
                    native_keyring_source_factory=lambda: events.append("keyring"),
                )
                self.assertEqual(code, 2)
                self.assertEqual(events, [])
                self.assertEqual(env.lookups, [])
                self.assertFalse(stage_path.exists())
                self.assertIn('"external_model_attempts":0', output.getvalue())

    def test_spent_exp1354_profile_is_rejected_during_argument_parsing(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--authorization-card-id", "EXP-1354"])
        self.assertEqual(raised.exception.code, 2)

    def test_local_credential_status_check_is_not_applicable_without_lookup(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        output, errors = io.StringIO(), io.StringIO()
        code = cli.main(
            [
                "--authorization-card-id",
                "EXP-1230",
                "--model-backend",
                "local-ollama",
                "--credential-source",
                "not-applicable",
                "--check-credential-source",
            ],
            environ=env,
            stdout=output,
            stderr=errors,
        )
        self.assertEqual(code, 2)
        self.assertEqual(env.lookups, [])
        self.assertIn('"credential_source":"not-applicable"', output.getvalue())
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())

    def test_spent_exp984_exp985_exp986_exp988_and_exp990_profiles_are_rejected_before_preflight(self):
        env = RecordingEnvironment({"AI_PROCESS_API": SECRET})
        for card_id in ("EXP-984", "EXP-985", "EXP-986", "EXP-988", "EXP-990"):
            with self.subTest(card_id=card_id), tempfile.TemporaryDirectory(
                prefix="pinned-worker-unknown-card-"
            ) as temporary:
                events: list[str] = []
                stage_path = Path(temporary) / "stage.sqlite3"
                output, errors = io.StringIO(), io.StringIO()
                with patch("sys.stderr", errors):
                    with self.assertRaises(SystemExit) as raised:
                        cli.main(
                            ["--authorization-card-id", card_id, str(stage_path)],
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
            self.assertIn("github-readiness-ineligible", errors.getvalue())
            self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())
            with SQLiteObservationStore(observer_path) as reopened:
                events = reopened.events()
        self.assertEqual([event["sequence"] for event in events], list(range(6)))
        self.assertEqual(events[-2]["decision_or_tool"], "RemoteExecutionPermit.issue")
        self.assertEqual(events[-2]["status"], "denied")
        self.assertEqual(events[-2]["error_code"], "readiness-ineligible")
        self.assertEqual(events[-1]["event_type"], "agent_finished")
        self.assertEqual(events[-1]["status"], "failed")
        self.assertEqual(events[-1]["invocation_id"], events[0]["invocation_id"])

    def test_observer_enabled_local_worker_binds_model_channel_to_same_run(self):
        transport = ValidReadinessTransport(fresh_readiness())
        captured = {}
        profile = cli.AUTHORIZATION_PROFILES["EXP-851"]
        with tempfile.TemporaryDirectory(prefix="pinned-worker-observed-model-") as root:
            stage = Path(root) / "stage.sqlite3"
            observer = Path(root) / "observer.sqlite3"
            output, errors = io.StringIO(), io.StringIO()

            def build_worker(channel, *, docker_executable, model_timeout_seconds):
                self.assertIsInstance(channel, JournaledModelChannel)
                self.assertIsInstance(channel._channel, LocalOllamaChatCompletionsChannel)
                self.assertEqual(docker_executable, "/usr/bin/docker")
                self.assertEqual(model_timeout_seconds, 180)
                captured["channel"] = channel
                return SimpleNamespace(propose=lambda _request: None)

            def runtime(**kwargs):
                execution_worker = kwargs["execution_worker"]
                self.assertIs(captured["channel"]._run, execution_worker)
                captured.update(kwargs)
                return 0

            with patch.object(cli, "ContainerProposalWorker", side_effect=build_worker):
                code = cli.main(
                    [
                        "--authorization-card-id", "EXP-851",
                        "--model-backend", "local-ollama",
                        "--credential-source", "not-applicable",
                        "--observation-database", str(observer),
                        str(stage),
                    ],
                    input_fn=lambda _prompt: profile[0],
                    stdout=output,
                    stderr=errors,
                    readiness_transport_factory=lambda: transport,
                    runtime_runner=runtime,
                    docker_which=lambda _name: "/usr/bin/docker",
                    docker_inspect=lambda _path: None,
                )

            self.assertEqual(code, 0, errors.getvalue())
            self.assertEqual(transport.calls, 1)
            self.assertIsInstance(captured["execution_worker"], JournaledProposalWorker)
            with SQLiteObservationStore(observer) as reopened:
                events = reopened.events()
            self.assertEqual(
                [event["sequence"] for event in events], list(range(len(events)))
            )
            preflight_events = [
                event
                for event in events
                if event.get("decision_or_tool")
                == "LocalOllamaMetadataPreflight.inspect"
            ]
            self.assertEqual(
                [event["event_type"] for event in preflight_events],
                ["tool_requested", "tool_completed"],
            )
            self.assertEqual(
                [event["status"] for event in preflight_events], ["pending", "ok"]
            )
            self.assertEqual(
                preflight_events[1]["causal_event_ids"],
                [preflight_events[0]["event_id"]],
            )
            self.assertNotIn(cli.LOCAL_OLLAMA_MODEL_DIGEST, repr(events))

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
