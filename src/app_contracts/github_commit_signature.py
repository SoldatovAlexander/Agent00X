"""Locally verify one OpenPGP-signed Git commit against a pinned key.

This proves that the exact Git object was signed by a key with the supplied
primary fingerprint. It does not establish who owns that key or authenticate
the GitHub/TLS transport that supplied the object and public key.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .github_snapshot import (
    GitHubCommitClaim,
    MAX_GIT_COMMIT_OBJECT_BYTES,
    parse_git_commit_object,
)


MAX_ARMORED_PUBLIC_KEY_BYTES = 64 * 1024
MAX_GPG_OUTPUT_BYTES = 64 * 1024
MAX_TIMEOUT_SECONDS = 30.0
_FINGERPRINT_RE = re.compile(r"(?:[0-9A-F]{40}|[0-9A-F]{64})\Z")
_SIGNATURE_BLOCK_START = b"-----BEGIN PGP SIGNATURE-----"
_SIGNATURE_BLOCK_END = b"-----END PGP SIGNATURE-----"


class GitCommitSignatureError(ValueError):
    """A pinned commit signature could not be verified safely."""


@dataclass(frozen=True)
class GitCommitSignatureProof:
    """Sanitized evidence that one pinned OpenPGP key signed one Git object."""

    commit_oid: str
    tree_oid: str
    primary_fingerprint: str
    signature_valid: bool = True
    evidence_origin: str = "local_openpgp_signature"
    identity_authenticated: bool = False
    independent_transport_trust_established: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.commit_oid) is not str
            or re.fullmatch(r"[0-9a-f]{40}", self.commit_oid) is None
            or type(self.tree_oid) is not str
            or re.fullmatch(r"[0-9a-f]{40}", self.tree_oid) is None
            or type(self.primary_fingerprint) is not str
            or _FINGERPRINT_RE.fullmatch(self.primary_fingerprint) is None
            or type(self.signature_valid) is not bool
            or self.signature_valid is not True
            or self.evidence_origin != "local_openpgp_signature"
            or self.identity_authenticated is not False
            or self.independent_transport_trust_established is not False
        ):
            raise GitCommitSignatureError(
                "github commit signature: proof is invalid"
            )


def primary_fingerprint_from_armored_public_key(
    armored_public_key: object,
    *,
    gpg_executable: object,
    timeout_seconds: float = 5.0,
) -> str:
    """Read one public key's primary fingerprint without importing or saving it."""

    try:
        if (
            type(armored_public_key) is not bytes
            or not armored_public_key
            or len(armored_public_key) > MAX_ARMORED_PUBLIC_KEY_BYTES
            or b"-----BEGIN PGP PUBLIC KEY BLOCK-----" not in armored_public_key
            or b"-----END PGP PUBLIC KEY BLOCK-----" not in armored_public_key
            or type(gpg_executable) is not str
            or not Path(gpg_executable).is_absolute()
            or not Path(gpg_executable).is_file()
            or not os.access(gpg_executable, os.X_OK)
            or isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or not 0 < float(timeout_seconds) <= MAX_TIMEOUT_SECONDS
        ):
            raise ValueError
        deadline = time.monotonic() + float(timeout_seconds)
        with tempfile.TemporaryDirectory(
            prefix="a0p-", dir=_short_temp_directory()
        ) as home_text:
            home = Path(home_text)
            (home / "gpg.conf").write_text(
                "no-auto-key-retrieve\ndisable-dirmngr\n", encoding="ascii"
            )
            (home / "gpg.conf").chmod(0o600)
            output = _run_bounded(
                [
                    gpg_executable,
                    "--batch",
                    "--no-tty",
                    "--no-options",
                    "--disable-dirmngr",
                    "--no-auto-key-retrieve",
                    "--homedir",
                    str(home),
                    "--with-colons",
                    "--fingerprint",
                    "--show-keys",
                ],
                input_bytes=armored_public_key,
                cwd=home,
                environment={
                    "HOME": str(home),
                    "GNUPGHOME": str(home),
                    "PATH": os.pathsep.join(
                        (str(Path(gpg_executable).parent), os.defpath)
                    ),
                    "LANG": "C",
                    "LC_ALL": "C",
                },
                deadline=deadline,
                max_output_bytes=MAX_GPG_OUTPUT_BYTES,
            )
        fingerprints = _primary_fingerprints(output)
        if len(fingerprints) != 1:
            raise ValueError
        return fingerprints[0]
    except Exception:
        raise GitCommitSignatureError(
            "github commit signature: public key rejected"
        ) from None


