#!/usr/bin/env python3
"""Verify and persist only the exact current EXP-2196/2197 trust artifacts."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_detached_verifier_trust_signature import (  # noqa: E402
    verify_response,
)


EVIDENCE_DIR = Path("/Volumes/AlexDATA/Agent00X-local-evidence")
AUTHORITY_KEY_SET = EVIDENCE_DIR / "control-plane-authority-keys-exp1977.json"
AUTHORITY_KEY_SET_DIGEST = "sha256:34b6a92168c02d8f37325b060545740d7e2061d991604daeac04b3b3df144ffc"
AUTHORITY_KEY_ID = "cp-macos-keychain-exp1977-20261026-v1"
ENDPOINT = "https://testdev.local/v1/verify"
VERIFIER_ID = (
    "docker-image:sha256:3e162642f617aa27d657d401393be483239ee1ee0bb7f9125c9fdb6ada8b0fc7"
    "/code:sha256:f9a39b21c3fe91c2445178d715ec6aa47063585da7f82955a4adbcbf8c7ae31b"
)
PROFILE_DIGEST = "sha256:2b5f093aefc915c8248bd04326f6cfc8f3958313384944869fb81adeffdad1f6"
VERIFIER_KEY_ID = "brainbooster-verifier-v1"
WORKER_HOST_ID = "Mac-mini-Aleksandr-3"
VERIFIER_HOST_ID = "testdev"
SEPARATION_DIGEST = "sha256:607a8dd219cfdc82f27e7a47fef84b63a1439fa14b05b47e068960c4c940b332"
ENROLLMENT_REPORT = EVIDENCE_DIR / "verifier-enrollment-exp2196.json"
ENROLLMENT_ARTIFACT = EVIDENCE_DIR / "verifier-enrollment-exp2196-artifact.json"
HOST_DECISION_REPORT = EVIDENCE_DIR / "verifier-host-decision-exp2197.json"
HOST_DECISION_ARTIFACT = EVIDENCE_DIR / "verifier-host-decision-exp2197-artifact.json"
ENROLLMENT_REPORT_EXP2258 = EVIDENCE_DIR / "verifier-enrollment-exp2258.json"
ENROLLMENT_ARTIFACT_EXP2258 = EVIDENCE_DIR / "verifier-enrollment-exp2258-artifact.json"
HOST_DECISION_REPORT_EXP2259 = EVIDENCE_DIR / "verifier-host-decision-exp2259.json"
HOST_DECISION_ARTIFACT_EXP2259 = EVIDENCE_DIR / "verifier-host-decision-exp2259-artifact.json"
ENROLLMENT_REPORT_EXP2271 = EVIDENCE_DIR / "verifier-enrollment-exp2271.json"
ENROLLMENT_ARTIFACT_EXP2271 = EVIDENCE_DIR / "verifier-enrollment-exp2271-artifact.json"
HOST_DECISION_REPORT_EXP2272 = EVIDENCE_DIR / "verifier-host-decision-exp2272.json"
HOST_DECISION_ARTIFACT_EXP2272 = EVIDENCE_DIR / "verifier-host-decision-exp2272-artifact.json"
ENROLLMENT_REPORT_EXP2381 = EVIDENCE_DIR / "verifier-enrollment-exp2381.json"
ENROLLMENT_ARTIFACT_EXP2381 = EVIDENCE_DIR / "verifier-enrollment-exp2381-artifact.json"
HOST_DECISION_REPORT_EXP2382 = EVIDENCE_DIR / "verifier-host-decision-exp2382.json"
HOST_DECISION_ARTIFACT_EXP2382 = EVIDENCE_DIR / "verifier-host-decision-exp2382-artifact.json"
ENROLLMENT_REPORT_EXP2401 = EVIDENCE_DIR / "verifier-enrollment-exp2401.json"
ENROLLMENT_ARTIFACT_EXP2401 = EVIDENCE_DIR / "verifier-enrollment-exp2401-artifact.json"
HOST_DECISION_REPORT_EXP2403 = EVIDENCE_DIR / "verifier-host-decision-exp2403.json"
HOST_DECISION_ARTIFACT_EXP2403 = EVIDENCE_DIR / "verifier-host-decision-exp2403-artifact.json"
ENROLLMENT_REPORT_EXP2485 = EVIDENCE_DIR / "verifier-enrollment-exp2485.json"
ENROLLMENT_ARTIFACT_EXP2485 = EVIDENCE_DIR / "verifier-enrollment-exp2485-artifact.json"
HOST_DECISION_REPORT_EXP2488 = EVIDENCE_DIR / "verifier-host-decision-exp2488.json"
HOST_DECISION_ARTIFACT_EXP2488 = EVIDENCE_DIR / "verifier-host-decision-exp2488-artifact.json"
ENROLLMENT_REPORT_EXP2544 = EVIDENCE_DIR / "verifier-enrollment-exp2544.json"
ENROLLMENT_ARTIFACT_EXP2544 = EVIDENCE_DIR / "verifier-enrollment-exp2544-artifact.json"
HOST_DECISION_REPORT_EXP2547 = EVIDENCE_DIR / "verifier-host-decision-exp2547.json"
HOST_DECISION_ARTIFACT_EXP2547 = EVIDENCE_DIR / "verifier-host-decision-exp2547-artifact.json"
ENROLLMENT_REPORT_EXP2843 = EVIDENCE_DIR / "verifier-enrollment-exp2843.json"
ENROLLMENT_ARTIFACT_EXP2843 = EVIDENCE_DIR / "verifier-enrollment-exp2843-artifact.json"
HOST_DECISION_REPORT_EXP2844 = EVIDENCE_DIR / "verifier-host-decision-exp2844.json"
HOST_DECISION_ARTIFACT_EXP2844 = EVIDENCE_DIR / "verifier-host-decision-exp2844-artifact.json"
ENROLLMENT_REPORT_EXP2955 = EVIDENCE_DIR / "verifier-enrollment-exp2955.json"
ENROLLMENT_ARTIFACT_EXP2955 = EVIDENCE_DIR / "verifier-enrollment-exp2955-artifact.json"
HOST_DECISION_REPORT_EXP2956 = EVIDENCE_DIR / "verifier-host-decision-exp2956.json"
HOST_DECISION_ARTIFACT_EXP2956 = EVIDENCE_DIR / "verifier-host-decision-exp2956-artifact.json"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SPECS = {
    "EXP-2196": (
        "enrollment",
        "agent00x-enrollment-exp2196",
        ENROLLMENT_REPORT,
        ENROLLMENT_ARTIFACT,
    ),
    "EXP-2197": (
        "host-decision",
        "agent00x-host-decision-exp2197",
        HOST_DECISION_REPORT,
        HOST_DECISION_ARTIFACT,
    ),
    "EXP-2258": (
        "enrollment",
        "agent00x-enrollment-exp2258",
        ENROLLMENT_REPORT_EXP2258,
        ENROLLMENT_ARTIFACT_EXP2258,
    ),
    "EXP-2259": (
        "host-decision",
        "agent00x-host-decision-exp2259",
        HOST_DECISION_REPORT_EXP2259,
        HOST_DECISION_ARTIFACT_EXP2259,
    ),
    "EXP-2271": (
        "enrollment",
        "agent00x-enrollment-exp2271",
        ENROLLMENT_REPORT_EXP2271,
        ENROLLMENT_ARTIFACT_EXP2271,
    ),
    "EXP-2272": (
        "host-decision",
        "agent00x-host-decision-exp2272",
        HOST_DECISION_REPORT_EXP2272,
        HOST_DECISION_ARTIFACT_EXP2272,
    ),
    "EXP-2381": (
        "enrollment",
        "agent00x-enrollment-exp2271",
        ENROLLMENT_REPORT_EXP2381,
        ENROLLMENT_ARTIFACT_EXP2381,
    ),
    "EXP-2382": (
        "host-decision",
        "agent00x-host-decision-exp2272",
        HOST_DECISION_REPORT_EXP2382,
        HOST_DECISION_ARTIFACT_EXP2382,
    ),
    "EXP-2401": (
        "enrollment",
        "agent00x-enrollment-exp2401",
        ENROLLMENT_REPORT_EXP2401,
        ENROLLMENT_ARTIFACT_EXP2401,
    ),
    "EXP-2403": (
        "host-decision",
        "agent00x-host-decision-exp2403",
        HOST_DECISION_REPORT_EXP2403,
        HOST_DECISION_ARTIFACT_EXP2403,
    ),
    "EXP-2485": (
        "enrollment",
        "agent00x-enrollment-exp2485",
        ENROLLMENT_REPORT_EXP2485,
        ENROLLMENT_ARTIFACT_EXP2485,
    ),
    "EXP-2488": (
        "host-decision",
        "agent00x-host-decision-exp2488",
        HOST_DECISION_REPORT_EXP2488,
        HOST_DECISION_ARTIFACT_EXP2488,
    ),
    "EXP-2544": (
        "enrollment",
        "agent00x-enrollment-exp2544",
        ENROLLMENT_REPORT_EXP2544,
        ENROLLMENT_ARTIFACT_EXP2544,
    ),
    "EXP-2547": (
        "host-decision",
        "agent00x-host-decision-exp2547",
        HOST_DECISION_REPORT_EXP2547,
        HOST_DECISION_ARTIFACT_EXP2547,
    ),
    "EXP-2843": (
        "enrollment",
        "agent00x-enrollment-exp2843",
        ENROLLMENT_REPORT_EXP2843,
        ENROLLMENT_ARTIFACT_EXP2843,
    ),
    "EXP-2844": (
        "host-decision",
        "agent00x-host-decision-exp2844",
        HOST_DECISION_REPORT_EXP2844,
        HOST_DECISION_ARTIFACT_EXP2844,
    ),
    "EXP-2955": (
        "enrollment",
        "agent00x-enrollment-exp2974",
        ENROLLMENT_REPORT_EXP2955,
        ENROLLMENT_ARTIFACT_EXP2955,
    ),
    "EXP-2956": (
        "host-decision",
        "agent00x-host-decision-exp2975",
        HOST_DECISION_REPORT_EXP2956,
        HOST_DECISION_ARTIFACT_EXP2956,
    ),
}


def _read_bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError
    return raw


def _write_exclusive_0600(path: Path, raw: bytes) -> None:
    if not path.parent.is_dir() or path.exists() or path.is_symlink():
        raise ValueError
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    if not flags & getattr(os, "O_NOFOLLOW", 0):
        raise ValueError
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OSError
            view = view[count:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o777 != 0o600:
            raise ValueError
    finally:
        os.close(descriptor)


def _verification_args(card_id: str) -> argparse.Namespace:
    kind = _SPECS[card_id][0]
    expected_enrollment_digest = None
    enrollment_artifact = None
    if kind == "host-decision":
        enrollment_card = {
            "EXP-2197": "EXP-2196",
            "EXP-2259": "EXP-2258",
            "EXP-2272": "EXP-2271",
            "EXP-2382": "EXP-2381",
            "EXP-2403": "EXP-2401",
            "EXP-2488": "EXP-2485",
            "EXP-2547": "EXP-2544",
            "EXP-2844": "EXP-2843",
            "EXP-2956": "EXP-2955",
        }[card_id]
        enrollment_spec = _SPECS[enrollment_card]
        report = json.loads(_read_bounded(enrollment_spec[2], 32_768).decode("utf-8"))
        expected_enrollment_digest = report.get("artifact_digest")
        if type(expected_enrollment_digest) is not str or _DIGEST.fullmatch(
            expected_enrollment_digest
        ) is None:
            raise ValueError
        enrollment_artifact = str(enrollment_spec[3])
    return argparse.Namespace(
        kind=kind,
        authority_key_set=str(AUTHORITY_KEY_SET),
        authority_key_set_digest=AUTHORITY_KEY_SET_DIGEST,
        expected_authority_key_id=AUTHORITY_KEY_ID,
        expected_endpoint_url=ENDPOINT,
        expected_verifier_id=VERIFIER_ID,
        expected_verifier_profile_digest=PROFILE_DIGEST,
        expected_verifier_key_id=VERIFIER_KEY_ID,
        expected_worker_host_id=WORKER_HOST_ID,
        expected_verifier_host_id=VERIFIER_HOST_ID,
        expected_host_separation_evidence_digest=SEPARATION_DIGEST,
        expected_enrollment_digest=expected_enrollment_digest,
        enrollment_artifact=enrollment_artifact,
    )


def record_signature_response(card_id: object, raw: object) -> tuple[str, str]:
    if type(card_id) is not str or card_id not in _SPECS or type(raw) is not bytes:
        raise ValueError("VERIFIER_TRUST_RECORD_REJECTED")
    kind, expected_id, report_path, artifact_path = _SPECS[card_id]
    try:
        report_raw = verify_response(_verification_args(card_id), raw)
        report = json.loads(report_raw.decode("ascii", errors="strict"))
        if (
            report.get("kind") != kind
            or report.get("artifact_id") != expected_id
            or report.get("authority_signature_valid") is not True
            or report.get("authority_key_set_digest") != AUTHORITY_KEY_SET_DIGEST
            or report.get("independent_host_trust_established") is not False
            or type(report.get("artifact_digest")) is not str
            or _DIGEST.fullmatch(report["artifact_digest"]) is None
            or type(report.get("artifact_base64")) is not str
        ):
            raise ValueError
        artifact = base64.b64decode(report["artifact_base64"], validate=True)
        if "sha256:" + hashlib.sha256(artifact).hexdigest() != report["artifact_digest"]:
            raise ValueError
        if any(path.exists() or path.is_symlink() for path in (artifact_path, report_path)):
            raise ValueError
        _write_exclusive_0600(artifact_path, artifact)
        _write_exclusive_0600(report_path, report_raw)
        return kind, report["artifact_digest"]
    except Exception:
        raise ValueError("VERIFIER_TRUST_RECORD_REJECTED") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card-id", required=True, choices=tuple(_SPECS))
    args = parser.parse_args(argv)
    try:
        kind, digest = record_signature_response(
            args.card_id, sys.stdin.buffer.read(131_073)
        )
        print(f"VERIFIER_TRUST_RECORDED|card={args.card_id}|kind={kind}|digest={digest}")
        return 0
    except Exception:
        print("VERIFIER_TRUST_RECORD_REJECTED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
