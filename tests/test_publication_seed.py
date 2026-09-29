from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, asdict, replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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
    PublicationSeed,
    PublicationSeedError,
    build_publication_seed,
)
import app_contracts.publication_seed as seed_module


EXPECTED_SEED_FIELDS = frozenset(
    {
        "process_id",
        "repository_id",
        "base_commit",
        "staged_change_digest",
        "verified_contents_digest",
        "verifier_id",
        "verdict",
        "replay_result_digest",
        "snapshot_tree_digest",
        "snapshot_origin",
    }
)


def valid_seed(**overrides) -> PublicationSeed:
    fields = {
        "process_id": "process-local-001",
        "repository_id": "fixture-repository",
        "base_commit": "fixture-base-001",
        "staged_change_digest": "sha256:" + "a" * 64,
        "verified_contents_digest": "sha256:" + "b" * 64,
        "verifier_id": "test-verifier",
        "verdict": "pass",
        "replay_result_digest": None,
        "snapshot_tree_digest": None,
        "snapshot_origin": "unverified_local_test",
    }
    fields.update(overrides)
    return PublicationSeed(**fields)


def valid_request(**overrides) -> ExecutionRequest:
    fields = {
        "process_id": "process-local-001",
        "task_id": "task-local-001",
        "repository_id": "fixture-repository",
        "base_commit": "fixture-base-001",
        "snapshot_path": (ROOT / "fixtures/repository/project").resolve(),
        "allowed_commands": frozenset({"python3"}),
        "declared_change_paths": ("calculator.py",),
        "test_command": ("python3", "-c", "print('ok')"),
    }
    fields.update(overrides)
    return ExecutionRequest(**fields)


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
        return WorkerProposal((("calculator.py", original + "\n# seed-bound change\n"),))