def verify_git_commit_signature(
    claim: object,
    raw_commit: object,
    armored_public_key: object,
    *,
    expected_primary_fingerprint: object,
    git_executable: object,
    gpg_executable: object,
    timeout_seconds: float = 15.0,
) -> GitCommitSignatureProof:
    """Verify an exact raw commit with one explicitly pinned OpenPGP key.

    The temporary Git repository and GnuPG home are isolated from user/system
    configuration. Key retrieval, prompts, credential helpers and shell
    execution are disabled. The supplied public key is not treated as a trust
    anchor by itself: its primary fingerprint must match the caller's pin.
    """

    fingerprint = _validate_configuration(
        claim,
        raw_commit,
        armored_public_key,
        expected_primary_fingerprint,
        git_executable,
        gpg_executable,
        timeout_seconds,
    )
    try:
        parsed_commit = parse_git_commit_object(claim, raw_commit)
        _validate_openpgp_signature_header(raw_commit)
        deadline = time.monotonic() + float(timeout_seconds)
        with tempfile.TemporaryDirectory(prefix="agent00x-commit-signature-") as root_text:
            root = Path(root_text)
            home = root / "home"
            repository = root / "objects.git"
            home.mkdir(mode=0o700)
            with tempfile.TemporaryDirectory(
                prefix="a0g-", dir=_short_temp_directory()
            ) as gnupg_text:
                gnupg_home = Path(gnupg_text)
                (gnupg_home / "gpg.conf").write_text(
                    "no-auto-key-retrieve\ndisable-dirmngr\n",
                    encoding="ascii",
                )
                (gnupg_home / "gpg.conf").chmod(0o600)
                environment = {
                    "HOME": str(home),
                    "GNUPGHOME": str(gnupg_home),
                    "PATH": os.pathsep.join(
                        (
                            str(Path(gpg_executable).parent),
                            str(Path(git_executable).parent),
                            os.defpath,
                        )
                    ),
                    "LANG": "C",
                    "LC_ALL": "C",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_ASKPASS": os.devnull,
                    "SSH_ASKPASS": os.devnull,
                    "GIT_TRACE": "0",
                }
                _run_bounded(
                    [
                        gpg_executable,
                        "--batch",
                        "--no-tty",
                        "--no-options",
                        "--disable-dirmngr",
                        "--no-auto-key-retrieve",
                        "--homedir",
                        str(gnupg_home),
                        "--import",
                    ],
                    input_bytes=armored_public_key,
                    cwd=root,
                    environment=environment,
                    deadline=deadline,
                    max_output_bytes=MAX_GPG_OUTPUT_BYTES,
                )
                listed_keys = _run_bounded(
                    [
                        gpg_executable,
                        "--batch",
                        "--no-tty",
                        "--no-options",
                        "--disable-dirmngr",
                        "--no-auto-key-retrieve",
                        "--homedir",
                        str(gnupg_home),
                        "--with-colons",
                        "--fingerprint",
                        "--list-keys",
                    ],
                    input_bytes=None,
                    cwd=root,
                    environment=environment,
                    deadline=deadline,
                    max_output_bytes=MAX_GPG_OUTPUT_BYTES,
                )
                if _primary_fingerprints(listed_keys) != (fingerprint,):
                    raise ValueError

                _run_bounded(
                    [
                        git_executable,
                        "init",
                        "--bare",
                        "--quiet",
                        "--template=",
                        str(repository),
                    ],
                    input_bytes=None,
                    cwd=root,
                    environment=environment,
                    deadline=deadline,
                    max_output_bytes=MAX_GPG_OUTPUT_BYTES,
                )
                stored_oid = _run_bounded(
                    [
                        git_executable,
                        "-C",
                        str(repository),
                        "-c",
                        f"gpg.program={gpg_executable}",
                        "-c",
                        "gpg.format=openpgp",
                        "hash-object",
                        "-t",
                        "commit",
                        "-w",
                        "--stdin",
                    ],
                    input_bytes=raw_commit,
                    cwd=root,
                    environment=environment,
                    deadline=deadline,
                    max_output_bytes=MAX_GPG_OUTPUT_BYTES,
                )
                if stored_oid.strip() != claim.commit_oid.encode("ascii"):
                    raise ValueError
                verification_output = _run_bounded(
                    [
                        git_executable,
                        "-C",
                        str(repository),
                        "-c",
                        f"gpg.program={gpg_executable}",
                        "-c",
                        "gpg.format=openpgp",
                        "verify-commit",
                        "--raw",
                        claim.commit_oid,
                    ],
                    input_bytes=None,
                    cwd=root,
                    environment=environment,
                    deadline=deadline,
                    max_output_bytes=MAX_GPG_OUTPUT_BYTES,
                    include_stderr=True,
                )
                if _valid_signature_primary_fingerprints(verification_output) != (
                    fingerprint,
                ):
                    raise ValueError
        return GitCommitSignatureProof(
            commit_oid=parsed_commit.commit_oid,
            tree_oid=parsed_commit.tree_oid,
            primary_fingerprint=fingerprint,
        )
    except GitCommitSignatureError:
        raise
    except Exception:
        raise GitCommitSignatureError(
            "github commit signature: verification failed"
        ) from None


