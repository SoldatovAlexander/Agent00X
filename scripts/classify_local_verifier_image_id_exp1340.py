#!/usr/bin/env python3
"""Classify local Docker image ID vs archive config digest without disclosure."""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Callable, TextIO

from scripts import audit_pinned_verifier_save_archive as audit
from scripts import stream_pinned_verifier_image as pinned


_MARKER_CODES = {
    "LOCAL_INSPECT_FAILED": 10,
    "LOCAL_IDENTITY_FIELDS_INVALID": 11,
    "LOCAL_IMAGE_ID_MISMATCH": 12,
    "LOCAL_IMAGE_DESCRIPTOR_UNAVAILABLE": 13,
    "LOCAL_IMAGE_SAVE_FAILED": 14,
    "LOCAL_IMAGE_SAVE_TIMEOUT": 15,
    "LOCAL_IMAGE_SAVE_LAUNCH_FAILED": 16,
}
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _emit(marker: str, output: TextIO) -> int:
    output.write(marker + "\n")
    return _MARKER_CODES[marker]


def _parse_identity_line(value: bytes) -> tuple[str, str] | None:
    try:
        decoded = value.decode("ascii")
    except (AttributeError, UnicodeDecodeError):
        return None
    if not decoded.endswith("\n") or decoded.count("\n") != 1:
        return None
    fields = decoded[:-1].split("|", 1)
    if len(fields) != 2:
        return None
    image_id, descriptor_digest = fields
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        return None
    if descriptor_digest == "none":
        return image_id, descriptor_digest
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", descriptor_digest):
        return None
    return image_id, descriptor_digest


def run_once(
    runner: Runner = subprocess.run,
    output: TextIO = sys.stdout,
) -> int:
    """Run one local inspect then one local save, exposing only fixed facts."""
    inspect_command = (
        "/usr/local/bin/docker",
        "image",
        "inspect",
        "--format",
        "{{.Id}}|{{if .Descriptor}}{{.Descriptor.Digest}}{{else}}none{{end}}",
        pinned.IMAGE_ID,
    )
    try:
        inspected = runner(
            inspect_command, capture_output=True, timeout=15, check=False
        )
    except Exception:
        return _emit("LOCAL_INSPECT_FAILED", output)
    if inspected.returncode != 0:
        return _emit("LOCAL_INSPECT_FAILED", output)
    identity = _parse_identity_line(inspected.stdout)
    if identity is None:
        return _emit("LOCAL_IDENTITY_FIELDS_INVALID", output)
    image_id, descriptor_digest = identity
    if image_id != pinned.IMAGE_ID:
        return _emit("LOCAL_IMAGE_ID_MISMATCH", output)
    if descriptor_digest == "none":
        return _emit("LOCAL_IMAGE_DESCRIPTOR_UNAVAILABLE", output)

    try:
        saved = runner(
            ("/usr/local/bin/docker", "image", "save", pinned.IMAGE_ID),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _emit("LOCAL_IMAGE_SAVE_TIMEOUT", output)
    except Exception:
        return _emit("LOCAL_IMAGE_SAVE_LAUNCH_FAILED", output)
    if saved.returncode != 0:
        return _emit("LOCAL_IMAGE_SAVE_FAILED", output)

    output.write(
        "LOCAL_IMAGE_ID_MODEL|image_id_matches_pin=true|"
        f"id_equals_descriptor_digest={str(image_id == descriptor_digest).lower()}\n"
    )
    return audit.inspect_archive(
        saved.stdout,
        descriptor_digest=descriptor_digest,
        output=output,
    )


if __name__ == "__main__":
    raise SystemExit(run_once())
