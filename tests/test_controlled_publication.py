from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unittest.mock import patch

from app_contracts.authority import DeterministicPolicy, PolicyConfig
from app_contracts.broker import InMemoryCredentialBroker
from app_contracts.controlled_publication import (
    ControlledPublicationError,
    run_approval_gate,
    run_broker_gate,
    run_controlled_local_publication,
    run_gateway_gate,
    run_policy_gate,
)
import app_contracts.controlled_publication as gate_module
from app_contracts.digests import sha256_digest
from app_contracts.gateway import GatewayDecision, GatewayPath
from app_contracts.executor import (
    ExecutionError,
    ExecutionRequest,
    ExecutionStatus,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    WorkerInput,
    WorkerProposal,
    run_local_execution,
)
from app_contracts.pinned_snapshot import (
    PinnedSnapshot,
    compute_snapshot_tree_digest,
    export_local_commit_tree,
    open_local_repository,
)
from app_contracts.publication_seed import (
    PublicationIntent,
    PublicationSeed,
    PublicationSeedError,
    build_publication_seed,
    derive_publication_intent,
)
from app_contracts.mock_github import MockGitHubEndpoint
from app_contracts.publication import PublicationJournal, PublicationRecord
from app_contracts.repository_process import prepare_change as real_prepare_change
from app_contracts.validator import ContractValidationError


FIXED_NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


def format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class AcceptingVerifier:
    def verify(self, prepared: VerifierInput) -> VerifierResult:
        return VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id="test-verifier",
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=VerifierVerdict.PASS,
        )


class SeedWorker:
    def propose(self, task: WorkerInput) -> WorkerProposal:
        original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
        return WorkerProposal((("calculator.py", original + "\n# gate-bound change\n"),))


@contextmanager
def seed_bound_intent(branch="agent/process-demo-001", process_id="process-local-001"):
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        repository = root / "source-repository"
        shutil.copytree(ROOT / "fixtures/repository/project", repository)
        subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "add", "-A"], check=True)
        subprocess.run(
            [
                "git", "-C", str(repository), "-c", "user.name=Gate Test",
                "-c", "user.email=gate@example.invalid", "commit", "--quiet", "-m",
                "fixture snapshot",
            ],
            check=True,
        )
        commit_oid = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        lease = export_local_commit_tree(
            open_local_repository(repository), commit_oid, root
        )
        try:
            pin = PinnedSnapshot(
                repository_id="fixture-repository",
                commit_oid=commit_oid,
                tree_digest=compute_snapshot_tree_digest(lease.path),
                snapshot_path=lease.path,
            )
            request = ExecutionRequest(
                process_id=process_id,
                task_id="task-local-001",
                repository_id=pin.repository_id,
                base_commit=pin.commit_oid,
                snapshot_path=lease.path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-c", "print('ok')"),
                pinned_snapshot=pin,
            )
            result = run_local_execution(
                request, SeedWorker(), verifier=AcceptingVerifier(),
                require_pinned_snapshot=True,
            )
            assert result.status == ExecutionStatus.VERIFIED, repr(result)
            seed = build_publication_seed(request, result)
            yield derive_publication_intent(seed, branch)
        finally:
            lease.close()


def matching_approval(intent: PublicationIntent, *, expires_at: str) -> dict:
    return {
        "approval_id": "approval-local-001",
        "approved_intent_digest": sha256_digest(asdict(intent)),
        "expires_at": expires_at,
    }


def fresh_approval(intent: PublicationIntent) -> dict:
    return matching_approval(intent, expires_at=format_time(FIXED_NOW + timedelta(hours=1)))


class DownstreamPath:
    """Ordered policy/gateway/broker/provider doubles behind one proceed seam."""

    STAGES = ("policy", "gateway", "broker", "provider")

    def __init__(self):
        self.calls = {stage: 0 for stage in self.STAGES}

    def proceed(self, intent: PublicationIntent):
        for stage in self.STAGES:
            self.calls[stage] += 1
        return ("completed-path", intent)

    def assert_untouched(self, test: unittest.TestCase):
        for stage in self.STAGES:
            test.assertEqual(self.calls[stage], 0, stage)


class ApprovalGateTests(unittest.TestCase):
    def test_matching_fresh_approval_reaches_downstream_exactly_once(self):
        with seed_bound_intent() as intent:
            downstream = DownstreamPath()
            marker, passed = run_approval_gate(
                intent, fresh_approval(intent), now=FIXED_NOW, proceed=downstream.proceed
            )
            self.assertEqual(marker, "completed-path")
            self.assertIs(passed, intent)
            for stage in DownstreamPath.STAGES:
                self.assertEqual(downstream.calls[stage], 1, stage)

    def test_missing_approval_stops_before_downstream(self):
        with seed_bound_intent() as intent:
            for approval in (None, "not-a-dict", 42, []):
                with self.subTest(approval=repr(approval)):
                    downstream = DownstreamPath()
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: approval is missing$",
                    ):
                        run_approval_gate(
                            intent, approval, now=FIXED_NOW, proceed=downstream.proceed
                        )
                    downstream.assert_untouched(self)

    def test_expired_approval_stops_before_downstream(self):
        with seed_bound_intent() as intent:
            for expires_at in (
                format_time(FIXED_NOW - timedelta(seconds=1)),
                format_time(FIXED_NOW),
            ):
                with self.subTest(expires_at=expires_at):
                    downstream = DownstreamPath()
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: approval expired$",
                    ):
                        run_approval_gate(
                            intent,
                            matching_approval(intent, expires_at=expires_at),
                            now=FIXED_NOW,
                            proceed=downstream.proceed,
                        )
                    downstream.assert_untouched(self)

    def test_mismatched_approval_stops_before_downstream(self):
        with seed_bound_intent() as intent:
            with seed_bound_intent(branch="agent/process-other-001") as other_intent:
                foreign = matching_approval(other_intent, expires_at=format_time(FIXED_NOW + timedelta(hours=1)))
                downstream = DownstreamPath()
                with self.assertRaisesRegex(
                    ContractValidationError,
                    "^approval: approved intent digest mismatch$",
                ):
                    run_approval_gate(
                        intent, foreign, now=FIXED_NOW, proceed=downstream.proceed
                    )
                downstream.assert_untouched(self)

    def test_approval_without_intent_digest_stops_before_downstream(self):
        with seed_bound_intent() as intent:
            approval = {
                "approval_id": "approval-local-001",
                "expires_at": format_time(FIXED_NOW + timedelta(hours=1)),
            }
            downstream = DownstreamPath()
            with self.assertRaisesRegex(
                ContractValidationError,
                "^approval: approved intent digest is invalid$",
            ):
                run_approval_gate(intent, approval, now=FIXED_NOW, proceed=downstream.proceed)
            downstream.assert_untouched(self)

    def test_malformed_expiry_and_clock_stop_before_downstream(self):
        with seed_bound_intent() as intent:
            for expires_at in (None, 42, "", "not-a-time", "2026-09-29T12:00:00"):
                with self.subTest(expires_at=repr(expires_at)):
                    approval = dict(fresh_approval(intent), expires_at=expires_at)
                    downstream = DownstreamPath()
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: approval expiry is invalid$",
                    ):
                        run_approval_gate(
                            intent, approval, now=FIXED_NOW, proceed=downstream.proceed
                        )
                    downstream.assert_untouched(self)
            for now in (None, "now", 42, datetime(2026, 9, 29, 12, 0, 0)):
                with self.subTest(now=repr(now)):
                    downstream = DownstreamPath()
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: clock is invalid$",
                    ):
                        run_approval_gate(
                            intent, fresh_approval(intent), now=now, proceed=downstream.proceed
                        )
                    downstream.assert_untouched(self)

    def test_invalid_wiring_is_rejected_without_side_effects(self):
        with seed_bound_intent() as intent:
            downstream = DownstreamPath()
            for proceed in (None, "proceed"):
                with self.subTest(proceed=repr(proceed)):
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: downstream step is invalid$",
                    ):
                        run_approval_gate(
                            intent, fresh_approval(intent), now=FIXED_NOW, proceed=proceed
                        )
            downstream.assert_untouched(self)
            for bad_intent in (None, {"process_id": "process-local-001"}):
                with self.subTest(intent=repr(bad_intent)):
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: intent is invalid$",
                    ):
                        run_approval_gate(
                            bad_intent, fresh_approval(intent),
                            now=FIXED_NOW, proceed=downstream.proceed,
                        )
            downstream.assert_untouched(self)

    def test_approval_values_never_reach_errors_or_evidence(self):
        canary = "APPROVAL-CANARY-SECRET"
        with seed_bound_intent() as intent:
            foreign_approval = {
                "approval_id": canary,
                "approved_intent_digest": "sha256:" + "e" * 64,
                "expires_at": format_time(FIXED_NOW + timedelta(hours=1)),
                "note": canary,
            }
            downstream = DownstreamPath()
            with self.assertRaisesRegex(
                ContractValidationError,
                "^approval: approved intent digest mismatch$",
            ) as raised:
                run_approval_gate(
                    intent, foreign_approval, now=FIXED_NOW, proceed=downstream.proceed
                )
            self.assertNotIn(canary, str(raised.exception))
            downstream.assert_untouched(self)
            expired = dict(
                fresh_approval(intent), approval_id=canary,
                expires_at=format_time(FIXED_NOW - timedelta(hours=1)),
            )
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: approval expired$",
            ) as raised:
                run_approval_gate(intent, expired, now=FIXED_NOW, proceed=downstream.proceed)
            self.assertNotIn(canary, str(raised.exception))
            downstream.assert_untouched(self)
            _marker, passed = run_approval_gate(
                intent, fresh_approval(intent), now=FIXED_NOW, proceed=downstream.proceed
            )
            self.assertNotIn(canary, json.dumps(asdict(passed)))

    def test_gate_creates_no_approval_and_uses_no_hidden_clock(self):
        source = Path(gate_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = set()
        from_modules = set()
        gateway_type_names = set()
        called_names = set()
        defined_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                from_modules.add((node.module or "").lower())
                imported_modules.add((node.module or "").lower())
                imported_modules.update(alias.name.lower() for alias in node.names)
                if (node.module or "").lower() == "gateway":
                    gateway_type_names.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id.lower())
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr.lower())
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_names.add(node.name.lower())
        self.assertFalse(any("github_app" in module for module in imported_modules))
        approval_gate = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run_approval_gate"
        )
        approval_gate_calls = {
            node.func.id.lower() if isinstance(node.func, ast.Name)
            else node.func.attr.lower() if isinstance(node.func, ast.Attribute)
            else ""
            for node in ast.walk(approval_gate)
            if isinstance(node, ast.Call)
        }
        self.assertTrue(
            {"run_broker_gate", "execute_publication", "publish_pull_request",
             "open_github_publication_channel"}.isdisjoint(approval_gate_calls)
        )
        if "gateway" in from_modules:
            self.assertEqual(gateway_type_names, {"gatewaydecision", "gatewaypath"})
        for module in from_modules:
            if "publication" in module:
                self.assertIn(
                    module, {"publication_seed", "controlled_publication", "publication"}
                )
        self.assertTrue({"now", "utcnow", "monotonic", "monotonic_ns"}.isdisjoint(called_names))
        self.assertTrue(
            not any(
                keyword in name
                for name in defined_names
                for keyword in ("mint", "issue", "create_approval", "recover", "refresh")
            )
        )
        self.assertTrue(
            {"publish_pull_request", "publish_verified_files", "create_pull_request"}.isdisjoint(
                called_names
            )
        )