def _short_temp_directory() -> str | None:
    candidate = Path("/tmp")
    return str(candidate) if candidate.is_dir() else None


def _validate_configuration(
    claim: object,
    raw_commit: object,
    armored_public_key: object,
    expected_primary_fingerprint: object,
    git_executable: object,
    gpg_executable: object,
    timeout_seconds: object,
) -> str:
    try:
        if type(claim) is not GitHubCommitClaim:
            raise ValueError
        if (
            type(raw_commit) is not bytes
            or not raw_commit
            or len(raw_commit) > MAX_GIT_COMMIT_OBJECT_BYTES
            or type(armored_public_key) is not bytes
            or not armored_public_key
            or len(armored_public_key) > MAX_ARMORED_PUBLIC_KEY_BYTES
            or b"-----BEGIN PGP PUBLIC KEY BLOCK-----" not in armored_public_key
            or b"-----END PGP PUBLIC KEY BLOCK-----" not in armored_public_key
        ):
            raise ValueError
        if (
            type(expected_primary_fingerprint) is not str
            or _FINGERPRINT_RE.fullmatch(expected_primary_fingerprint.upper()) is None
        ):
            raise ValueError
        for executable in (git_executable, gpg_executable):
            if (
                type(executable) is not str
                or not Path(executable).is_absolute()
                or not Path(executable).is_file()
                or not os.access(executable, os.X_OK)
            ):
                raise ValueError
        valid_timeout = (
            not isinstance(timeout_seconds, bool)
            and isinstance(timeout_seconds, (int, float))
            and math.isfinite(float(timeout_seconds))
            and 0 < float(timeout_seconds) <= MAX_TIMEOUT_SECONDS
        )
        if not valid_timeout:
            raise ValueError
        return expected_primary_fingerprint.upper()
    except Exception:
        raise GitCommitSignatureError(
            "github commit signature: configuration rejected"
        ) from None


