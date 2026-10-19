#!/usr/bin/env python3
"""One read-only inspect of the exact isolated OCI candidate tag."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
import sys
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.load_oci_verifier_candidate_exp1546 import IMAGE_TAG
from scripts.audit_portable_verifier_image_exp1350 import _bounded_process_output


DOCKER = "/usr/local/bin/docker"
MAX_OUTPUT_BYTES = 16384
TIMEOUT_SECONDS = 15
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CODES = {"OPT_IN_REQUIRED": 10, "CANDIDATE_TAG_NOT_FOUND": 11,
          "INSPECT_FACTS_INVALID": 12, "CANDIDATE_TAG_INSPECTED": 0}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(output: TextIO, marker: str, code: int) -> int:
    output.write(marker + "\n")
    return code


def run_once(*, runner: Runner = _bounded_process_output,
             output: TextIO = sys.stdout,
             temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        return _emit(output, "OPT_IN_REQUIRED", _CODES["OPT_IN_REQUIRED"])
    template = "{{.Id}}|{{.Os}}|{{.Architecture}}|{{json .RootFS.Layers}}|{{.Config.User}}|{{json .Config.Entrypoint}}"
    try:
        with temporary_directory(prefix="agent00x-exp1548-docker-config-") as config_dir:
            result = runner(
                (DOCKER, "image", "inspect", "--format", template, IMAGE_TAG),
                max_bytes=MAX_OUTPUT_BYTES,
                timeout=TIMEOUT_SECONDS,
                env={"DOCKER_CONFIG": str(config_dir), "PATH": "/usr/local/bin:/usr/bin:/bin"},
            )
    except Exception:
        return _emit(output, "CANDIDATE_TAG_NOT_FOUND", _CODES["CANDIDATE_TAG_NOT_FOUND"])
    if result.returncode != 0:
        return _emit(output, "CANDIDATE_TAG_NOT_FOUND", _CODES["CANDIDATE_TAG_NOT_FOUND"])
    if type(result.stdout) is not bytes:
        return _emit(output, "INSPECT_FACTS_INVALID", _CODES["INSPECT_FACTS_INVALID"])
    try:
        fields = result.stdout.decode("ascii").strip().split("|", 5)
        if len(fields) != 6:
            raise ValueError
        image_id, os_name, architecture, raw_diff_ids, user, raw_entrypoint = fields
        diff_ids = json.loads(raw_diff_ids)
        entrypoint = json.loads(raw_entrypoint)
        if (
            _DIGEST.fullmatch(image_id) is None
            or os_name not in {"linux", "windows"}
            or architecture not in {"amd64", "arm64", "386", "arm", "ppc64le", "s390x"}
            or not isinstance(diff_ids, list)
            or not all(isinstance(item, str) and _DIGEST.fullmatch(item) for item in diff_ids)
            or not isinstance(user, str)
            or not isinstance(entrypoint, list)
            or not all(isinstance(item, str) for item in entrypoint)
        ):
            raise ValueError
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return _emit(output, "INSPECT_FACTS_INVALID", _CODES["INSPECT_FACTS_INVALID"])
    output.write(
        "CANDIDATE_TAG_INSPECTED|"
        f"config={image_id}|platform={os_name}/{architecture}|"
        f"diff_ids={','.join(diff_ids)}|user={user}|"
        f"entrypoint={' '.join(entrypoint)}|tag={IMAGE_TAG}\n"
    )
    return _CODES["CANDIDATE_TAG_INSPECTED"]


if __name__ == "__main__":
    raise SystemExit(run_once())
