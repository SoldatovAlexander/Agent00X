#!/usr/bin/env python3
"""One bounded read-only save to classify EXP-1632 archive tag semantics."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_portable_verifier_image_exp1350 import (  # noqa: E402
    MAX_ARCHIVE_BYTES,
    _bounded_process_output,
)


DOCKER = "/usr/local/bin/docker"
DOCKER_HOST = "unix:///var/run/docker.sock"
IMAGE_ID = "sha256:f49397ccfb59beefa21161c86379e17ae754acee810cedd3fc5de4f5494d913f"
IMAGE_TAG = "agent00x-verifier:exp-1632"
MAX_MANIFEST_BYTES = 65_536
TIMEOUT_SECONDS = 90
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _classify_archive(archive_bytes: bytes) -> tuple[str, int] | None:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as archive:
            members = archive.getmembers()
            if not 0 < len(members) <= 128:
                return None
            by_name = {member.name: member for member in members}
            if len(by_name) != len(members):
                return None
            manifest_member = by_name.get("manifest.json")
            if (
                manifest_member is None
                or not manifest_member.isfile()
                or manifest_member.size > MAX_MANIFEST_BYTES
            ):
                return None
            stream = archive.extractfile(manifest_member)
            if stream is None:
                return None
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
            if len(raw) != manifest_member.size:
                return None
        records = json.loads(raw)
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            return None
        record = records[0]
        if set(record) != {"Config", "RepoTags", "Layers"}:
            return None
        if not isinstance(record["Config"], str) or not record["Config"]:
            return None
        layers = record["Layers"]
        if (
            not isinstance(layers, list)
            or len(layers) != 9
            or any(not isinstance(layer, str) or not layer for layer in layers)
        ):
            return None
        tags = record["RepoTags"]
        if tags is None or tags == []:
            tag_class = "tagless"
        elif tags == [IMAGE_TAG]:
            tag_class = "exact-tag"
        else:
            tag_class = "unexpected"
        return tag_class, len(layers)
    except Exception:
        return None


def run_once(
    *,
    runner: Runner = _bounded_process_output,
    output: TextIO = sys.stdout,
    temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory,
) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return 10
    command = (
        DOCKER,
        "--host=" + DOCKER_HOST,
        "image",
        "save",
        IMAGE_ID,
    )
    try:
        with temporary_directory(prefix="agent00x-exp1635-docker-config-") as config_dir:
            result = runner(
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
    except Exception:
        output.write("IMAGE_SAVE_UNAVAILABLE\n")
        return 11
    if result.returncode != 0 or type(result.stdout) is not bytes:
        output.write("IMAGE_SAVE_UNAVAILABLE\n")
        return 11
    facts = _classify_archive(result.stdout)
    if facts is None:
        output.write("SAVE_ARCHIVE_FACTS_INVALID\n")
        return 12
    tag_class, layer_count = facts
    output.write(
        f"SAVE_ARCHIVE_FACTS|archive_bytes={len(result.stdout)}"
        f"|repo_tags={tag_class}|layers={layer_count}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_once())
