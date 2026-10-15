"""Select and bind the exact first five blinded attempts in the R5 casebook.

This module only reads pinned local fixtures and builds ordinary WorkerInput
payloads. It has no model, network, target, verifier, credential, or write
capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re

from app_contracts.deepseek_worker import build_chat_completions_payload
from app_contracts.digests import canonical_json, sha256_bytes
from app_contracts.executor import WorkerInput
from scripts.r5_context_renderer import render_blinded_ordered_context_bundle
from scripts.r5_worker_input import (
    CASEBOOK_PATH,
    SOURCE_PATH,
    SOURCE_SHA256,
    build_r5_worker_input,
)


CASEBOOK_SHA256 = "bf27eb21434f6a8f099871b2608459c5a7dbae04be6186490d053fe7f07a8fe5"
RUN_ORDER_SEED = "EXP-1045-R5-2026-10-13"
EXPECTED_FIRST_FIVE = ("R5-001", "R5-002", "R5-003", "R5-004", "R5-005")
_ATTEMPT_ID = re.compile(r"R5-(?:00[1-9]|0[1-9][0-9]|100)\Z")
_SCENARIOS = frozenset(
    {
        "S1-canonical-repair",
        "S2-transfer-time-ms",
        "S3-incomplete-conflict",
        "S4-test-tool-failure",
        "S5-denied-publication",
    }
)
_ARMS = frozenset("ABCD")


class R5BatchSelectionError(ValueError):
    """A fixed, redacted error for invalid preregistered R5 selection."""


@dataclass(frozen=True, repr=False)
class R5SelectedAttempt:
    """One blinded Worker request plus control-plane-only schedule metadata."""

    attempt_id: str
    scenario_id: str
    arm_id: str
    repeat: int
    casebook_digest: str
    source_digest: str
    context_digest: str
    input_digest: str
    worker_input: WorkerInput = field(repr=False, compare=False)

    def __repr__(self) -> str:
        return (
            "R5SelectedAttempt("
            f"attempt_id={self.attempt_id!r}, scenario_id={self.scenario_id!r}, "
            f"arm_id={self.arm_id!r}, repeat={self.repeat!r}, "
            f"input_digest={self.input_digest!r})"
        )


def select_first_five_attempts() -> tuple[R5SelectedAttempt, ...]:
    """Return exactly the original first five preregistered Worker inputs."""

    return select_r5_attempts(EXPECTED_FIRST_FIVE)


def select_r5_attempts(attempt_ids: tuple[str, ...]) -> tuple[R5SelectedAttempt, ...]:
    """Build an exact bounded selection from the frozen schedule, in caller order."""

    try:
        if (
            type(attempt_ids) is not tuple
            or not 1 <= len(attempt_ids) <= 5
            or any(
                type(attempt_id) is not str
                or _ATTEMPT_ID.fullmatch(attempt_id) is None
                for attempt_id in attempt_ids
            )
            or len(set(attempt_ids)) != len(attempt_ids)
        ):
            raise ValueError
        casebook_bytes = CASEBOOK_PATH.read_bytes()
        casebook_digest = sha256_bytes(casebook_bytes)
        if casebook_digest != "sha256:" + CASEBOOK_SHA256:
            raise ValueError
        casebook = json.loads(casebook_bytes)
        if (
            type(casebook) is not dict
            or casebook.get("execution_state") != "PREREGISTERED_NOT_RUN"
            or casebook.get("run_order_seed") != RUN_ORDER_SEED
            or casebook.get("total_worker_run_attempts") != 100
            or casebook.get("credential_free") is not True
            or casebook.get("external_write") is not False
        ):
            raise ValueError
        order = casebook.get("run_order")
        if type(order) is not list or len(order) != 100:
            raise ValueError
        seen: set[str] = set()
        for item in order:
            if type(item) is not dict or set(item) != {
                "attempt_id",
                "scenario_id",
                "arm_id",
                "repeat",
            }:
                raise ValueError
            attempt_id = item["attempt_id"]
            if (
                type(attempt_id) is not str
                or _ATTEMPT_ID.fullmatch(attempt_id) is None
                or attempt_id in seen
                or item["scenario_id"] not in _SCENARIOS
                or item["arm_id"] not in _ARMS
                or type(item["repeat"]) is not int
                or not 1 <= item["repeat"] <= 5
            ):
                raise ValueError
            seen.add(attempt_id)
        if seen != {f"R5-{number:03d}" for number in range(1, 101)}:
            raise ValueError

        first = order[:5]
        if tuple(item["attempt_id"] for item in first) != EXPECTED_FIRST_FIVE:
            raise ValueError
        schedule_by_id = {item["attempt_id"]: item for item in order}
        selected_schedule = tuple(schedule_by_id[attempt_id] for attempt_id in attempt_ids)
        source = SOURCE_PATH.read_bytes()
        if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
            raise ValueError
        rendered_contexts = render_blinded_ordered_context_bundle()
        result: list[R5SelectedAttempt] = []
        for schedule_entry in selected_schedule:
            attempt_id = schedule_entry["attempt_id"]
            worker_input = build_r5_worker_input(attempt_id)
            payload = build_chat_completions_payload(worker_input)
            context_digest = sha256_bytes(rendered_contexts[schedule_entry["arm_id"]])
            input_digest = sha256_bytes(canonical_json(payload))
            result.append(
                R5SelectedAttempt(
                    attempt_id=attempt_id,
                    scenario_id=schedule_entry["scenario_id"],
                    arm_id=schedule_entry["arm_id"],
                    repeat=schedule_entry["repeat"],
                    casebook_digest=casebook_digest,
                    source_digest="sha256:" + SOURCE_SHA256,
                    context_digest=context_digest,
                    input_digest=input_digest,
                    worker_input=worker_input,
                )
            )
        return tuple(result)
    except R5BatchSelectionError:
        raise
    except Exception:
        raise R5BatchSelectionError("R5 batch selection: fixed inputs rejected") from None
