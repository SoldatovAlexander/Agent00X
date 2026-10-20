#!/usr/bin/env python3
"""One bounded, read-only inspect of the exact EXP-1658 local image."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_portable_verifier_image_exp1350 import _bounded_process_output


DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
IMAGE_TAG = "agent00x-verifier:exp-1658"
EXPECTED_ID = "sha256:228e703737010ccc001b5d784f35711ca49a00e3af4be5f0a8fcdd2fe06350a0"
EXPECTED_SIZE = 48_857_457
MAX_OUTPUT_BYTES = 8192
TIMEOUT_SECONDS = 15
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
Runner = Callable[..., object]


def inspect_once(
    *,
    runner: Runner = _bounded_process_output,
    output: TextIO = sys.stdout,
    temporary_directory=tempfile.TemporaryDirectory,
) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
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
        with temporary_directory(prefix="agent00x-exp1659-docker-config-") as config_dir:
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
        output.write("IMAGE_TUPLE_UNAVAILABLE\n")
        return 11
    if getattr(result, "returncode", None) != 0 or type(getattr(result, "stdout", None)) is not bytes:
        output.write("IMAGE_TUPLE_UNAVAILABLE\n")
        return 11
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
            or type(diff_ids) is not list
            or len(diff_ids) != 9
            or any(type(item) is not str or _DIGEST.fullmatch(item) is None for item in diff_ids)
            or tags != [IMAGE_TAG]
        ):
            raise ValueError
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        output.write("IMAGE_TUPLE_MISMATCH\n")
        return 12
    output.write(
        "IMAGE_TUPLE_CONFIRMED|"
        f"id={image_id}|platform=linux/amd64|size={EXPECTED_SIZE}|"
        f"diff_ids={','.join(diff_ids)}|tag={IMAGE_TAG}\n"
    )
    return 0


def main() -> int:
    return inspect_once()


if __name__ == "__main__":
    raise SystemExit(main())
