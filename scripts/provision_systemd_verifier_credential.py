#!/usr/bin/env python3
"""Create one host-encrypted verifier signer seed without plaintext storage.

The utility is an operator-side provisioning primitive, not a service manager
or trust-enrollment tool. It generates a fresh key in memory, sends the seed
only to systemd-creds stdin, atomically saves validated ciphertext, and emits
the matching public key for a separate out-of-band enrollment process.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.signed_verifier_service import (  # noqa: E402
    BRAINBOOSTER_VERIFIER_PROFILE,
)


SYSTEMD_CREDS_PATH = "/usr/bin/systemd-creds"
CREDENTIAL_NAME = "AGENT_VERIFIER_SIGNING_SEED"
ENCRYPTION_KEY = "host"
MAX_CIPHERTEXT_BYTES = 4096
MIN_DECODED_CIPHERTEXT_BYTES = 64
ENCRYPT_TIMEOUT_SECONDS = 30
_OUTPUT_SCHEMA = "agent00x-systemd-verifier-credential/v1"
_ERROR_MARKER = "systemd verifier credential provisioning: operation failed\n"


class CredentialProvisioningError(ValueError):
    """A credential could not be encrypted and atomically published."""


@dataclass(frozen=True)
class PublicProvisioningResult:
    """Public-only metadata emitted after encrypted-file publication."""

    credential_name: str
    encrypted_credential_sha256: str
    verifier_key_id: str
    verifier_public_key: str
    verifier_public_key_sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "schema": _OUTPUT_SCHEMA,
            "status": "encrypted",
            "credential_name": self.credential_name,
            "encryption_key": ENCRYPTION_KEY,
            "encrypted_credential_sha256": self.encrypted_credential_sha256,
            "verifier_key_id": self.verifier_key_id,
            "verifier_public_key": self.verifier_public_key,
            "verifier_public_key_sha256": self.verifier_public_key_sha256,
        }


def _canonical_output_path(value: object) -> Path:
    try:
        if type(value) is not str or not value or len(value) > 4096:
            raise ValueError
        path = Path(value)
        if not path.is_absolute() or path.name in {"", ".", ".."}:
            raise ValueError
        parent = path.parent
        resolved_parent = parent.resolve(strict=True)
        if resolved_parent != parent:
            raise ValueError
        parent_stat = parent.lstat()
        if not stat.S_ISDIR(parent_stat.st_mode):
            raise ValueError
        if os.path.lexists(path):
            raise ValueError
        return path
    except Exception:
        raise CredentialProvisioningError(
            "systemd verifier credential provisioning: output path rejected"
        ) from None


def _require_root(effective_uid: object) -> None:
    if type(effective_uid) is not int or effective_uid != 0:
        raise CredentialProvisioningError(
            "systemd verifier credential provisioning: root privileges are required"
        )


def _validate_ciphertext(
    value: object,
    *,
    forbidden_values: tuple[bytes, ...] = (),
) -> bytes:
    try:
        if type(value) is not bytes or not value or len(value) > MAX_CIPHERTEXT_BYTES:
            raise ValueError
        encoded = value.strip()
        if not encoded or any(byte > 0x7F for byte in encoded):
            raise ValueError
        decoded = base64.b64decode(encoded, validate=True)
        if (
            len(decoded) < MIN_DECODED_CIPHERTEXT_BYTES
            or base64.b64encode(decoded) != encoded
            or any(
                marker and (marker in decoded or marker in encoded)
                for marker in forbidden_values
            )
        ):
            raise ValueError
        return encoded + b"\n"
    except Exception:
        raise CredentialProvisioningError(
            "systemd verifier credential provisioning: encrypted output rejected"
        ) from None


def _write_no_overwrite(path: Path, ciphertext: bytes) -> None:
    """Publish ciphertext by same-directory hard link; never replace a target."""

    directory_fd = -1
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    linked = False
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(path.parent, directory_flags)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        temporary_name = f".{path.name}.tmp-{secrets.token_hex(16)}"
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                descriptor = -1
                stream.write(ciphertext)
                stream.flush()
                os.fsync(stream.fileno())
                metadata = os.fstat(stream.fileno())
                temporary_identity = (metadata.st_dev, metadata.st_ino)
        finally:
            if descriptor >= 0:
                os.close(descriptor)

        os.link(
            temporary_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        linked = True
        os.unlink(temporary_name, dir_fd=directory_fd)
        temporary_name = None
        os.fsync(directory_fd)
    except Exception:
        if linked and directory_fd >= 0 and temporary_identity is not None:
            try:
                metadata = os.stat(
                    path.name, dir_fd=directory_fd, follow_symlinks=False
                )
                if (metadata.st_dev, metadata.st_ino) == temporary_identity:
                    os.unlink(path.name, dir_fd=directory_fd)
            except Exception:
                pass
        raise CredentialProvisioningError(
            "systemd verifier credential provisioning: encrypted file publication failed"
        ) from None
    finally:
        if temporary_name is not None and directory_fd >= 0:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except Exception:
                pass
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except Exception:
                pass


def provision_systemd_verifier_credential(
    output_path: object,
    *,
    runner: Callable[..., object] | None = None,
    token_bytes: Callable[[int], bytes] | None = None,
    effective_uid: int | None = None,
) -> PublicProvisioningResult:
    """Generate, encrypt, and atomically save one fresh host-bound signer key."""

    get_effective_uid = getattr(os, "geteuid", None)
    current_uid = (
        get_effective_uid() if callable(get_effective_uid) else None
    ) if effective_uid is None else effective_uid
    _require_root(current_uid)
    path = _canonical_output_path(output_path)
    random_bytes = secrets.token_bytes if token_bytes is None else token_bytes
    run = subprocess.run if runner is None else runner
    seed = bytearray()
    seed_hex = bytearray()
    try:
        generated = random_bytes(32)
        if type(generated) is not bytes or len(generated) != 32:
            raise ValueError
        seed.extend(generated)
        del generated
        seed_hex.extend(seed.hex().encode("ascii"))
        signing_key = Ed25519PrivateKey.from_private_bytes(bytes(seed))
        public_key = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        result = run(
            [
                SYSTEMD_CREDS_PATH,
                "--with-key=host",
                f"--name={CREDENTIAL_NAME}",
                "encrypt",
                "-",
                "-",
            ],
            input=bytes(seed_hex),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=ENCRYPT_TIMEOUT_SECONDS,
            check=False,
            close_fds=True,
        )
        if getattr(result, "returncode", None) != 0:
            raise ValueError
        ciphertext = _validate_ciphertext(
            getattr(result, "stdout", None),
            forbidden_values=(bytes(seed), bytes(seed_hex)),
        )
        _write_no_overwrite(path, ciphertext)
        return PublicProvisioningResult(
            credential_name=CREDENTIAL_NAME,
            encrypted_credential_sha256=(
                "sha256:" + hashlib.sha256(ciphertext).hexdigest()
            ),
            verifier_key_id=BRAINBOOSTER_VERIFIER_PROFILE.signer_key_id,
            verifier_public_key=public_key.hex(),
            verifier_public_key_sha256=(
                "sha256:" + hashlib.sha256(public_key).hexdigest()
            ),
        )
    except CredentialProvisioningError:
        raise
    except Exception:
        raise CredentialProvisioningError(
            "systemd verifier credential provisioning: operation failed"
        ) from None
    finally:
        for index in range(len(seed)):
            seed[index] = 0
        for index in range(len(seed_hex)):
            seed_hex[index] = 0


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[..., object] | None = None,
    token_bytes: Callable[[int], bytes] | None = None,
    platform_name: str | None = None,
    effective_uid: int | None = None,
    stdout=None,
    stderr=None,
) -> int:
    """CLI entrypoint; prints only public enrollment metadata on success."""

    output_stream = sys.stdout if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr
    try:
        parser = argparse.ArgumentParser(add_help=True)
        parser.add_argument("--output", required=True)
        args = parser.parse_args(argv)
        current_platform = sys.platform if platform_name is None else platform_name
        if not current_platform.startswith("linux"):
            raise CredentialProvisioningError(
                "systemd verifier credential provisioning: Linux is required"
            )
        get_effective_uid = getattr(os, "geteuid", None)
        current_uid = (
            get_effective_uid() if callable(get_effective_uid) else None
        ) if effective_uid is None else effective_uid
        _require_root(current_uid)
        result = provision_systemd_verifier_credential(
            args.output,
            runner=runner,
            token_bytes=token_bytes,
            effective_uid=current_uid,
        )
        output_stream.write(
            json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        output_stream.flush()
        return 0
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        try:
            error_stream.write(_ERROR_MARKER)
            error_stream.flush()
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
