from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app_contracts.executor import VerifierResult, VerifierVerdict
from app_contracts.signed_verifier_service import BRAINBOOSTER_VERIFIER_PROFILE
from app_contracts.verifier_classic_store import (
    ClassicStoreBrainboosterVerifier,
    create_brainbooster_classic_store_verifier_runner,
)
from app_contracts.verifier_image_pin import (
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_CONFIG_IMAGE_ID,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from app_contracts.verifier_process import VerifierProcessError
from test_verifier_container import valid_input


def _config_result(prepared):
    return VerifierResult(
        process_id=prepared.process_id,
        base_commit=prepared.base_commit,
        snapshot_tree_digest=prepared.snapshot_tree_digest,
        replay_result_digest=prepared.replay_result_digest,
        verifier_id=(
            f"docker-image:{VERIFIER_RUNTIME_CONFIG_IMAGE_ID}"
            f"/code:{VERIFIER_RUNTIME_CODE_DIGEST}"
        ),
        patch_digest=prepared.patch_digest,
        evidence_digest=prepared.evidence_digest,
        verification_digest=prepared.verification_digest,
        verified_contents_digest=prepared.verified_contents_digest,
        verdict=VerifierVerdict.PASS,
        evidence_origin=prepared.evidence_origin,
    )


def _inspect_result(*, stdout=None, returncode=0, stderr=b""):
    if stdout is None:
        stdout = f"{VERIFIER_RUNTIME_CONFIG_IMAGE_ID}|linux|amd64\n".encode("ascii")
    return stdout, stderr, returncode


class ClassicStoreBrainboosterVerifierTests(unittest.TestCase):
    def setUp(self):
        self.prepared = valid_input()
        self.runner = create_brainbooster_classic_store_verifier_runner("/usr/bin/docker")

    def test_current_classic_store_config_pin_is_exact(self):
        self.assertEqual(
            VERIFIER_RUNTIME_CONFIG_IMAGE_ID,
            "sha256:bbae0284355b7b3937a07f5a20ed7d003686aac09a1438bf0a57274bc6aa9469",
        )
        self.assertEqual(
            BRAINBOOSTER_VERIFIER_PROFILE.profile_digest,
            "sha256:d0be8d8fd547e838e22bb826ada17a6526b4a416a45e67eb94ac44358bb8628f",
        )
        self.assertEqual(
            BRAINBOOSTER_VERIFIER_PROFILE.expected_verifier_id,
            f"docker-image:{VERIFIER_RUNTIME_IMAGE_ID}/code:{VERIFIER_RUNTIME_CODE_DIGEST}",
        )

    def test_exact_config_preflight_precedes_run_and_rebinds_fixed_manifest(self):
        self.assertIs(type(self.runner), ClassicStoreBrainboosterVerifier)
        self.assertEqual(
            self.runner._inner._config.runtime_image_id,
            VERIFIER_RUNTIME_CONFIG_IMAGE_ID,
        )
        self.assertEqual(
            self.runner._inner._config.verifier_code_digest,
            VERIFIER_RUNTIME_CODE_DIGEST,
        )
        events = []

        process = object()

        def inspect(argv, **kwargs):
            events.append("inspect")
            self.assertEqual(argv, [
                "/usr/bin/docker", "--host=unix:///var/run/docker.sock",
                "image", "inspect", "--format",
                "{{.Id}}|{{.Os}}|{{.Architecture}}",
                VERIFIER_RUNTIME_CONFIG_IMAGE_ID,
            ])
            self.assertEqual(kwargs["executable"], "/usr/bin/docker")
            self.assertIs(kwargs["stdin"], subprocess.PIPE)
            self.assertIs(kwargs["stdout"], subprocess.PIPE)
            self.assertIs(kwargs["stderr"], subprocess.PIPE)
            self.assertFalse(kwargs["shell"])
            self.assertEqual(set(kwargs["env"]), {"DOCKER_CONFIG"})
            return process

        def collect(child, request, **kwargs):
            self.assertIs(child, process)
            self.assertEqual(request, b"")
            self.assertEqual(kwargs, {
                "stdout_cap": 256, "stderr_cap": 4096, "timeout_seconds": 15,
            })
            return _inspect_result()

        def run(prepared):
            events.append("run")
            self.assertIs(prepared, self.prepared)
            return _config_result(prepared)

        with (
            patch("app_contracts.verifier_classic_store.subprocess.Popen", side_effect=inspect),
            patch("app_contracts.verifier_classic_store._collect_bounded_output", side_effect=collect),
            patch.object(self.runner._inner, "verify", side_effect=run),
        ):
            result = self.runner.verify(self.prepared)
        self.assertEqual(events, ["inspect", "run"])
        self.assertEqual(result.verifier_id, BRAINBOOSTER_VERIFIER_PROFILE.expected_verifier_id)
        self.assertEqual(BRAINBOOSTER_VERIFIER_PROFILE.verifier_image_id, VERIFIER_RUNTIME_IMAGE_ID)

    def test_inspect_mismatch_or_failure_never_runs_container(self):
        cases = (
            _inspect_result(stdout=b"sha256:" + b"0" * 64 + b"|linux|amd64\n"),
            _inspect_result(stdout=f"{VERIFIER_RUNTIME_CONFIG_IMAGE_ID}|linux|arm64\n".encode()),
            _inspect_result(stdout=f"{VERIFIER_RUNTIME_CONFIG_IMAGE_ID}|linux|amd64\n\n".encode()),
            _inspect_result(returncode=1),
            _inspect_result(stdout=b""),
        )
        for inspected in cases:
            with self.subTest(inspected=inspected[2]):
                with (
                    patch("app_contracts.verifier_classic_store.subprocess.Popen") as popen,
                    patch("app_contracts.verifier_classic_store._collect_bounded_output", return_value=inspected) as collect,
                    patch.object(self.runner._inner, "verify") as run,
                ):
                    with self.assertRaisesRegex(
                        VerifierProcessError, "exact config identity unavailable"
                    ):
                        self.runner.verify(self.prepared)
                    popen.assert_called_once()
                    collect.assert_called_once()
                    run.assert_not_called()

    def test_inspect_exception_and_wrong_input_fail_closed(self):
        with patch("app_contracts.verifier_classic_store.subprocess.Popen") as inspect:
            with self.assertRaises(VerifierProcessError):
                self.runner.verify(object())
            inspect.assert_not_called()
        with (
            patch("app_contracts.verifier_classic_store.subprocess.Popen", side_effect=OSError("private path")),
            patch.object(self.runner._inner, "verify") as run,
        ):
            with self.assertRaises(VerifierProcessError) as raised:
                self.runner.verify(self.prepared)
            self.assertNotIn("private path", str(raised.exception))
            run.assert_not_called()
        with (
            patch("app_contracts.verifier_classic_store.subprocess.Popen"),
            patch(
                "app_contracts.verifier_classic_store._collect_bounded_output",
                side_effect=VerifierProcessError("private child output"),
            ),
            patch.object(self.runner._inner, "verify") as run,
        ):
            with self.assertRaises(VerifierProcessError) as raised:
                self.runner.verify(self.prepared)
            self.assertNotIn("private child output", str(raised.exception))
            run.assert_not_called()

    def test_wrong_inner_identity_or_result_binding_never_promotes(self):
        for result in (
            replace(_config_result(self.prepared), verifier_id="docker-image:untrusted"),
            replace(_config_result(self.prepared), patch_digest="sha256:" + "0" * 64),
        ):
            with self.subTest(verifier_id=result.verifier_id):
                with (
                    patch("app_contracts.verifier_classic_store.subprocess.Popen"),
                    patch("app_contracts.verifier_classic_store._collect_bounded_output", return_value=_inspect_result()),
                    patch.object(self.runner._inner, "verify", return_value=result),
                ):
                    with self.assertRaises(VerifierProcessError):
                        self.runner.verify(self.prepared)

    def test_factory_rejects_untrusted_executable_without_subprocess(self):
        with patch("app_contracts.verifier_classic_store.subprocess.Popen") as inspect:
            with self.assertRaises(VerifierProcessError):
                create_brainbooster_classic_store_verifier_runner("docker")
            inspect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
