#!/usr/bin/env python3
"""One non-sensitive, network-isolated verifier request against EXP-1551 image."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app_contracts.digests import sha256_digest
from src.app_contracts.executor import (
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
    verifier_snapshot_tree_digest,
)
from src.app_contracts.verifier_container import DockerContainerVerifier, VerifierContainerConfig
from src.app_contracts.verifier_process import VerifierProcessError


DOCKER = "/usr/local/bin/docker"
CONFIG_DIGEST = "sha256:f9352ed122050abfa42526544c101a713f4724271e0aa044fb92e56972a0ae38"
CODE_DIGEST = "sha256:e6fb28b9296648bc866560b81c87a0934b8f10cb36867a8c0191849761c29f1e"
SyntheticVerifierFactory = Callable[[VerifierContainerConfig], object]
_RESULTS = {
    "OPT_IN_REQUIRED": 10,
    "SYNTHETIC_VERIFIER_CONFIRMED": 0,
    "SYNTHETIC_VERIFIER_PROCESS_ERROR": 1,
    "SYNTHETIC_VERIFIER_EXCEPTION": 2,
    "SYNTHETIC_VERIFIER_RESULT_REJECTED": 3,
}
_PROCESS_FAILURE_MARKERS = {
    "verifier process: child launch failed": "SYNTHETIC_VERIFIER_PROCESS_LAUNCH_FAILED",
    "verifier process: child timed out": "SYNTHETIC_VERIFIER_PROCESS_TIMEOUT",
    "verifier process: child output exceeds limit": "SYNTHETIC_VERIFIER_PROCESS_OUTPUT_LIMIT",
    "verifier process: child response is empty": "SYNTHETIC_VERIFIER_RESPONSE_EMPTY",
    "verifier process: child response is malformed": "SYNTHETIC_VERIFIER_RESPONSE_MALFORMED",
    "verifier process: child request rejected": "SYNTHETIC_VERIFIER_CHILD_REJECTED",
    "verifier container: invocation nonce mismatch": "SYNTHETIC_VERIFIER_NONCE_MISMATCH",
}


def _process_failure_marker(error: VerifierProcessError) -> str:
    """Project only stable internal error categories into fixed markers."""

    message = str(error)
    marker = _PROCESS_FAILURE_MARKERS.get(message)
    if marker is not None:
        return marker
    if message.startswith("verifier process: child exit failed"):
        return "SYNTHETIC_VERIFIER_CHILD_EXIT_FAILED"
    if message.startswith("verifier process: child rejected ("):
        return "SYNTHETIC_VERIFIER_CHILD_REJECTED"
    return "SYNTHETIC_VERIFIER_PROCESS_ERROR"


def build_synthetic_input() -> VerifierInput:
    snapshot_files = (("calculator.py", "100644", b"def add(a, b): return 0\n"),)
    verified_contents = (("calculator.py", "def add(a, b): return a + b\n"),)
    return VerifierInput(
        process_id="exp-1552-synthetic-001",
        repository_id="synthetic-local-fixture",
        base_commit="a" * 40,
        snapshot_tree_digest=verifier_snapshot_tree_digest(snapshot_files),
        declared_change_paths=("calculator.py",),
        verified_contents=verified_contents,
        test_command=(
            "python3", "-c",
            "import calculator; assert calculator.add(2, 3) == 5; print('EXP1552_CANARY')",
        ),
        test_timeout_seconds=10,
        patch_digest="sha256:" + "1" * 64,
        evidence_digest="sha256:" + "2" * 64,
        verification_digest="sha256:" + "3" * 64,
        verified_contents_digest=sha256_digest(verified_contents),
        replay_result_digest="sha256:" + "5" * 64,
        snapshot_files=snapshot_files,
    )


def run_once(*, verifier_factory: SyntheticVerifierFactory = DockerContainerVerifier,
             output: TextIO = sys.stdout) -> int:
    if os.environ.get("RUN_DOCKER_SANDBOX_TESTS") != "1":
        output.write("OPT_IN_REQUIRED\n")
        return _RESULTS["OPT_IN_REQUIRED"]
    config = VerifierContainerConfig(
        docker_executable=DOCKER,
        runtime_image_id=CONFIG_DIGEST,
        verifier_code_digest=CODE_DIGEST,
        timeout_seconds=60,
    )
    verifier = verifier_factory(config)
    try:
        result = verifier.verify(build_synthetic_input())
    except VerifierProcessError as exc:
        marker = _process_failure_marker(exc)
        output.write(marker + "\n")
        return _RESULTS["SYNTHETIC_VERIFIER_PROCESS_ERROR"]
    except Exception:
        output.write("SYNTHETIC_VERIFIER_EXCEPTION\n")
        return _RESULTS["SYNTHETIC_VERIFIER_EXCEPTION"]
    if (
        type(result) is not VerifierResult
        or result.verdict is not VerifierVerdict.PASS
        or result.blocker_codes
    ):
        output.write("SYNTHETIC_VERIFIER_RESULT_REJECTED\n")
        return _RESULTS["SYNTHETIC_VERIFIER_RESULT_REJECTED"]
    output.write(
        "SYNTHETIC_VERIFIER_CONFIRMED|"
        f"config={CONFIG_DIGEST}|code={CODE_DIGEST}|verdict=pass|"
        "blockers=0|network=none\n"
    )
    return _RESULTS["SYNTHETIC_VERIFIER_CONFIRMED"]


if __name__ == "__main__":
    raise SystemExit(run_once())