@contextmanager
def decided_gate_fixture(*, include_seed=False, include_details=False):
    captured = {}
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        repository = root / "source-repository"
        shutil.copytree(ROOT / "fixtures/repository/project", repository)
        subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "add", "-A"], check=True)
        subprocess.run(
            [
                "git", "-C", str(repository), "-c", "user.name=Policy Test",
                "-c", "user.email=policy@example.invalid", "commit", "--quiet", "-m",
                "fixture snapshot",
            ],
            check=True,
        )
        commit_oid = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        lease = export_local_commit_tree(open_local_repository(repository), commit_oid, root)
        try:
            pin = PinnedSnapshot(
                repository_id="fixture-repository",
                commit_oid=commit_oid,
                tree_digest=compute_snapshot_tree_digest(lease.path),
                snapshot_path=lease.path,
            )
            request = ExecutionRequest(
                process_id="process-local-001",
                task_id="task-local-001",
                repository_id=pin.repository_id,
                base_commit=pin.commit_oid,
                snapshot_path=lease.path,
                allowed_commands=frozenset({"python3"}),
                declared_change_paths=("calculator.py",),
                test_command=("python3", "-c", "print('ok')"),
                pinned_snapshot=pin,
            )

            def capturing_prepare(sandbox, **kwargs):
                prepared = real_prepare_change(sandbox, **kwargs)
                captured["staged_change"] = dict(prepared.staged_change)
                return prepared

            with patch("app_contracts.executor.prepare_change", side_effect=capturing_prepare):
                result = run_local_execution(
                    request, SeedWorker(), verifier=AcceptingVerifier(),
                    require_pinned_snapshot=True,
                )
            assert result.status == ExecutionStatus.VERIFIED, repr(result)
            seed = build_publication_seed(request, result)
            intent = derive_publication_intent(seed, "agent/process-demo-001")
            staged_change = captured["staged_change"]
            config = PolicyConfig(
                version="policy-test-v1",
                allowed_repositories=frozenset({"fixture-repository"}),
                allowed_actuators=frozenset({"test-actuator"}),
                decision_ttl_seconds=300,
            )
            future = format_time(FIXED_NOW + timedelta(hours=1))
            engine_intent = {
                "process_id": intent.process_id,
                "repository_id": intent.repository_id,
                "base_commit": intent.base_commit,
                "operation": "publish_pull_request",
                "approval_id": "approval-local-001",
                "expires_at": future,
                "branch_namespace": "agent",
                "idempotency_key": intent.idempotency_key,
                "staged_change_digest": intent.staged_change_digest,
            }
            approval = {
                "process_id": intent.process_id,
                "repository_id": intent.repository_id,
                "operation": "publish_pull_request",
                "approval_id": "approval-local-001",
                "policy_version": config.version,
                "expires_at": future,
                "staged_change_digest": intent.staged_change_digest,
                "approved_intent_digest": sha256_digest(engine_intent),
            }
            policy = DeterministicPolicy(config)
            evaluated = policy.decide(
                decision_id="decision-local-001",
                actuator_request={
                    "operation": "publish_pull_request",
                    "repository_id": intent.repository_id,
                    "actuator_id": "test-actuator",
                    "staged_change_digest": intent.staged_change_digest,
                    "branch_namespace": "agent",
                    "idempotency_key": intent.idempotency_key,
                },
                approval=approval,
                staged_change=staged_change,
                intent=engine_intent,
                now=FIXED_NOW,
            )
            assert evaluated["effect"] == "allow", repr(evaluated)
            fixture = intent, approval, policy, engine_intent, staged_change, evaluated
            if include_details:
                yield (*fixture, seed, request, result)
            elif include_seed:
                yield (*fixture, seed)
            else:
                yield fixture
        finally:
            lease.close()


class PolicyDownstream(DownstreamPath):
    def proceed(self, intent, approval, decision):
        for stage in self.STAGES:
            self.calls[stage] += 1
        return ("completed-path", intent, approval, decision)


def invoke_policy_gate(intent, approval, policy, engine_intent, staged_change, downstream,
                       *, now=FIXED_NOW, actuator_id="test-actuator",
                       decision_id="decision-local-001"):
    return run_policy_gate(
        intent, approval, policy, engine_intent, staged_change,
        decision_id=decision_id, actuator_id=actuator_id, now=now,
        proceed=downstream.proceed,
    )


