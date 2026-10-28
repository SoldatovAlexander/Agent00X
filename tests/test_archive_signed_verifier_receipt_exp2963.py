from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import archive_signed_verifier_receipt_exp2963 as archive


class ArchiveSignedVerifierReceiptExp2963Tests(unittest.TestCase):
    def test_profile_pins_exp2915_stage_and_future_exp2962_receipt(self):
        self.assertEqual(archive.STAGE_DIGEST, "sha256:ac1c28ebeb908d971baad950a83ce60ed795435cedfc796c198a590522189a1b")
        self.assertEqual(archive.ARTIFACT_DIGEST, "sha256:146abcc35d054952a8ef941b9c40599e2ae1322a36b56294ec1753fe66d40e48")
        self.assertEqual(archive.REQUEST_DIGEST, "sha256:86bdaebfcad6ed61bfaaa44fc69f5dcc6606d958f8c387b5bfeb8ff47d664613")
        self.assertEqual(archive.PROCESS_ID, "process-exp-2915-local-001")
        self.assertEqual(archive.RECEIPT_PATH.name, "signed-verifier-evidence-exp2962.json")
        self.assertEqual(archive.ARCHIVE_DATABASE.name, "EXP-2963-stage-archive.sqlite3")
        self.assertEqual(archive.ATTEMPT_PATH.name, "EXP-2963-stage-archive.attempted")
        self.assertEqual(archive.GATE, "RUN EXP-2963 ONCE")

    def test_configure_uses_detached_store_and_pinned_authority_key_set(self):
        with patch.object(archive.core, "main", return_value=2):
            self.assertEqual(archive.main(), 2)
        self.assertEqual(archive.core.SOURCE_DATABASE, archive.EVIDENCE_DIR / "EXP-2915-stage.sqlite3")
        self.assertEqual(archive.core.ARCHIVE_DATABASE, archive.EVIDENCE_DIR / "EXP-2963-stage-archive.sqlite3")
        self.assertNotEqual(archive.core.SOURCE_DATABASE, archive.core.ARCHIVE_DATABASE)
        self.assertEqual(archive.core.RECEIPT_PATH, archive.RECEIPT_PATH)
        self.assertEqual(archive.core.KEY_SET_PATH, archive.KEY_SET_PATH)
        self.assertEqual(archive.core.KEY_SET_DIGEST, archive.KEY_SET_DIGEST)
        self.assertEqual(archive.core.GATE, archive.GATE)


if __name__ == "__main__":
    unittest.main()
