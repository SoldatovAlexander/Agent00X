from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.pinned_verifier_cli import (  # noqa: E402
    VERIFIER_TRUST_ARTIFACT_ARGUMENTS,
    has_any_verifier_trust_artifact_args,
    read_pinned_public_record,
)


class PinnedVerifierCliTests(unittest.TestCase):
    def test_reads_exact_absolute_regular_public_record_by_digest(self):
        with tempfile.TemporaryDirectory(prefix="pinned-verifier-public-") as directory:
            path = Path(directory) / "public.json"
            content = b'{"public":true}\n'
            path.write_bytes(content)
            digest = "sha256:" + hashlib.sha256(content).hexdigest()

            raw, observed_digest = read_pinned_public_record(
                str(path), digest, max_bytes=128
            )

        self.assertEqual(raw, content)
        self.assertEqual(observed_digest, digest)

    def test_rejects_digest_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="pinned-verifier-mismatch-") as directory:
            path = Path(directory) / "public.json"
            path.write_bytes(b"public")
            with self.assertRaisesRegex(ValueError, "public trust material unavailable"):
                read_pinned_public_record(
                    str(path), "sha256:" + "0" * 64, max_bytes=128
                )

    def test_rejects_symlink_and_oversized_record(self):
        with tempfile.TemporaryDirectory(prefix="pinned-verifier-file-gates-") as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_bytes(b"public")
            link = root / "link.json"
            link.symlink_to(target)
            digest = "sha256:" + hashlib.sha256(b"public").hexdigest()

            with self.assertRaisesRegex(ValueError, "public trust material unavailable"):
                read_pinned_public_record(str(link), digest, max_bytes=128)
            with self.assertRaisesRegex(ValueError, "public trust material unavailable"):
                read_pinned_public_record(str(target), digest, max_bytes=5)

    def test_trust_argument_presence_is_detected_without_loading_files(self):
        empty = SimpleNamespace(**{name: None for name in VERIFIER_TRUST_ARTIFACT_ARGUMENTS})
        partial = SimpleNamespace(
            **{
                name: ("public-value" if name == "verifier_enrollment" else None)
                for name in VERIFIER_TRUST_ARTIFACT_ARGUMENTS
            }
        )

        self.assertFalse(has_any_verifier_trust_artifact_args(empty))
        self.assertTrue(has_any_verifier_trust_artifact_args(partial))


if __name__ == "__main__":
    unittest.main()
