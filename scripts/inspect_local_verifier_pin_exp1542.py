#!/usr/bin/env python3
"""One read-only local inspect of the exact verifier candidate tag."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Callable, TextIO

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import export_verify_portable_image_exp1529 as pinned
from scripts.audit_portable_verifier_image_exp1350 import _bounded_process_output


DOCKER = "/usr/local/bin/docker"
MAX_OUTPUT_BYTES = 16384
TIMEOUT_SECONDS = 15
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CODES = {"OPT_IN_REQUIRED": 10, "INSPECT_FAILED": 11, "INSPECT_FACTS_INVALID": 12,
          "LOCAL_IMAGE_PIN_MISMATCH": 13, "LOCAL_IMAGE_PIN_CONFIRMED": 0}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def run_once(*, runner: Runner = _bounded_process_output,
             output: TextIO = sys.stdout) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        return _emit(output, "OPT_IN_REQUIRED", _CODES["OPT_IN_REQUIRED"])
    template = "{{.Id}}|{{.Os}}|{{.Architecture}}|{{json .RootFS.Layers}}"
    try:
        with tempfile.TemporaryDirectory(prefix="agent00x-exp1542-docker-config-") as config_dir:
            result = runner(
                (DOCKER, "image", "inspect", "--format", template, pinned.IMAGE_TAG),
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=TIMEOUT_SECONDS,
                env={"DOCKER_CONFIG": config_dir, "PATH": "/usr/local/bin:/usr/bin:/bin"},
            )
    except Exception:
        return _emit(output, "INSPECT_FAILED", _CODES["INSPECT_FAILED"])
    if result.returncode != 0 or type(result.stdout) is not bytes:
        return _emit(output, "INSPECT_FAILED", _CODES["INSPECT_FAILED"])
    try:
        fields = result.stdout.decode("ascii").strip().split("|", 3)
        if len(fields) != 4:
            raise ValueError
        image_id, os_name, architecture, diff_ids_json = fields
        diff_ids = json.loads(diff_ids_json)
        if (
            _DIGEST.fullmatch(image_id) is None
            or os_name not in {"linux", "windows"}
            or architecture not in {"amd64", "arm64", "386", "arm", "ppc64le", "s390x"}
            or not isinstance(diff_ids, list)
            or not all(isinstance(value, str) and _DIGEST.fullmatch(value) for value in diff_ids)
        ):
            raise ValueError
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return _emit(output, "INSPECT_FACTS_INVALID", _CODES["INSPECT_FACTS_INVALID"])

    expected = (
        image_id == pinned.CONFIG_DIGEST
        and os_name == "linux"
        and architecture == "amd64"
        and tuple(diff_ids) == pinned.DIFF_IDS
    )
    marker = "LOCAL_IMAGE_PIN_CONFIRMED" if expected else "LOCAL_IMAGE_PIN_MISMATCH"
    code = _CODES[marker]
    output.write(
        f"{marker}|config={image_id}|platform={os_name}/{architecture}|"
        f"diff_ids={','.join(diff_ids)}\n"
    )
    return code


if __name__ == "__main__":
    raise SystemExit(run_once())
