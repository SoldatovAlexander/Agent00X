from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.authority_key_set import (
    AuthorityKeySetError,
    MAX_AUTHORITY_KEY_SET_BYTES,
    load_control_plane_authority_key_set,
)


class AuthorityKeySetTests(unittest.TestCase):
    def test_loads_only_exact_out_of_band_pinned_public_keys(self):
        with tempfile.TemporaryDirectory(prefix="authority-key-set-") as temporary:
            path = Path(temporary) / "authority-keys.json"
            raw = json.dumps(
                {
                    "schema": "control-plane-authority-key-set/v1",
                    "keys": {"synthetic-authority": "ab" * 32},
                },
                sort_keys=True,
            ).encode("utf-8")
            path.write_bytes(raw)

            keys, digest = load_control_plane_authority_key_set(
                path,
                expected_digest="sha256:" + hashlib.sha256(raw).hexdigest(),
            )

        self.assertEqual(keys, {"synthetic-authority": bytes.fromhex("ab" * 32)})
        self.assertEqual(digest, "sha256:" + hashlib.sha256(raw).hexdigest())

    def test_rejects_wrong_pin_schema_duplicate_or_oversized_input(self):
        malformed_records = (
            b'{"schema":"control-plane-authority-key-set/v1","keys":{},"keys":{}}',
            b'{"schema":"control-plane-authority-key-set/v1","keys":{},"extra":1}',
            b'{"schema":"control-plane-authority-key-set/v1","keys":{"bad id":"'
            + b"0" * 64
            + b'"}}',
        )
        with tempfile.TemporaryDirectory(prefix="authority-key-set-invalid-") as temporary:
            path = Path(temporary) / "authority-keys.json"
            for raw in (*malformed_records, b" " * (MAX_AUTHORITY_KEY_SET_BYTES + 1)):
                with self.subTest(size=len(raw)):
                    path.write_bytes(raw)
                    with self.assertRaisesRegex(
                        AuthorityKeySetError,
                        "^authority key set: caller-pinned public keys are unavailable$",
                    ):
                        load_control_plane_authority_key_set(
                            path,
                            expected_digest="sha256:" + hashlib.sha256(raw).hexdigest(),
                        )

    def test_rejects_symlinks_and_wrong_out_of_band_pin(self):
        with tempfile.TemporaryDirectory(prefix="authority-key-set-link-") as temporary:
            root = Path(temporary)
            path = root / "authority-keys.json"
            raw = b'{"schema":"control-plane-authority-key-set/v1","keys":{"a":"' + b"0" * 64 + b'"}}'
            path.write_bytes(raw)
            with self.assertRaises(AuthorityKeySetError):
                load_control_plane_authority_key_set(path, expected_digest="sha256:" + "0" * 64)

            link = root / "link.json"
            link.symlink_to(path)
            with self.assertRaises(AuthorityKeySetError):
                load_control_plane_authority_key_set(
                    link,
                    expected_digest="sha256:" + hashlib.sha256(raw).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
