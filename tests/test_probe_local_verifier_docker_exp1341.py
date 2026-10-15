from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock

from scripts import probe_local_verifier_docker_exp1341 as probe
from scripts import stream_pinned_verifier_image as pinned


class LocalVerifierDockerProbeTests(unittest.TestCase):
    def test_info_failure_stops_before_image_inspect(self):
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess((), 1, b"SECRET", b"SECRET")
        )
        output = io.StringIO()
        result = probe.run_probe(runner, output)
        self.assertEqual(result, 10)
        self.assertEqual(output.getvalue(), "LOCAL_DOCKER_INFO_FAILED\n")
        runner.assert_called_once()

    def test_info_classifies_containerd_store_and_exact_pin_descriptor(self):
        digest = "sha256:" + pinned.IMAGE_ID.split(":", 1)[1]
        runner = mock.Mock(
            side_effect=(
                subprocess.CompletedProcess(
                    (), 0, b'overlayfs|[["driver-type","io.containerd.snapshotter.v1"]]\n', b""
                ),
                subprocess.CompletedProcess(
                    (), 0, f"{pinned.IMAGE_ID}|{digest}\n".encode(), b""
                ),
            )
        )
        output = __import__("io").StringIO()
        self.assertEqual(probe.run_probe(runner, output), 0)
        self.assertEqual(
            output.getvalue(),
            "LOCAL_DOCKER_STORE|driver_present=true|containerd_snapshotter=true\n"
            "LOCAL_PINNED_IMAGE|id_matches_pin=true|descriptor_available=true|"
            "id_equals_descriptor_digest=true\n",
        )
        self.assertEqual(runner.call_count, 2)

    def test_absent_pin_is_classified_without_leaking_error_text(self):
        runner = mock.Mock(
            side_effect=(
                subprocess.CompletedProcess((), 0, b'overlay2|[]\n', b""),
                subprocess.CompletedProcess(
                    (), 1, b"", b"Error response: No such image: PRIVATE"
                ),
            )
        )
        output = __import__("io").StringIO()
        self.assertEqual(probe.run_probe(runner, output), 12)
        self.assertEqual(
            output.getvalue(),
            "LOCAL_DOCKER_STORE|driver_present=true|containerd_snapshotter=false\n"
            "LOCAL_PINNED_IMAGE_ABSENT\n",
        )
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertEqual(runner.call_count, 2)


if __name__ == "__main__":
    unittest.main()
