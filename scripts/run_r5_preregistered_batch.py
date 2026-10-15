"""Run the fixed first-five R5 batch with a no-replay ledger.

This module is orchestration only. Live collaborators are supplied by a
separate caller; this file has no CLI entrypoint or environment discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app_contracts.digests import canonical_json, sha256_bytes
from app_contracts.executor import ExecutionStatus
from app_contracts.r5_attempt_ledger import (
    R5_EXECUTION_FAILURE_REASONS,
    R5AttemptRecord,
    SQLiteR5AttemptLedger,
)
from app_contracts.r5_execution import (
    R5ExecutionError,
    R5ExecutionRecord,
    run_r5_attempt,
)
from scripts.r5_batch_selection import (
    R5SelectedAttempt,
    select_first_five_attempts,
    select_r5_attempts,
)


_TERMINAL_OUTCOMES = {
    "clarification_required": (
        "needs_input", "worker-clarification", "conflicting_requirements"
    ),
    "blocked": ("blocked", "worker-blocked", "target_test_outcome_unknown"),
    "denied": ("denied", "worker-denied", "publication_not_authorized"),
}
_RESULT_REASON_CODES = frozenset(
    {
        "none",
        "execution-failed",
        "worker-clarification",
        "worker-blocked",
        "worker-denied",
    }
) | R5_EXECUTION_FAILURE_REASONS


class R5BatchRunnerError(ValueError):
    """A fixed, redacted R5 batch orchestration error."""


@dataclass(frozen=True)
class R5BatchRecord:
    attempt_id: str
    state: str
    input_digest: str
    result_digest: str | None
    outcome: str | None
    reason_code: str | None


@dataclass(frozen=True, repr=False)
class R5BatchResult:
    status: str
    records: tuple[R5BatchRecord, ...] = field(repr=False)

    def __repr__(self) -> str:
        return f"R5BatchResult(status={self.status!r}, attempt_count={len(self.records)})"


def run_first_five_r5_attempts(
    snapshot: object,
    ledger: SQLiteR5AttemptLedger,
    *,
    worker_factory,
    verifier: object,
    sandbox_backend: object,
    stage_sink: object,
    attempt_executor=run_r5_attempt,
    observation_store: object | None = None,
    selected_attempts: tuple[R5SelectedAttempt, ...] | None = None,
    continue_after_failed: bool = False,
) -> R5BatchResult:
    """Run selected IDs once; continue after failures only with explicit opt-in."""

    try:
        if (
            type(ledger) is not SQLiteR5AttemptLedger
            or type(getattr(ledger, "_closed", None)) is not bool
            or ledger._closed
            or type(continue_after_failed) is not bool
            or (continue_after_failed and selected_attempts is None)
            or not callable(attempt_executor)
            or not callable(worker_factory)
            or not callable(getattr(verifier, "verify", None))
            or not callable(getattr(sandbox_backend, "create", None))
            or not callable(getattr(stage_sink, "save", None))
            or not callable(getattr(stage_sink, "load", None))
        ):
            raise ValueError
        selected = (
            select_first_five_attempts()
            if selected_attempts is None
            else selected_attempts
        )
        if type(selected) is not tuple or not 1 <= len(selected) <= 5 or any(
            type(item) is not R5SelectedAttempt for item in selected
        ):
            raise ValueError
        if selected != select_r5_attempts(
            tuple(item.attempt_id for item in selected)
        ):
            raise ValueError
        if observation_store is not None and (
            not callable(getattr(observation_store, "append", None))
            or not callable(getattr(observation_store, "events", None))
            or not callable(getattr(observation_store, "record_checkpoint", None))
        ):
            raise ValueError

        existing = {record.attempt_id: record for record in ledger.records()}
        if not {item.attempt_id for item in selected} <= set(existing):
            raise ValueError
        output: list[R5BatchRecord] = []
        saw_failure = False
        for item in selected:
            prior = existing[item.attempt_id]
            if prior.state == "COMPLETED":
                if prior.input_digest != item.input_digest:
                    raise ValueError
                output.append(_batch_record(prior))
                if prior.outcome == "failed":
                    if not continue_after_failed:
                        return R5BatchResult("stopped-failed", tuple(output))
                    saw_failure = True
                continue
            if prior.state in {"CLAIMED", "UNKNOWN"}:
                output.append(_batch_record(prior))
                return R5BatchResult("stopped-unknown", tuple(output))
            if prior.state != "PENDING" or prior.input_digest is not None:
                raise ValueError

        # Preflight every row and digest before the first claim/call.
        for item in selected:
            prior = existing[item.attempt_id]
            if prior.state == "PENDING" and prior.input_digest is not None:
                raise ValueError
            if prior.state == "COMPLETED" and prior.input_digest != item.input_digest:
                raise ValueError

        output.clear()
        seen_workers: list[object] = []
        for item in selected:
            prior = existing[item.attempt_id]
            if prior.state == "COMPLETED":
                output.append(_batch_record(prior))
                continue
            try:
                current_worker = worker_factory(item)
            except Exception:
                return R5BatchResult("stopped-preflight", tuple(output))
            if (
                not callable(getattr(current_worker, "propose", None))
                or any(current_worker is previous for previous in seen_workers)
            ):
                return R5BatchResult("stopped-preflight", tuple(output))
            seen_workers.append(current_worker)
            ledger.claim(item.attempt_id, item.input_digest)
            try:
                record = attempt_executor(
                    item,
                    snapshot,
                    worker=current_worker,
                    verifier=verifier,
                    sandbox_backend=sandbox_backend,
                    stage_sink=stage_sink,
                    observation_store=observation_store,
                )
                if (
                    type(record) is not R5ExecutionRecord
                    or record.attempt_id != item.attempt_id
                    or record.input_digest != item.input_digest
                ):
                    raise ValueError
                outcome, reason_code = _classify_result(record)
                result_digest = _result_digest(record, reason_code=reason_code)
                ledger.complete(
                    item.attempt_id,
                    result_digest=result_digest,
                    outcome=outcome,
                    reason_code=reason_code,
                )
                output.append(
                    R5BatchRecord(
                        item.attempt_id,
                        "COMPLETED",
                        item.input_digest,
                        result_digest,
                        outcome,
                        reason_code,
                    )
                )
                if outcome == "failed":
                    if not continue_after_failed:
                        return R5BatchResult("stopped-failed", tuple(output))
                    saw_failure = True
            except Exception as exc:
                reason_code = (
                    exc.reason_code
                    if type(exc) is R5ExecutionError
                    else "pipeline-error"
                )
                try:
                    ledger.mark_unknown(
                        item.attempt_id, reason_code=reason_code
                    )
                    unknown = ledger.get(item.attempt_id)
                    output.append(_batch_record(unknown))
                except Exception:
                    output.append(
                        R5BatchRecord(
                            item.attempt_id,
                            "CLAIMED",
                            item.input_digest,
                            None,
                            None,
                            None,
                        )
                    )
                return R5BatchResult("stopped-unknown", tuple(output))
            existing[item.attempt_id] = ledger.get(item.attempt_id)
        return R5BatchResult(
            "complete-with-failures" if saw_failure else "complete",
            tuple(output),
        )
    except R5BatchRunnerError:
        raise
    except Exception:
        raise R5BatchRunnerError("R5 batch runner: fixed batch rejected") from None


def _classify_result(record: R5ExecutionRecord) -> tuple[str, str]:
    result = record.result
    if type(result.status) is not ExecutionStatus:
        raise R5BatchRunnerError("R5 batch runner: result rejected")
    if result.status is ExecutionStatus.VERIFIED:
        if result.worker_terminal_outcome is not None:
            raise R5BatchRunnerError("R5 batch runner: result rejected")
        return "verified", "none"
    terminal = _TERMINAL_OUTCOMES.get(result.worker_terminal_outcome)
    if terminal is not None:
        if result.worker_terminal_reason_code != terminal[2]:
            raise R5BatchRunnerError("R5 batch runner: result rejected")
        return terminal[:2]
    if result.worker_terminal_outcome is not None:
        raise R5BatchRunnerError("R5 batch runner: result rejected")
    failure_code = result.failure_code
    if type(failure_code) is str and failure_code in R5_EXECUTION_FAILURE_REASONS:
        return "failed", failure_code
    return "failed", "execution-failed"


def _result_digest(record: R5ExecutionRecord, *, reason_code: str) -> str:
    if type(reason_code) is not str or reason_code not in _RESULT_REASON_CODES:
        raise R5BatchRunnerError("R5 batch runner: result rejected")
    result = record.result
    fields = {
        "attempt_id": record.attempt_id,
        "input_digest": record.input_digest,
        "status": result.status.value,
        "reason_code": reason_code,
        "patch_digest": result.patch_digest,
        "verified_contents_digest": result.verified_contents_digest,
        "verification_digest": result.verification_digest,
        "staged_change_digest": result.staged_change_digest,
        "worker_terminal_outcome": result.worker_terminal_outcome,
        "worker_terminal_reason_code": result.worker_terminal_reason_code,
    }
    for name in (
        "patch_digest",
        "verified_contents_digest",
        "verification_digest",
        "staged_change_digest",
    ):
        value = fields[name]
        if value is not None and (
            type(value) is not str
            or len(value) != 71
            or not value.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in value[7:])
        ):
            raise R5BatchRunnerError("R5 batch runner: result rejected")
    if fields["worker_terminal_outcome"] is not None:
        expected = _TERMINAL_OUTCOMES.get(fields["worker_terminal_outcome"])
        if expected is None or fields["worker_terminal_reason_code"] != expected[2]:
            raise R5BatchRunnerError("R5 batch runner: result rejected")
    return sha256_bytes(canonical_json(fields))


def _batch_record(record: R5AttemptRecord) -> R5BatchRecord:
    if record.input_digest is None:
        raise R5BatchRunnerError("R5 batch runner: ledger record rejected")
    return R5BatchRecord(
        record.attempt_id,
        record.state,
        record.input_digest,
        record.result_digest,
        record.outcome,
        record.reason_code,
    )
