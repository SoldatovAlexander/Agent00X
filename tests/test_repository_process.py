from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.repository_process import (
    _safe_relative_path,
    build_publish_manifest,
    prepare_change,
)
from app_contracts.sandbox import LocalProcessSandboxBackend
from app_contracts.validator import ContractValidationError, validate


def load_schema(name: str) -> dict:
    with (ROOT / "schemas" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


class RepositoryProcessTests(unittest.TestCase):
    def setUp(self):
        self.backend = LocalProcessSandboxBackend()
        self.fixture = ROOT / "fixtures" / "repository" / "project"
        self.new_calculator = (
            '"""Tiny repository fixture used by the repository-change process tests."""\n\n\n'
            "def add(left: int, right: int) -> int:\n"
            "    return left + right\n\n\n"
            "def subtract(left: int, right: int) -> int:\n"
            "    return left - right\n"
        )

    def prepare(self):
        sandbox = self.backend.create(self.fixture, {"python3"})
        self.addCleanup(sandbox.close)
        result = prepare_change(
            sandbox,
            process_id="process-m1-demo",
            task_id="task-m1-demo",
            repository_id="github-installation/42/repository/1001",
            base_commit="a" * 40,
            changes={"calculator.py": self.new_calculator},
            test_command=["python3", "-m", "unittest", "-v"],
            now=datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
        )
        return sandbox, result

    def test_prepares_schema_valid_evidence_verification_and_stage(self):
        _, result = self.prepare()
        validate(result.evidence_bundle, load_schema("evidence-bundle.schema.json"))
        validate(result.verification_report, load_schema("verification-report.schema.json"))
        validate(result.staged_change, load_schema("staged-change.schema.json"))
        self.assertEqual(result.verification_report["verdict"], "pass")
        self.assertEqual(result.staged_change["evidence_digest"], sha256_digest(result.evidence_bundle))
        self.assertEqual(result.staged_change["verification_digest"], sha256_digest(result.verification_report))
        self.assertIn("+def subtract", result.patch)

    def test_original_snapshot_is_not_modified(self):
        sandbox, _ = self.prepare()
        self.assertNotIn("def subtract", (sandbox.snapshot / "calculator.py").read_text())
        self.assertNotIn("def subtract", (self.fixture / "calculator.py").read_text())
        self.assertIn("def subtract", (sandbox.workspace / "calculator.py").read_text())

    def test_publish_manifest_exports_only_verified_workspace_content(self):
        sandbox, result = self.prepare()
        manifest = build_publish_manifest(sandbox, result, {"calculator.py": self.new_calculator})
        self.assertEqual(manifest[0].path, "calculator.py")
        self.assertEqual(manifest[0].content_digest, sha256_bytes(self.new_calculator.encode("utf-8")))
        (sandbox.workspace / "calculator.py").write_text("mutated", encoding="utf-8")
        with self.assertRaisesRegex(ContractValidationError, "content changed"):
            build_publish_manifest(sandbox, result, {"calculator.py": self.new_calculator})

    def test_publish_manifest_rejects_resubmitted_mapping_with_new_content(self):
        sandbox, result = self.prepare()
        tampered = self.new_calculator + "# tampered-after-verification\n"
        (sandbox.workspace / "calculator.py").write_text(tampered, encoding="utf-8")
        with self.assertRaisesRegex(ContractValidationError, "verified workspace content changed"):
            build_publish_manifest(sandbox, result, {"calculator.py": tampered})

    def test_publish_manifest_rejects_empty_and_unfixed_file_lists(self):
        sandbox, result = self.prepare()
        with self.assertRaisesRegex(ContractValidationError, "empty"):
            build_publish_manifest(sandbox, result, {})
        with self.assertRaisesRegex(ContractValidationError, "does not match verified"):
            build_publish_manifest(
                sandbox, result, {"calculator.py": self.new_calculator, "extra.py": "unverified"}
            )
        with self.assertRaisesRegex(ContractValidationError, "does not match verified"):
            build_publish_manifest(sandbox, result, {"other.py": self.new_calculator})

    def test_publish_manifest_ignores_resubmitted_mapping_values(self):
        sandbox, result = self.prepare()
        manifest = build_publish_manifest(sandbox, result, {"calculator.py": "stale-or-forged-value"})
        self.assertEqual(manifest[0].content, self.new_calculator)
        self.assertEqual(manifest[0].content_digest, sha256_bytes(self.new_calculator.encode("utf-8")))

    def prepare_many(self):
        new_tests = (
            "import unittest\n\n"
            "from calculator import add, subtract\n\n\n"
            "class CalculatorTests(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n\n"
            "    def test_subtract(self):\n"
            "        self.assertEqual(subtract(5, 3), 2)\n\n\n"
            'if __name__ == "__main__":\n'
            "    unittest.main()\n"
        )
        changes = {"calculator.py": self.new_calculator, "test_calculator.py": new_tests}
        sandbox = self.backend.create(self.fixture, {"python3"})
        self.addCleanup(sandbox.close)
        result = prepare_change(
            sandbox,
            process_id="process-m1-demo",
            task_id="task-m1-demo",
            repository_id="github-installation/42/repository/1001",
            base_commit="a" * 40,
            changes=dict(reversed(list(changes.items()))),
            test_command=["python3", "-m", "unittest", "-v"],
            now=datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
        )
        return sandbox, result, changes

    def test_publish_manifest_multi_file_is_deterministic_by_path_order(self):
        sandbox, result, changes = self.prepare_many()
        first = build_publish_manifest(sandbox, result, changes)
        second = build_publish_manifest(
            sandbox, result, dict(reversed(list(changes.items())))
        )
        self.assertEqual([item.path for item in first], ["calculator.py", "test_calculator.py"])
        self.assertEqual(first, second)
        expected = {
            name: sha256_bytes(content.encode("utf-8")) for name, content in changes.items()
        }
        for item in first:
            self.assertEqual(item.content_digest, expected[item.path])

    def test_publish_manifest_multi_file_rejects_missing_or_extra_path(self):
        sandbox, result, changes = self.prepare_many()
        partial = {"calculator.py": changes["calculator.py"]}
        with self.assertRaisesRegex(ContractValidationError, "does not match verified"):
            build_publish_manifest(sandbox, result, partial)
        extra = dict(changes)
        extra["extra.py"] = "unverified"
        with self.assertRaisesRegex(ContractValidationError, "does not match verified"):
            build_publish_manifest(sandbox, result, extra)

    def test_publish_manifest_rejects_single_file_tamper(self):
        sandbox, result, changes = self.prepare_many()
        (sandbox.workspace / "test_calculator.py").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ContractValidationError, "verified workspace content changed"):
            build_publish_manifest(sandbox, result, changes)

    def test_unsafe_path_variants_leave_workspace_untouched(self):
        for unsafe in ("./calculator.py", "pkg//calculator.py", "dir\\calculator.py", "../escape.py"):
            with self.subTest(path=unsafe):
                sandbox = self.backend.create(self.fixture, {"python3"})
                self.addCleanup(sandbox.close)
                with self.assertRaisesRegex(ContractValidationError, "unsafe relative path"):
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes={unsafe: "evil"},
                        test_command=["python3", "-m", "unittest", "-v"],
                    )
                self.assertEqual(
                    sorted(path.name for path in sandbox.workspace.iterdir()),
                    ["calculator.py", "test_calculator.py"],
                )

    def test_normal_nested_relative_path_stays_accepted(self):
        self.assertEqual(_safe_relative_path("pkg/mod.py").as_posix(), "pkg/mod.py")

    def test_empty_and_noop_changes_build_nothing(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        for changes in ({}, {"calculator.py": original}):
            with self.subTest(changes=sorted(changes)):
                sandbox = self.backend.create(self.fixture, {"python3"})
                self.addCleanup(sandbox.close)
                with self.assertRaises(ContractValidationError):
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes=changes,
                        test_command=["python3", "-m", "unittest", "-v"],
                    )
                self.assertEqual(
                    (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), original
                )
                self.assertEqual(
                    sorted(path.name for path in sandbox.workspace.iterdir()),
                    ["calculator.py", "test_calculator.py"],
                )

    def test_conflicting_duplicate_path_leaves_workspace_unchanged(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        sandbox = self.backend.create(self.fixture, {"python3"})
        self.addCleanup(sandbox.close)
        with self.assertRaisesRegex(ContractValidationError, "duplicate workspace path"):
            prepare_change(
                sandbox,
                process_id="process-m1-demo",
                task_id="task-m1-demo",
                repository_id="github-installation/42/repository/1001",
                base_commit="a" * 40,
                changes={"calculator.py": self.new_calculator, "calculator.py/": self.new_calculator},
                test_command=["python3", "-m", "unittest", "-v"],
            )
        self.assertEqual(
            (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), original
        )

    def test_late_failing_entry_leaves_workspace_unchanged(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        sandbox = self.backend.create(self.fixture, {"python3"})
        self.addCleanup(sandbox.close)
        with self.assertRaisesRegex(ContractValidationError, "source file is unavailable"):
            prepare_change(
                sandbox,
                process_id="process-m1-demo",
                task_id="task-m1-demo",
                repository_id="github-installation/42/repository/1001",
                base_commit="a" * 40,
                changes={"calculator.py": self.new_calculator, "pkg/": "evil"},
                test_command=["python3", "-m", "unittest", "-v"],
            )
        self.assertEqual(
            (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), original
        )
        self.assertEqual(
            sorted(path.name for path in sandbox.workspace.iterdir()),
            ["calculator.py", "test_calculator.py"],
        )

    def test_equivalent_unsafe_paths_denied_without_host_leak_or_mutation(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        variants = (
            "./calculator.py", "pkg//calculator.py", "dir\\calculator.py",
            "../escape.py", "a/./b.py", "a/b/", "/abs.py", "a/b/.",
        )
        for unsafe in variants:
            with self.subTest(path=unsafe):
                sandbox = self.backend.create(self.fixture, {"python3"})
                self.addCleanup(sandbox.close)
                with self.assertRaises(ContractValidationError) as raised:
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes={unsafe: "evil"},
                        test_command=["python3", "-m", "unittest", "-v"],
                    )
                message = str(raised.exception)
                self.assertNotIn(str(sandbox.workspace), message)
                self.assertNotIn(str(sandbox.snapshot), message)
                self.assertEqual(
                    (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), original
                )
                self.assertEqual(
                    sorted(path.name for path in sandbox.workspace.iterdir()),
                    ["calculator.py", "test_calculator.py"],
                )

    def test_path_traversal_is_rejected(self):
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            with self.assertRaisesRegex(ContractValidationError, "unsafe relative path"):
                prepare_change(
                    sandbox,
                    process_id="process-m1-demo",
                    task_id="task-m1-demo",
                    repository_id="github-installation/42/repository/1001",
                    base_commit="a" * 40,
                    changes={"../escape.py": "bad"},
                    test_command=["python3", "-m", "unittest"],
                )

    def test_failed_tests_do_not_create_staged_change(self):
        broken = self.new_calculator.replace("return left + right", "return left - right")
        with self.backend.create(self.fixture, {"python3"}) as sandbox:
            with self.assertRaisesRegex(ContractValidationError, "verification failed"):
                prepare_change(
                    sandbox,
                    process_id="process-m1-demo",
                    task_id="task-m1-demo",
                    repository_id="github-installation/42/repository/1001",
                    base_commit="a" * 40,
                    changes={"calculator.py": broken},
                    test_command=["python3", "-m", "unittest", "-v"],
                )


if __name__ == "__main__":
    unittest.main()
