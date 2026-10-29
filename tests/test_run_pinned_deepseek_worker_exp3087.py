from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest import mock

from scripts import run_pinned_deepseek_worker_exp3087 as profile
from scripts import run_pinned_deepseek_worker_exp1893 as shared_profile


class RunPinnedDeepSeekWorkerExp3087Tests(unittest.TestCase):
    def test_profile_is_exact_local_credential_free_worker_run(self):
        now = datetime(2026, 10, 29, 19, 0, tzinfo=timezone.utc)
        with mock.patch.object(profile, "run_profile", return_value=0) as runner:
            result = profile.main([], now=now)
        self.assertEqual(result, 0)
        args, kwargs = runner.call_args
        self.assertEqual(args[:4], (
            "EXP-3087",
            "RUN EXP-3087 ONCE",
            "process-exp-3087-local-001",
            "task-exp-3087-local-001",
        ))
        self.assertEqual(args[4], profile.AUTHORIZATION_EXPIRES_AT)
        self.assertEqual(args[5], profile.PINNED_ARGUMENTS)
        self.assertEqual(kwargs["now"], now)
        self.assertEqual(kwargs["runtime_metrics_path"], profile.RUNTIME_METRICS_PATH)
        self.assertIn("--model-backend", profile.PINNED_ARGUMENTS)
        self.assertIn("local-ollama", profile.PINNED_ARGUMENTS)
        self.assertIn("--credential-source", profile.PINNED_ARGUMENTS)
        self.assertIn("not-applicable", profile.PINNED_ARGUMENTS)
        self.assertIn("--worker-backend", profile.PINNED_ARGUMENTS)
        self.assertIn("restricted-container", profile.PINNED_ARGUMENTS)
        self.assertIn("--verifier-backend", profile.PINNED_ARGUMENTS)
        self.assertIn("pinned-docker", profile.PINNED_ARGUMENTS)

    def test_expired_profile_never_reaches_runner(self):
        with mock.patch.object(shared_profile.worker_cli, "main") as runner:
            result = profile.main([], now=profile.AUTHORIZATION_EXPIRES_AT)
        self.assertEqual(result, 2)
        runner.assert_not_called()

    def test_additional_arguments_are_rejected_before_runner(self):
        with mock.patch.object(profile, "run_profile") as runner:
            result = profile.main(["--model-backend", "deepseek"])
        self.assertEqual(result, 2)
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