class PolicyGateTests(unittest.TestCase):
    def test_policy_engine_evaluates_matching_approval_before_downstream_once(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, expected):
            downstream = PolicyDownstream()
            marker, passed_intent, passed_approval, decision = invoke_policy_gate(
                intent, approval, policy, engine_intent, staged_change, downstream
            )
            self.assertEqual(marker, "completed-path")
            self.assertIs(passed_intent, intent)
            self.assertIs(passed_approval, approval)
            self.assertEqual(decision["effect"], "allow")
            self.assertEqual(decision["operation"], expected["operation"])
            self.assertEqual(decision["repository_id"], intent.repository_id)
            self.assertEqual(decision["staged_change_digest"], intent.staged_change_digest)
            for stage in PolicyDownstream.STAGES:
                self.assertEqual(downstream.calls[stage], 1, stage)

    def test_precomputed_allow_cannot_be_used_as_policy_engine(self):
        with decided_gate_fixture() as (intent, approval, _policy, engine_intent,
                                        staged_change, cached_allow):
            downstream = PolicyDownstream()
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: policy engine is invalid$",
            ):
                invoke_policy_gate(
                    intent, approval, cached_allow, engine_intent, staged_change, downstream
                )
            downstream.assert_untouched(self)

    def test_policy_deny_stops_before_downstream(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _expected):
            downstream = PolicyDownstream()
            with self.assertRaisesRegex(ContractValidationError, "^decision: not allow$"):
                invoke_policy_gate(
                    intent, approval, policy, engine_intent, staged_change, downstream,
                    actuator_id="actuator-not-allowlisted",
                )
            downstream.assert_untouched(self)

    def test_stale_or_malformed_engine_result_stops_before_downstream(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, decision):
            cases = [
                (dict(decision, expires_at=format_time(FIXED_NOW - timedelta(seconds=1))),
                 "^decision: expired$"),
                (dict(decision, expires_at=format_time(FIXED_NOW)),
                 "^decision: expired$"),
                ({key: value for key, value in decision.items() if key != "expires_at"},
                 "^decision: expiry is invalid$"),
            ]
            for result, message in cases:
                with self.subTest(message=message):
                    downstream = PolicyDownstream()
                    with patch.object(policy, "decide", return_value=result):
                        with self.assertRaisesRegex(ContractValidationError, message):
                            invoke_policy_gate(
                                intent, approval, policy, engine_intent, staged_change, downstream
                            )
                    downstream.assert_untouched(self)

    def test_mismatched_engine_result_stops_before_downstream(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, decision):
            cases = [
                (dict(decision, operation="merge_pull_request"),
                 "^controlled publication: decision operation mismatch$"),
                (dict(decision, repository_id="repository-foreign"),
                 "^controlled publication: decision repository mismatch$"),
                (dict(decision, staged_change_digest="sha256:" + "f" * 64),
                 "^controlled publication: decision digest mismatch$"),
                (dict(decision, policy_version="policy-foreign"),
                 "^controlled publication: decision policy version mismatch$"),
            ]
            for result, message in cases:
                with self.subTest(message=message):
                    downstream = PolicyDownstream()
                    with patch.object(policy, "decide", return_value=result):
                        with self.assertRaisesRegex(ControlledPublicationError, message):
                            invoke_policy_gate(
                                intent, approval, policy, engine_intent, staged_change, downstream
                            )
                    downstream.assert_untouched(self)

    def test_invalid_policy_engine_and_gate_inputs_stop_before_downstream(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, cached_allow):
            downstream = PolicyDownstream()
            invalid_inputs = [
                (None, approval, policy, engine_intent, staged_change, "decision-local-001",
                 "test-actuator", "^controlled publication: intent is invalid$"),
                (intent, None, policy, engine_intent, staged_change, "decision-local-001",
                 "test-actuator", "^controlled publication: approval is missing$"),
                (intent, approval, cached_allow, engine_intent, staged_change, "decision-local-001",
                 "test-actuator", "^controlled publication: policy engine is invalid$"),
                (intent, approval, policy, None, staged_change, "decision-local-001",
                 "test-actuator", "^controlled publication: engine intent is missing$"),
                (intent, approval, policy, engine_intent, [], "decision-local-001",
                 "test-actuator", "^controlled publication: staged change is invalid$"),
                (intent, approval, policy, engine_intent, staged_change, "",
                 "test-actuator", "^controlled publication: decision id is invalid$"),
                (intent, approval, policy, engine_intent, staged_change, "decision-local-001",
                 "", "^controlled publication: actuator id is invalid$"),
            ]
            for (given_intent, given_approval, given_policy, given_engine, staged,
                 decision_id, actuator_id, message) in invalid_inputs:
                with self.subTest(message=message):
                    with self.assertRaisesRegex(ControlledPublicationError, message):
                        run_policy_gate(
                            given_intent, given_approval, given_policy, given_engine, staged,
                            decision_id=decision_id, actuator_id=actuator_id, now=FIXED_NOW,
                            proceed=downstream.proceed,
                        )
            with self.assertRaisesRegex(ControlledPublicationError,
                                        "^controlled publication: clock is invalid$"):
                invoke_policy_gate(
                    intent, approval, policy, engine_intent, staged_change, downstream,
                    now=datetime(2026, 9, 29, 12, 0, 0),
                )
            downstream.assert_untouched(self)

    def test_staged_change_and_engine_intent_are_bound_before_policy_call(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _decision):
            with patch.object(policy, "decide", wraps=policy.decide) as decide:
                downstream = PolicyDownstream()
                with self.assertRaisesRegex(
                    ControlledPublicationError,
                    "^controlled publication: staged change digest mismatch$",
                ):
                    invoke_policy_gate(
                        intent, approval, policy, engine_intent,
                        {"different": "staged data"}, downstream,
                    )
                decide.assert_not_called()
                for field, value in (
                    ("idempotency_key", "foreign-key"),
                    ("base_commit", "foreign-commit"),
                ):
                    foreign = dict(engine_intent, **{field: value})
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: engine intent binding mismatch$",
                    ):
                        invoke_policy_gate(
                            intent, approval, policy, foreign, staged_change, downstream,
                        )
                    decide.assert_not_called()
            downstream.assert_untouched(self)

    def test_expired_or_mismatched_approval_stops_before_policy_and_downstream(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _decision):
            cases = [
                (dict(approval, expires_at=format_time(FIXED_NOW)), "approval expired"),
                (dict(approval, expires_at=format_time(FIXED_NOW - timedelta(seconds=1))),
                 "approval expired"),
                (dict(approval, approved_intent_digest="sha256:" + "f" * 64),
                 "approval binding is invalid"),
            ]
            with patch.object(policy, "decide", wraps=policy.decide) as decide:
                for bad_approval, message in cases:
                    downstream = PolicyDownstream()
                    with self.subTest(message=message):
                        with self.assertRaisesRegex(
                            ControlledPublicationError,
                            f"^controlled publication: {message}$",
                        ):
                            invoke_policy_gate(
                                intent, bad_approval, policy, engine_intent,
                                staged_change, downstream,
                            )
                        downstream.assert_untouched(self)
                decide.assert_not_called()
            downstream = PolicyDownstream()
            with self.assertRaisesRegex(ContractValidationError, "^decision: not allow$"):
                invoke_policy_gate(
                    intent, dict(approval, approval_id="approval-foreign"), policy,
                    engine_intent, staged_change, downstream,
                )
            downstream.assert_untouched(self)

    def test_substituted_approval_and_old_allow_are_not_accepted(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, old_allow):
            forged_engine = dict(engine_intent, approval_id="approval-substituted")
            forged_approval = dict(
                approval, approval_id="approval-substituted",
                approved_intent_digest=sha256_digest(forged_engine),
            )
            downstream = PolicyDownstream()
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: policy engine is invalid$",
            ):
                invoke_policy_gate(
                    intent, forged_approval, old_allow, forged_engine,
                    staged_change, downstream,
                )
            downstream.assert_untouched(self)

    def test_error_messages_do_not_expose_approval_or_decision_values(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, decision):
            canary = "APPROVAL-DECISION-CANARY"
            forged = dict(approval, approval_id=canary,
                          approved_intent_digest="sha256:" + "f" * 64)
            downstream = PolicyDownstream()
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: approval binding is invalid$",
            ) as raised:
                invoke_policy_gate(
                    intent, forged, policy, engine_intent, staged_change, downstream
                )
            self.assertNotIn(canary, str(raised.exception))
            downstream.assert_untouched(self)
            foreign_result = dict(decision, repository_id=canary)
            with patch.object(policy, "decide", return_value=foreign_result):
                with self.assertRaisesRegex(
                    ControlledPublicationError,
                    "^controlled publication: decision repository mismatch$",
                ) as raised:
                    invoke_policy_gate(
                        intent, approval, policy, engine_intent, staged_change, downstream
                    )
            self.assertNotIn(canary, str(raised.exception))
            downstream.assert_untouched(self)


def gateway_envelope(intent: PublicationIntent) -> dict:
    return {
        "intent": {"operation": "publish_pull_request"},
        "destination": {"port": "approval", "repository_id": intent.repository_id},
        "source": {"protocol": "internal", "principal_id": intent.process_id},
        "security": {"tainted": False, "sensitivity": "internal"},
        "payload": {"content_digest": intent.staged_change_digest},
        "correlation_id": intent.idempotency_key,
    }


class FakeGateway:
    _DEFAULT = object()

    def __init__(self, events, verdict=_DEFAULT, error=None):
        self.events = events
        self.calls = []
        if verdict is FakeGateway._DEFAULT:
            verdict = GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))
        self.verdict = verdict
        self.error = error

    def __call__(self, envelope, *, now):
        self.events.append("gateway.call")
        self.calls.append((envelope, now))
        if self.error is not None:
            raise self.error
        return self.verdict


class GatewayDownstream:
    STAGES = ("broker",)

    def __init__(self, events):
        self.events = events
        self.calls = 0
        self.received = None

    def proceed(self, intent, approval, decision, gateway_decision):
        self.events.append("broker.call")
        self.calls += 1
        self.received = (intent, approval, decision, gateway_decision)
        return ("broker-reached", intent)


class PolicyProceedAdapter:
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def proceed(self, intent, approval, decision):
        return self.wrapped(intent, approval, decision)


def invoke_gateway_gate(intent, approval, decision, gateway, envelope, broker, *, now=FIXED_NOW):
    return run_gateway_gate(
        intent, approval, decision, gateway, envelope,
        now=now, proceed=broker.proceed,
    )


