from __future__ import annotations

import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from app_contracts.brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID
from scripts import export_loaded_verifier_candidate_exp1580 as candidate
from scripts import export_loaded_verifier_candidate_exp1586 as exp1586
from scripts import export_loaded_verifier_candidate_exp1587 as exp1587
from scripts import export_loaded_verifier_candidate_exp1590 as exp1590
from scripts import export_loaded_verifier_candidate_exp1593 as exp1593
from scripts import export_loaded_verifier_candidate_exp1603 as exp1603
from scripts import export_loaded_verifier_candidate_exp1607 as exp1607
from scripts import export_loaded_verifier_candidate_exp1616 as exp1616
from scripts import export_loaded_verifier_candidate_exp1619 as exp1619
from scripts import export_loaded_verifier_candidate_exp1621 as exp1621
from scripts import export_loaded_verifier_candidate_exp1623 as exp1623
from scripts import export_loaded_verifier_candidate_exp1625 as exp1625
from scripts import export_loaded_verifier_candidate_exp1627 as exp1627
from scripts import export_loaded_verifier_candidate_exp1630 as exp1630
from scripts import export_loaded_verifier_candidate_exp1632 as exp1632


_CONTAINER = "a" * 64
_BASE_ID = "sha256:" + "c" * 64


class ExportLoadedVerifierCandidateExp1580Tests(unittest.TestCase):
    @staticmethod
    def _archive(*, image_tag: str = candidate.IMAGE_TAG, os_name: str = "linux",
                 runtime_user: str = candidate.EXPECTED_USER,
                 diff_ids: list[str] | None = None) -> tuple[bytes, str, str]:
        layer_buffer = io.BytesIO()
        with tarfile.open(fileobj=layer_buffer, mode="w") as layer_tar:
            payload = b"synthetic-layer"
            info = tarfile.TarInfo("payload")
            info.size = len(payload)
            layer_tar.addfile(info, io.BytesIO(payload))
        layer = layer_buffer.getvalue()
        diff_id = "sha256:" + hashlib.sha256(layer).hexdigest()
        config = {
            "os": os_name,
            "architecture": "amd64",
            "config": {
                "User": runtime_user,
                "Entrypoint": candidate.EXPECTED_ENTRYPOINT,
            },
            "rootfs": {"type": "layers", "diff_ids": diff_ids or [diff_id]},
        }
        config_raw = json.dumps(config, separators=(",", ":")).encode("ascii")
        config_digest = "sha256:" + hashlib.sha256(config_raw).hexdigest()
        config_name = config_digest.removeprefix("sha256:") + ".json"
        manifest = [{
            "Config": config_name,
            "RepoTags": [image_tag],
            "Layers": ["layer/layer.tar"],
        }]
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as archive:
            for name, data in (
                ("manifest.json", json.dumps(manifest, separators=(",", ":")).encode()),
                (config_name, config_raw),
                ("layer/layer.tar", layer),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return output.getvalue(), config_digest, diff_id

    def _runners(self, archive: bytes, config_digest: str, diff_id: str,
                 *, tag_listing: bytes = b"", tag_remove_code: int = 0,
                 container_remove_code: int = 0,
                 image_tag: str = candidate.IMAGE_TAG,
                 build_return_code: int = 0,
                 build_stderr: bytes = b"",
                 tag_probe_output: bytes | None = None,
                 image_id: str | None = None):
        calls: list[tuple[str, ...]] = []
        after_build = False
        tag_removed = False
        inspected_id = image_id or config_digest
        tuple_output = (
            f"{inspected_id}|linux|amd64|12345|"
            f"{json.dumps([diff_id], separators=(',', ':'))}\n"
        ).encode("ascii")

        def runner(command, *, max_bytes, timeout, env):
            nonlocal after_build, tag_removed
            del max_bytes, timeout, env
            calls.append(command)
            if "image" in command and "ls" in command:
                if after_build:
                    if tag_removed:
                        return subprocess.CompletedProcess(command, 0, b"", None)
                    listing = tag_probe_output
                    if listing is None:
                        listing = (image_tag + "\n").encode("ascii") if build_return_code == 0 else b""
                    return subprocess.CompletedProcess(command, 0, listing, None)
                return subprocess.CompletedProcess(command, 0, tag_listing, None)
            if "inspect" in command and TARGET_RUNTIME_IMAGE_ID in command:
                return subprocess.CompletedProcess(
                    command, 0, (TARGET_RUNTIME_IMAGE_ID + "\n").encode(), None
                )
            if "inspect" in command and candidate.PYTHON_BASE_REF in command:
                return subprocess.CompletedProcess(
                    command, 0, (_BASE_ID + "\n").encode(), None
                )
            if "inspect" in command and image_tag in command:
                return subprocess.CompletedProcess(command, 0, tuple_output, None)
            if "create" in command:
                return subprocess.CompletedProcess(command, 0, (_CONTAINER + "\n").encode(), None)
            if "cp" in command:
                return subprocess.CompletedProcess(command, 0, b"", None)
            if "buildx" in command:
                after_build = True
                return subprocess.CompletedProcess(command, build_return_code, b"", build_stderr)
            if "rm" in command and "image" not in command:
                return subprocess.CompletedProcess(command, container_remove_code, b"", None)
            if "image" in command and "rm" in command:
                tag_removed = tag_remove_code == 0
                return subprocess.CompletedProcess(command, tag_remove_code, b"", None)
            raise AssertionError("unexpected Docker operation")

        def save_runner(command, *, max_bytes, max_stderr_bytes, timeout, env):
            del max_bytes, max_stderr_bytes, timeout, env
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, archive, b"")

        return runner, save_runner, calls

    def test_load_save_path_binds_inspect_facts_and_removes_only_new_tag(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, calls = self._runners(archive, config_digest, diff_id)
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 0)
        self.assertTrue(output.getvalue().startswith("PORTABLE_ARCHIVE_CONFIRMED|"))
        self.assertIn("--load", next(command for command in calls if "buildx" in command))
        self.assertIn(candidate.IMAGE_TAG, next(command for command in calls if "save" in command))
        self.assertIn(
            (candidate.DOCKER, "--host=" + candidate.DOCKER_HOST, "image", "rm", candidate.IMAGE_TAG),
            calls,
        )

    def test_exp1586_uses_only_its_unique_allowlisted_tag(self):
        image_tag = candidate.EXP1586_IMAGE_TAG
        archive, config_digest, diff_id = self._archive(image_tag=image_tag)
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, image_tag=image_tag
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(
                runner=runner,
                save_runner=save_runner,
                output=output,
                image_tag=image_tag,
            )
        self.assertEqual(code, 0)
        self.assertTrue(output.getvalue().startswith("PORTABLE_ARCHIVE_CONFIRMED|"))
        self.assertTrue(any("reference=" + image_tag in call for call in calls))
        self.assertTrue(any("--tag" in call and image_tag in call for call in calls))
        self.assertTrue(any("save" in call and image_tag in call for call in calls))
        self.assertTrue(any("inspect" in call and image_tag in call for call in calls))
        self.assertTrue(any("rm" in call and "image" in call and image_tag in call for call in calls))
        self.assertFalse(any(candidate.IMAGE_TAG in call for call in calls))

    def test_arbitrary_tag_refuses_before_docker(self):
        calls = []
        output = io.StringIO()

        def fail_if_called(*args, **kwargs):
            calls.append(args)
            raise AssertionError("Docker must not run")

        code = candidate.run_once(
            runner=fail_if_called,
            save_runner=fail_if_called,
            output=output,
            image_tag="agent00x-verifier:unapproved",
        )
        self.assertEqual(code, 23)
        self.assertEqual(output.getvalue(), "IMAGE_TAG_NOT_ALLOWLISTED\n")
        self.assertEqual(calls, [])

    def test_exp1586_entrypoint_binds_its_task_unique_tag(self):
        with patch.object(exp1586, "run_once", return_value=7) as run:
            self.assertEqual(exp1586.main(), 7)
        run.assert_called_once_with(image_tag="agent00x-verifier:exp-1586")

    def test_exp1587_entrypoint_binds_its_task_unique_tag(self):
        with patch.object(exp1587, "run_once", return_value=7) as run:
            self.assertEqual(exp1587.main(), 7)
        run.assert_called_once_with(image_tag="agent00x-verifier:exp-1587")

    def test_exp1590_entrypoint_binds_its_task_unique_tag(self):
        with patch.object(exp1590, "run_once", return_value=7) as run:
            self.assertEqual(exp1590.main(), 7)
        run.assert_called_once_with(image_tag="agent00x-verifier:exp-1590")

    def test_exp1590_direct_script_reaches_opt_in_guard_without_docker(self):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [
                os.sys.executable,
                str(candidate.ROOT / "scripts" / "export_loaded_verifier_candidate_exp1590.py"),
            ],
            cwd=candidate.ROOT,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, b"OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, b"")

    def test_exp1593_entrypoint_binds_its_task_unique_tag(self):
        with patch.object(exp1593, "run_once", return_value=7) as run:
            self.assertEqual(exp1593.main(), 7)
        run.assert_called_once_with(image_tag="agent00x-verifier:exp-1593")

    def test_exp1593_direct_script_reaches_opt_in_guard_without_docker(self):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [
                os.sys.executable,
                str(candidate.ROOT / "scripts" / "export_loaded_verifier_candidate_exp1593.py"),
            ],
            cwd=candidate.ROOT,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, b"OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, b"")

    def test_exp1587_direct_script_reaches_opt_in_guard_without_docker(self):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [
                os.sys.executable,
                str(candidate.ROOT / "scripts" / "export_loaded_verifier_candidate_exp1587.py"),
            ],
            cwd=candidate.ROOT,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, b"OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, b"")

    def test_existing_task_tag_stops_before_build_or_cleanup(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id,
            tag_listing=(candidate.IMAGE_TAG + "\n").encode("ascii"),
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 11)
        self.assertEqual(output.getvalue(), "PREFLIGHT_FAILED\n")
        self.assertFalse(any("buildx" in command for command in calls))
        self.assertFalse(any("image" in command and "rm" in command for command in calls))

    def test_archive_image_id_mismatch_fails_closed_and_cleans_new_tag(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, image_id="sha256:" + "d" * 64
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 17)
        self.assertEqual(
            output.getvalue(),
            "ARCHIVE_INVALID|stage=daemon-image-id-mismatch"
            "|fact=config-name-matches-content|archive=docker-legacy"
            "|legacy-config=daemon-mismatch|oci-config=absent|oci-manifest=absent\n",
        )
        self.assertTrue(any("image" in command and "rm" in command for command in calls))

    def test_archive_relation_facts_compare_both_archive_views_without_values(self):
        legacy, legacy_digest, _ = self._archive()
        self.assertEqual(
            candidate._archive_identity_relation_facts(legacy, legacy_digest),
            ("docker-legacy", "daemon-match", "absent", "absent"),
        )
        portable, portable_digest, diff_id, manifest_digest = self._oci_archive(
            candidate.EXP1625_IMAGE_TAG
        )
        self.assertEqual(
            candidate._archive_identity_relation_facts(portable, portable_digest),
            (
                "oci+docker-legacy", "daemon-match", "daemon-match",
                "daemon-mismatch",
            ),
        )
        facts = candidate._validate_archive(
            portable, manifest_digest,
            image_tag=candidate.EXP1625_IMAGE_TAG,
            expected_diff_ids=(diff_id,),
            require_portable_manifest=True,
        )
        self.assertEqual(facts.config_digest, portable_digest)
        self.assertEqual(facts.portable_manifest_digest, manifest_digest)

    def test_hybrid_archive_accepts_gzip_legacy_layer_after_oci_validation(self):
        archive, config_digest, diff_id, manifest_digest = self._oci_archive(
            candidate.EXP1632_IMAGE_TAG, legacy_layer_compressed=True
        )
        facts = candidate._validate_archive(
            archive, manifest_digest,
            image_tag=candidate.EXP1632_IMAGE_TAG,
            expected_diff_ids=(diff_id,),
            require_portable_manifest=True,
        )
        self.assertEqual(facts.config_digest, config_digest)
        self.assertEqual(facts.portable_manifest_digest, manifest_digest)

    def test_synthetic_archive_failures_emit_specific_safe_stages(self):
        cases = (
            (b"not-a-tar", "sha256:" + "0" * 64, candidate.IMAGE_TAG, (), False, "archive-layout"),
        )
        for archive, inspected, tag, expected, portable, stage in cases:
            with self.subTest(stage=stage), self.assertRaises(candidate.InvalidChain) as caught:
                candidate._validate_archive(
                    archive, inspected, image_tag=tag, expected_diff_ids=expected,
                    require_portable_manifest=portable,
                )
            self.assertEqual(caught.exception.stage, stage)

        archive, digest, diff_id = self._archive()
        with self.assertRaises(candidate.InvalidChain) as caught:
            candidate._validate_archive(
                archive, digest, image_tag="agent00x-verifier:wrong",
                expected_diff_ids=(diff_id,),
            )
        self.assertEqual(caught.exception.stage, "docker-manifest")

        with self.assertRaises(candidate.InvalidChain) as caught:
            candidate._validate_archive(
                archive, "sha256:" + "f" * 64, expected_diff_ids=(diff_id,),
            )
        self.assertEqual(caught.exception.stage, "daemon-image-id-mismatch")

        bad_platform, bad_platform_digest, platform_diff = self._archive(os_name="darwin")
        with self.assertRaises(candidate.InvalidChain) as caught:
            candidate._validate_archive(
                bad_platform, bad_platform_digest, expected_diff_ids=(platform_diff,),
            )
        self.assertEqual(caught.exception.stage, "daemon-platform-mismatch")

        bad_runtime, bad_runtime_digest, runtime_diff = self._archive(runtime_user="0:0")
        with self.assertRaises(candidate.InvalidChain) as caught:
            candidate._validate_archive(
                bad_runtime, bad_runtime_digest, expected_diff_ids=(runtime_diff,),
            )
        self.assertEqual(caught.exception.stage, "docker-config")

        wrong_layer_diff = "sha256:" + "e" * 64
        bad_diff, bad_diff_digest, actual_diff = self._archive(diff_ids=[wrong_layer_diff])
        with self.assertRaises(candidate.InvalidChain) as caught:
            candidate._validate_archive(
                bad_diff, bad_diff_digest, expected_diff_ids=(actual_diff,),
            )
        self.assertEqual(caught.exception.stage, "daemon-diff-id-mismatch")

        legacy, legacy_digest, legacy_diff = self._archive(
            image_tag=candidate.EXP1621_IMAGE_TAG
        )
        with self.assertRaises(candidate.InvalidChain) as caught:
            candidate._validate_archive(
                legacy, legacy_digest, image_tag=candidate.EXP1621_IMAGE_TAG,
                expected_diff_ids=(legacy_diff,), require_portable_manifest=True,
            )
        self.assertEqual(caught.exception.stage, "archive-format")

    def test_archive_invalid_emits_only_allowlisted_parser_stage(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, _ = self._runners(archive, config_digest, diff_id)
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.object(
            candidate, "_validate_archive",
            side_effect=candidate.InvalidChain("daemon-platform-mismatch"),
        ), patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 17)
        self.assertEqual(output.getvalue(), "ARCHIVE_INVALID|stage=daemon-platform-mismatch\n")

    def test_unknown_archive_failure_stage_is_reduced_to_generic_marker(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, _ = self._runners(archive, config_digest, diff_id)
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.object(
            candidate, "_validate_archive",
            side_effect=candidate.InvalidChain("private/path secret-token"),
        ), patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 17)
        self.assertEqual(output.getvalue(), "ARCHIVE_INVALID|stage=archive-validation\n")

    def test_archive_failure_detail_is_fixed_allowlisted_value_only(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, _ = self._runners(archive, config_digest, diff_id)
        output = io.StringIO()
        with patch.object(
            candidate, "_validate_archive",
            side_effect=candidate.InvalidChain(
                "daemon-config-digest-mismatch", safe_detail="private/path token"
            ),
        ), patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(
                runner=runner, save_runner=save_runner, output=output,
            )
        self.assertEqual(code, 17)
        self.assertEqual(
            output.getvalue(),
            "ARCHIVE_INVALID|stage=daemon-config-digest-mismatch\n",
        )

    def test_container_cleanup_failure_names_exact_owned_container(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, container_remove_code=1
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 22)
        self.assertEqual(
            output.getvalue(),
            f"CLEANUP_FAILED|resources=copy_container:{_CONTAINER}\n",
        )
        self.assertEqual(sum("rm" in call and "image" not in call for call in calls), 1)

    def test_owned_tag_cleanup_failure_names_tag(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, _ = self._runners(
            archive, config_digest, diff_id, tag_remove_code=1
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 22)
        self.assertEqual(output.getvalue(), "CLEANUP_FAILED|resources=verifier_tag\n")

    def test_build_failure_with_absent_tag_preserves_build_result(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, build_return_code=1
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 14)
        self.assertEqual(output.getvalue(), "BUILD_FAILED|reason=unknown|exit=1|stderr_bytes=0\n")
        self.assertEqual(sum("image" in call and "ls" in call for call in calls), 2)
        self.assertFalse(any("image" in call and "rm" in call for call in calls))

    def test_build_failure_with_present_tag_removes_exact_tag_once(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id,
            build_return_code=1,
            tag_probe_output=(candidate.IMAGE_TAG + "\n").encode("ascii"),
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 14)
        self.assertEqual(output.getvalue(), "BUILD_FAILED|reason=unknown|exit=1|stderr_bytes=0\n")
        self.assertEqual(
            sum("image" in call and "rm" in call and candidate.IMAGE_TAG in call for call in calls),
            1,
        )

    def test_unclassified_post_build_tag_state_fails_cleanup_closed(self):
        archive, config_digest, diff_id = self._archive()
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, tag_probe_output=b"unexpected\n"
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 22)
        self.assertEqual(output.getvalue(), "CLEANUP_FAILED|resources=verifier_tag\n")
        self.assertFalse(any("image" in call and "rm" in call for call in calls))

    def test_build_failure_reports_only_allowlisted_reason_and_stderr_length(self):
        archive, config_digest, diff_id = self._archive()
        secret_like_raw = b"failed to solve: network is disabled; private detail"
        runner, save_runner, _ = self._runners(
            archive, config_digest, diff_id,
            build_return_code=1,
            build_stderr=secret_like_raw,
        )
        output = io.StringIO()
        with patch.object(candidate, "DIFF_IDS", (diff_id,)), patch.dict(
            os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}
        ):
            code = candidate.run_once(runner=runner, save_runner=save_runner, output=output)
        self.assertEqual(code, 14)
        self.assertEqual(
            output.getvalue(),
            f"BUILD_FAILED|reason=network_dependency|exit=1|stderr_bytes={len(secret_like_raw)}\n",
        )
        self.assertNotIn("private detail", output.getvalue())

    def test_both_cleanup_failures_name_only_owned_resources(self):
        self.assertEqual(
            candidate._cleanup_failure_marker(
                container_ok=False, tag_ok=False, container_id=_CONTAINER
            ),
            f"CLEANUP_FAILED|resources=copy_container:{_CONTAINER},verifier_tag",
        )

    def test_malformed_container_id_is_never_emitted(self):
        self.assertEqual(
            candidate._cleanup_failure_marker(
                container_ok=False, tag_ok=True, container_id="not-an-id"
            ),
            "CLEANUP_FAILED|resources=copy_container",
        )

    def test_opt_in_gate_prevents_docker_operations(self):
        calls = []

        def fail_if_called(*args, **kwargs):
            calls.append(args)
            raise AssertionError("Docker must not run")

        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            code = candidate.run_once(
                runner=fail_if_called, save_runner=fail_if_called, output=output
            )
        self.assertEqual(code, 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        self.assertEqual(calls, [])

    @staticmethod
    def _oci_archive(image_tag: str, *, legacy_layer_compressed: bool = False):
        layer_buffer = io.BytesIO()
        with tarfile.open(fileobj=layer_buffer, mode="w") as layer_tar:
            payload = b"synthetic-oci-layer"
            info = tarfile.TarInfo("payload")
            info.size = len(payload)
            layer_tar.addfile(info, io.BytesIO(payload))
        layer = layer_buffer.getvalue()
        layer_digest = "sha256:" + hashlib.sha256(layer).hexdigest()
        config = {
            "os": "linux",
            "architecture": "amd64",
            "config": {
                "User": candidate.EXPECTED_USER,
                "Entrypoint": candidate.EXPECTED_ENTRYPOINT,
            },
            "rootfs": {"type": "layers", "diff_ids": [layer_digest]},
        }
        config_raw = json.dumps(config, separators=(",", ":")).encode("ascii")
        config_digest = "sha256:" + hashlib.sha256(config_raw).hexdigest()
        config_name = config_digest.removeprefix("sha256:") + ".json"
        config_descriptor = {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": config_digest,
            "size": len(config_raw),
        }
        layer_descriptor = {
            "mediaType": "application/vnd.oci.image.layer.v1.tar",
            "digest": layer_digest,
            "size": len(layer),
        }
        manifest_raw = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": config_descriptor,
                "layers": [layer_descriptor],
            },
            separators=(",", ":"),
        ).encode("ascii")
        manifest_digest = "sha256:" + hashlib.sha256(manifest_raw).hexdigest()
        manifest_name = "blobs/sha256/" + manifest_digest.removeprefix("sha256:")
        index_raw = json.dumps(
            {
                "schemaVersion": 2,
                "manifests": [
                    {
                        "mediaType": "application/vnd.oci.image.manifest.v1+json",
                        "digest": manifest_digest,
                        "size": len(manifest_raw),
                        "annotations": {
                            "org.opencontainers.image.ref.name": image_tag.rsplit(":", 1)[1]
                        },
                    }
                ],
            },
            separators=(",", ":"),
        ).encode("ascii")
        legacy_manifest = json.dumps(
            [{
                "Config": config_name,
                "RepoTags": [image_tag],
                "Layers": ["layer/layer.tar"],
            }],
            separators=(",", ":"),
        ).encode("ascii")
        legacy_layer = gzip.compress(layer, mtime=0) if legacy_layer_compressed else layer
        members = (
            ("index.json", index_raw),
            (manifest_name, manifest_raw),
            ("blobs/sha256/" + config_digest.removeprefix("sha256:"), config_raw),
            ("blobs/sha256/" + layer_digest.removeprefix("sha256:"), layer),
            ("manifest.json", legacy_manifest),
            (config_name, config_raw),
            ("layer/layer.tar", legacy_layer),
        )
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as archive:
            for name, data in members:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return output.getvalue(), config_digest, layer_digest, manifest_digest

    def test_exp1603_entrypoint_binds_offline_candidate_and_retains_tag(self):
        archive, config_digest, diff_id, manifest_digest = self._oci_archive(
            candidate.EXP1603_IMAGE_TAG
        )
        runner, save_runner, calls = self._runners(
            archive,
            config_digest,
            diff_id,
            image_tag=candidate.EXP1603_IMAGE_TAG,
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(
                runner=runner,
                save_runner=save_runner,
                output=output,
                image_tag=candidate.EXP1603_IMAGE_TAG,
                retain_tag=True,
                dynamic_diff_ids=True,
                require_portable_manifest=True,
            )
        self.assertEqual(code, 0)
        self.assertIn(f"manifest={manifest_digest}", output.getvalue())
        self.assertIn(f"config={config_digest}", output.getvalue())
        self.assertIn("|layers=1|", output.getvalue())
        self.assertIn("--network=none", next(call for call in calls if "buildx" in call))
        self.assertIn("--pull=false", next(call for call in calls if "buildx" in call))
        self.assertFalse(any("image" in call and "rm" in call for call in calls))

    def test_exp1603_refuses_legacy_archive_without_portable_manifest(self):
        archive, config_digest, diff_id = self._archive(
            image_tag=candidate.EXP1603_IMAGE_TAG
        )
        with self.assertRaises(candidate.InvalidChain):
            candidate._validate_archive(
                archive,
                config_digest,
                image_tag=candidate.EXP1603_IMAGE_TAG,
                expected_diff_ids=(diff_id,),
                require_portable_manifest=True,
            )

    def test_exp1603_entrypoint_hard_binds_tag_and_validation_mode(self):
        with patch.object(exp1603, "run_once", return_value=7) as run:
            self.assertEqual(exp1603.main(), 7)
        run.assert_called_once_with(
            image_tag=candidate.EXP1603_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1603_direct_entrypoint_stops_at_opt_in_without_docker(self):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [
                os.sys.executable,
                str(candidate.ROOT / "scripts" / "export_loaded_verifier_candidate_exp1603.py"),
            ],
            cwd=candidate.ROOT,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, b"OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, b"")

    def test_exp1607_entrypoint_binds_offline_candidate_and_retains_tag(self):
        image_tag = candidate.EXP1607_IMAGE_TAG
        archive, config_digest, diff_id, manifest_digest = self._oci_archive(image_tag)
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, image_tag=image_tag
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(
                runner=runner,
                save_runner=save_runner,
                output=output,
                image_tag=image_tag,
                retain_tag=True,
                dynamic_diff_ids=True,
                require_portable_manifest=True,
            )
        self.assertEqual(code, 0)
        self.assertIn(f"manifest={manifest_digest}", output.getvalue())
        self.assertIn(f"config={config_digest}", output.getvalue())
        self.assertIn("--tag", next(call for call in calls if "buildx" in call))
        self.assertIn(image_tag, next(call for call in calls if "buildx" in call))
        self.assertFalse(any(candidate.EXP1603_IMAGE_TAG in call for call in calls))
        self.assertFalse(any("image" in call and "rm" in call for call in calls))

    def test_exp1607_entrypoint_hard_binds_tag_and_validation_mode(self):
        with patch.object(exp1607, "run_once", return_value=7) as run:
            self.assertEqual(exp1607.main(), 7)
        run.assert_called_once_with(
            image_tag=candidate.EXP1607_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1607_direct_entrypoint_stops_at_opt_in_without_docker(self):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [
                os.sys.executable,
                str(candidate.ROOT / "scripts" / "export_loaded_verifier_candidate_exp1607.py"),
            ],
            cwd=candidate.ROOT,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, b"OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, b"")

    def test_isolated_config_links_only_unique_user_plugin(self):
        with tempfile.TemporaryDirectory() as root:
            user_plugin = str(Path(root) / "docker-buildx")
            config_dir = Path(root) / "config"
            config_dir.mkdir()
            candidate._prepare_isolated_buildx_plugin(
                str(config_dir),
                candidates=(user_plugin,),
                is_executable=lambda path: path == user_plugin,
                user_local_path=user_plugin,
            )
            link = config_dir / "cli-plugins" / "docker-buildx"
            self.assertTrue(link.is_symlink())
            self.assertEqual(os.readlink(link), user_plugin)

    def test_isolated_config_leaves_unique_system_plugin_unlinked(self):
        with tempfile.TemporaryDirectory() as root:
            system_plugin = "/usr/local/libexec/docker/cli-plugins/docker-buildx"
            candidate._prepare_isolated_buildx_plugin(
                root,
                candidates=(system_plugin,),
                is_executable=lambda path: path == system_plugin,
            )
            self.assertFalse((Path(root) / "cli-plugins").exists())

    def test_isolated_config_rejects_zero_or_multiple_plugin_candidates(self):
        with tempfile.TemporaryDirectory() as root:
            for candidates, executable in (
                (("/first",), lambda _path: False),
                (("/first", "/second"), lambda _path: True),
            ):
                with self.subTest(candidates=candidates), self.assertRaisesRegex(
                    RuntimeError, "^buildx-plugin-candidate-count$"
                ):
                    candidate._prepare_isolated_buildx_plugin(
                        root, candidates=candidates, is_executable=executable
                    )

    def test_isolated_config_rejects_existing_plugin_link(self):
        with tempfile.TemporaryDirectory() as root:
            plugin_dir = Path(root) / "cli-plugins"
            plugin_dir.mkdir()
            (plugin_dir / "docker-buildx").symlink_to("/dev/null")
            with self.assertRaisesRegex(RuntimeError, "^buildx-plugin-link-exists$"):
                candidate._prepare_isolated_buildx_plugin(
                    root,
                    candidates=("/Users/aleksandrsoldatov/.docker/cli-plugins/docker-buildx",),
                    is_executable=lambda _path: True,
                )

    def test_exp1616_entrypoint_binds_offline_candidate_and_retains_tag(self):
        image_tag = candidate.EXP1616_IMAGE_TAG
        archive, config_digest, diff_id, manifest_digest = self._oci_archive(image_tag)
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, image_tag=image_tag
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(
                runner=runner,
                save_runner=save_runner,
                output=output,
                image_tag=image_tag,
                retain_tag=True,
                dynamic_diff_ids=True,
                require_portable_manifest=True,
            )
        self.assertEqual(code, 0)
        self.assertIn(f"manifest={manifest_digest}", output.getvalue())
        self.assertIn(f"config={config_digest}", output.getvalue())
        self.assertIn("--network=none", next(call for call in calls if "buildx" in call))
        self.assertIn("--pull=false", next(call for call in calls if "buildx" in call))
        self.assertIn(image_tag, next(call for call in calls if "buildx" in call))
        self.assertFalse(any(candidate.EXP1607_IMAGE_TAG in call for call in calls))
        self.assertFalse(any("image" in call and "rm" in call for call in calls))

    def test_exp1616_entrypoint_hard_binds_tag_and_validation_mode(self):
        with patch.object(exp1616, "run_once", return_value=7) as run:
            self.assertEqual(exp1616.main(), 7)
        run.assert_called_once_with(
            image_tag=candidate.EXP1616_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1616_direct_entrypoint_stops_at_opt_in_without_docker(self):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [
                os.sys.executable,
                str(candidate.ROOT / "scripts" / "export_loaded_verifier_candidate_exp1616.py"),
            ],
            cwd=candidate.ROOT,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, b"OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, b"")

    def test_exp1619_entrypoint_binds_offline_candidate_and_retains_tag(self):
        image_tag = candidate.EXP1619_IMAGE_TAG
        archive, config_digest, diff_id, manifest_digest = self._oci_archive(image_tag)
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, image_tag=image_tag
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(
                runner=runner,
                save_runner=save_runner,
                output=output,
                image_tag=image_tag,
                retain_tag=True,
                dynamic_diff_ids=True,
                require_portable_manifest=True,
            )
        self.assertEqual(code, 0)
        self.assertIn(f"manifest={manifest_digest}", output.getvalue())
        self.assertIn(f"config={config_digest}", output.getvalue())
        self.assertIn("--network=none", next(call for call in calls if "buildx" in call))
        self.assertIn("--pull=false", next(call for call in calls if "buildx" in call))
        self.assertIn(image_tag, next(call for call in calls if "buildx" in call))
        self.assertFalse(any(candidate.EXP1616_IMAGE_TAG in call for call in calls))
        self.assertFalse(any("image" in call and "rm" in call for call in calls))

    def test_exp1619_entrypoint_hard_binds_tag_and_validation_mode(self):
        with patch.object(exp1619, "run_once", return_value=7) as run:
            self.assertEqual(exp1619.main(), 7)
        run.assert_called_once_with(
            image_tag=candidate.EXP1619_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1619_direct_entrypoint_stops_at_opt_in_without_docker(self):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [
                os.sys.executable,
                str(candidate.ROOT / "scripts" / "export_loaded_verifier_candidate_exp1619.py"),
            ],
            cwd=candidate.ROOT,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, b"OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, b"")

    def test_exp1621_entrypoint_binds_offline_candidate_and_retains_tag(self):
        image_tag = candidate.EXP1621_IMAGE_TAG
        archive, config_digest, diff_id, manifest_digest = self._oci_archive(image_tag)
        runner, save_runner, calls = self._runners(
            archive, config_digest, diff_id, image_tag=image_tag
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = candidate.run_once(
                runner=runner, save_runner=save_runner, output=output,
                image_tag=image_tag, retain_tag=True, dynamic_diff_ids=True,
                require_portable_manifest=True,
            )
        self.assertEqual(code, 0)
        self.assertIn(f"manifest={manifest_digest}", output.getvalue())
        self.assertIn(f"config={config_digest}", output.getvalue())
        self.assertIn(image_tag, next(call for call in calls if "buildx" in call))
        self.assertFalse(any("image" in call and "rm" in call for call in calls))

    def test_exp1621_wrapper_hard_binds_its_tag_and_validation_mode(self):
        with patch.object(exp1621, "run_once", return_value=9) as run:
            self.assertEqual(exp1621.main(), 9)
        run.assert_called_once_with(
            image_tag=candidate.EXP1621_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1621_direct_entrypoint_stops_at_opt_in_without_docker(self):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [os.sys.executable, str(candidate.ROOT / "scripts" / "export_loaded_verifier_candidate_exp1621.py")],
            cwd=candidate.ROOT, env=env, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, b"OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, b"")

    def test_exp1623_wrapper_binds_its_tag_and_validation_mode(self):
        with patch.object(exp1623, "run_once", return_value=9) as run:
            self.assertEqual(exp1623.main(), 9)
        run.assert_called_once_with(
            image_tag=candidate.EXP1623_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1625_wrapper_binds_its_tag_and_validation_mode(self):
        with patch.object(exp1625, "run_once", return_value=9) as run:
            self.assertEqual(exp1625.main(), 9)
        run.assert_called_once_with(
            image_tag=candidate.EXP1625_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1627_wrapper_binds_its_tag_and_validation_mode(self):
        with patch.object(exp1627, "run_once", return_value=9) as run:
            self.assertEqual(exp1627.main(), 9)
        run.assert_called_once_with(
            image_tag=candidate.EXP1627_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1630_wrapper_binds_its_tag_and_validation_mode(self):
        with patch.object(exp1630, "run_once", return_value=9) as run:
            self.assertEqual(exp1630.main(), 9)
        run.assert_called_once_with(
            image_tag=candidate.EXP1630_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )

    def test_exp1632_wrapper_binds_its_tag_and_validation_mode(self):
        with patch.object(exp1632, "run_once", return_value=9) as run:
            self.assertEqual(exp1632.main(), 9)
        run.assert_called_once_with(
            image_tag=candidate.EXP1632_IMAGE_TAG,
            retain_tag=True,
            dynamic_diff_ids=True,
            require_portable_manifest=True,
        )


if __name__ == "__main__":
    unittest.main()
