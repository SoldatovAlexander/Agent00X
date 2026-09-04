from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.digests import sha256_digest
from app_contracts.repository_process import prepare_change
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
