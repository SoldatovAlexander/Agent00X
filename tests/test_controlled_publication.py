from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import asdict
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

from app_contracts.controlled_publication import (
    ControlledPublicationError,
    run_approval_gate,
)
import app_contracts.controlled_publication as gate_module
from app_contracts.digests import sha256_digest
from app_contracts.executor import (
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
    build_publication_seed,
    derive_publication_intent,
)
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
        called_names = set()
        defined_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                from_modules.add((node.module or "").lower())
                imported_modules.add((node.module or "").lower())
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id.lower())
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr.lower())
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_names.add(node.name.lower())
        forbidden_modules = {"gateway", "broker", "actuator", "mock_github", "github_app"}
        self.assertTrue(
            all(
                not any(forbidden in module for module in imported_modules)
                for forbidden in forbidden_modules
            )
        )
        for module in from_modules:
            if "publication" in module:
                self.assertIn(module, {"publication_seed", "controlled_publication"})
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


if __name__ == "__main__":
    unittest.main()