class GatewayGateTests(unittest.TestCase):
    def test_matching_slow_allow_reaches_broker_once_with_ordered_trace(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, _evaluated):
            events = []
            gateway = FakeGateway(events)
            broker = GatewayDownstream(events)
            envelope = gateway_envelope(intent)

            def proceed_to_gateway(gate_intent, gate_approval, gate_decision):
                self.assertIs(gate_intent, intent)
                return invoke_gateway_gate(
                    gate_intent, gate_approval, gate_decision, gateway, envelope, broker
                )

            marker, passed = invoke_policy_gate(
                intent, approval, policy, engine_intent, staged_change,
                PolicyProceedAdapter(proceed_to_gateway),
            )
            self.assertEqual(marker, "broker-reached")
            self.assertIs(passed, intent)
            self.assertEqual(events, ["gateway.call", "broker.call"])
            self.assertEqual(broker.calls, 1)
            self.assertIs(gateway.calls[0][0], envelope)
            self.assertIsNotNone(gateway.calls[0][1].tzinfo)
            received_intent, _approval, received_decision, gateway_decision = broker.received
            self.assertIs(received_intent, intent)
            self.assertEqual(received_decision["effect"], "allow")
            self.assertEqual(received_decision["staged_change_digest"], intent.staged_change_digest)
            self.assertIsInstance(gateway_decision, GatewayDecision)
            self.assertIs(gateway_decision.path, GatewayPath.SLOW)
            self.assertIs(gateway_decision.allowed, True)

    def test_deny_degraded_and_fast_outputs_stop_before_broker(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            cases = {
                "slow-deny": GatewayDecision(GatewayPath.SLOW, False, ("tainted-content",)),
                "degraded-deny": GatewayDecision(GatewayPath.DEGRADED, False, ("write-or-unknown-denied",)),
                "degraded-allow": GatewayDecision(GatewayPath.DEGRADED, True, ("read-only-allowlist",)),
                "fast-allow": GatewayDecision(GatewayPath.FAST, True, ("internal-read-only",)),
            }
            for label, verdict in cases.items():
                with self.subTest(gateway=label):
                    events = []
                    gateway = FakeGateway(events, verdict=verdict)
                    broker = GatewayDownstream(events)
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: gateway has not authorized slow path$",
                    ):
                        invoke_gateway_gate(
                            intent, approval, evaluated, gateway,
                            gateway_envelope(intent), broker,
                        )
                    self.assertEqual(events, ["gateway.call"])
                    self.assertEqual(broker.calls, 0)

    def test_malformed_gateway_output_stops_before_broker(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            malformed = (
                None, "allow", {"path": "slow", "allowed": True},
                GatewayDecision(GatewayPath.SLOW, "yes", ("write-or-unknown-operation",)),
                GatewayDecision("slow", True, ("write-or-unknown-operation",)),
                GatewayDecision(GatewayPath.SLOW, True, ["write-or-unknown-operation"]),
            )
            for verdict in malformed:
                with self.subTest(verdict=repr(verdict)):
                    events = []
                    gateway = FakeGateway(events, verdict=verdict)
                    broker = GatewayDownstream(events)
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: gateway has not authorized slow path$",
                    ):
                        invoke_gateway_gate(
                            intent, approval, evaluated, gateway,
                            gateway_envelope(intent), broker,
                        )
                    self.assertEqual(events, ["gateway.call"])
                    self.assertEqual(broker.calls, 0)

    def test_raising_gateway_fails_closed_without_leak(self):
        canary = "GATEWAY-CANARY-SECRET"
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            events = []
            gateway = FakeGateway(events, error=RuntimeError(f"gateway blew up: {canary}"))
            broker = GatewayDownstream(events)
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: gateway invocation failed$",
            ) as raised:
                invoke_gateway_gate(
                    intent, approval, evaluated, gateway,
                    gateway_envelope(intent), broker,
                )
            self.assertNotIn(canary, str(raised.exception))
            self.assertEqual(events, ["gateway.call"])
            self.assertEqual(broker.calls, 0)

    def test_mismatched_envelope_stops_before_gateway_call(self):
        canary = "ENVELOPE-CANARY-SECRET"
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            almost = gateway_envelope(intent)
            foreign_destination = dict(almost["destination"], repository_id="repository-foreign")
            foreign_source = dict(almost["source"], principal_id="process-foreign-001")
            mismatched = (
                None, "not-a-mapping", {},
                dict(almost, intent={"operation": "merge_pull_request"}),
                dict(almost, intent={"operation": canary}),
                dict(almost, payload={"content_digest": "sha256:" + "f" * 64}),
                dict(almost, payload={"content_digest": canary}),
                dict(almost, destination=foreign_destination),
                dict(almost, source=foreign_source),
                dict(almost, correlation_id="foreign-correlation"),
                dict(almost, correlation_id=canary),
                {key: value for key, value in almost.items() if key != "payload"},
                {key: value for key, value in almost.items() if key != "correlation_id"},
            )
            for envelope in mismatched:
                with self.subTest(envelope=repr(envelope)[:60]):
                    events = []
                    gateway = FakeGateway(events)
                    broker = GatewayDownstream(events)
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: gateway envelope mismatch$",
                    ) as raised:
                        invoke_gateway_gate(intent, approval, evaluated, gateway, envelope, broker)
                    self.assertNotIn(canary, str(raised.exception))
                    self.assertNotIn("foreign-correlation", str(raised.exception))
                    self.assertEqual(events, [])
                    self.assertEqual(broker.calls, 0)

    def test_stale_decision_and_bad_wiring_stop_before_gateway_call(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            stale = dict(evaluated, expires_at=format_time(FIXED_NOW - timedelta(seconds=1)))
            events = []
            with self.assertRaisesRegex(ContractValidationError, "^decision: expired$"):
                invoke_gateway_gate(
                    intent, approval, stale, FakeGateway(events),
                    gateway_envelope(intent), GatewayDownstream(events),
                )
            self.assertEqual(events, [])
            for decision in (None, "not-a-decision"):
                with self.subTest(decision=repr(decision)):
                    events = []
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: decision is missing$",
                    ):
                        invoke_gateway_gate(
                            intent, approval, decision, FakeGateway(events),
                            gateway_envelope(intent), GatewayDownstream(events),
                        )
                    self.assertEqual(events, [])
            for gateway in (None, "gateway"):
                with self.subTest(gateway=repr(gateway)):
                    events = []
                    broker = GatewayDownstream(events)
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: gateway is invalid$",
                    ):
                        invoke_gateway_gate(
                            intent, approval, evaluated, gateway,
                            gateway_envelope(intent), broker,
                        )
                    self.assertEqual(events, [])
                    self.assertEqual(broker.calls, 0)
            for now in (None, datetime(2026, 9, 29, 12, 0, 0)):
                with self.subTest(now=repr(now)):
                    events = []
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: clock is invalid$",
                    ):
                        invoke_gateway_gate(
                            intent, approval, evaluated, FakeGateway(events),
                            gateway_envelope(intent), GatewayDownstream(events), now=now,
                        )
                    self.assertEqual(events, [])
            events = []
            broker = GatewayDownstream(events)
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: downstream step is invalid$",
            ):
                run_gateway_gate(
                    intent, approval, evaluated, FakeGateway(events),
                    gateway_envelope(intent), now=FIXED_NOW, proceed=None,
                )
            self.assertEqual(events, [])
            self.assertEqual(broker.calls, 0)
            with self.assertRaisesRegex(
                ControlledPublicationError, "^controlled publication: intent is invalid$"
            ):
                invoke_gateway_gate(
                    None, approval, evaluated, FakeGateway(events),
                    gateway_envelope(intent), GatewayDownstream(events),
                )
            with self.assertRaisesRegex(
                ControlledPublicationError, "^controlled publication: approval is missing$"
            ):
                invoke_gateway_gate(
                    intent, None, evaluated, FakeGateway(events),
                    gateway_envelope(intent), GatewayDownstream(events),
                )


class FakeBrokerError(Exception):
    pass


class FakeChannel:
    def __init__(self, endpoint_calls):
        self.endpoint_calls = endpoint_calls

    def publish_pull_request(self, request):
        self.endpoint_calls.append(request)
        return {"pull_request_id": 1}


class FakeBroker:
    def __init__(self):
        self.opens = []
        self.used_grants = set()

    def open_github_publication_channel(self, credential_grant, actuator_request, *, now):
        grant_id = credential_grant.get("credential_grant_id")
        self.opens.append((credential_grant, actuator_request, now))
        if grant_id in self.used_grants:
            raise FakeBrokerError("credential grant already used")
        self.used_grants.add(grant_id)
        return FakeChannel([])


def broker_actuator_request(intent: PublicationIntent, actuator_id="test-actuator") -> dict:
    return {
        "operation": "publish_pull_request",
        "repository_id": intent.repository_id,
        "actuator_id": actuator_id,
        "staged_change_digest": intent.staged_change_digest,
        "branch_namespace": intent.branch.split("/", 1)[0],
        "idempotency_key": intent.idempotency_key,
    }


def matching_grant(intent: PublicationIntent, *, actuator_id="test-actuator") -> dict:
    return {
        "credential_grant_id": "grant-local-001",
        "actuator_id": actuator_id,
        "repository_id": intent.repository_id,
        "operation": "publish_pull_request",
        "request_digest": sha256_digest(broker_actuator_request(intent, actuator_id)),
        "single_use": True,
        "credential_class": "github-app-installation",
        "expires_at": format_time(FIXED_NOW + timedelta(hours=1)),
    }


