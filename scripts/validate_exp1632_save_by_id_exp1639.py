#!/usr/bin/env python3
"""One bounded by-ID save, validating its complete tagless image chain."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_portable_verifier_image_exp1350 import (  # noqa: E402
    MAX_ARCHIVE_BYTES,
    InvalidChain,
    OutputLimitExceeded,
    _bounded_process_output,
    parse_portable_archive,
)
from scripts.stream_pinned_verifier_image import (  # noqa: E402
    DIFF_IDS,
    IMAGE_ID,
    IMAGE_SIZE,
    IMAGE_TAG,
    REMOTE_CONFIG_IMAGE_ID,
    STREAM_SIZE,
)


DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
TIMEOUT_SECONDS = 90
Runner = Callable[..., subprocess.CompletedProcess[bytes]]
_SAFE_STAGE = re.compile(r"[a-z0-9-]{1,64}\Z")


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
        return _emit(output, "OPT_IN_REQUIRED", 10)
    command = (
        DOCKER,
        "--host=" + DOCKER_HOST,
        "image",
        "save",
        IMAGE_ID,
    )
    try:
        with temporary_directory(prefix="agent00x-exp1639-docker-config-") as config_dir:
            saved = runner(
                command,
                max_bytes=MAX_ARCHIVE_BYTES,
                timeout=TIMEOUT_SECONDS,
                env={
                    "DOCKER_CONFIG": str(config_dir),
                    "DOCKER_HOST": DOCKER_HOST,
                    "LANG": "C",
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                },
            )
    except OutputLimitExceeded:
        return _emit(output, "IMAGE_SAVE_LIMIT", 11)
    except subprocess.TimeoutExpired:
        return _emit(output, "IMAGE_SAVE_TIMEOUT", 12)
    except Exception:
        return _emit(output, "IMAGE_SAVE_UNAVAILABLE", 13)
    if saved.returncode != 0 or type(saved.stdout) is not bytes:
        return _emit(output, "IMAGE_SAVE_UNAVAILABLE", 13)
    if len(saved.stdout) != STREAM_SIZE:
        return _emit(output, "IMAGE_SAVE_SIZE_MISMATCH", 14)
    try:
        facts = parse_portable_archive(
            saved.stdout,
            expected_config_digest=REMOTE_CONFIG_IMAGE_ID,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=DIFF_IDS,
            expected_repo_tag=None,
            max_archive_bytes=MAX_ARCHIVE_BYTES,
        )
    except InvalidChain as exc:
        stage = exc.stage if _SAFE_STAGE.fullmatch(exc.stage) else "archive-validation"
        return _emit(output, "ARCHIVE_INVALID|stage=" + stage, 15)
    except Exception:
        return _emit(output, "ARCHIVE_INVALID|stage=archive-validation", 15)
    if (
        facts.config_digest != REMOTE_CONFIG_IMAGE_ID
        or facts.os_name != "linux"
        or facts.architecture != "amd64"
        or facts.diff_ids != DIFF_IDS
        or facts.repo_tags != ()
        or facts.archive_format not in {"docker-legacy", "oci+docker-legacy"}
        or (facts.portable_manifest_digest is not None and facts.portable_manifest_digest != IMAGE_ID)
    ):
        return _emit(output, "ARCHIVE_INVALID|stage=archive-identity", 15)
    manifest_fact = "bound" if facts.portable_manifest_digest is not None else "absent"
    return _emit(
        output,
        "IMAGE_SAVE_CHAIN_CONFIRMED|"
        f"format={facts.archive_format}|manifest={manifest_fact}|config=verified|"
        f"size={IMAGE_SIZE}|archive_bytes={len(saved.stdout)}|layers={len(DIFF_IDS)}|"
        f"repo_tags=tagless|tag={IMAGE_TAG}",
        0,
    )


if __name__ == "__main__":
    raise SystemExit(run_once())
