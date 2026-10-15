from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from provision_systemd_verifier_credential import (
    CREDENTIAL_NAME,
    ENCRYPT_TIMEOUT_SECONDS,
    SYSTEMD_CREDS_PATH,
    CredentialProvisioningError,
    main,
    provision_systemd_verifier_credential,
)


SEED = bytes(range(32))
SEED_HEX = SEED.hex().encode("ascii")
TOOL_DIAGNOSTIC_SECRET = b"synthetic-tool-diagnostic-secret"
SYNTHETIC_CIPHERTEXT = base64.b64encode(
    b"encrypted-systemd-credential-fixture:" + bytes(range(64, 160))
) + b"\n"


class FakeSystemdCreds:
    def __init__(self, *, returncode=0, stdout=SYNTHETIC_CIPHERTEXT):
        self.returncode = returncode
        self.stdout = stdout
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=TOOL_DIAGNOSTIC_SECRET,
        )


class SystemdVerifierCredentialProvisioningTests(unittest.TestCase):
    def test_success_sends_seed_only_on_stdin_and_emits_public_metadata(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"
            fake = FakeSystemdCreds()
            stdout = io.StringIO()
            stderr = io.StringIO()

            result = main(
                ["--output", str(destination)],
                runner=fake,
                token_bytes=lambda size: SEED,
                platform_name="linux",
                effective_uid=0,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(len(fake.calls), 1)
            args, kwargs = fake.calls[0]
            self.assertEqual(
                args,
                [
                    SYSTEMD_CREDS_PATH,
                    "--with-key=host",
                    f"--name={CREDENTIAL_NAME}",
                    "encrypt",
                    "-",
                    "-",
                ],
            )
            self.assertEqual(kwargs["input"], SEED_HEX)
            self.assertEqual(kwargs["stdout"], subprocess.PIPE)
            self.assertEqual(kwargs["stderr"], subprocess.PIPE)
            self.assertEqual(kwargs["timeout"], ENCRYPT_TIMEOUT_SECONDS)
            self.assertTrue(kwargs["close_fds"])
            self.assertNotIn(SEED_HEX.decode("ascii"), args)

            metadata = json.loads(stdout.getvalue())
            expected_public_key = Ed25519PrivateKey.from_private_bytes(SEED).public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
            self.assertEqual(metadata["status"], "encrypted")
            self.assertEqual(metadata["credential_name"], CREDENTIAL_NAME)
            self.assertEqual(metadata["encryption_key"], "host")
            self.assertEqual(metadata["verifier_key_id"], "brainbooster-verifier-v1")
            self.assertEqual(metadata["verifier_public_key"], expected_public_key.hex())
            self.assertEqual(
                metadata["verifier_public_key_sha256"],
                "sha256:" + hashlib.sha256(expected_public_key).hexdigest(),
            )
            normalized_ciphertext = base64.b64encode(
                base64.b64decode(SYNTHETIC_CIPHERTEXT.strip(), validate=True)
            ) + b"\n"
            self.assertEqual(destination.read_bytes(), normalized_ciphertext)
            self.assertEqual(
                metadata["encrypted_credential_sha256"],
                "sha256:" + hashlib.sha256(normalized_ciphertext).hexdigest(),
            )
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            self.assertEqual(sorted(path.name for path in Path(root).iterdir()), ["signer.cred"])
            self.assertNotIn(SEED_HEX.decode("ascii"), stdout.getvalue())
            self.assertNotIn(TOOL_DIAGNOSTIC_SECRET.decode("ascii"), stdout.getvalue())

    def test_existing_output_is_rejected_before_entropy_or_tool_call(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-existing-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"
            destination.write_bytes(b"existing encrypted value")

            def fail_if_called(*_args, **_kwargs):
                self.fail("entropy/tool must not be used for an existing target")

            with self.assertRaisesRegex(
                CredentialProvisioningError, "output path rejected"
            ):
                provision_systemd_verifier_credential(
                    str(destination),
                    runner=fail_if_called,
                    token_bytes=fail_if_called,
                    effective_uid=0,
                )
            self.assertEqual(destination.read_bytes(), b"existing encrypted value")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink is unavailable")
    def test_symlinked_output_is_rejected_without_following_target(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-link-") as root:
            directory = Path(root).resolve(strict=True)
            target = directory / "target"
            target.write_bytes(b"do not replace")
            destination = directory / "signer.cred"
            destination.symlink_to(target)
            fake = FakeSystemdCreds()

            with self.assertRaisesRegex(
                CredentialProvisioningError, "output path rejected"
            ):
                provision_systemd_verifier_credential(
                    str(destination),
                    runner=fake,
                    token_bytes=lambda _size: SEED,
                    effective_uid=0,
                )
            self.assertEqual(fake.calls, [])
            self.assertEqual(target.read_bytes(), b"do not replace")

    def test_symlinked_parent_is_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink is unavailable")
        with tempfile.TemporaryDirectory(prefix="verifier-credential-parent-") as root:
            directory = Path(root).resolve(strict=True)
            real_parent = directory / "real"
            real_parent.mkdir()
            linked_parent = directory / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            fake = FakeSystemdCreds()

            with self.assertRaisesRegex(
                CredentialProvisioningError, "output path rejected"
            ):
                provision_systemd_verifier_credential(
                    str(linked_parent / "signer.cred"),
                    runner=fake,
                    token_bytes=lambda _size: SEED,
                    effective_uid=0,
                )
            self.assertEqual(fake.calls, [])
            self.assertEqual(list(real_parent.iterdir()), [])

    def test_encryption_failure_is_redacted_and_creates_no_output(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-failed-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"
            fake = FakeSystemdCreds(returncode=1, stdout=b"")
            stderr = io.StringIO()

            result = main(
                ["--output", str(destination)],
                runner=fake,
                token_bytes=lambda _size: SEED,
                platform_name="linux",
                effective_uid=0,
                stdout=io.StringIO(),
                stderr=stderr,
            )

            self.assertEqual(result, 2)
            self.assertEqual(
                stderr.getvalue(),
                "systemd verifier credential provisioning: operation failed\n",
            )
            self.assertNotIn(TOOL_DIAGNOSTIC_SECRET.decode("ascii"), stderr.getvalue())
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_malformed_ciphertext_is_rejected_without_public_metadata(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-malformed-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"
            fake = FakeSystemdCreds(stdout=b"not encrypted output")
            stdout = io.StringIO()
            stderr = io.StringIO()

            result = main(
                ["--output", str(destination)],
                runner=fake,
                token_bytes=lambda _size: SEED,
                platform_name="linux",
                effective_uid=0,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(result, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                stderr.getvalue(),
                "systemd verifier credential provisioning: operation failed\n",
            )
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_ciphertext_that_contains_plaintext_seed_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-echo-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"
            echoed = base64.b64encode(SEED_HEX + b"x" * 64)
            fake = FakeSystemdCreds(stdout=echoed)

            with self.assertRaisesRegex(
                CredentialProvisioningError, "encrypted output rejected"
            ):
                provision_systemd_verifier_credential(
                    str(destination),
                    runner=fake,
                    token_bytes=lambda _size: SEED,
                    effective_uid=0,
                )
            self.assertFalse(destination.exists())

    def test_timeout_is_redacted_and_creates_no_output(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-timeout-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"

            def timeout(*_args, **_kwargs):
                raise subprocess.TimeoutExpired(
                    SYSTEMD_CREDS_PATH,
                    ENCRYPT_TIMEOUT_SECONDS,
                    output=SEED_HEX,
                    stderr=TOOL_DIAGNOSTIC_SECRET,
                )

            with self.assertRaisesRegex(
                CredentialProvisioningError, "operation failed"
            ) as raised:
                provision_systemd_verifier_credential(
                    str(destination),
                    runner=timeout,
                    token_bytes=lambda _size: SEED,
                    effective_uid=0,
                )
            self.assertNotIn(SEED_HEX.decode("ascii"), str(raised.exception))
            self.assertNotIn(TOOL_DIAGNOSTIC_SECRET.decode("ascii"), str(raised.exception))
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_non_linux_cli_fails_before_entropy_or_tool_call(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-platform-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"

            def fail_if_called(*_args, **_kwargs):
                self.fail("non-Linux execution must not create or encrypt a key")

            stdout = io.StringIO()
            stderr = io.StringIO()
            result = main(
                ["--output", str(destination)],
                runner=fail_if_called,
                token_bytes=fail_if_called,
                platform_name="darwin",
                stdout=stdout,
                stderr=stderr,
            )
            self.assertEqual(result, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                stderr.getvalue(),
                "systemd verifier credential provisioning: operation failed\n",
            )
            self.assertFalse(destination.exists())

    def test_non_root_cli_fails_before_entropy_or_tool_call(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-nonroot-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"

            def fail_if_called(*_args, **_kwargs):
                self.fail("non-root execution must not create or encrypt a key")

            stdout = io.StringIO()
            stderr = io.StringIO()
            result = main(
                ["--output", str(destination)],
                runner=fail_if_called,
                token_bytes=fail_if_called,
                platform_name="linux",
                effective_uid=1000,
                stdout=stdout,
                stderr=stderr,
            )
            self.assertEqual(result, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                stderr.getvalue(),
                "systemd verifier credential provisioning: operation failed\n",
            )
            self.assertFalse(destination.exists())

    def test_racing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="verifier-credential-race-") as root:
            destination = Path(root).resolve(strict=True) / "signer.cred"
            existing = b"racing writer value"

            def create_destination_then_encrypt(_args, **_kwargs):
                destination.write_bytes(existing)
                return SimpleNamespace(
                    returncode=0,
                    stdout=SYNTHETIC_CIPHERTEXT,
                    stderr=b"",
                )

            with self.assertRaisesRegex(
                CredentialProvisioningError, "publication failed"
            ):
                provision_systemd_verifier_credential(
                    str(destination),
                    runner=create_destination_then_encrypt,
                    token_bytes=lambda _size: SEED,
                    effective_uid=0,
                )
            self.assertEqual(destination.read_bytes(), existing)
            self.assertEqual(sorted(path.name for path in Path(root).iterdir()), ["signer.cred"])


if __name__ == "__main__":
    unittest.main()