def slow_allow_decision():
    return GatewayDecision(GatewayPath.SLOW, True, ("write-or-unknown-operation",))


class BrokerDownstream:
    def __init__(self, events):
        self.events = events
        self.calls = 0
        self.received = None

    def proceed(self, intent, approval, decision, gateway_decision, channel):
        self.events.append("endpoint.ready")
        self.calls += 1
        self.received = (intent, approval, decision, gateway_decision, channel)
        return ("channel-ready", intent)


class InMemoryPublicationJournal:
    def __init__(self):
        self.records = {}

    def get(self, process_id):
        return self.records[process_id]

    def prepare(self, process_id, *, idempotency_key, request_digest, repository_id):
        existing = self.records.get(process_id)
        if existing is not None:
            if (existing.idempotency_key, existing.request_digest, existing.repository_id) == (
                idempotency_key, request_digest, repository_id
            ):
                return existing
            raise ValueError("publication payload conflict")
        record = PublicationRecord(
            process_id, idempotency_key, request_digest, repository_id, "prepared", None
        )
        self.records[process_id] = record
        return record


def invoke_broker_gate(intent, approval, decision, broker, grant, downstream,
                       *, policy=None, engine_intent=None, staged_change=None,
                       seed=None, journal=None,
                       actuator_id="test-actuator", now=FIXED_NOW,
                       gateway=None, envelope=None):
    if gateway is None:
        gateway = FakeGateway([])
    if envelope is None:
        envelope = gateway_envelope(intent)
    if seed is None:
        seed = journal_seed_for(intent)
    if journal is None:
        journal = InMemoryPublicationJournal()
    return run_broker_gate(
        intent, approval, policy, engine_intent, staged_change,
        decision.get("decision_id") if isinstance(decision, dict) else "decision-local-001",
        gateway, envelope,
        broker, grant, actuator_id=actuator_id, now=now, proceed=downstream.proceed,
        seed=seed, journal=journal,
    )