class PublicationSeedTests(unittest.TestCase):
    def test_seed_has_exact_bounded_immutable_shape(self):
        seed = valid_seed()
        self.assertEqual(frozenset(PublicationSeed.__dataclass_fields__), EXPECTED_SEED_FIELDS)
        with self.assertRaises(FrozenInstanceError):
            seed.process_id = "process-replaced"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            seed.staged_change_digest = "sha256:" + "f" * 64  # type: ignore[misc]
        forbidden_fields = {
            "prompt", "content", "contents", "stdout", "stderr", "output",
            "token", "credential", "credentials", "capability", "capabilities",
            "approval", "gateway", "broker", "actuator", "publication_client",
            "github_client", "patch", "snapshot_path", "test_command", "environment",
        }
        self.assertTrue(forbidden_fields.isdisjoint(PublicationSeed.__dataclass_fields__))

    def test_valid_seed_serializes_digests_only(self):
        seed = valid_seed(
            replay_result_digest="sha256:" + "c" * 64,
            snapshot_tree_digest="sha256:" + "d" * 64,
            snapshot_origin="local_git_commit",
        )
        serialized = json.dumps(asdict(seed))
        for digest in (
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
            "sha256:" + "c" * 64,
            "sha256:" + "d" * 64,
        ):
            self.assertIn(digest, serialized)
        self.assertIn('"pass"', serialized)
        self.assertIn('"local_git_commit"', serialized)

    def test_seed_fields_reproduce_unpinned_execution_request_and_result(self):
        request = valid_request()
        result = run_local_execution(request, SeedWorker(), verifier=AcceptingVerifier())
        self.assertEqual(result.status, ExecutionStatus.VERIFIED)
        seed = PublicationSeed(
            process_id=request.process_id,
            repository_id=request.repository_id,
            base_commit=request.base_commit,
            staged_change_digest=result.staged_change_digest,
            verified_contents_digest=result.verified_contents_digest,
            verifier_id=result.verifier_result.verifier_id,
            verdict=result.verifier_result.verdict.value,
            replay_result_digest=result.verifier_result.replay_result_digest,
            snapshot_tree_digest=result.snapshot_tree_digest,
            snapshot_origin=result.snapshot_origin,
        )
        self.assertEqual(seed.process_id, "process-local-001")
        self.assertEqual(seed.repository_id, "fixture-repository")
        self.assertEqual(seed.base_commit, "fixture-base-001")
        self.assertEqual(seed.staged_change_digest, result.staged_change_digest)
        self.assertEqual(seed.verified_contents_digest, result.verified_contents_digest)
        self.assertEqual(seed.verifier_id, "test-verifier")
        self.assertEqual(seed.verdict, "pass")
        self.assertIsNone(seed.replay_result_digest)
        self.assertIsNone(seed.snapshot_tree_digest)
        self.assertEqual(seed.snapshot_origin, "unverified_local_test")
        twin = PublicationSeed(**asdict(seed))
        self.assertEqual(twin, seed)
        serialized = json.dumps(asdict(seed))
        self.assertNotIn("seed-bound change", serialized)

    def test_seed_fields_reproduce_pinned_execution_request_and_result(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = root / "source-repository"
            shutil.copytree(ROOT / "fixtures/repository/project", repository)
            subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "add", "-A"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(repository), "-c", "user.name=Seed Test",
                    "-c", "user.email=seed@example.invalid", "commit", "--quiet", "-m",
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
                result = run_local_execution(
                    request, SeedWorker(), verifier=AcceptingVerifier(),
                    require_pinned_snapshot=True,
                )
                self.assertEqual(result.status, ExecutionStatus.VERIFIED)
                seed = PublicationSeed(
                    process_id=request.process_id,
                    repository_id=request.repository_id,
                    base_commit=request.base_commit,
                    staged_change_digest=result.staged_change_digest,
                    verified_contents_digest=result.verified_contents_digest,
                    verifier_id=result.verifier_result.verifier_id,
                    verdict=result.verifier_result.verdict.value,
                    replay_result_digest=result.verifier_result.replay_result_digest,
                    snapshot_tree_digest=result.snapshot_tree_digest,
                    snapshot_origin=result.snapshot_origin,
                )
                self.assertEqual(seed.snapshot_tree_digest, pin.tree_digest)
                self.assertEqual(
                    seed.replay_result_digest,
                    result.verifier_result.replay_result_digest,
                )
                self.assertRegex(seed.replay_result_digest, r"^sha256:[0-9a-f]{64}$")
                self.assertEqual(seed.snapshot_origin, "local_git_commit")
                self.assertEqual(seed.base_commit, commit_oid)
            finally:
                lease.close()

    def test_malformed_seed_fields_fail_without_echo(self):
        canary = "SEED-CANARY-SECRET-VALUE"
        malformed = []
        for field in ("process_id", "repository_id", "base_commit"):
            malformed.extend(
                (field, value, "publication seed: identity field is invalid")
                for value in (None, 42, "", "  ", " leading", "trailing ", f"bad\n{canary}")
            )
        for field in ("staged_change_digest", "verified_contents_digest"):
            malformed.extend(
                (field, value, "publication seed: digest is invalid")
                for value in (
                    None, 42, "", "sha256:" + "z" * 64, "a" * 64,
                    "sha256:" + "a" * 63, f"sha256:{canary}",
                )
            )
        for field in ("replay_result_digest", "snapshot_tree_digest"):
            malformed.extend(
                (field, value, "publication seed: digest is invalid")
                for value in ("", "sha256:" + "z" * 64, f"plain-{canary}")
            )
        malformed.extend(
            ("verifier_id", value, "publication seed: verifier identity is invalid")
            for value in (None, "", "has space", f"bad\n{canary}")
        )
        malformed.extend(
            ("verdict", value, "publication seed: verifier verdict is invalid")
            for value in (None, "", "PASS", "unknown", f"{canary}")
        )
        malformed.extend(
            ("snapshot_origin", value, "publication seed: snapshot origin is invalid")
            for value in (None, "", "remote_attested", f"{canary}")
        )
        for field, value, message in malformed:
            with self.subTest(field=field, value=repr(value)):
                with self.assertRaisesRegex(PublicationSeedError, f"^{message}$") as raised:
                    valid_seed(**{field: value})
                self.assertNotIn(canary, str(raised.exception))

    def test_seed_module_exposes_no_publication_capability(self):
        source = Path(seed_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = set()
        called_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add((node.module or "").lower())
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id.lower())
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr.lower())
        forbidden_modules = {
            "gateway", "broker", "actuator", "publication", "github_app",
            "authority",
        }
        self.assertTrue(
            all(
                not any(forbidden in module for module in imported_modules)
                for forbidden in forbidden_modules
            )
        )
        self.assertTrue(
            {"publish_pull_request", "publish_verified_files", "create_pull_request"}.isdisjoint(
                called_names
            )
        )

    def test_seed_module_takes_no_collaborators_and_performs_no_effects(self):
        source = Path(seed_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "build_publication_seed"
        )
        self.assertEqual(
            [argument.arg for argument in function.args.args],
            ["request", "result"],
        )
        self.assertEqual(function.args.vararg, None)
        self.assertEqual(function.args.kwarg, None)


