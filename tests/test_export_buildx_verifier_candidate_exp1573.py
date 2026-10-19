from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import unittest
from unittest.mock import patch

from app_contracts.brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID
from scripts.audit_portable_verifier_image_exp1350 import InvalidChain, OutputLimitExceeded
from scripts import export_buildx_verifier_candidate_exp1573 as candidate


_CONTAINER = "a" * 64


class BuildxVerifierCandidateTests(unittest.TestCase):
    @staticmethod
    def _docker_archive(*, tag: str | None = None, mutate_layer: bool = False) -> tuple[bytes, str]:
        layer_buffer = io.BytesIO()
        with tarfile.open(fileobj=layer_buffer, mode="w") as layer_tar:
            payload = b"x"
            info = tarfile.TarInfo("payload")
            info.size = len(payload)
            layer_tar.addfile(info, io.BytesIO(payload))
        layer = layer_buffer.getvalue()
        diff_id = "sha256:" + hashlib.sha256(layer).hexdigest()
        archive_layer = layer
        if mutate_layer:
            altered = io.BytesIO()
            with tarfile.open(fileobj=altered, mode="w") as layer_tar:
                info = tarfile.TarInfo("payload")
                info.size = 1
                layer_tar.addfile(info, io.BytesIO(b"y"))
            archive_layer = altered.getvalue()
        config = {
            "os": "linux",
            "architecture": "amd64",
            "config": {
                "User": candidate.EXPECTED_USER,
                "Entrypoint": candidate.EXPECTED_ENTRYPOINT,
            },
            "rootfs": {"type": "layers", "diff_ids": [diff_id]},
        }
        config_raw = json.dumps(config, separators=(",", ":")).encode()
        config_name = hashlib.sha256(config_raw).hexdigest() + ".json"
        manifest = [{
            "Config": config_name,
            "RepoTags": [tag or candidate.IMAGE_TAG],
            "Layers": ["layer/layer.tar"],
        }]
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as outer:
            for name, data in (
                ("manifest.json", json.dumps(manifest, separators=(",", ":")).encode()),
                (config_name, config_raw),
                ("layer/layer.tar", archive_layer),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                outer.addfile(info, io.BytesIO(data))
        return archive.getvalue(), diff_id

    def _runner(self, *, cleanup_code: int = 0, build_result: bytes = b"archive",
                build_returncode: int = 0, build_stderr: bytes = b""):
        calls: list[tuple[str, ...]] = []

        def run(command, *, max_bytes, timeout, env):
            del max_bytes, timeout, env
            calls.append(command)
            if "inspect" in command:
                return subprocess.CompletedProcess(command, 0, (TARGET_RUNTIME_IMAGE_ID + "\n").encode(), None)
            if "create" in command:
                return subprocess.CompletedProcess(command, 0, (_CONTAINER + "\n").encode(), None)
            if "cp" in command:
                return subprocess.CompletedProcess(command, 0, b"", None)
            if "rm" in command:
                return subprocess.CompletedProcess(command, cleanup_code, b"", None)
            raise AssertionError("unexpected command")

        def build(command, *, max_bytes, max_stderr_bytes, timeout, env):
            del max_bytes, max_stderr_bytes, timeout, env
            calls.append(command)
            return subprocess.CompletedProcess(
                command, build_returncode, build_result, build_stderr
            )

        return run, calls, build

    def test_command_is_one_platform_offline_archive_export_without_load(self):
        runner, calls, build_runner = self._runner()
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), patch.object(
            candidate, "_read_archive_config", return_value=("sha256:" + "b" * 64, {})
        ):
            code = candidate.run_once(runner=runner, build_runner=build_runner, output=output)
        self.assertEqual(code, 0)
        self.assertIn("BUILDX_EXPORT_CONFIRMED", output.getvalue())
        build = next(command for command in calls if "buildx" in command)
        for flag in (
            "--platform=linux/amd64", "--pull=false", "--network=none", "--no-cache",
            "--provenance=false", "--output", "type=docker,dest=-",
        ):
            self.assertIn(flag, build)
        self.assertNotIn("load", build)
        self.assertNotIn("push", build)
        self.assertEqual(calls[-1][-1], _CONTAINER)

    def test_archive_mismatch_is_fixed_marker_and_still_cleans_container(self):
        runner, calls, build_runner = self._runner()
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), patch.object(
            candidate, "_read_archive_config", side_effect=InvalidChain("archive-validation")
        ):
            code = candidate.run_once(runner=runner, build_runner=build_runner, output=output)
        self.assertEqual(code, candidate._CODES["ARCHIVE_INVALID"])
        self.assertEqual(output.getvalue(), "ARCHIVE_INVALID\n")
        self.assertEqual(calls[-1][-2:], ("--force", _CONTAINER))

    def test_output_limit_is_bounded_and_exact_temporary_container_is_removed(self):
        runner, calls, build_runner = self._runner()

        def limited_build(command, **kwargs):
            del kwargs
            calls.append(command)
            raise OutputLimitExceeded

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(
                runner=runner, build_runner=limited_build, output=output
            )
        self.assertEqual(code, candidate._CODES["EXPORT_LIMIT"])
        self.assertEqual(output.getvalue(), "EXPORT_LIMIT\n")
        self.assertTrue(any("rm" in command and command[-1] == _CONTAINER for command in calls))

    def test_cleanup_failure_is_not_reported_as_success(self):
        runner, _, build_runner = self._runner(cleanup_code=1)
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), patch.object(
            candidate, "_read_archive_config", return_value=("sha256:" + "b" * 64, {})
        ):
            code = candidate.run_once(runner=runner, build_runner=build_runner, output=output)
        self.assertEqual(code, candidate._CODES["CLEANUP_FAILED"])
        self.assertEqual(output.getvalue(), "CLEANUP_FAILED\n")

    def test_cleanup_failure_overrides_export_failure_marker(self):
        runner, _, build_runner = self._runner(
            cleanup_code=1, build_result=b"", build_returncode=2
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(runner=runner, build_runner=build_runner, output=output)
        self.assertEqual(code, candidate._CODES["CLEANUP_FAILED"])
        self.assertEqual(output.getvalue(), "CLEANUP_FAILED\n")

    def test_export_failure_is_fixed_and_container_cleanup_is_attempted(self):
        runner, calls, build_runner = self._runner(build_result=b"", build_returncode=2)
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(runner=runner, build_runner=build_runner, output=output)
        self.assertEqual(code, candidate._CODES["EXPORT_FAILED"])
        self.assertEqual(
            output.getvalue(),
            "EXPORT_FAILED|reason=unclassified_stderr|exit=2|stderr_bytes=0\n",
        )
        self.assertTrue(any("rm" in command and command[-1] == _CONTAINER for command in calls))

    def test_export_failure_class_is_fixed_and_raw_stderr_is_not_emitted(self):
        runner, _, build_runner = self._runner(
            build_result=b"", build_returncode=1,
            build_stderr=b"ERROR: exporter docker is unsupported at /private/path\n",
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(
                runner=runner, build_runner=build_runner, output=output
            )
        self.assertEqual(code, candidate._CODES["EXPORT_FAILED"])
        self.assertEqual(
            output.getvalue(),
            "EXPORT_FAILED|reason=exporter_unsupported|exit=1|stderr_bytes=55\n",
        )
        self.assertNotIn("/private/path", output.getvalue())

    def test_runner_exception_has_a_distinct_fixed_marker(self):
        runner, calls, _ = self._runner()

        def failed_build(command, **kwargs):
            del kwargs
            calls.append(command)
            raise RuntimeError("do not expose this exception")

        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(
                runner=runner, build_runner=failed_build, output=output
            )
        self.assertEqual(code, candidate._CODES["EXPORT_FAILED"])
        self.assertEqual(output.getvalue(), "EXPORT_FAILED|reason=runner_error\n")
        self.assertNotIn("do not expose", output.getvalue())

    def test_bounded_build_export_captures_both_streams(self):
        command = (
            sys.executable,
            "-c",
            "import sys;sys.stdout.buffer.write(b'archive');"
            "sys.stderr.buffer.write(b'fixed diagnostic')",
        )
        result = candidate._bounded_build_export(
            command,
            max_bytes=128,
            max_stderr_bytes=128,
            timeout=5,
            env=os.environ.copy(),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"archive")
        self.assertEqual(result.stderr, b"fixed diagnostic")

    def test_bounded_build_export_stops_on_stderr_limit(self):
        command = (
            sys.executable,
            "-c",
            "import sys;sys.stderr.buffer.write(b'x'*1024)",
        )
        with self.assertRaises(candidate.DiagnosticOutputLimitExceeded):
            candidate._bounded_build_export(
                command,
                max_bytes=128,
                max_stderr_bytes=16,
                timeout=5,
                env=os.environ.copy(),
            )

    def test_gate_prevents_all_docker_commands(self):
        runner, calls, build_runner = self._runner()
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            code = candidate.run_once(runner=runner, build_runner=build_runner, output=output)
        self.assertEqual(code, candidate._CODES["OPT_IN_REQUIRED"])
        self.assertEqual(calls, [])

    def test_real_memory_validator_accepts_a_bound_legacy_archive(self):
        archive, diff_id = self._docker_archive()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)):
            config_digest, config = candidate._read_archive_config(archive)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            manifest = json.loads(tar.extractfile("manifest.json").read())
            config_raw = tar.extractfile(manifest[0]["Config"]).read()
        self.assertEqual(config_digest, "sha256:" + hashlib.sha256(config_raw).hexdigest())
        self.assertEqual(config["os"], "linux")

    def test_real_memory_validator_rejects_tag_or_layer_mismatch(self):
        wrong_tag, diff_id = self._docker_archive(tag="agent00x-verifier:wrong")
        altered_layer, same_diff_id = self._docker_archive(mutate_layer=True)
        self.assertEqual(diff_id, same_diff_id)
        with patch.object(candidate, "DIFF_IDS", (diff_id,)):
            with self.assertRaises(InvalidChain):
                candidate._read_archive_config(wrong_tag)
            with self.assertRaises(InvalidChain):
                candidate._read_archive_config(altered_layer)


if __name__ == "__main__":
    unittest.main()