class BrokerGateTests(unittest.TestCase):
    def test_matching_grant_opens_single_channel_with_zero_endpoint_calls(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            broker = FakeBroker()
            downstream = BrokerDownstream(events := [])
            marker, passed = invoke_broker_gate(
                intent, approval, evaluated, broker, matching_grant(intent), downstream,
                policy=policy, engine_intent=engine_intent, staged_change=staged_change,
            )
            self.assertEqual(marker, "channel-ready")
            self.assertIs(passed, intent)
            self.assertEqual(downstream.calls, 1)
            self.assertEqual(len(broker.opens), 1)
            grant, actuator_request, moment = broker.opens[0]
            self.assertEqual(grant["credential_grant_id"], "grant-local-001")
            self.assertEqual(actuator_request, broker_actuator_request(intent))
            self.assertIsNotNone(moment.tzinfo)
            _i, _a, _d, gateway_decision, channel = downstream.received
            self.assertIs(gateway_decision.path, GatewayPath.SLOW)
            self.assertIsInstance(channel, FakeChannel)
            self.assertEqual(channel.endpoint_calls, [])

    def test_broker_runs_after_gateway_with_ordered_trace(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            events = []
            gateway = FakeGateway(events)
            broker = FakeBroker()
            downstream = BrokerDownstream(events)
            envelope = gateway_envelope(intent)

            def proceed_to_broker(gate_intent, gate_approval, gate_decision):
                return invoke_broker_gate(
                    gate_intent, gate_approval, gate_decision, broker,
                    matching_grant(gate_intent), downstream,
                    policy=policy, engine_intent=engine_intent,
                    staged_change=staged_change,
                    gateway=gateway, envelope=envelope,
                )

            marker, passed = invoke_policy_gate(
                intent, approval, policy, engine_intent, staged_change,
                PolicyProceedAdapter(proceed_to_broker),
            )
            self.assertEqual(marker, "channel-ready")
            self.assertIs(passed, intent)
            self.assertEqual(events, ["gateway.call", "endpoint.ready"])
            self.assertEqual(len(gateway.calls), 1)
            self.assertIs(gateway.calls[0][0], envelope)
            self.assertEqual(len(broker.opens), 1)

    def test_binding_mismatch_stops_before_broker_open(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            cases = [
                ("repository", {"repository_id": "repository-foreign"}),
                ("operation", {"operation": "merge_pull_request"}),
                ("actuator", {"actuator_id": "actuator-foreign"}),
                ("digest", {"request_digest": "sha256:" + "f" * 64}),
                ("single-use", {"single_use": False}),
                ("class", {"credential_class": "github-app-admin"}),
            ]
            for label, override in cases:
                with self.subTest(grant=label):
                    broker = FakeBroker()
                    downstream = BrokerDownstream(events := [])
                    grant = dict(matching_grant(intent), **override)
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^(controlled publication: credential grant binding mismatch"
                        "|controlled publication: credential grant must be single-use)$",
                    ):
                        invoke_broker_gate(
                            intent, approval, evaluated, broker, grant, downstream,
                            policy=policy, engine_intent=engine_intent,
                            staged_change=staged_change,
                        )
                    self.assertEqual(broker.opens, [])
                    self.assertEqual(events, [])
                    self.assertEqual(downstream.calls, 0)
            for label, grant in (
                ("non-mapping", "not-a-grant"),
                ("missing-id", {key: value for key, value in matching_grant(intent).items()
                                if key != "credential_grant_id"}),
            ):
                with self.subTest(grant=label):
                    broker = FakeBroker()
                    downstream = BrokerDownstream(events := [])
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: credential grant is invalid$",
                    ):
                        invoke_broker_gate(
                            intent, approval, evaluated, broker, grant, downstream,
                            policy=policy, engine_intent=engine_intent,
                            staged_change=staged_change,
                        )
                    self.assertEqual(broker.opens, [])
                    self.assertEqual(downstream.calls, 0)

    def test_expired_or_malformed_grant_expiry_stops_before_broker_open(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            for expires_at, message in (
                (format_time(FIXED_NOW - timedelta(seconds=1)),
                 "^controlled publication: credential grant expired$"),
                (format_time(FIXED_NOW),
                 "^controlled publication: credential grant expired$"),
                (None, "^controlled publication: credential grant expiry is invalid$"),
                ("not-a-time", "^controlled publication: credential grant expiry is invalid$"),
            ):
                with self.subTest(expires_at=repr(expires_at)):
                    broker = FakeBroker()
                    downstream = BrokerDownstream(events := [])
                    grant = dict(matching_grant(intent), expires_at=expires_at)
                    with self.assertRaisesRegex(ControlledPublicationError, message):
                        invoke_broker_gate(
                            intent, approval, evaluated, broker, grant, downstream,
                            policy=policy, engine_intent=engine_intent,
                            staged_change=staged_change,
                        )
                    self.assertEqual(broker.opens, [])
                    self.assertEqual(downstream.calls, 0)

    def test_reused_grant_stops_with_zero_endpoint_calls(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            broker = FakeBroker()
            first = BrokerDownstream(events := [])
            invoke_broker_gate(
                intent, approval, evaluated, broker, matching_grant(intent), first,
                policy=policy, engine_intent=engine_intent, staged_change=staged_change,
            )
            self.assertEqual(first.calls, 1)
            second = BrokerDownstream(events)
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: broker invocation failed$",
            ):
                invoke_broker_gate(
                    intent, approval, evaluated, broker, matching_grant(intent), second,
                    policy=policy, engine_intent=engine_intent, staged_change=staged_change,
                )
            self.assertEqual(second.calls, 0)
            self.assertEqual(len(broker.opens), 2)
            self.assertEqual(first.received[4].endpoint_calls, [])

    def test_non_slow_gateway_output_stops_before_broker_open(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            for label, verdict in {
                "deny": GatewayDecision(GatewayPath.SLOW, False, ("denied",)),
                "degraded": GatewayDecision(GatewayPath.DEGRADED, False, ("denied",)),
                "fast": GatewayDecision(GatewayPath.FAST, True, ("read-only",)),
                "malformed": "not-a-decision",
            }.items():
                with self.subTest(gateway=label):
                    events = []
                    gateway = FakeGateway(events, verdict=verdict)
                    broker = FakeBroker()
                    downstream = BrokerDownstream(events)
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: gateway has not authorized slow path$",
                    ):
                        invoke_broker_gate(
                            intent, approval, evaluated, broker, matching_grant(intent),
                            downstream, gateway=gateway,
                            policy=policy, engine_intent=engine_intent,
                            staged_change=staged_change,
                            envelope=gateway_envelope(intent),
                        )
                    self.assertEqual(events, ["gateway.call"])
                    self.assertEqual(broker.opens, [])
                    self.assertEqual(downstream.calls, 0)

    def test_fabricated_verdict_cannot_replace_gateway_invocation(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            fabricated = slow_allow_decision()
            self.assertIs(fabricated.path, GatewayPath.SLOW)
            self.assertIs(fabricated.allowed, True)
            events = []
            broker = FakeBroker()
            downstream = BrokerDownstream(events)
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: gateway is invalid$",
            ):
                invoke_broker_gate(
                    intent, approval, evaluated, broker, matching_grant(intent),
                    downstream,
                    policy=policy, engine_intent=engine_intent,
                    staged_change=staged_change,
                    gateway=fabricated,
                    envelope=gateway_envelope(intent),
                )
            self.assertEqual(events, [])
            self.assertEqual(broker.opens, [])
            self.assertEqual(downstream.calls, 0)

    def test_unbound_envelope_never_reaches_live_gateway(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            foreign = dict(
                gateway_envelope(intent), correlation_id="foreign-correlation"
            )
            events = []
            gateway = FakeGateway(events)
            broker = FakeBroker()
            downstream = BrokerDownstream(events)
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: gateway envelope mismatch$",
            ):
                invoke_broker_gate(
                    intent, approval, evaluated, broker, matching_grant(intent),
                    downstream,
                    policy=policy, engine_intent=engine_intent,
                    staged_change=staged_change,
                    gateway=gateway, envelope=foreign,
                )
            self.assertEqual(events, [])
            self.assertEqual(broker.opens, [])
            self.assertEqual(downstream.calls, 0)

    def test_bad_wiring_stops_before_broker_open(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            for label, kwargs in (
                ("bad-intent", {"intent": None}),
                ("bad-approval", {"approval": None}),
                ("bad-gateway", {"gateway": None}),
                ("bad-envelope", {"envelope": "not-a-mapping"}),
                ("bad-broker", {"broker": None}),
                ("bad-seed", {"seed": None}),
                ("bad-journal", {"journal": None}),
                ("bad-actuator", {"actuator_id": ""}),
                ("bad-now", {"now": None}),
            ):
                with self.subTest(wiring=label):
                    broker = FakeBroker()
                    downstream = BrokerDownstream(events := [])
                    gateway_events = []
                    base = {
                        "intent": intent, "approval": approval, "decision": evaluated,
                        "gateway": FakeGateway(gateway_events),
                        "envelope": gateway_envelope(intent),
                        "broker": broker, "grant": matching_grant(intent),
                        "seed": journal_seed_for(intent),
                        "journal": InMemoryPublicationJournal(),
                        "downstream": downstream,
                    }
                    base.update(kwargs)
                    if label == "bad-broker":
                        broker_used = None
                    else:
                        broker_used = broker
                    with self.assertRaises(ControlledPublicationError):
                        run_broker_gate(
                            base["intent"], base["approval"], policy, engine_intent,
                            staged_change, "decision-local-001", base["gateway"],
                            base["envelope"], broker_used, base["grant"],
                            actuator_id=base.get("actuator_id", "test-actuator")
                            if label != "bad-actuator" else "",
                            now=base["now"] if "now" in base else FIXED_NOW,
                            proceed=downstream.proceed,
                            seed=base["seed"], journal=base["journal"],
                        )
                    self.assertEqual(gateway_events, [])
                    self.assertEqual(broker.opens, [])
                    self.assertEqual(downstream.calls, 0)

    def test_policy_engine_is_rerun_inside_broker_gate(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            broker = FakeBroker()
            downstream = BrokerDownstream(events := [])
            with patch.object(policy, "decide", wraps=policy.decide) as decide:
                invoke_broker_gate(
                    intent, approval, evaluated, broker, matching_grant(intent), downstream,
                    policy=policy, engine_intent=engine_intent,
                    staged_change=staged_change,
                    gateway=FakeGateway(events),
                )
            decide.assert_called_once()
            self.assertEqual(len(broker.opens), 1)
            self.assertEqual(downstream.calls, 1)
            self.assertEqual(events, ["gateway.call", "endpoint.ready"])

    def test_forged_policy_decision_cannot_authorize_broker(self):
        with decided_gate_fixture() as (intent, approval, _policy, engine_intent,
                                        staged_change, evaluated):
            forged_allow = dict(evaluated, effect="allow")
            gateway_events = []
            broker = FakeBroker()
            downstream = BrokerDownstream([])
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: policy engine is invalid$",
            ):
                run_broker_gate(
                    intent, approval, forged_allow, engine_intent, staged_change,
                    "decision-local-001", FakeGateway(gateway_events),
                    gateway_envelope(intent), broker, matching_grant(intent),
                    actuator_id="test-actuator", now=FIXED_NOW,
                    proceed=downstream.proceed, seed=journal_seed_for(intent),
                    journal=InMemoryPublicationJournal(),
                )
            self.assertEqual(gateway_events, [])
            self.assertEqual(broker.opens, [])
            self.assertEqual(downstream.calls, 0)

    def test_grant_values_never_reach_errors_or_evidence(self):
        canary = "GRANT-CANARY-SECRET"
        with decided_gate_fixture() as (intent, approval, policy, engine_intent, staged_change, evaluated):
            grant = dict(matching_grant(intent), credential_grant_id=canary,
                         repository_id="repository-foreign")
            broker = FakeBroker()
            downstream = BrokerDownstream(events := [])
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: credential grant binding mismatch$",
            ) as raised:
                invoke_broker_gate(
                    intent, approval, evaluated, broker, grant, downstream,
                    policy=policy, engine_intent=engine_intent,
                    staged_change=staged_change,
                )
            self.assertNotIn(canary, str(raised.exception))
            self.assertEqual(broker.opens, [])
            self.assertEqual(downstream.calls, 0)
            exploding = FakeBroker()
            exploding.used_grants.add("grant-local-001")
            with self.assertRaisesRegex(
                ControlledPublicationError,
                "^controlled publication: broker invocation failed$",
            ) as raised:
                invoke_broker_gate(intent, approval, evaluated, exploding,
                                   matching_grant(intent), downstream,
                                   policy=policy, engine_intent=engine_intent,
                                   staged_change=staged_change)
            self.assertNotIn("grant-local-001", str(raised.exception))
            received = downstream.received
            self.assertIsNone(received)


def journal_seed_for(intent):
    digest = sha256_digest("journal-test-evidence")
    return PublicationSeed(
        process_id=intent.process_id,
        repository_id=intent.repository_id,
        base_commit=intent.base_commit,
        staged_change_digest=intent.staged_change_digest,
        verified_contents_digest=digest,
        verifier_id="journal-test-verifier",
        verdict="pass",
        replay_result_digest=digest,
        snapshot_tree_digest=digest,
        snapshot_origin="local_git_commit",
    )


class JournalPreparationTests(unittest.TestCase):
    def test_journal_is_prepared_only_after_policy_gateway_and_broker(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _evaluated):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    events = []
                    gateway = FakeGateway(events)
                    broker = FakeBroker()
                    seed = journal_seed_for(intent)
                    approval_with_canary = dict(approval, access_token="APPROVAL-TOKEN-CANARY")
                    original_prepare = journal.prepare

                    def record_prepare(*args, **kwargs):
                        events.append("journal.prepare")
                        return original_prepare(*args, **kwargs)

                    journal.prepare = record_prepare

                    def after_gates(gate_intent, _gate_approval, _decision,
                                    _gateway_decision, _channel):
                        events.append("endpoint.ready")
                        return journal.get(gate_intent.process_id)

                    prepared = run_broker_gate(
                        intent, approval_with_canary, policy, engine_intent,
                        staged_change, "decision-local-001", gateway,
                        gateway_envelope(intent), broker, matching_grant(intent),
                        actuator_id="test-actuator", now=FIXED_NOW,
                        proceed=after_gates, seed=seed, journal=journal,
                    )
                    self.assertEqual(
                        events, ["gateway.call", "journal.prepare", "endpoint.ready"]
                    )
                    self.assertEqual(len(broker.opens), 1)
                    self.assertEqual(prepared.status, "prepared")
                    self.assertRegex(prepared.request_digest, r"^sha256:[0-9a-f]{64}$")
                    self.assertEqual(prepared.process_id, intent.process_id)
                    self.assertEqual(prepared.repository_id, intent.repository_id)
                    self.assertNotIn("APPROVAL-TOKEN-CANARY", repr(prepared))
                    self.assertEqual(journal.get(intent.process_id), prepared)

                    replayed = run_broker_gate(
                        intent, approval_with_canary, policy, engine_intent,
                        staged_change, "decision-local-001", FakeGateway([]),
                        gateway_envelope(intent), FakeBroker(), matching_grant(intent),
                        actuator_id="test-actuator", now=FIXED_NOW,
                        proceed=lambda gate_intent, *_args: journal.get(gate_intent.process_id),
                        seed=seed, journal=journal,
                    )
                    self.assertEqual(replayed, prepared)

    def test_conflicting_journal_binding_is_not_reused_or_overwritten(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _evaluated):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    original = journal.prepare(
                        intent.process_id,
                        idempotency_key=intent.idempotency_key,
                        request_digest=sha256_digest("preexisting-conflicting-request"),
                        repository_id=intent.repository_id,
                    )
                    downstream = BrokerDownstream(events := [])
                    gateway = FakeGateway(events)
                    broker = FakeBroker()
                    with self.assertRaisesRegex(ValueError, "^publication payload conflict$"):
                        run_broker_gate(
                            intent, approval, policy, engine_intent, staged_change,
                            "decision-local-001", gateway, gateway_envelope(intent),
                            broker, matching_grant(intent), actuator_id="test-actuator",
                            now=FIXED_NOW, proceed=downstream.proceed,
                            seed=journal_seed_for(intent), journal=journal,
                        )
                    self.assertEqual(journal.get(intent.process_id), original)
                    self.assertEqual(original.status, "prepared")
                    self.assertEqual(events, ["gateway.call"])
                    self.assertEqual(len(broker.opens), 1)
                    self.assertEqual(downstream.calls, 0)

    def test_denied_gateway_never_creates_journal_record(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _evaluated):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    events = []
                    denied = FakeGateway(
                        events,
                        verdict=GatewayDecision(GatewayPath.SLOW, False, ("denied",)),
                    )

                    downstream = BrokerDownstream(events)

                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: gateway has not authorized slow path$",
                    ):
                        run_broker_gate(
                            intent, approval, policy, engine_intent, staged_change,
                            "decision-local-001", denied, gateway_envelope(intent),
                            FakeBroker(), matching_grant(intent), actuator_id="test-actuator",
                            now=FIXED_NOW, proceed=downstream.proceed,
                            seed=journal_seed_for(intent), journal=journal,
                        )
                    self.assertEqual(events, ["gateway.call"])
                    self.assertEqual(downstream.calls, 0)
                    with self.assertRaises(KeyError):
                        journal.get(intent.process_id)


class ControlledLocalPublicationTests(unittest.TestCase):
    def _run(self, intent, approval, policy, engine_intent, staged_change,
             gateway, broker, journal, endpoint, loader):
        return run_controlled_local_publication(
            journal_seed_for(intent), intent, approval, policy, engine_intent,
            loader, "decision-local-001", gateway, gateway_envelope(intent),
            broker, matching_grant(intent), journal, endpoint,
            actuator_id="test-actuator", now=FIXED_NOW,
        )

    def test_composes_approval_policy_gateway_broker_journal_and_mock(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _evaluated):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    endpoint = MockGitHubEndpoint()
                    broker = InMemoryCredentialBroker(lambda: endpoint)
                    gateway_events = []
                    gateway = FakeGateway(gateway_events)
                    loader_calls = []

                    def load_staged_change(seed):
                        loader_calls.append(seed.staged_change_digest)
                        return staged_change

                    with patch.object(policy, "decide", wraps=policy.decide) as decide:
                        receipt = self._run(
                            intent, approval, policy, engine_intent, staged_change,
                            gateway, broker, journal, endpoint, load_staged_change,
                        )

                    decide.assert_called_once()
                    self.assertEqual(loader_calls, [intent.staged_change_digest])
                    self.assertEqual(len(gateway.calls), 1)
                    self.assertEqual(len(broker.opened_grants), 1)
                    self.assertEqual(broker.opened_grants, ["grant-local-001"])
                    self.assertEqual(receipt.repository_id, intent.repository_id)
                    self.assertEqual(receipt.branch, intent.branch)
                    self.assertEqual(receipt.staged_change_digest, intent.staged_change_digest)
                    self.assertEqual(receipt.idempotency_key, intent.idempotency_key)
                    self.assertEqual(
                        endpoint.find_by_idempotency_key(intent.idempotency_key), receipt
                    )
                    self.assertEqual(journal.get(intent.process_id).status, "completed")

    def test_missing_approval_stops_before_loader_or_effectful_collaborators(self):
        with decided_gate_fixture() as (intent, _approval, policy, engine_intent,
                                        staged_change, _evaluated):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    endpoint = MockGitHubEndpoint()
                    broker = InMemoryCredentialBroker(lambda: endpoint)
                    gateway_events = []
                    loader_calls = []
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: approval is missing$",
                    ):
                        self._run(
                            intent, None, policy, engine_intent, staged_change,
                            FakeGateway(gateway_events), broker, journal, endpoint,
                            lambda _seed: loader_calls.append("called"),
                        )
                    self.assertEqual(loader_calls, [])
                    self.assertEqual(gateway_events, [])
                    self.assertEqual(broker.opened_grants, [])
                    with self.assertRaises(KeyError):
                        journal.get(intent.process_id)

    def test_staged_digest_mismatch_stops_before_gateway_broker_journal_and_mock(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _evaluated):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    endpoint = MockGitHubEndpoint()
                    broker = InMemoryCredentialBroker(lambda: endpoint)
                    gateway_events = []
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: staged change digest mismatch$",
                    ):
                        self._run(
                            intent, approval, policy, engine_intent, staged_change,
                            FakeGateway(gateway_events), broker, journal, endpoint,
                            lambda _seed: {"tampered.py": "unapproved"},
                        )
                    self.assertEqual(gateway_events, [])
                    self.assertEqual(broker.opened_grants, [])
                    with self.assertRaises(KeyError):
                        journal.get(intent.process_id)
                    self.assertIsNone(endpoint.find_by_idempotency_key(intent.idempotency_key))

    def test_gateway_deny_stops_before_broker_journal_and_mock(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _evaluated):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    endpoint = MockGitHubEndpoint()
                    broker = InMemoryCredentialBroker(lambda: endpoint)
                    gateway_events = []
                    denied = FakeGateway(
                        gateway_events,
                        verdict=GatewayDecision(GatewayPath.SLOW, False, ("denied",)),
                    )
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: gateway has not authorized slow path$",
                    ):
                        self._run(
                            intent, approval, policy, engine_intent, staged_change,
                            denied, broker, journal, endpoint, lambda _seed: staged_change,
                        )
                    self.assertEqual(gateway_events, ["gateway.call"])
                    self.assertEqual(broker.opened_grants, [])
                    with self.assertRaises(KeyError):
                        journal.get(intent.process_id)
                    self.assertIsNone(endpoint.find_by_idempotency_key(intent.idempotency_key))

    def test_non_mock_endpoint_is_rejected_before_approval_or_loader(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, _evaluated):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    gateway_events = []
                    broker = InMemoryCredentialBroker(lambda: MockGitHubEndpoint())
                    loader_calls = []
                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: mock endpoint is required$",
                    ):
                        self._run(
                            intent, approval, policy, engine_intent, staged_change,
                            FakeGateway(gateway_events), broker, journal, object(),
                            lambda _seed: loader_calls.append("called"),
                        )
                    self.assertEqual(loader_calls, [])
                    self.assertEqual(gateway_events, [])
                    self.assertEqual(broker.opened_grants, [])
                    with self.assertRaises(KeyError):
                        journal.get(intent.process_id)


