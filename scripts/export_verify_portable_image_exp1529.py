#!/usr/bin/env python3
"""One-shot bounded export identity check for EXP-1529."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_portable_verifier_image_exp1350 import (
    MAX_ARCHIVE_BYTES,
    InvalidChain,
    OutputLimitExceeded,
    _bounded_process_output,
    parse_portable_archive,
)


IMAGE_TAG = "agent00x-verifier:exp-1521-e6fb28b"
CONFIG_DIGEST = "sha256:b2bf83dac718dea7afc71436a2554927e016b0137893013aa96cbb098fc7456b"
DIFF_IDS = (
    "sha256:a6dc765193a52cbaede3c93a9ff48b9540948dd0774bbe7031fcb5847606f9ac",
    "sha256:a5c84380b3657bb723a1f71fa963f1e3a3f01e2c6bcba12e3b9a0d336158c7a9",
    "sha256:4a01ba3ac604812ef31dab0006efecd1d572676f7a68afa169a9d57883025006",
    "sha256:d190d09d7bd91836f809045799a7024a54026b3da5de1ccb811627fcf9878b92",
    "sha256:3e75ba9aef5c39f98681cc9e5d855962d5ec605737b177bf4158808f2fab912f",
    "sha256:d3c6d5884cd20f77425c93e783c6c5e1a6194f075fb812b0930713fae653a9fe",
    "sha256:e46f605241b75cc66c281ff8b041f8cfb24e186fd59db1934e3168e01850e8b7",
    "sha256:ffdcb91d12de3289b1ae1f0746b9feb527bdff847290aef6d6566f023ccc0bc0",
    "sha256:42dd3bf00f8da207856004c82d617e5de5400c48ccf04f26246b8f29e7af5238",
)
DOCKER_EXECUTABLE = "/usr/local/bin/docker"
TIMEOUT_SECONDS = 60
_CODES = {
    "OPT_IN_REQUIRED": 10,
    "IMAGE_SAVE_FAILED": 11,
    "IMAGE_SAVE_SIZE_LIMIT": 12,
    "IMAGE_SAVE_TIMEOUT": 13,
    "PORTABLE_IMAGE_CHAIN_INVALID": 14,
    "PORTABLE_IMAGE_IDENTITY_CONFIRMED": 0,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def run_once(
    *,
    runner: Runner = _bounded_process_output,
    output: TextIO = sys.stdout,
    temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory,
) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        return _emit(output, "OPT_IN_REQUIRED", _CODES["OPT_IN_REQUIRED"])

    try:
        with temporary_directory(prefix="agent00x-exp1529-docker-config-") as config_dir:
            result = runner(
                (DOCKER_EXECUTABLE, "image", "save", IMAGE_TAG),
                max_bytes=MAX_ARCHIVE_BYTES,
                timeout=TIMEOUT_SECONDS,
                env={
                    "DOCKER_CONFIG": str(config_dir),
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                },
            )
    except OutputLimitExceeded:
        return _emit(output, "IMAGE_SAVE_SIZE_LIMIT", _CODES["IMAGE_SAVE_SIZE_LIMIT"])
    except subprocess.TimeoutExpired:
        return _emit(output, "IMAGE_SAVE_TIMEOUT", _CODES["IMAGE_SAVE_TIMEOUT"])
    except Exception:
        return _emit(output, "IMAGE_SAVE_FAILED", _CODES["IMAGE_SAVE_FAILED"])

    if result.returncode != 0 or type(result.stdout) is not bytes:
        return _emit(output, "IMAGE_SAVE_FAILED", _CODES["IMAGE_SAVE_FAILED"])
    try:
        facts = parse_portable_archive(
            result.stdout,
            expected_config_digest=CONFIG_DIGEST,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=DIFF_IDS,
            expected_repo_tag=IMAGE_TAG,
            max_archive_bytes=MAX_ARCHIVE_BYTES,
        )
    except InvalidChain as exc:
        layer_suffix = (
            f"|layer_index={exc.layer_index}"
            if exc.layer_index is not None
            else ""
        )
        return _emit(
            output,
            f"PORTABLE_IMAGE_CHAIN_INVALID|stage={exc.stage}{layer_suffix}",
            _CODES["PORTABLE_IMAGE_CHAIN_INVALID"],
        )
    except Exception:
        return _emit(
            output,
            "PORTABLE_IMAGE_CHAIN_INVALID|stage=archive-validation",
            _CODES["PORTABLE_IMAGE_CHAIN_INVALID"],
        )

    manifest = facts.portable_manifest_digest or "null"
    output.write(
        "PORTABLE_IMAGE_IDENTITY_CONFIRMED|"
        f"format={facts.archive_format}|archive_bytes={len(result.stdout)}|"
        f"manifest={manifest}|config={facts.config_digest}|"
        f"platform={facts.os_name}/{facts.architecture}|"
        f"diff_ids={','.join(facts.diff_ids)}|repo_tag={facts.repo_tags[0]}\n"
    )
    return _CODES["PORTABLE_IMAGE_IDENTITY_CONFIRMED"]


if __name__ == "__main__":
    raise SystemExit(run_once())
