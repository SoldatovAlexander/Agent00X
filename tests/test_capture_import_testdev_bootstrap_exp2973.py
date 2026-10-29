from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import capture_import_testdev_bootstrap_exp2973 as profile


class CaptureImportTestdevBootstrapExp2973Tests(unittest.TestCase):
    def test_profile_pins_host_gate_target_and_unique_paths(self):
        self.assertEqual(profile.CARD_ID, "EXP-2973")
        self.assertEqual(profile.GATE, "RUN EXP-2973 ONCE")
        self.assertEqual(profile.TARGET_HOST, "alex@192.168.88.101")
        self.assertEqual(profile.OUTPUT.name, "verifier-bootstrap-exp2973.json")
        self.assertEqual(profile.ATTEMPT.name, "verifier-bootstrap-exp2973.attempted")
        self.assertEqual(profile.EXPIRES_AT.isoformat(), "2026-10-29T20:00:00+00:00")

    def test_ssh_is_noninteractive_strict_host_key_no_forwarding(self):
        command = profile.ssh_command()
        self.assertIn("-T", command)
        self.assertIn("-oStrictHostKeyChecking=yes", command)
        self.assertIn("-oForwardAgent=no", command)
        self.assertIn("-oClearAllForwardings=yes", command)
        self.assertEqual(command[-2], profile.TARGET_HOST)
        self.assertIn("exp-2927/scripts/serve_ephemeral_signed_verifier_https.py", command[-1])

    def test_tty_gate_preflight_failure_does_not_touch_importer_or_ssh(self):
        with patch.object(profile, "_check_known_host", return_value=False), \
             patch.object(profile.importer, "main") as run:
            self.assertEqual(profile.main(), 2)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