class PinnedToMockPublicationTests(unittest.TestCase):
    def test_pinned_verified_seed_produces_one_mock_receipt_and_completed_journal(self):
        with decided_gate_fixture(include_seed=True) as (
            intent, approval, policy, engine_intent, staged_change, _evaluated, seed
        ):
            self.assertEqual(seed.verdict, "pass")
            self.assertEqual(seed.snapshot_origin, "local_git_commit")
            self.assertEqual(seed.base_commit, intent.base_commit)
            self.assertEqual(seed.repository_id, intent.repository_id)
            self.assertEqual(seed.staged_change_digest, intent.staged_change_digest)
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    endpoint = MockGitHubEndpoint()
                    broker = InMemoryCredentialBroker(lambda: endpoint)
                    events = []
                    gateway = FakeGateway(events)
                    raw_content = repr(staged_change)

                    original_decide = policy.decide

                    def record_decide(**kwargs):
                        events.append("policy.evaluate")
                        return original_decide(**kwargs)

                    policy.decide = record_decide
                    original_open = broker.open_github_publication_channel

                    def record_open(*args, **kwargs):
                        events.append("broker.open")
                        return original_open(*args, **kwargs)

                    broker.open_github_publication_channel = record_open
                    original_prepare = journal.prepare

                    def record_prepare(*args, **kwargs):
                        events.append("journal.prepare")
                        return original_prepare(*args, **kwargs)

                    journal.prepare = record_prepare
                    original_attempting = journal.mark_attempting

                    def record_attempting(*args, **kwargs):
                        events.append("journal.mark_attempting")
                        return original_attempting(*args, **kwargs)

                    journal.mark_attempting = record_attempting
                    original_publish = endpoint.publish_pull_request

                    def record_publish(*args, **kwargs):
                        events.append("mock.publish")
                        return original_publish(*args, **kwargs)

                    endpoint.publish_pull_request = record_publish
                    original_completed = journal.mark_completed

                    def record_completed(*args, **kwargs):
                        events.append("journal.mark_completed")
                        return original_completed(*args, **kwargs)

                    journal.mark_completed = record_completed

                    def load_staged_change(request_seed):
                        events.append("staged.load")
                        self.assertIs(request_seed, seed)
                        return staged_change

                    receipt = run_controlled_local_publication(
                        seed, intent, approval, policy, engine_intent,
                        load_staged_change, "decision-local-001", gateway,
                        gateway_envelope(intent), broker, matching_grant(intent),
                        journal, endpoint, actuator_id="test-actuator", now=FIXED_NOW,
                    )
                    self.assertEqual(events, [
                        "staged.load", "policy.evaluate", "gateway.call", "broker.open",
                        "journal.prepare", "journal.mark_attempting", "mock.publish",
                        "journal.mark_completed",
                    ])
                    record = journal.get(intent.process_id)
                    self.assertEqual(record.status, "completed")
                    self.assertEqual(record.pull_request_id, receipt.pull_request_id)
                    self.assertEqual(receipt.repository_id, seed.repository_id)
                    self.assertEqual(receipt.branch, intent.branch)
                    self.assertEqual(receipt.staged_change_digest, seed.staged_change_digest)
                    self.assertEqual(receipt.idempotency_key, intent.idempotency_key)
                    self.assertEqual(len(endpoint._by_idempotency_key), 1)
                    serialized_evidence = repr((receipt, record))
                    self.assertNotIn(approval["approval_id"], serialized_evidence)
                    self.assertNotIn("grant-local-001", serialized_evidence)
                    self.assertNotIn(raw_content, serialized_evidence)

                    with self.assertRaisesRegex(
                        ControlledPublicationError,
                        "^controlled publication: broker invocation failed$",
                    ):
                        run_controlled_local_publication(
                            seed, intent, approval, policy, engine_intent,
                            load_staged_change, "decision-local-001", gateway,
                            gateway_envelope(intent), broker, matching_grant(intent),
                            journal, endpoint, actuator_id="test-actuator", now=FIXED_NOW,
                        )
                    self.assertEqual(len(endpoint._by_idempotency_key), 1)
                    self.assertEqual(journal.get(intent.process_id).status, "completed")


