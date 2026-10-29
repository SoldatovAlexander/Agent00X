from __future__ import annotations

import io
import hashlib
import json
import subprocess
import tarfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from scripts import stream_pinned_target_image_exp3066 as transfer


def completed(stdout=b"", returncode=0):
    return subprocess.CompletedProcess(args=(), returncode=returncode, stdout=stdout, stderr=b"")


class TargetImageTransferTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.before_expiry = datetime(2026, 10, 29, 19, 0, tzinfo=timezone.utc)

    def fake_run(self, *, inspect=None, saved=None, ssh=None, host_check=True, now=None):
        inspect = completed((transfer.EXPECTED_LOCAL + "\n").encode()) if inspect is None else inspect
        saved = completed(b"x" * transfer.STREAM_SIZE) if saved is None else saved
        ssh = completed(b"EXP3066_IMAGE_IMPORT_CONFIRMED\n") if ssh is None else ssh
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            if command[0] == "/usr/local/bin/docker" and command[2] == "inspect": return inspect
            if command[0] == "/usr/local/bin/docker" and command[2] == "save": return saved
            if command[0] == "/usr/bin/ssh": return ssh
            raise AssertionError("unexpected command")
        with mock.patch.object(transfer, "STREAM_SHA256", "".join(["x"]*64)), \
             mock.patch.object(transfer, "_reserve_attempt"):
            # The fake stream hash is matched by the injected hashlib result below.
            with mock.patch.object(transfer.hashlib, "sha256", return_value=mock.Mock(hexdigest=lambda: "x"*64)):
                status = transfer.run_once(runner=runner, output=self.output,
                    host_check=lambda: host_check,
                    archive_validator=lambda _stream: True,
                    now=now or self.before_expiry)
        return status, calls

    def test_exact_one_ssh_stream_and_fixed_success(self):
        status, calls = self.fake_run()
        self.assertEqual(status, 0)
        self.assertEqual(self.output.getvalue(), "IMAGE_IMPORT_CONFIRMED\n")
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][0], ("/usr/local/bin/docker", "image", "save", transfer.TARGET_RUNTIME_IMAGE_ID))
        self.assertEqual(calls[2][1]["input"], b"x" * transfer.STREAM_SIZE)
        self.assertIn("-oStrictHostKeyChecking=yes", calls[2][0])
        self.assertIn("-oForwardAgent=no", calls[2][0])
        self.assertIn(transfer.TARGET_CONFIG_IMAGE_ID, calls[2][0][-1])

    def test_local_inspect_failure_stops_before_save_or_ssh(self):
        status, calls = self.fake_run(inspect=completed(returncode=1))
        self.assertEqual(status, transfer._CODES["LOCAL_IMAGE_INSPECT_FAILED"])
        self.assertEqual(len(calls), 1)

    def test_mismatched_local_identity_stops(self):
        status, calls = self.fake_run(inspect=completed(b"different\n"))
        self.assertEqual(status, transfer._CODES["LOCAL_IMAGE_IDENTITY_MISMATCH"])
        self.assertEqual(len(calls), 1)

    def test_wrong_archive_digest_stops_before_attempt_marker_or_ssh(self):
        with mock.patch.object(transfer, "_reserve_attempt") as reserve:
            with mock.patch.object(transfer.hashlib, "sha256", return_value=mock.Mock(hexdigest=lambda: "0"*64)):
                status = transfer.run_once(
                    runner=lambda command, **kwargs: completed((transfer.EXPECTED_LOCAL+"\n").encode())
                        if command[2] == "inspect" else completed(b"x"*transfer.STREAM_SIZE),
                    output=self.output, host_check=lambda: True, now=self.before_expiry,
                )
        self.assertEqual(status, transfer._CODES["LOCAL_ARCHIVE_PIN_MISMATCH"])
        reserve.assert_not_called()

    @staticmethod
    def make_archive(diff_ids=None):
        diff_ids = list(transfer.DIFF_IDS if diff_ids is None else diff_ids)
        config = json.dumps({"rootfs": {"diff_ids": diff_ids}}, separators=(",", ":")).encode()
        image_id = "sha256:" + hashlib.sha256(config).hexdigest()
        # Containerd-backed source pins the OCI manifest digest as its daemon
        # image ID; Docker-save's config file can therefore have a separate ID.
        config_name = transfer.TARGET_RUNTIME_IMAGE_ID.removeprefix("sha256:") + ".json"
        manifest = json.dumps([{"Config": config_name, "RepoTags": None, "Layers": [f"layer-{i}/layer.tar" for i in range(6)]}]).encode()
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:") as archive:
            for name, payload in (("manifest.json", manifest), (config_name, config), *((f"layer-{i}/layer.tar", b"layer") for i in range(6))):
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
        return stream.getvalue(), image_id

    def test_archive_content_validator_binds_distinct_config_digest_and_ordered_diffids(self):
        archive, config_id = self.make_archive()
        self.assertNotEqual(config_id, transfer.TARGET_RUNTIME_IMAGE_ID)
        with mock.patch.object(transfer, "TARGET_CONFIG_IMAGE_ID", config_id):
            self.assertTrue(transfer._validate_archive_content(archive))

        wrong_archive, _ = self.make_archive(["sha256:" + "0"*64] + list(transfer.DIFF_IDS[1:]))
        with mock.patch.object(transfer, "TARGET_CONFIG_IMAGE_ID", config_id):
            self.assertFalse(transfer._validate_archive_content(wrong_archive))
        with mock.patch.object(transfer, "TARGET_CONFIG_IMAGE_ID", "sha256:" + "0"*64):
            self.assertFalse(transfer._validate_archive_content(archive))
        self.assertFalse(transfer._validate_archive_content(b"not a tar"))

    def test_archive_content_validator_rejects_duplicate_manifest_entries(self):
        duplicate = io.BytesIO()
        with tarfile.open(fileobj=duplicate, mode="w:") as archive:
            for _ in range(2):
                info = tarfile.TarInfo("manifest.json")
                info.size = 2
                archive.addfile(info, io.BytesIO(b"[]"))
        self.assertFalse(transfer._validate_archive_content(duplicate.getvalue()))

    def test_content_mismatch_stops_before_attempt_marker_and_ssh(self):
        runner = mock.Mock(side_effect=(
            completed((transfer.EXPECTED_LOCAL+"\n").encode()),
            completed(b"x"*transfer.STREAM_SIZE),
        ))
        with mock.patch.object(transfer, "STREAM_SHA256", "x"*64), \
             mock.patch.object(transfer.hashlib, "sha256", return_value=mock.Mock(hexdigest=lambda: "x"*64)), \
             mock.patch.object(transfer, "_reserve_attempt") as reserve:
            status = transfer.run_once(runner=runner, output=self.output,
                host_check=lambda: True, archive_validator=lambda _raw: False,
                now=self.before_expiry)
        self.assertEqual(status, transfer._CODES["LOCAL_ARCHIVE_CONTENT_MISMATCH"])
        self.assertEqual(self.output.getvalue(), "LOCAL_ARCHIVE_CONTENT_MISMATCH\n")
        self.assertEqual(runner.call_count, 2)
        reserve.assert_not_called()

    def test_host_key_failure_and_expiry_precede_docker(self):
        runner = mock.Mock()
        self.assertEqual(transfer.run_once(runner=runner, output=self.output,
            host_check=lambda: False, now=self.before_expiry), transfer._CODES["HOST_KEY_PREFLIGHT_REJECTED"])
        self.assertEqual(transfer.run_once(runner=runner, output=self.output,
            host_check=lambda: True, now=datetime(2026, 10, 29, 20, 0, tzinfo=timezone.utc)),
            transfer._CODES["AUTHORIZATION_EXPIRED"])
        runner.assert_not_called()

    def test_remote_failure_markers_are_sanitized_and_not_retried(self):
        for marker, expected in (
            (b"REMOTE_ARCHIVE_REJECTED\n", "REMOTE_ARCHIVE_REJECTED"),
            (b"REMOTE_IMAGE_LOAD_FAILED\n", "REMOTE_IMAGE_LOAD_FAILED"),
            (b"REMOTE_IMAGE_IDENTITY_MISMATCH\n", "REMOTE_IMAGE_IDENTITY_MISMATCH"),
        ):
            with self.subTest(marker=expected):
                self.output = io.StringIO()
                status, calls = self.fake_run(ssh=completed(marker, returncode=41))
                self.assertEqual(status, transfer._CODES[expected])
                self.assertEqual(self.output.getvalue(), expected + "\n")
                self.assertEqual(sum(c[0][0] == "/usr/bin/ssh" for c in calls), 1)


if __name__ == "__main__":
    unittest.main()
