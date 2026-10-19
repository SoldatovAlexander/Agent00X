#!/usr/bin/env python3
"""One bounded, read-only inspect of the accepted EXP-1632 local image."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_portable_verifier_image_exp1350 import _bounded_process_output  # noqa: E402


DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
IMAGE_TAG = "agent00x-verifier:exp-1632"
EXPECTED_ID = "sha256:f49397ccfb59beefa21161c86379e17ae754acee810cedd3fc5de4f5494d913f"
EXPECTED_SIZE = 48_857_362
MAX_OUTPUT_BYTES = 8192
TIMEOUT_SECONDS = 15
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
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
        return _emit(output, "OPT_IN_REQUIRED", 10)
    template = "{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|{{json .RootFS.Layers}}|{{json .RepoTags}}"
    command = (
        DOCKER,
        "--host=" + DOCKER_HOST,
        "image",
        "inspect",
        "--format",
        template,
        IMAGE_TAG,
    )
    try:
        with temporary_directory(prefix="agent00x-exp1634-docker-config-") as config_dir:
            result = runner(
                command,
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=TIMEOUT_SECONDS,
                env={
                    "DOCKER_CONFIG": str(config_dir),
                    "DOCKER_HOST": DOCKER_HOST,
                    "LANG": "C",
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                },
            )
    except Exception:
        return _emit(output, "IMAGE_TUPLE_UNAVAILABLE", 11)
    if result.returncode != 0 or type(result.stdout) is not bytes:
        return _emit(output, "IMAGE_TUPLE_UNAVAILABLE", 11)
    try:
        fields = result.stdout.decode("ascii").rstrip("\n").split("|", 5)
        if len(fields) != 6:
            raise ValueError
        image_id, os_name, architecture, size_text, raw_diff_ids, raw_tags = fields
        diff_ids = json.loads(raw_diff_ids)
        tags = json.loads(raw_tags)
        if (
            image_id != EXPECTED_ID
            or os_name != "linux"
            or architecture != "amd64"
            or size_text != str(EXPECTED_SIZE)
            or not isinstance(diff_ids, list)
            or len(diff_ids) != 9
            or any(not isinstance(item, str) or _DIGEST.fullmatch(item) is None for item in diff_ids)
            or tags != [IMAGE_TAG]
        ):
            raise ValueError
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return _emit(output, "IMAGE_TUPLE_MISMATCH", 12)
    return _emit(
        output,
        "IMAGE_TUPLE_CONFIRMED|"
        f"id={image_id}|platform=linux/amd64|size={EXPECTED_SIZE}|"
        f"diff_ids={','.join(diff_ids)}|tag={IMAGE_TAG}",
        0,
    )


if __name__ == "__main__":
    raise SystemExit(run_once())