class InvalidExecutionEvidenceTests(unittest.TestCase):
    def test_failed_verifier_replay_mismatch_and_stale_pin_stop_before_publication_gates(self):
        with decided_gate_fixture(include_details=True) as (
            intent, approval, policy, engine_intent, staged_change, _evaluated,
            _seed, request, _verified_result,
        ):
            class FailedVerifier:
                def verify(self, prepared):
                    return replace(
                        AcceptingVerifier().verify(prepared),
                        verdict=VerifierVerdict.FAIL,
                        blocker_codes=("verification-failed",),
                    )

            class ReplayMismatchVerifier:
                def verify(self, prepared):
                    return replace(
                        AcceptingVerifier().verify(prepared),
                        replay_result_digest=sha256_digest("mismatched-replay"),
                    )

            stale_pin = replace(
                request.pinned_snapshot,
                tree_digest=sha256_digest("stale-pinned-tree"),
            )
            stale_request = replace(request, pinned_snapshot=stale_pin)
            cases = (
                ("failed-verifier", request, FailedVerifier(), PublicationSeedError,
                 "^publication seed: execution status is not verified$"),
                ("replay-mismatch", request, ReplayMismatchVerifier(), ExecutionError,
                 "^execution verifier: result binding mismatch$"),
                ("stale-pin", stale_request, AcceptingVerifier(), ExecutionError,
                 "^execution snapshot: digest mismatch$"),
            )
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    endpoint = MockGitHubEndpoint()
                    broker = InMemoryCredentialBroker(lambda: endpoint)
                    gateway_events = []
                    gateway = FakeGateway(gateway_events)
                    approval_calls = []
                    policy_calls = []
                    loader_calls = []
                    original_approval_gate = gate_module.run_approval_gate
                    original_decide = policy.decide

                    def checked_attempt(candidate_request, verifier):
                        result = run_local_execution(
                            candidate_request,
                            SeedWorker(),
                            verifier=verifier,
                            require_pinned_snapshot=True,
                        )
                        candidate_seed = build_publication_seed(candidate_request, result)
                        return gate_module.run_controlled_local_publication(
                            candidate_seed, intent, approval, policy, engine_intent,
                            lambda _seed: loader_calls.append("called") or staged_change,
                            "decision-local-001", gateway, gateway_envelope(intent),
                            broker, matching_grant(intent), journal, endpoint,
                            actuator_id="test-actuator", now=FIXED_NOW,
                        )

                    def record_approval_gate(*args, **kwargs):
                        approval_calls.append("called")
                        return original_approval_gate(*args, **kwargs)

                    def record_policy_decide(**kwargs):
                        policy_calls.append("called")
                        return original_decide(**kwargs)

                    with patch.object(gate_module, "run_approval_gate", record_approval_gate), \
                         patch.object(policy, "decide", record_policy_decide):
                        for label, candidate_request, verifier, error_type, message in cases:
                            with self.subTest(case=label):
                                with self.assertRaisesRegex(error_type, message):
                                    checked_attempt(candidate_request, verifier)
                                self.assertEqual(approval_calls, [])
                                self.assertEqual(policy_calls, [])
                                self.assertEqual(loader_calls, [])
                                self.assertEqual(gateway_events, [])
                                self.assertEqual(broker.opened_grants, [])
                                self.assertEqual(len(endpoint._by_idempotency_key), 0)
                                with self.assertRaises(KeyError):
                                    journal.get(intent.process_id)


class AuthorityBindingMatrixTests(unittest.TestCase):
    def test_stale_and_mismatched_approval_never_reaches_gateway_broker_journal_or_mock(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, evaluated):
            cases = (
                ("expired", {"expires_at": format_time(FIXED_NOW - timedelta(seconds=1))},
                 ControlledPublicationError,
                 "^controlled publication: approval expired$"),
                ("repository", {"repository_id": "repository-foreign"},
                 ContractValidationError, "^decision: not allow$"),
                ("operation", {"operation": "merge_pull_request"},
                 ContractValidationError, "^decision: not allow$"),
                ("staged-digest", {"staged_change_digest": "sha256:" + "f" * 64},
                 ContractValidationError, "^decision: not allow$"),
            )
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    endpoint = MockGitHubEndpoint()
                    broker = InMemoryCredentialBroker(lambda: endpoint)
                    gateway_events = []
                    gateway = FakeGateway(gateway_events)
                    loader_calls = []
                    for label, override, error_type, message in cases:
                        with self.subTest(approval=label):
                            with self.assertRaisesRegex(error_type, message):
                                run_controlled_local_publication(
                                    journal_seed_for(intent), intent,
                                    dict(approval, **override), policy, engine_intent,
                                    lambda _seed: loader_calls.append(label) or staged_change,
                                    "decision-local-001", gateway,
                                    gateway_envelope(intent), broker, matching_grant(intent),
                                    journal, endpoint, actuator_id="test-actuator",
                                    now=FIXED_NOW,
                                )
                            self.assertEqual(gateway_events, [])
                            self.assertEqual(broker.opened_grants, [])
                            self.assertEqual(len(endpoint._by_idempotency_key), 0)
                            with self.assertRaises(KeyError):
                                journal.get(intent.process_id)
                    self.assertEqual(loader_calls, ["repository", "operation", "staged-digest"])

    def test_stale_or_mismatched_policy_result_stops_before_gateway_and_later_effects(self):
        with decided_gate_fixture() as (intent, approval, policy, engine_intent,
                                        staged_change, evaluated):
            cases = (
                ("expired", {"expires_at": format_time(FIXED_NOW - timedelta(seconds=1))},
                 ContractValidationError, "^decision: expired$"),
                ("operation", {"operation": "merge_pull_request"},
                 ControlledPublicationError,
                 "^controlled publication: decision operation mismatch$"),
                ("repository", {"repository_id": "repository-foreign"},
                 ControlledPublicationError,
                 "^controlled publication: decision repository mismatch$"),
                ("staged-digest", {"staged_change_digest": "sha256:" + "f" * 64},
                 ControlledPublicationError,
                 "^controlled publication: decision digest mismatch$"),
            )
            with tempfile.TemporaryDirectory() as temporary_directory:
                with PublicationJournal(Path(temporary_directory) / "journal.sqlite") as journal:
                    endpoint = MockGitHubEndpoint()
                    broker = InMemoryCredentialBroker(lambda: endpoint)
                    gateway_events = []
                    gateway = FakeGateway(gateway_events)
                    for label, override, error_type, message in cases:
                        with self.subTest(decision=label):
                            with patch.object(policy, "decide", return_value=dict(evaluated, **override)):
                                with self.assertRaisesRegex(error_type, message):
                                    run_controlled_local_publication(
                                        journal_seed_for(intent), intent, approval,
                                        policy, engine_intent, lambda _seed: staged_change,
                                        "decision-local-001", gateway,
                                        gateway_envelope(intent), broker,
                                        matching_grant(intent), journal, endpoint,
                                        actuator_id="test-actuator", now=FIXED_NOW,
                                    )
                            self.assertEqual(gateway_events, [])
                            self.assertEqual(broker.opened_grants, [])
                            self.assertEqual(len(endpoint._by_idempotency_key), 0)
                            with self.assertRaises(KeyError):
                                journal.get(intent.process_id)

if __name__ == "__main__":
    unittest.main()