def _validate_openpgp_signature_header(raw_commit: bytes) -> None:
    header_end = raw_commit.find(b"\n\n")
    if header_end <= 0:
        raise ValueError
    headers = raw_commit[:header_end].split(b"\n")
    signature_indexes = [
        index for index, line in enumerate(headers) if line.startswith(b"gpgsig ")
    ]
    if len(signature_indexes) != 1 or any(
        line.startswith(b"gpgsig-sha256 ") for line in headers
    ):
        raise ValueError
    signature_index = signature_indexes[0]
    signature_lines: list[bytes] = [
        headers[signature_index][len(b"gpgsig "):]
    ]
    for line in headers[signature_index + 1:]:
        if not line.startswith(b" "):
            break
        signature_lines.append(line[1:])
    signature = b"\n".join(signature_lines)
    if (
        len(signature) > MAX_ARMORED_PUBLIC_KEY_BYTES
        or _SIGNATURE_BLOCK_START not in signature
        or _SIGNATURE_BLOCK_END not in signature
    ):
        raise ValueError


def _primary_fingerprints(listing: bytes) -> tuple[str, ...]:
    if type(listing) is not bytes or len(listing) > MAX_GPG_OUTPUT_BYTES:
        raise ValueError
    fingerprints: list[str] = []
    awaiting_primary_fingerprint = False
    for line in listing.splitlines():
        fields = line.split(b":")
        if fields[0] == b"pub":
            if awaiting_primary_fingerprint:
                raise ValueError
            # A revoked, expired or disabled primary key is not accepted.
            if len(fields) < 2 or fields[1] in {b"r", b"e", b"d"}:
                raise ValueError
            awaiting_primary_fingerprint = True
        elif fields[0] == b"fpr" and awaiting_primary_fingerprint:
            if len(fields) < 10:
                raise ValueError
            value = fields[9].decode("ascii").upper()
            if _FINGERPRINT_RE.fullmatch(value) is None:
                raise ValueError
            fingerprints.append(value)
            awaiting_primary_fingerprint = False
    if awaiting_primary_fingerprint:
        raise ValueError
    return tuple(fingerprints)


def _valid_signature_primary_fingerprints(output: bytes) -> tuple[str, ...]:
    if type(output) is not bytes or len(output) > MAX_GPG_OUTPUT_BYTES:
        raise ValueError
    fingerprints: list[str] = []
    for line in output.splitlines():
        marker = b"[GNUPG:] VALIDSIG "
        index = line.find(marker)
        if index < 0:
            continue
        fields = line[index + len(marker):].split()
        if not fields:
            raise ValueError
        signer_fingerprint = fields[0].decode("ascii").upper()
        primary_fingerprint = signer_fingerprint
        # GnuPG appends the primary key fingerprint for signing subkeys.
        if len(fields) >= 10:
            candidate = fields[9].decode("ascii").upper()
            if _FINGERPRINT_RE.fullmatch(candidate) is None:
                raise ValueError
            primary_fingerprint = candidate
        if _FINGERPRINT_RE.fullmatch(primary_fingerprint) is None:
            raise ValueError
        fingerprints.append(primary_fingerprint)
    return tuple(fingerprints)


def _run_bounded(
    command: list[str],
    *,
    input_bytes: bytes | None,
    cwd: Path,
    environment: dict[str, str],
    deadline: float,
    max_output_bytes: int,
    include_stderr: bool = False,
) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    result = subprocess.run(
        command,
        input=input_bytes,
        cwd=str(cwd),
        env=environment,
        stdin=subprocess.DEVNULL if input_bytes is None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=remaining,
        check=False,
        shell=False,
        close_fds=True,
    )
    if (
        len(result.stdout) > max_output_bytes
        or len(result.stderr) > max_output_bytes
        or result.returncode != 0
    ):
        raise ValueError
    return result.stdout + result.stderr if include_stderr else result.stdout