@contextmanager
def pinned_verified_execution(process_id="process-local-001", content_marker="seed-bound change"):
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        repository = root / "source-repository"
        shutil.copytree(ROOT / "fixtures/repository/project", repository)
        subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "add", "-A"], check=True)
        subprocess.run(
            [
                "git", "-C", str(repository), "-c", "user.name=Seed Test",
                "-c", "user.email=seed@example.invalid", "commit", "--quiet", "-m",
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

            class PinnedWorker:
                def propose(self, task: WorkerInput) -> WorkerProposal:
                    original = (ROOT / "fixtures/repository/project/calculator.py").read_text()
                    return WorkerProposal((("calculator.py", original + f"\n# {content_marker}\n"),))

            result = run_local_execution(
                request, PinnedWorker(), verifier=AcceptingVerifier(),
                require_pinned_snapshot=True,
            )
            assert result.status == ExecutionStatus.VERIFIED, repr(result)
            yield request, result
        finally:
            lease.close()


class BuildPublicationSeedTests(unittest.TestCase):
    def test_matching_pinned_result_builds_single_correct_seed(self):
        with pinned_verified_execution() as (request, result):
            seed = build_publication_seed(request, result)
            expected = PublicationSeed(
                process_id=request.process_id,
                repository_id=request.repository_id,
                base_commit=request.base_commit,
                staged_change_digest=result.staged_change_digest,
                verified_contents_digest=result.verified_contents_digest,
                verifier_id=result.verifier_result.verifier_id,
                verdict="pass",
                replay_result_digest=result.verifier_result.replay_result_digest,
                snapshot_tree_digest=result.snapshot_tree_digest,
                snapshot_origin="local_git_commit",
            )
            self.assertEqual(seed, expected)
            self.assertEqual(seed.snapshot_tree_digest, request.pinned_snapshot.tree_digest)
            self.assertEqual(seed.base_commit, request.pinned_snapshot.commit_oid)
            twin = build_publication_seed(request, result)
            self.assertEqual(twin, seed)
            self.assertIsNot(twin, seed)

    def test_non_verified_status_is_rejected(self):
        with pinned_verified_execution() as (request, result):
            for status in (ExecutionStatus.PREPARED, ExecutionStatus.FAILED):
                with self.subTest(status=status):
                    with self.assertRaisesRegex(
                        PublicationSeedError,
                        "^publication seed: execution status is not verified$",
                    ):
                        build_publication_seed(request, replace(result, status=status))

    def test_fail_and_blocked_verdicts_are_rejected(self):
        with pinned_verified_execution() as (request, result):
            for verdict in (VerifierVerdict.FAIL, VerifierVerdict.BLOCKED):
                with self.subTest(verdict=verdict):
                    denied = replace(
                        result,
                        verifier_result=replace(result.verifier_result, verdict=verdict),
                    )
                    with self.assertRaisesRegex(
                        PublicationSeedError,
                        "^publication seed: verifier verdict is not pass$",
                    ):
                        build_publication_seed(request, denied)

    def test_missing_verifier_evidence_and_digests_are_rejected(self):
        with pinned_verified_execution() as (request, result):
            with self.assertRaisesRegex(
                PublicationSeedError,
                "^publication seed: verifier evidence is missing$",
            ):
                build_publication_seed(request, replace(result, verifier_result=None))
            for field in ("staged_change_digest", "verified_contents_digest"):
                with self.subTest(field=field):
                    with self.assertRaisesRegex(
                        PublicationSeedError,
                        "^publication seed: staged digest is missing$",
                    ):
                        build_publication_seed(request, replace(result, **{field: None}))

    def test_unverified_snapshot_origin_is_rejected(self):
        with pinned_verified_execution() as (request, result):
            with self.assertRaisesRegex(
                PublicationSeedError,
                "^publication seed: snapshot origin is unverified$",
            ):
                build_publication_seed(
                    request,
                    replace(
                        result,
                        snapshot_origin="unverified_local_test",
                        snapshot_tree_digest=None,
                    ),
                )

    def test_unpinned_request_is_rejected_before_verifier_evidence(self):
        unpinned = valid_request()
        unpinned_result = run_local_execution(
            unpinned, SeedWorker(), verifier=AcceptingVerifier()
        )
        self.assertEqual(unpinned_result.status, ExecutionStatus.VERIFIED)
        with self.assertRaisesRegex(
            PublicationSeedError,
            "^publication seed: pinned snapshot is required$",
        ):
            build_publication_seed(unpinned, unpinned_result)

    def test_binding_mismatch_is_rejected(self):
        with pinned_verified_execution() as (request, result):
            tampered_cases = [
                ("process", replace(
                    result.verifier_result, process_id="process-foreign-001")),
                ("base", replace(
                    result.verifier_result, base_commit="b" * 40)),
                ("tree", replace(
                    result.verifier_result,
                    snapshot_tree_digest="sha256:" + "f" * 64)),
                ("patch", replace(
                    result.verifier_result, patch_digest="sha256:" + "f" * 64)),
                ("evidence", replace(
                    result.verifier_result, evidence_digest="sha256:" + "f" * 64)),
                ("verification", replace(
                    result.verifier_result, verification_digest="sha256:" + "f" * 64)),
                ("contents", replace(
                    result.verifier_result,
                    verified_contents_digest="sha256:" + "f" * 64)),
            ]
            for label, verifier_result in tampered_cases:
                with self.subTest(binding=label):
                    with self.assertRaisesRegex(
                        PublicationSeedError,
                        "^publication seed: execution binding mismatch$",
                    ):
                        build_publication_seed(
                            request, replace(result, verifier_result=verifier_result))
            with self.subTest(binding="result-tree"):
                with self.assertRaisesRegex(
                    PublicationSeedError,
                    "^publication seed: execution binding mismatch$",
                ):
                    build_publication_seed(
                        request,
                        replace(result, snapshot_tree_digest="sha256:" + "f" * 64),
                    )

    def test_cross_pair_request_and_result_are_rejected(self):
        with pinned_verified_execution(
            process_id="process-local-001"
        ) as (first_request, _first_result):
            with pinned_verified_execution(
                process_id="process-local-002"
            ) as (second_request, second_result):
                with self.assertRaisesRegex(
                    PublicationSeedError,
                    "^publication seed: execution binding mismatch$",
                ):
                    build_publication_seed(first_request, second_result)
                with self.assertRaisesRegex(
                    PublicationSeedError,
                    "^publication seed: execution binding mismatch$",
                ):
                    build_publication_seed(second_request, _first_result)

    def test_malformed_inputs_and_errors_carry_no_raw_values(self):
        canary = "BUILD-SEED-CANARY-CONTENT"
        with pinned_verified_execution(content_marker=canary) as (request, result):
            malformed_inputs = [
                (None, result, "publication seed: execution request is invalid"),
                ("not-a-request", result, "publication seed: execution request is invalid"),
                (request, None, "publication seed: execution result is invalid"),
                (request, object(), "publication seed: execution result is invalid"),
            ]
            for bad_request, bad_result, message in malformed_inputs:
                with self.subTest(message=message):
                    with self.assertRaisesRegex(
                        PublicationSeedError, f"^{message}$"
                    ) as raised:
                        build_publication_seed(bad_request, bad_result)
                    self.assertNotIn(canary, str(raised.exception))
            with self.assertRaisesRegex(
                PublicationSeedError,
                "^publication seed: execution binding mismatch$",
            ) as raised:
                build_publication_seed(
                    request,
                    replace(
                        result,
                        verifier_result=replace(
                            result.verifier_result, process_id="process-foreign-001"),
                    ),
                )
            self.assertNotIn(canary, str(raised.exception))


class HandBuiltEvidenceRemediationTests(unittest.TestCase):
    def test_hand_built_result_with_missing_digests_is_rejected(self):
        with pinned_verified_execution() as (request, result):
            forged_verifier = replace(
                result.verifier_result,
                patch_digest=None,
                evidence_digest=None,
                verification_digest=None,
                replay_result_digest=None,
                evidence_origin="remote_attested",
            )
            forged_result = replace(
                result,
                patch_digest=None,
                evidence_digest=None,
                verification_digest=None,
                verifier_result=forged_verifier,
                evidence_origin="remote_attested",
            )
            with self.assertRaisesRegex(
                PublicationSeedError,
                "^publication seed: digest is invalid$",
            ) as raised:
                build_publication_seed(request, forged_result)
            self.assertNotIn("remote_attested", str(raised.exception))

    def test_each_missing_canonical_digest_is_rejected(self):
        with pinned_verified_execution() as (request, result):
            for field in ("patch_digest", "evidence_digest", "verification_digest"):
                with self.subTest(field=field):
                    with self.assertRaisesRegex(
                        PublicationSeedError,
                        "^publication seed: digest is invalid$",
                    ):
                        build_publication_seed(request, replace(result, **{field: None}))
                    with self.assertRaisesRegex(
                        PublicationSeedError,
                        "^publication seed: digest is invalid$",
                    ):
                        build_publication_seed(request, replace(result, **{field: "not-a-digest"}))

    def test_verifier_side_missing_digest_cannot_match(self):
        with pinned_verified_execution() as (request, result):
            for field in ("patch_digest", "evidence_digest", "verification_digest"):
                with self.subTest(field=field):
                    with self.assertRaisesRegex(
                        PublicationSeedError,
                        "^publication seed: execution binding mismatch$",
                    ):
                        build_publication_seed(
                            request,
                            replace(
                                result,
                                verifier_result=replace(result.verifier_result, **{field: None}),
                            ),
                        )

    def test_forged_evidence_origin_is_rejected(self):
        with pinned_verified_execution() as (request, result):
            with self.subTest(origin="verifier"):
                with self.assertRaisesRegex(
                    PublicationSeedError,
                    "^publication seed: evidence origin is invalid$",
                ) as raised:
                    build_publication_seed(
                        request,
                        replace(
                            result,
                            verifier_result=replace(
                                result.verifier_result, evidence_origin="remote_attested"),
                        ),
                    )
                self.assertNotIn("remote_attested", str(raised.exception))
            with self.subTest(origin="result"):
                with self.assertRaisesRegex(
                    PublicationSeedError,
                    "^publication seed: evidence origin is invalid$",
                ) as raised:
                    build_publication_seed(
                        request, replace(result, evidence_origin="remote_attested"))
                self.assertNotIn("remote_attested", str(raised.exception))

    def test_missing_or_malformed_replay_digest_is_rejected(self):
        with pinned_verified_execution() as (request, result):
            for replay in (None, "not-a-digest", "sha256:" + "z" * 64):
                with self.subTest(replay=repr(replay)):
                    with self.assertRaisesRegex(
                        PublicationSeedError,
                        "^publication seed: digest is invalid$",
                    ) as raised:
                        build_publication_seed(
                            request,
                            replace(
                                result,
                                verifier_result=replace(
                                    result.verifier_result, replay_result_digest=replay),
                            ),
                        )
                    self.assertNotIn("not-a-digest", str(raised.exception))

    def test_matching_pinned_result_still_builds_after_remediation(self):
        with pinned_verified_execution() as (request, result):
            seed = build_publication_seed(request, result)
            self.assertEqual(seed.staged_change_digest, result.staged_change_digest)
            self.assertEqual(seed.verdict, "pass")
            self.assertEqual(seed.snapshot_origin, "local_git_commit")


if __name__ == "__main__":
    unittest.main()
