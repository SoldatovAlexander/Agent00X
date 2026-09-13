from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.digests import sha256_bytes, sha256_digest
from app_contracts.repository_process import (
    PublishableFile,
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

    def test_malformed_preparation_clocks_denied_before_workspace_writes(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        naive = datetime(2026, 9, 4, 12, 0)
        for bad in (False, 0, "", "2026-09-04T12:00:00Z", 123, naive, (2026, 9, 4)):
            with self.subTest(now=repr(bad)):
                sandbox = self.backend.create(self.fixture, {"python3"})
                self.addCleanup(sandbox.close)
                with self.assertRaisesRegex(
                    ContractValidationError, "preparation timestamp must be timezone-aware"
                ):
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes={"calculator.py": self.new_calculator},
                        test_command=["python3", "-m", "unittest", "-v"],
                        now=bad,
                    )
                self.assertEqual(
                    (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), original
                )
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
        )
        self.assertEqual(result.verification_report["verdict"], "pass")

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

    def test_non_string_content_rejected_before_any_write(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        bad_values = [b"bytes-content", None, 123, ["nested"]]
        for bad in bad_values:
            with self.subTest(kind=type(bad).__name__):
                sandbox = self.backend.create(self.fixture, {"python3"})
                self.addCleanup(sandbox.close)
                with self.assertRaisesRegex(
                    ContractValidationError, "proposed content is not text"
                ) as raised:
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes={"calculator.py": self.new_calculator, "test_calculator.py": bad},
                        test_command=["python3", "-m", "unittest", "-v"],
                    )
                self.assertNotIn(str(bad)[:20], str(raised.exception))
                self.assertEqual(
                    (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), original
                )
                self.assertEqual(
                    sorted(path.name for path in sandbox.workspace.iterdir()),
                    ["calculator.py", "test_calculator.py"],
                )

    def test_manifest_request_duplicate_spellings_are_denied(self):
        sandbox, result = self.prepare()
        with self.assertRaisesRegex(ContractValidationError, "duplicate paths"):
            build_publish_manifest(
                sandbox, result,
                {"calculator.py": self.new_calculator, "calculator.py/": self.new_calculator},
            )
        manifest = build_publish_manifest(sandbox, result, {"calculator.py": self.new_calculator})
        self.assertEqual([item.path for item in manifest], ["calculator.py"])

    def test_non_text_publishable_content_rejected_without_output(self):
        for bad in (b"bytes-content", None, 123):
            with self.subTest(kind=type(bad).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "content is not text"
                ):
                    PublishableFile("calculator.py", bad, "sha256:" + "a" * 64)
        manifest_item = PublishableFile(
            "calculator.py", self.new_calculator,
            sha256_bytes(self.new_calculator.encode("utf-8")),
        )
        self.assertEqual(manifest_item.content, self.new_calculator)

    def test_absolute_paths_denied_before_output(self):
        sandbox, result = self.prepare()
        for absolute in ("/etc/passwd", "/tmp/evil.py", str(sandbox.workspace / "calculator.py")):
            with self.subTest(path=absolute):
                with self.assertRaisesRegex(ContractValidationError, "unsafe relative path"):
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes={absolute: "evil"},
                        test_command=["python3", "-m", "unittest", "-v"],
                    )
                with self.assertRaisesRegex(ContractValidationError, "unsafe relative path"):
                    build_publish_manifest(sandbox, result, {absolute: "evil"})
        manifest = build_publish_manifest(sandbox, result, {"calculator.py": self.new_calculator})
        self.assertEqual([item.path for item in manifest], ["calculator.py"])

    def test_whitespace_padded_paths_denied_without_mutation(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        for unsafe in (" calculator.py", "calculator.py ", "\tcalculator.py", "calculator.py\n"):
            with self.subTest(path=repr(unsafe)):
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
                    (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), original
                )
        self.assertEqual(_safe_relative_path("my dir/file.txt").as_posix(), "my dir/file.txt")

    def test_malformed_mapping_keys_denied_without_output(self):
        sandbox, result = self.prepare()
        for bad_changes in ({123: "x"}, {None: "x"}, [("calculator.py", "x")], "calculator.py"):
            with self.subTest(changes=type(bad_changes).__name__):
                with self.assertRaises(ContractValidationError):
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes=bad_changes,
                        test_command=["python3", "-m", "unittest", "-v"],
                    )
                with self.assertRaises(ContractValidationError):
                    build_publish_manifest(sandbox, result, bad_changes)
        self.assertEqual(
            (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), self.new_calculator
        )
        manifest = build_publish_manifest(sandbox, result, {"calculator.py": self.new_calculator})
        self.assertEqual([item.path for item in manifest], ["calculator.py"])

    def test_malformed_prepared_change_denied_without_output(self):
        sandbox, result = self.prepare()
        for bad in (None, {"patch": "x"}, ["prepared"], "prepared", 42):
            with self.subTest(prepared=type(bad).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "^publish manifest prepared change is invalid$"
                ):
                    build_publish_manifest(sandbox, bad, {"calculator.py": self.new_calculator})
        self.assertEqual(
            (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), self.new_calculator
        )
        manifest = build_publish_manifest(sandbox, result, {"calculator.py": self.new_calculator})
        self.assertEqual([item.path for item in manifest], ["calculator.py"])

    def test_malformed_test_command_denied_before_writes(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        for bad in (None, 123, "python3 -m unittest", b"python3", [], [None], ["python3", 42]):
            with self.subTest(command=type(bad).__name__):
                sandbox = self.backend.create(self.fixture, {"python3"})
                self.addCleanup(sandbox.close)
                with self.assertRaisesRegex(
                    ContractValidationError, "^test command is malformed$"
                ):
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes={"calculator.py": self.new_calculator},
                        test_command=bad,
                    )
                self.assertEqual(
                    (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"), original
                )
                self.assertEqual(
                    sorted(path.name for path in sandbox.workspace.iterdir()),
                    ["calculator.py", "test_calculator.py"],
                )

    def test_malformed_metadata_leaves_workspace_untouched(self):
        original = (self.fixture / "calculator.py").read_text(encoding="utf-8")
        base_kwargs = {
            "process_id": "process-m1-demo",
            "task_id": "task-m1-demo",
            "repository_id": "github-installation/42/repository/1001",
            "base_commit": "a" * 40,
        }
        for field in ("process_id", "task_id", "repository_id", "base_commit"):
            for bad in (None, 123, ""):
                with self.subTest(field=field, value=bad):
                    kwargs = dict(base_kwargs)
                    kwargs[field] = bad
                    sandbox = self.backend.create(self.fixture, {"python3"})
                    self.addCleanup(sandbox.close)
                    with self.assertRaisesRegex(
                        ContractValidationError, f"preparation {field} is invalid"
                    ):
                        prepare_change(
                            sandbox,
                            changes={"calculator.py": self.new_calculator},
                            test_command=["python3", "-m", "unittest", "-v"],
                            **kwargs,
                        )
                    self.assertEqual(
                        (sandbox.workspace / "calculator.py").read_text(encoding="utf-8"),
                        original,
                    )

    def test_malformed_sandbox_denied_before_writes_or_execution(self):
        class NoRunSandbox:
            snapshot = Path("/nonexistent-snapshot")
            workspace = Path("/nonexistent-workspace")

        for bad in (None, "sandbox", 42, NoRunSandbox()):
            with self.subTest(sandbox=type(bad).__name__):
                with self.assertRaisesRegex(
                    ContractValidationError, "^preparation sandbox is malformed$"
                ):
                    prepare_change(
                        bad,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes={"calculator.py": self.new_calculator},
                        test_command=["python3", "-m", "unittest", "-v"],
                    )

    def test_malformed_command_result_denied_without_staged_result(self):
        from types import SimpleNamespace
        malformed = [
            None,
            SimpleNamespace(returncode="0", stdout="", stderr=""),
            SimpleNamespace(returncode=None, stdout="", stderr=""),
            SimpleNamespace(returncode=True, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout=None, stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=123),
            SimpleNamespace(returncode=0, stdout=""),
            "passed",
        ]
        for bad in malformed:
            with self.subTest(result=type(bad).__name__):
                sandbox = self.backend.create(self.fixture, {"python3"})
                self.addCleanup(sandbox.close)
                sandbox.run = lambda *args, **kwargs: bad
                with self.assertRaisesRegex(
                    ContractValidationError, "^test result is malformed$"
                ):
                    prepare_change(
                        sandbox,
                        process_id="process-m1-demo",
                        task_id="task-m1-demo",
                        repository_id="github-installation/42/repository/1001",
                        base_commit="a" * 40,
                        changes={"calculator.py": self.new_calculator},
                        test_command=["python3", "-m", "unittest", "-v"],
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
