from __future__ import annotations

import hashlib
import gzip
import io
import json
import subprocess
import tarfile
import unittest
from unittest import mock

from scripts import audit_pinned_verifier_save_archive as audit


class PinnedVerifierArchiveAuditTests(unittest.TestCase):
    def make_archive(
        self,
        *,
        repo_tags=None,
        diff_ids=None,
        wrong_layer=False,
        tamper_config=False,
        config_name_override=None,
        layers_override=None,
        manifest_entries=1,
        malformed_manifest=False,
        omit_config=False,
        gzip_layers=False,
    ):
        layer_contents = [f"layer-{index}".encode() for index in range(2)]
        computed_diff_ids = [
            "sha256:" + hashlib.sha256(content).hexdigest()
            for content in layer_contents
        ]
        selected_diff_ids = computed_diff_ids if diff_ids is None else diff_ids
        config = json.dumps(
            {"rootfs": {"type": "layers", "diff_ids": selected_diff_ids}},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        config_name = hashlib.sha256(config).hexdigest() + ".json"
        image_id = "sha256:" + hashlib.sha256(config).hexdigest()
        layer_paths = [f"layer-{index}/layer.tar" for index in range(2)]
        archive_layer_contents = (
            [gzip.compress(content, mtime=0) for content in layer_contents]
            if gzip_layers
            else layer_contents
        )
        entry = {
            "Config": config_name if config_name_override is None else config_name_override,
            "RepoTags": repo_tags,
            "Layers": layer_paths if layers_override is None else layers_override,
        }
        manifest = (
            b"{"
            if malformed_manifest
            else json.dumps(
                [entry for _ in range(manifest_entries)], separators=(",", ":")
            ).encode()
        )
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as tar:
            for name, content in (
                ("manifest.json", manifest),
                *(() if omit_config else ((
                    config_name if config_name_override is None else config_name_override,
                    config + (b" " if tamper_config else b""),
                ),)),
                *zip(layer_paths, archive_layer_contents, strict=True),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
        archive = output.getvalue()
        if wrong_layer:
            mutated = io.BytesIO()
            with tarfile.open(fileobj=mutated, mode="w") as tar:
                for name, content in (
                    ("manifest.json", manifest),
                    (config_name, config),
                    (layer_paths[0], b"wrong-layer"),
                    (layer_paths[1], layer_contents[1]),
                ):
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))
            archive = mutated.getvalue()
        return archive, image_id, tuple(selected_diff_ids)

    def inspect(self, archive, image_id, diff_ids, expected_size=None):
        output = io.StringIO()
        result = audit.inspect_archive(
            archive,
            image_id=image_id,
            diff_ids=diff_ids,
            stream_size=len(archive) if expected_size is None else expected_size,
            output=output,
        )
        return result, output.getvalue()

    def test_valid_archive_confirms_config_diffids_and_layer_content(self):
        archive, image_id, diff_ids = self.make_archive()

        result, output = self.inspect(archive, image_id, diff_ids)

        self.assertEqual(result, 0)
        self.assertEqual(
            output,
            f"ARCHIVE_CONFIRMED|{image_id}|{len(archive)}|2|"
            f"config_sha256={image_id}|config_filename_stem_matches_hash=true|"
            "repo_tags=null\n",
        )

    def test_stream_size_mismatch_is_fixed_marker(self):
        archive, image_id, diff_ids = self.make_archive()

        result, output = self.inspect(archive, image_id, diff_ids, len(archive) + 1)

        self.assertEqual(result, 13)
        self.assertEqual(output, "LOCAL_IMAGE_STREAM_SIZE_MISMATCH\n")

    def test_invalid_tar_and_manifest_are_redacted(self):
        archive, image_id, diff_ids = self.make_archive(malformed_manifest=True)
        for blob, expected, code in (
            (b"SECRET_RAW_ARCHIVE", "ARCHIVE_INVALID", 14),
            (archive, "MANIFEST_INVALID", 16),
        ):
            with self.subTest(expected=expected):
                result, output = self.inspect(blob, image_id, diff_ids)
                self.assertEqual(result, code)
                self.assertEqual(output, expected + "\n")
                self.assertNotIn("SECRET", output)

    def test_manifest_shape_issues_have_distinct_fixed_markers(self):
        cases = (
            (self.make_archive(manifest_entries=2), "MANIFEST_ENTRY_COUNT_MISMATCH", 17),
            (self.make_archive(repo_tags=["private-tag"]), "MANIFEST_REPOTAGS_PRESENT", 19),
            (self.make_archive(layers_override="not-a-list"), "MANIFEST_LAYERS_INVALID", 20),
            (self.make_archive(layers_override=["one/layer.tar"]), "MANIFEST_LAYER_COUNT_MISMATCH", 21),
            (self.make_archive(layers_override=["../private", "two/layer.tar"]), "MANIFEST_LAYER_PATH_INVALID", 22),
        )
        for (archive, image_id, diff_ids), marker, code in cases:
            with self.subTest(marker=marker):
                result, output = self.inspect(archive, image_id, diff_ids)
                self.assertEqual(result, code)
                self.assertEqual(output, marker + "\n")

    def test_config_path_is_safe_but_content_must_match_image_id(self):
        archive, image_id, diff_ids = self.make_archive(
            config_name_override="metadata/alternate-config.json"
        )
        result, output = self.inspect(archive, image_id, diff_ids)
        self.assertEqual(result, 0)
        self.assertIn("ARCHIVE_CONFIRMED|", output)
        self.assertNotIn("alternate-config", output)

        archive, image_id, diff_ids = self.make_archive(
            config_name_override="../private-config.json"
        )
        result, output = self.inspect(archive, image_id, diff_ids)
        self.assertEqual(result, 18)
        self.assertEqual(output, "MANIFEST_CONFIG_PATH_INVALID\n")

        archive, image_id, diff_ids = self.make_archive(omit_config=True)
        result, output = self.inspect(archive, image_id, diff_ids)
        self.assertEqual(result, 15)
        self.assertEqual(output, "ARCHIVE_STRUCTURE_INVALID\n")

    def test_config_and_layer_content_mismatches_are_rejected(self):
        archive, image_id, diff_ids = self.make_archive(wrong_layer=True)

        result, output = self.inspect(archive, image_id, diff_ids)

        self.assertEqual(result, 25)
        self.assertEqual(output, "LAYER_DIGEST_MISMATCH\n")

        archive, image_id, diff_ids = self.make_archive(tamper_config=True)
        result, output = self.inspect(archive, image_id, diff_ids)
        self.assertEqual(result, 23)
        self.assertEqual(
            output,
            "ARCHIVE_FACTS|config_hash_matches_pin=false|"
            "config_filename_stem_matches_hash=false|diff_ids_match_pin=true|"
            "raw_layers_match_diff_ids=true|"
            "uncompressed_layers_match_diff_ids=true|gzip_layer_count=0\n",
        )

        archive, image_id, diff_ids = self.make_archive()
        wrong_diff_ids = ("sha256:" + "0" * 64, *diff_ids[1:])
        result, output = self.inspect(archive, image_id, wrong_diff_ids)
        self.assertEqual(result, 24)
        self.assertEqual(output, "DIFF_IDS_MISMATCH\n")

    def test_gzip_layer_bytes_are_decoded_before_diffid_comparison(self):
        archive, image_id, diff_ids = self.make_archive(gzip_layers=True)

        result, output = self.inspect(archive, image_id, diff_ids)

        self.assertEqual(result, 0)
        self.assertIn("ARCHIVE_CONFIRMED|", output)

        archive, image_id, diff_ids = self.make_archive(
            gzip_layers=True, tamper_config=True
        )
        result, output = self.inspect(archive, image_id, diff_ids)
        self.assertEqual(result, 23)
        self.assertIn("raw_layers_match_diff_ids=false", output)
        self.assertIn("uncompressed_layers_match_diff_ids=true", output)
        self.assertIn("gzip_layer_count=2", output)

    def test_runner_uses_one_bounded_local_save_and_never_leaks_output(self):
        archive, image_id, diff_ids = self.make_archive()
        runner = mock.Mock(return_value=subprocess.CompletedProcess((), 0, archive, b""))
        output = io.StringIO()

        result = audit.audit_local_archive(runner, output)

        self.assertEqual(result, 13)  # synthetic archive is not the pinned size
        self.assertEqual(output.getvalue(), "LOCAL_IMAGE_STREAM_SIZE_MISMATCH\n")
        runner.assert_called_once_with(
            ("/usr/local/bin/docker", "image", "save", audit.pinned.IMAGE_ID),
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertNotIn(image_id, output.getvalue())
        self.assertNotIn("SECRET", output.getvalue())

    def test_save_failure_timeout_and_launch_error_are_fixed(self):
        scenarios = (
            (mock.Mock(return_value=subprocess.CompletedProcess((), 1, b"SECRET", b"SECRET")), 10, "LOCAL_IMAGE_SAVE_FAILED"),
            (mock.Mock(side_effect=subprocess.TimeoutExpired("docker", 60, b"SECRET")), 11, "LOCAL_IMAGE_SAVE_TIMEOUT"),
            (mock.Mock(side_effect=OSError("SECRET")), 12, "LOCAL_IMAGE_SAVE_LAUNCH_FAILED"),
        )
        for runner, code, marker in scenarios:
            with self.subTest(marker=marker):
                output = io.StringIO()
                result = audit.audit_local_archive(runner, output)
                self.assertEqual(result, code)
                self.assertEqual(output.getvalue(), marker + "\n")
                self.assertNotIn("SECRET", output.getvalue())
                runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
