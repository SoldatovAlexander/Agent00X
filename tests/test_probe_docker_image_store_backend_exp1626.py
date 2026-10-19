from __future__ import annotations

import io
import subprocess
import unittest

from scripts import probe_docker_image_store_backend_exp1626 as probe


class ProbeDockerImageStoreBackendExp1626Tests(unittest.TestCase):
    def test_classifies_containerd_driver_type_without_returning_raw_fields(self):
        output = io.StringIO()
        calls = []

        def runner(command, *, max_bytes, timeout, env):
            calls.append((command, max_bytes, timeout, env))
            return subprocess.CompletedProcess(
                command, 0,
                b'overlayfs\n[["driver-type","io.containerd.snapshotter.v1"]]\n',
                b"",
            )

        code = probe.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "IMAGE_STORE_BACKEND|classification=containerd\n")
        command, cap, timeout, env = calls[0]
        self.assertEqual(
            command,
            (
                probe.DOCKER,
                "--host=" + probe.DOCKER_HOST,
                "info",
                "--format",
                "{{.Driver}}\n{{json .DriverStatus}}",
            ),
        )
        self.assertEqual(cap, probe.MAX_OUTPUT_BYTES)
        self.assertEqual(timeout, probe.TIMEOUT_SECONDS)
        self.assertEqual(env["DOCKER_HOST"], probe.DOCKER_HOST)
        self.assertIn("DOCKER_CONFIG", env)
        self.assertEqual(env["PATH"], "/usr/local/bin:/usr/bin:/bin")

    def test_classifies_allowlisted_classic_driver(self):
        self.assertEqual(probe._classify(b'overlay2\n[["Backing Filesystem","extfs"]]\n'), "classic")

    def test_unknown_driver_and_malformed_status_fail_closed(self):
        self.assertEqual(probe._classify(b'unknown\n[]\n'), "unclassified")
        self.assertEqual(probe._classify(b'overlay2\nnot-json\n'), "unclassified")

    def test_nonzero_process_emits_no_raw_output(self):
        output = io.StringIO()
        secret_like = b"credentials and server details"

        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, secret_like, secret_like)

        self.assertEqual(probe.run_once(runner=runner, output=output), 11)
        self.assertEqual(output.getvalue(), "IMAGE_STORE_BACKEND|classification=unavailable\n")
        self.assertNotIn("credentials", output.getvalue())


if __name__ == "__main__":
    unittest.main()
