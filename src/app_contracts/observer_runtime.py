"""Narrow fail-closed observation gate for one proposal-worker invocation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Callable
from urllib.parse import urlsplit
import uuid

from .brainbooster_target_profile import (
    PINNED_HTTP_DB_FAILURE_CODES,
    PINNED_HTTP_DB_TEST_COMMAND,
)
from .observation_store import PreDispatchError, run_gated_dispatch


_IDENTITY = re.compile(r"^(process|task)-[a-z0-9-]{1,120}$")
_SAFE_ID_PART = re.compile(r"^[a-z0-9-]{8,64}$")
_WORKER_TOOL = "ProposalWorker.propose"
_TARGET_TEST_FAILURE_PREFIX = "agent00x:test-failure:"


def _safe_target_test_failure_code(result: object, *, purpose: str, argv) -> str | None:
    """Return only the exact allowlisted marker from the fixed target probe."""

    if purpose != "target-tests" or type(argv) not in (tuple, list):
        return None
    if tuple(argv) != PINNED_HTTP_DB_TEST_COMMAND:
        return None
    try:
        if getattr(result, "argv", None) != PINNED_HTTP_DB_TEST_COMMAND:
            return None
        if type(getattr(result, "returncode", None)) is not int:
            return None
        if result.returncode != 1:
            return None
        stdout = getattr(result, "stdout", None)
        if type(stdout) is not str or not stdout.endswith("\n") or stdout.count("\n") != 1:
            return None
        if not stdout.startswith(_TARGET_TEST_FAILURE_PREFIX):
            return None
        code = stdout[len(_TARGET_TEST_FAILURE_PREFIX):-1]
        return code if code in PINNED_HTTP_DB_FAILURE_CODES else None
    except Exception:
        return None


class WorkerJournalError(RuntimeError):
    """The journal gate refused a Worker proposal call before dispatch."""


class WorkerOutcomeUnknownError(RuntimeError):
    """A Worker call may have happened, but its outcome was not journaled."""


class WorkerProposalFailedError(RuntimeError):
    """The proposal Worker failed and a fixed failure event was stored."""


class VerifierJournalError(RuntimeError):
    """The journal refused an independent verifier call before dispatch."""


class VerifierOutcomeUnknownError(RuntimeError):
    """A verifier call may have happened, but its outcome was not journaled."""


class VerifierCallFailedError(RuntimeError):
    """The verifier failed and a fixed failure event was stored."""


class SandboxJournalError(RuntimeError):
    """The journal refused a sandbox command before dispatch."""


class SandboxOutcomeUnknownError(RuntimeError):
    """A sandbox command may have run, but its outcome was not journaled."""


class SandboxCallFailedError(RuntimeError):
    """The sandbox command could not be represented by bounded metadata."""


class StageJournalError(RuntimeError):
    """The stage journal refused a save or readback before dispatch."""


class StageOutcomeUnknownError(RuntimeError):
    """A stage operation may have happened, but its outcome was not journaled."""


class StageCallFailedError(RuntimeError):
    """A stage operation failed and a fixed failure event was stored."""


class SnapshotJournalError(RuntimeError):
    """The observer refused a snapshot source call before dispatch."""


class SnapshotOutcomeUnknownError(RuntimeError):
    """A snapshot source call may have happened, but was not terminally recorded."""


class SnapshotCallFailedError(RuntimeError):
    """A snapshot source call failed and a fixed failure event was stored."""


class SnapshotPinDecisionError(WorkerJournalError):
    """The observer could not safely record a pinned-snapshot decision."""


class SnapshotPinDecisionOutcomeUnknownError(SnapshotPinDecisionError):
    """A pin decision was evaluated but its terminal event was not stored."""


class ExecutionAuthorizationJournalError(WorkerJournalError):
    """The observer refused to record the one-shot execution authorization."""


class ExecutionAuthorizationOutcomeUnknownError(ExecutionAuthorizationJournalError):
    """Permit consumption may have occurred, but its result was not recorded."""


class ControlledPublicationJournalError(RuntimeError):
    """The observer refused a local controlled-publication call before dispatch."""


class ControlledPublicationOutcomeUnknownError(ControlledPublicationJournalError):
    """A local controlled-publication call ran, but its outcome was not recorded."""


class ControlledPublicationCallFailedError(ControlledPublicationJournalError):
    """A local controlled-publication call failed and a fixed result was recorded."""


# Generic aliases let non-publication runtime gates share the fixed journal
# implementation without importing a publication-named capability into the
# executor contract module.
JournaledStepGateError = ControlledPublicationJournalError
JournaledStepOutcomeUnknownError = ControlledPublicationOutcomeUnknownError


class JournaledProposalWorker:
    """Own one execution run and gate its wrapped operations with safe evidence.

    The adapter is intentionally partial: it covers explicit Worker, verifier,
    sandbox command, stage, and pinned snapshot source calls routed through its
    wrappers, plus selected fixed readiness, permit, approval, signature,
    policy, Gateway, broker, and publication steps when callers explicitly
    wrap them. It does not automatically instrument arbitrary runtime calls
    and is not a complete runtime collector.
    """

    __slots__ = (
        "_worker",
        "_store",
        "_process_id",
        "_task_id",
        "_run_id",
        "_branch_id",
        "_id_factory",
        "_clock",
        "_used",
        "_start_event_id",
        "_sequence",
        "_last_event_id",
        "_last_event_cursor",
        "_verifier_used",
        "_snapshot_pin_decision_used",
        "_execution_authorization_used",
        "_controlled_publication_used",
        "_controlled_steps_used",
    )

    def __init__(
        self,
        worker: object,
        store: object,
        *,
        process_id: str,
        task_id: str,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            not callable(getattr(worker, "propose", None))
            or not callable(getattr(store, "append", None))
            or not callable(getattr(store, "events", None))
            or not callable(getattr(store, "record_checkpoint", None))
        ):
            raise WorkerJournalError("worker journal: configuration unavailable")
        if (
            type(process_id) is not str
            or _IDENTITY.fullmatch(process_id) is None
            or not process_id.startswith("process-")
            or type(task_id) is not str
            or _IDENTITY.fullmatch(task_id) is None
            or not task_id.startswith("task-")
        ):
            raise WorkerJournalError("worker journal: configuration unavailable")
        self._worker = worker
        self._store = store
        self._process_id = process_id
        self._task_id = task_id
        self._id_factory = (lambda: uuid.uuid4().hex) if id_factory is None else id_factory
        self._clock = (lambda: datetime.now(timezone.utc)) if clock is None else clock
        try:
            run_suffix = self._next_id()
            self._run_id = f"run-{run_suffix}"
            self._reject_prior_attempt()
        except WorkerJournalError:
            raise
        except Exception:
            raise WorkerJournalError("worker journal: history unavailable") from None
        self._branch_id = "branch-main"
        self._used = False
        self._start_event_id: str | None = None
        self._sequence = 0
        self._last_event_id: str | None = None
        self._last_event_cursor: int | None = None
        self._verifier_used = False
        self._snapshot_pin_decision_used = False
        self._execution_authorization_used = False
        self._controlled_publication_used = False
        self._controlled_steps_used: set[str] = set()
        try:
            self._start_run()
        except WorkerJournalError:
            raise
        except Exception:
            raise WorkerJournalError("worker journal: run start unavailable") from None

    @classmethod
    def resume_existing(
        cls,
        worker: object,
        store: object,
        *,
        process_id: str,
        run_id: str,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> JournaledProposalWorker:
        """Attach to one complete, non-ambiguous run without starting a new one.

        Resume is read-only. It rejects any pending/unknown invocation and any
        run that already entered the publication path, so this adapter never
        interprets uncertainty as permission to repeat an action.
        """
        if (
            not callable(getattr(worker, "propose", None))
            or not callable(getattr(store, "append", None))
            or not callable(getattr(store, "events", None))
            or not callable(getattr(store, "record_checkpoint", None))
            or not callable(getattr(store, "check_result_causality", None))
            or type(process_id) is not str
            or _IDENTITY.fullmatch(process_id) is None
            or not process_id.startswith("process-")
            or type(run_id) is not str
            or not run_id.startswith("run-")
            or _SAFE_ID_PART.fullmatch(run_id[4:]) is None
        ):
            raise WorkerJournalError("worker journal: resume configuration unavailable")
        try:
            all_events = store.events()
            selected = [
                (cursor, event)
                for cursor, event in enumerate(all_events)
                if event.get("run_id") == run_id
            ]
            if not selected or any(
                event.get("process_id") != process_id for _, event in selected
            ):
                raise ValueError
            start_cursor, start = selected[0]
            task_id = start.get("task_id")
            branch_id = start.get("branch_id")
            if (
                start.get("event_type") != "agent_started"
                or start.get("sequence") != 0
                or start.get("agent_id") != "service-worker"
                or type(task_id) is not str
                or _IDENTITY.fullmatch(task_id) is None
                or not task_id.startswith("task-")
                or type(branch_id) is not str
                or not branch_id.startswith("branch-")
            ):
                raise ValueError
            matching_starts = [
                event
                for event in all_events
                if event.get("process_id") == process_id
                and event.get("task_id") == task_id
                and event.get("event_type") == "agent_started"
            ]
            if len(matching_starts) != 1 or matching_starts[0]["event_id"] != start["event_id"]:
                raise ValueError
            for expected_sequence, (cursor, event) in enumerate(selected):
                if (
                    event.get("process_id") != process_id
                    or event.get("task_id") != task_id
                    or event.get("branch_id") != branch_id
                    or event.get("sequence") != expected_sequence
                    or (expected_sequence == 0 and cursor != start_cursor)
                    or event.get("event_type") in {"agent_finished", "outcome_unknown"}
                    or event.get("status") == "unknown"
                ):
                    raise ValueError

            intent_types = {"decision_proposed", "tool_requested"}
            terminal_types = {
                "decision_applied", "tool_completed", "tool_failed", "tool_denied"
            }
            invocations: dict[str, list[dict]] = {}
            publication_labels = {
                "ControlledPublication.local-mock",
                "Approval.validate",
                "PolicyEngine.evaluate",
                "Gateway.authorize",
                "CredentialBroker.open-channel",
                "Publication.dispatch",
            }
            for _, event in selected:
                label = event.get("decision_or_tool")
                if label in publication_labels:
                    raise ValueError
                if event.get("event_type") in intent_types | terminal_types:
                    invocation_id = event.get("invocation_id")
                    if type(invocation_id) is not str:
                        raise ValueError
                    invocations.setdefault(invocation_id, []).append(event)
            for invocation_id, pair in invocations.items():
                if len(pair) != 2 or pair[0].get("event_type") not in intent_types:
                    raise ValueError
                if pair[1].get("event_type") not in terminal_types:
                    raise ValueError
                if pair[0].get("invocation_id") != invocation_id or pair[1].get(
                    "causal_event_ids"
                ) != [pair[0].get("event_id")]:
                    raise ValueError
                store.check_result_causality(pair[1])

            instance = cls.__new__(cls)
            instance._worker = worker
            instance._store = store
            instance._process_id = process_id
            instance._task_id = task_id
            instance._run_id = run_id
            instance._branch_id = branch_id
            instance._id_factory = (
                (lambda: uuid.uuid4().hex) if id_factory is None else id_factory
            )
            instance._clock = (
                (lambda: datetime.now(timezone.utc)) if clock is None else clock
            )
            instance._used = any(
                event.get("event_type") == "tool_requested"
                and event.get("decision_or_tool") == _WORKER_TOOL
                for _, event in selected
            )
            instance._start_event_id = start["event_id"]
            instance._sequence = selected[-1][1]["sequence"] + 1
            instance._last_event_id = selected[-1][1]["event_id"]
            instance._last_event_cursor = selected[-1][0]
            instance._verifier_used = any(
                event.get("decision_or_tool") == "IndependentVerifier.verify"
                for _, event in selected
            )
            instance._snapshot_pin_decision_used = any(
                event.get("decision_or_tool") == "PinnedSnapshot.validate-fixed-pin"
                for _, event in selected
            )
            instance._execution_authorization_used = any(
                event.get("decision_or_tool") == "RemoteExecutionPermit.consume"
                for _, event in selected
            )
            instance._controlled_publication_used = False
            controlled_steps = {
                "GitHubReadiness.fetch",
                "RemoteExecutionPermit.issue",
                "ModelChannel.create_chat_completion",
                "WorkerProposal.validate",
                "SandboxSnapshot.validate-binding",
                "PreparedChange.apply-proposal",
                "PreparedChange.validate-binding",
                "Approval.validate",
                "SignedApproval.verify",
                "PolicyEngine.evaluate",
                "Gateway.authorize",
                "CredentialBroker.open-channel",
                "Publication.dispatch",
            }
            instance._controlled_steps_used = {
                event.get("decision_or_tool")
                for _, event in selected
                if event.get("decision_or_tool") in controlled_steps
                and event.get("event_type") in intent_types | terminal_types
            }
            return instance
        except WorkerJournalError:
            raise
        except Exception:
            raise WorkerJournalError("worker journal: existing run cannot be resumed") from None

    def _next_id(self) -> str:
        value = self._id_factory()
        if type(value) is not str or _SAFE_ID_PART.fullmatch(value) is None:
            raise WorkerJournalError("worker journal: identifier unavailable")
        return value

    def _timestamp(self) -> str:
        moment = self._clock()
        if not isinstance(moment, datetime) or moment.tzinfo is None:
            raise WorkerJournalError("worker journal: clock unavailable")
        return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )

    def _reject_prior_attempt(self) -> None:
        events = self._store.events()
        prior_intents = [
            event
            for event in events
            if event.get("process_id") == self._process_id
            and event.get("task_id") == self._task_id
            and event.get("agent_id") == "service-worker"
            and (
                event.get("event_type") == "agent_started"
                or (
                    event.get("event_type") == "tool_requested"
                    and event.get("decision_or_tool") == _WORKER_TOOL
                )
            )
        ]
        if prior_intents:
            raise WorkerJournalError("worker journal: attempt already recorded")

    def _start_run(self) -> None:
        start_id = f"event-{self._next_id()}"
        start = self._base_event(
            event_type="agent_started", sequence=0, event_id=start_id
        )
        try:
            cursor = self._store.append(start)
        except Exception:
            raise WorkerJournalError("worker journal: run start unavailable") from None
        self._start_event_id = start_id
        self._last_event_id = start_id
        self._last_event_cursor = cursor
        self._sequence = 1

    def matches(self, store: object, *, process_id: str, task_id: str) -> bool:
        """Return whether this run is bound to the supplied executor context."""
        return (
            self._store is store
            and self._process_id == process_id
            and self._task_id == task_id
        )

    def observer_reference(self) -> dict[str, object]:
        """Return only the safe run locator and inclusive journal cursor."""
        if type(self._run_id) is not str or type(self._last_event_cursor) is not int:
            raise WorkerJournalError("worker journal: run reference unavailable")
        return {
            "run_id": self._run_id,
            "as_of_cursor": self._last_event_cursor,
            "completeness": "partial",
        }

    def record_snapshot_pin_decision(self, accepted: bool) -> bool:
        """Journal one fixed pin-comparison result without retaining pin data."""
        if type(accepted) is not bool or self._snapshot_pin_decision_used:
            raise SnapshotPinDecisionError(
                "snapshot pin journal: decision is unavailable"
            )
        self._snapshot_pin_decision_used = True
        if self._last_event_id is None or self._last_event_cursor is None:
            raise SnapshotPinDecisionError(
                "snapshot pin journal: execution run is unavailable"
            )
        try:
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "decision",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": "service-snapshot-validator",
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/snapshot-pin",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="decision_proposed",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id="service-snapshot-validator",
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": "PinnedSnapshot.validate-fixed-pin",
                    "expected_result": "bounded pinned snapshot comparison result",
                    "status": "pending",
                }
            )
            try:
                cursor, result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=lambda: accepted,
                )
            except PreDispatchError:
                raise SnapshotPinDecisionError(
                    "snapshot pin journal: pre-dispatch gate refused"
                ) from None
            self._last_event_id = intent_id
            self._last_event_cursor = cursor
            self._sequence += 1
            terminal = self._base_event(
                event_type="decision_applied",
                sequence=self._sequence,
                event_id=f"event-{self._next_id()}",
                agent_id="service-snapshot-validator",
            )
            terminal.update(
                {
                    "invocation_id": invocation_id,
                    "causal_event_ids": [intent_id],
                    "decision_or_tool": "PinnedSnapshot.validate-fixed-pin",
                    "status": "ok" if result else "denied",
                }
            )
            if not result:
                terminal["error_code"] = "pinned-snapshot-rejected"
            try:
                terminal_cursor = self._store.append(terminal)
            except Exception:
                raise SnapshotPinDecisionOutcomeUnknownError(
                    "snapshot pin journal: decision outcome is unknown"
                ) from None
            self._last_event_id = terminal["event_id"]
            self._last_event_cursor = terminal_cursor
            self._sequence += 1
            return result
        except (SnapshotPinDecisionError, SnapshotPinDecisionOutcomeUnknownError):
            raise
        except Exception:
            raise SnapshotPinDecisionError(
                "snapshot pin journal: decision gate unavailable"
            ) from None

    def record_execution_authorization(self, consume_permit: Callable[[], object]) -> bool:
        """Gate one fixed permit-consumption callback with bounded decision evidence."""
        if not callable(consume_permit) or self._execution_authorization_used:
            raise ExecutionAuthorizationJournalError(
                "execution authorization journal: decision is unavailable"
            )
        self._execution_authorization_used = True
        if self._last_event_id is None or self._last_event_cursor is None:
            raise ExecutionAuthorizationJournalError(
                "execution authorization journal: execution run is unavailable"
            )
        try:
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "decision",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": "service-execution-authorizer",
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/execution-authorization",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="decision_proposed",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id="service-execution-authorizer",
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": "RemoteExecutionPermit.consume",
                    "expected_result": "bounded execution authorization outcome",
                    "status": "pending",
                }
            )

            def dispatch():
                try:
                    consume_permit()
                    return True
                except Exception:
                    return False

            try:
                cursor, accepted = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=dispatch,
                )
            except Exception:
                raise ExecutionAuthorizationJournalError(
                    "execution authorization journal: pre-dispatch gate refused"
                ) from None
            self._last_event_id = intent_id
            self._last_event_cursor = cursor
            self._sequence += 1
            terminal = self._base_event(
                event_type="decision_applied",
                sequence=self._sequence,
                event_id=f"event-{self._next_id()}",
                agent_id="service-execution-authorizer",
            )
            terminal.update(
                {
                    "invocation_id": invocation_id,
                    "causal_event_ids": [intent_id],
                    "decision_or_tool": "RemoteExecutionPermit.consume",
                    "status": "ok" if accepted else "denied",
                }
            )
            if not accepted:
                terminal["error_code"] = "execution-authorization-unavailable"
            try:
                terminal_cursor = self._store.append(terminal)
            except Exception:
                raise ExecutionAuthorizationOutcomeUnknownError(
                    "execution authorization journal: outcome is unknown"
                ) from None
            self._last_event_id = terminal["event_id"]
            self._last_event_cursor = terminal_cursor
            self._sequence += 1
            return accepted
        except (
            ExecutionAuthorizationJournalError,
            ExecutionAuthorizationOutcomeUnknownError,
        ):
            raise
        except Exception:
            raise ExecutionAuthorizationJournalError(
                "execution authorization journal: decision gate unavailable"
            ) from None

    def run_local_mock_publication(
        self, dispatch: Callable[[], object], *, process_id: str
    ) -> object:
        """Observe one composed local-mock publication call, without authorizing it.

        The existing approval, policy, Gateway, broker and publication journal
        remain responsible for every authorization decision. This boundary
        records only that the fixed composed path was invoked and whether it
        returned or raised; no request or receipt payload is retained.
        """
        if (
            not callable(dispatch)
            or type(process_id) is not str
            or process_id != self._process_id
            or self._controlled_publication_used
        ):
            raise ControlledPublicationJournalError(
                "controlled publication journal: configuration unavailable"
            )
        self._controlled_publication_used = True
        if self._last_event_id is None or self._last_event_cursor is None:
            raise ControlledPublicationJournalError(
                "controlled publication journal: execution run is unavailable"
            )
        try:
            claim_suffix = hashlib.sha256(self._run_id.encode("ascii")).hexdigest()[:32]
            checkpoint_id = f"checkpoint-{claim_suffix}-publication"
            invocation_id = f"invocation-{claim_suffix}-publication"
            intent_id = f"event-{claim_suffix}-publication"
            agent_id = "service-publication-observer"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "tool_call",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": agent_id,
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/controlled-publication",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="tool_requested",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id=agent_id,
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": "ControlledPublication.local-mock",
                    "expected_result": "bounded local mock publication outcome",
                    "status": "pending",
                }
            )
            failure = object()
            captured_error: list[Exception] = []

            def guarded_dispatch():
                try:
                    return dispatch()
                except Exception as exc:
                    captured_error.append(exc)
                    return failure

            def intent_recorded(cursor: int) -> None:
                self._last_event_id = intent_id
                self._last_event_cursor = cursor
                self._sequence += 1

            try:
                cursor, result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=guarded_dispatch,
                    once=True,
                    on_intent_recorded=intent_recorded,
                )
            except PreDispatchError:
                raise ControlledPublicationJournalError(
                    "controlled publication journal: pre-dispatch gate refused"
                ) from None
            failed = result is failure
            unknown = bool(
                captured_error
                and isinstance(
                    captured_error[0], ControlledPublicationOutcomeUnknownError
                )
            )
            terminal = self._base_event(
                event_type=(
                    "outcome_unknown"
                    if unknown
                    else "tool_failed" if failed else "tool_completed"
                ),
                sequence=self._sequence,
                event_id=f"event-{self._next_id()}",
                agent_id=agent_id,
            )
            terminal.update(
                {
                    "invocation_id": invocation_id,
                    "causal_event_ids": [intent_id],
                    "decision_or_tool": "ControlledPublication.local-mock",
                    "status": "unknown" if unknown else "failed" if failed else "ok",
                }
            )
            if failed and not unknown:
                terminal["error_code"] = "local-mock-publication-failed"
            try:
                terminal_cursor = self._store.append(terminal)
            except Exception:
                raise ControlledPublicationOutcomeUnknownError(
                    "controlled publication journal: outcome is unknown"
                ) from None
            self._last_event_id = terminal["event_id"]
            self._last_event_cursor = terminal_cursor
            self._sequence += 1
            if unknown:
                raise ControlledPublicationOutcomeUnknownError(
                    "controlled publication journal: outcome is unknown"
                ) from None
            if failed:
                raise ControlledPublicationCallFailedError(
                    "controlled publication journal: call failed"
                ) from None
            return result
        except (
            ControlledPublicationJournalError,
            ControlledPublicationOutcomeUnknownError,
        ):
            raise
        except Exception:
            raise ControlledPublicationJournalError(
                "controlled publication journal: gate unavailable"
            ) from None

    def run_controlled_step(
        self, step: str, dispatch: Callable[[], object], *, process_id: str
    ) -> object:
        """Journal one allowlisted approval/publication gate before dispatch.

        Gate outcomes are represented only as fixed `ok`/`denied` statuses.
        The wrapped callable remains the authority and its result is returned
        unchanged; its exception is re-raised only after the denial event has
        been persisted. `Publication.dispatch` is the sole side-effecting step
        and uses tool events rather than decision events.
        """
        allowed_steps = {
            "GitHubReadiness.fetch",
            "RemoteExecutionPermit.issue",
            "ModelChannel.create_chat_completion",
            "WorkerProposal.validate",
            "SandboxSnapshot.validate-binding",
            "PreparedChange.apply-proposal",
            "PreparedChange.validate-binding",
            "Approval.validate",
            "SignedApproval.verify",
            "PolicyEngine.evaluate",
            "Gateway.authorize",
            "CredentialBroker.open-channel",
            "Publication.dispatch",
        }
        if (
            type(step) is not str
            or step not in allowed_steps
            or not callable(dispatch)
            or type(process_id) is not str
            or process_id != self._process_id
            or step in self._controlled_steps_used
        ):
            raise ControlledPublicationJournalError(
                "controlled publication journal: configuration unavailable"
            )
        self._controlled_steps_used.add(step)
        if self._last_event_id is None or self._last_event_cursor is None:
            raise ControlledPublicationJournalError(
                "controlled publication journal: execution run is unavailable"
            )
        is_readiness_fetch = step == "GitHubReadiness.fetch"
        is_tool = is_readiness_fetch or step in {
            "ModelChannel.create_chat_completion",
            "Publication.dispatch",
        }
        is_publication = step == "Publication.dispatch"
        agent_id = (
            "service-model-channel"
            if step == "ModelChannel.create_chat_completion"
            else "service-publication-observer"
        )
        captured_error: list[Exception] = []
        try:
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "tool_call" if is_tool else "decision",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": agent_id,
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/publication-{step.lower().replace('.', '-')}",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="tool_requested" if is_tool else "decision_proposed",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id=agent_id,
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": step,
                    "expected_result": {
                        "GitHubReadiness.fetch": "bounded readiness response metadata",
                        "RemoteExecutionPermit.issue": "bounded readiness eligibility result",
                        "ModelChannel.create_chat_completion": "bounded model-call outcome metadata",
                        "WorkerProposal.validate": "bounded proposal acceptance decision",
                        "SandboxSnapshot.validate-binding": "bounded sandbox snapshot binding decision",
                        "PreparedChange.apply-proposal": "bounded proposal workspace-application decision",
                        "PreparedChange.validate-binding": "bounded prepared-change binding decision",
                    }.get(step, "bounded publication-gate outcome"),
                    "status": "pending",
                }
            )
            failure = object()
            def guarded_dispatch():
                try:
                    return dispatch()
                except Exception as exc:
                    captured_error.append(exc)
                    return failure

            try:
                cursor, result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=guarded_dispatch,
                )
            except PreDispatchError:
                raise ControlledPublicationJournalError(
                    "controlled publication journal: pre-dispatch gate refused"
                ) from None
            self._last_event_id = intent_id
            self._last_event_cursor = cursor
            self._sequence += 1
            failed = result is failure
            if is_tool:
                event_type = "tool_failed" if failed else "tool_completed"
                status = "failed" if failed else "ok"
            else:
                event_type = "decision_applied"
                status = "denied" if failed else "ok"
            terminal = self._base_event(
                event_type=event_type,
                sequence=self._sequence,
                event_id=f"event-{self._next_id()}",
                agent_id=agent_id,
            )
            terminal.update(
                {
                    "invocation_id": invocation_id,
                    "causal_event_ids": [intent_id],
                    "decision_or_tool": step,
                    "status": status,
                }
            )
            if failed:
                terminal["error_code"] = {
                    "GitHubReadiness.fetch": "readiness-fetch-failed",
                    "RemoteExecutionPermit.issue": "readiness-ineligible",
                    "ModelChannel.create_chat_completion": "model-request-failed",
                    "Publication.dispatch": "publication-dispatch-failed",
                }.get(step, "publication-gate-denied")
            try:
                terminal_cursor = self._store.append(terminal)
            except Exception:
                raise ControlledPublicationOutcomeUnknownError(
                    "controlled publication journal: outcome is unknown"
                ) from None
            self._last_event_id = terminal["event_id"]
            self._last_event_cursor = terminal_cursor
            self._sequence += 1
            if failed:
                if captured_error:
                    raise captured_error[0]
                raise ControlledPublicationJournalError(
                    "controlled publication journal: call failed"
                )
            return result
        except (
            ControlledPublicationJournalError,
            ControlledPublicationOutcomeUnknownError,
        ):
            raise
        except Exception as exc:
            if captured_error and exc is captured_error[0]:
                raise
            raise ControlledPublicationJournalError(
                "controlled publication journal: gate unavailable"
            ) from None


    def _base_event(
        self, *, event_type: str, sequence: int, event_id: str,
        agent_id: str = "service-worker",
    ) -> dict:
        timestamp = self._timestamp()
        return {
            "schema_version": 1,
            "event_id": event_id,
            "event_type": event_type,
            "process_id": self._process_id,
            "run_id": self._run_id,
            "branch_id": self._branch_id,
            "task_id": self._task_id,
            "agent_id": agent_id,
            "sequence": sequence,
            "occurred_at": timestamp,
            "recorded_at": timestamp,
            "classification": "internal",
            "redaction_status": "complete",
        }

    def propose(self, worker_input):
        if self._used:
            raise WorkerJournalError("worker journal: proposal attempt already used")
        self._used = True
        try:
            if (
                getattr(worker_input, "process_id", None) != self._process_id
                or getattr(worker_input, "task_id", None) != self._task_id
            ):
                raise WorkerJournalError("worker journal: request binding mismatch")
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "tool_call",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": "service-worker",
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/worker-call",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="tool_requested", sequence=self._sequence, event_id=intent_id
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": _WORKER_TOOL,
                    "expected_result": "bounded proposal metadata",
                    "status": "pending",
                }
            )
            failure = object()

            def dispatch():
                try:
                    return self._worker.propose(worker_input)
                except Exception:
                    return failure

            try:
                intent_cursor, dispatch_result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=dispatch,
                )
            except PreDispatchError:
                raise WorkerJournalError("worker journal: pre-dispatch gate refused") from None
            self._last_event_id = intent_id
            self._last_event_cursor = intent_cursor
            self._sequence += 1

            if dispatch_result is failure:
                self._append_terminal(
                    event_type="tool_failed",
                    sequence=self._sequence,
                    invocation_id=invocation_id,
                    intent_id=intent_id,
                    status="failed",
                    error_code="worker-call-failed",
                )
                raise WorkerProposalFailedError(
                    "worker journal: proposal call failed"
                ) from None
            terminal_parameters = None
            try:
                from .executor import WorkerTerminalOutcome

                if type(dispatch_result) is WorkerTerminalOutcome:
                    terminal_parameters = {
                        "worker_outcome": dispatch_result.outcome
                    }
            except Exception:
                raise WorkerJournalError(
                    "worker journal: result type unavailable"
                ) from None
            self._append_terminal(
                event_type="tool_completed",
                sequence=self._sequence,
                invocation_id=invocation_id,
                intent_id=intent_id,
                status="ok",
                safe_parameters=terminal_parameters,
            )
            return dispatch_result
        except WorkerOutcomeUnknownError:
            raise
        except WorkerProposalFailedError:
            raise
        except WorkerJournalError:
            raise
        except Exception:
            raise WorkerJournalError("worker journal: gate unavailable") from None

    def _append_terminal(
        self,
        *,
        event_type: str,
        sequence: int,
        invocation_id: str,
        intent_id: str,
        status: str,
        error_code: str | None = None,
        safe_parameters: dict[str, str] | None = None,
    ) -> None:
        event = self._base_event(
            event_type=event_type,
            sequence=sequence,
            event_id=f"event-{self._next_id()}",
        )
        event.update(
            {
                "invocation_id": invocation_id,
                "causal_event_ids": [intent_id],
                "status": status,
            }
        )
        if error_code is not None:
            event["error_code"] = error_code
        if safe_parameters is not None:
            event["safe_parameters"] = safe_parameters
        try:
            cursor = self._store.append(event)
        except Exception:
            raise WorkerOutcomeUnknownError(
                "worker journal: proposal outcome is unknown"
            ) from None
        self._last_event_id = event["event_id"]
        self._last_event_cursor = cursor
        self._sequence = sequence + 1

    def verifier(self, verifier: object) -> JournaledVerifier:
        return JournaledVerifier(verifier, self)

    def sandbox_session(self, session: object, *, purpose: str) -> JournaledSandboxSession:
        if type(session) is JournaledSandboxSession:
            if session._run is self and session._purpose == purpose:
                return session
            raise SandboxJournalError("sandbox journal: session binding mismatch")
        return JournaledSandboxSession(session, self, purpose=purpose)

    def sandbox_backend(self, backend: object) -> JournaledSandboxBackend:
        return JournaledSandboxBackend(backend, self)

    def stage_sink(self, sink: object) -> JournaledStageSink:
        return JournaledStageSink(sink, self)

    def snapshot_transport(self, transport: object) -> JournaledGitHubSnapshotTransport:
        return JournaledGitHubSnapshotTransport(transport, self)

    def raw_commit_source(self, source: object) -> JournaledRawCommitObjectSource:
        return JournaledRawCommitObjectSource(source, self)

    def codeload_archive_transport(
        self, transport: object
    ) -> JournaledGitHubCodeloadArchiveTransport:
        return JournaledGitHubCodeloadArchiveTransport(transport, self)

    def _invoke_snapshot_source(self, *, tool_name: str, dispatch):
        allowed_tools = {
            "GitHubSnapshot.GET.commit",
            "GitHubSnapshot.GET.tree",
            "GitHubSnapshot.GET.blob",
            "GitHubRawCommitObjectSource.read",
            "GitHubCodeloadArchive.GET.archive",
        }
        if tool_name not in allowed_tools or not callable(dispatch):
            raise SnapshotJournalError("snapshot journal: configuration unavailable")
        if self._last_event_id is None or self._last_event_cursor is None:
            raise SnapshotJournalError("snapshot journal: execution run is unavailable")
        try:
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            agent_id = "service-snapshot-intake"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "tool_call",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": agent_id,
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/snapshot-intake",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="tool_requested",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id=agent_id,
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": tool_name,
                    "expected_result": "bounded pinned snapshot source result",
                    "status": "pending",
                }
            )
            failure = object()

            def guarded_dispatch():
                try:
                    return dispatch()
                except Exception:
                    return failure

            try:
                cursor, result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=guarded_dispatch,
                )
            except PreDispatchError:
                raise SnapshotJournalError(
                    "snapshot journal: pre-dispatch gate refused"
                ) from None
            self._last_event_id = intent_id
            self._last_event_cursor = cursor
            self._sequence += 1
            failed = result is failure
            terminal = self._base_event(
                event_type="tool_failed" if failed else "tool_completed",
                sequence=self._sequence,
                event_id=f"event-{self._next_id()}",
                agent_id=agent_id,
            )
            terminal.update(
                {
                    "invocation_id": invocation_id,
                    "causal_event_ids": [intent_id],
                    "status": "failed" if failed else "ok",
                }
            )
            if failed:
                terminal["error_code"] = "snapshot-source-call-failed"
            try:
                terminal_cursor = self._store.append(terminal)
            except Exception:
                raise SnapshotOutcomeUnknownError(
                    "snapshot journal: source outcome is unknown"
                ) from None
            self._last_event_id = terminal["event_id"]
            self._last_event_cursor = terminal_cursor
            self._sequence += 1
            if failed:
                raise SnapshotCallFailedError(
                    "snapshot journal: source call failed"
                ) from None
            return result
        except SnapshotOutcomeUnknownError:
            raise
        except SnapshotCallFailedError:
            raise
        except SnapshotJournalError:
            raise
        except Exception:
            raise SnapshotJournalError("snapshot journal: gate unavailable") from None

    def _invoke_stage_operation(self, sink: object, *, operation: str, value: object):
        labels = {
            "save": "StagedArtifactStore.save",
            "load": "StagedArtifactStore.load",
        }
        tool_name = labels[operation]
        if self._last_event_id is None or self._last_event_cursor is None:
            raise StageJournalError("stage journal: execution run is unavailable")
        try:
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "tool_call",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": "service-stage-store",
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/stage-{operation}",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="tool_requested",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id="service-stage-store",
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": tool_name,
                    "expected_result": "bounded stage operation metadata",
                    "status": "pending",
                }
            )
            failure = object()

            def dispatch():
                try:
                    return getattr(sink, operation)(value)
                except Exception:
                    return failure

            try:
                cursor, result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=dispatch,
                )
            except PreDispatchError:
                raise StageJournalError(
                    "stage journal: pre-dispatch gate refused"
                ) from None
            self._last_event_id = intent_id
            self._last_event_cursor = cursor
            self._sequence += 1
            failed = result is failure
            event = self._base_event(
                event_type="tool_failed" if failed else "tool_completed",
                sequence=self._sequence,
                event_id=f"event-{self._next_id()}",
                agent_id="service-stage-store",
            )
            event.update(
                {
                    "invocation_id": invocation_id,
                    "causal_event_ids": [intent_id],
                    "status": "failed" if failed else "ok",
                }
            )
            if failed:
                event["error_code"] = "stage-call-failed"
            try:
                terminal_cursor = self._store.append(event)
            except Exception:
                raise StageOutcomeUnknownError(
                    "stage journal: operation outcome is unknown"
                ) from None
            self._last_event_id = event["event_id"]
            self._last_event_cursor = terminal_cursor
            self._sequence += 1
            if failed:
                raise StageCallFailedError("stage journal: operation failed") from None
            return result
        except StageOutcomeUnknownError:
            raise
        except StageCallFailedError:
            raise
        except StageJournalError:
            raise
        except Exception:
            raise StageJournalError("stage journal: gate unavailable") from None

    def _invoke_verifier(self, verifier: object, verifier_input: object):
        if self._verifier_used:
            raise VerifierJournalError("verifier journal: attempt already used")
        self._verifier_used = True
        verify = getattr(verifier, "verify", None)
        if not callable(verify) or self._last_event_id is None or self._last_event_cursor is None:
            raise VerifierJournalError("verifier journal: configuration unavailable")
        try:
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            agent_id = "service-independent-verifier"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "tool_call",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": agent_id,
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/verifier-call",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="tool_requested",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id=agent_id,
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": "IndependentVerifier.verify",
                    "expected_result": "bounded verifier verdict metadata",
                    "status": "pending",
                }
            )
            failure = object()

            def dispatch():
                try:
                    return verify(verifier_input)
                except Exception:
                    return failure

            try:
                cursor, dispatch_result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=dispatch,
                )
            except PreDispatchError:
                raise VerifierJournalError(
                    "verifier journal: pre-dispatch gate refused"
                ) from None
            self._last_event_id = intent_id
            self._last_event_cursor = cursor
            self._sequence += 1

            if dispatch_result is failure:
                self._append_verifier_terminal(
                    event_type="tool_failed",
                    invocation_id=invocation_id,
                    intent_id=intent_id,
                    status="failed",
                    error_code="verifier-call-failed",
                )
                raise VerifierCallFailedError("verifier journal: call failed") from None
            self._append_verifier_terminal(
                event_type="tool_completed",
                invocation_id=invocation_id,
                intent_id=intent_id,
                status="ok",
            )
            return dispatch_result
        except VerifierOutcomeUnknownError:
            raise
        except VerifierCallFailedError:
            raise
        except VerifierJournalError:
            raise
        except Exception:
            raise VerifierJournalError("verifier journal: gate unavailable") from None

    def _append_verifier_terminal(
        self,
        *,
        event_type: str,
        invocation_id: str,
        intent_id: str,
        status: str,
        error_code: str | None = None,
    ) -> None:
        event = self._base_event(
            event_type=event_type,
            sequence=self._sequence,
            event_id=f"event-{self._next_id()}",
            agent_id="service-independent-verifier",
        )
        event.update(
            {
                "invocation_id": invocation_id,
                "causal_event_ids": [intent_id],
                "status": status,
            }
        )
        if error_code is not None:
            event["error_code"] = error_code
        try:
            cursor = self._store.append(event)
        except Exception:
            raise VerifierOutcomeUnknownError(
                "verifier journal: outcome is unknown"
            ) from None
        self._last_event_id = event["event_id"]
        self._last_event_cursor = cursor
        self._sequence += 1

    def _invoke_sandbox_run(
        self,
        session: object,
        *,
        purpose: str,
        argv,
        timeout_seconds: int | float,
    ):
        tool_name = {
            "target-tests": "SandboxSession.run.target-tests",
            "verifier-replay": "SandboxSession.run.verifier-replay",
        }[purpose]
        if self._last_event_id is None or self._last_event_cursor is None:
            raise SandboxJournalError("sandbox journal: execution run is unavailable")
        try:
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            agent_id = "service-sandbox"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "tool_call",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": agent_id,
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/{purpose}",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="tool_requested",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id=agent_id,
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": tool_name,
                    "expected_result": "bounded sandbox command metadata",
                    "status": "pending",
                }
            )
            failure = object()

            def dispatch():
                try:
                    return session.run(argv, timeout_seconds=timeout_seconds)
                except Exception:
                    return failure

            try:
                cursor, result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=dispatch,
                )
            except PreDispatchError:
                raise SandboxJournalError(
                    "sandbox journal: pre-dispatch gate refused"
                ) from None
            self._last_event_id = intent_id
            self._last_event_cursor = cursor
            self._sequence += 1

            if result is failure:
                self._append_sandbox_terminal(
                    event_type="tool_failed",
                    invocation_id=invocation_id,
                    intent_id=intent_id,
                    status="failed",
                    error_code="sandbox-call-failed",
                )
                raise SandboxCallFailedError("sandbox journal: command failed") from None
            returncode = getattr(result, "returncode", None)
            has_valid_returncode = type(returncode) is int
            success = has_valid_returncode and returncode == 0
            safe_parameters = (
                {"sandbox_return_code": returncode}
                if has_valid_returncode and -255 <= returncode <= 255
                else None
            )
            failure_code = _safe_target_test_failure_code(
                result,
                purpose=purpose,
                argv=argv,
            )
            if failure_code is not None:
                if safe_parameters is None:
                    safe_parameters = {}
                safe_parameters["sandbox_failure_code"] = failure_code
            self._append_sandbox_terminal(
                event_type="tool_completed" if success else "tool_failed",
                invocation_id=invocation_id,
                intent_id=intent_id,
                status="ok" if success else "failed",
                error_code=None if success else "sandbox-command-nonzero",
                safe_parameters=safe_parameters,
            )
            return result
        except SandboxOutcomeUnknownError:
            raise
        except SandboxCallFailedError:
            raise
        except SandboxJournalError:
            raise
        except Exception:
            raise SandboxJournalError("sandbox journal: gate unavailable") from None

    def _invoke_sandbox_lifecycle(
        self,
        source: object,
        *,
        operation: str,
        purpose: str,
        snapshot: object = None,
        allowed_commands: object = None,
    ):
        tools = {
            ("create", "target-tests"): "SandboxBackend.create.target-execution",
            ("create", "verifier-replay"): "SandboxBackend.create.verifier-replay",
            ("close", "target-tests"): "SandboxSession.close.target-execution",
            ("close", "verifier-replay"): "SandboxSession.close.verifier-replay",
        }
        tool_name = tools.get((operation, purpose))
        if (
            tool_name is None
            or (operation == "create" and not callable(getattr(source, "create", None)))
            or (operation == "close" and not callable(getattr(source, "close", None)))
        ):
            raise SandboxJournalError("sandbox journal: lifecycle call is unavailable")
        if self._last_event_id is None or self._last_event_cursor is None:
            raise SandboxJournalError("sandbox journal: execution run is unavailable")
        try:
            checkpoint_id = f"checkpoint-{self._next_id()}"
            invocation_id = f"invocation-{self._next_id()}"
            intent_id = f"event-{self._next_id()}"
            agent_id = "service-sandbox-lifecycle"
            timestamp = self._timestamp()
            checkpoint = {
                "schema_version": 1,
                "checkpoint_id": checkpoint_id,
                "kind": "tool_call",
                "process_id": self._process_id,
                "run_id": self._run_id,
                "branch_id": self._branch_id,
                "agent_id": agent_id,
                "trigger_event_id": self._last_event_id,
                "event_cursor": self._last_event_cursor,
                "state_ref": f"artifact://observer-state/{self._run_id}/{purpose}-{operation}",
                "completeness": "partial",
                "restore_mode": "none",
                "created_at": timestamp,
            }
            intent = self._base_event(
                event_type="tool_requested",
                sequence=self._sequence,
                event_id=intent_id,
                agent_id=agent_id,
            )
            intent.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "invocation_id": invocation_id,
                    "causal_event_ids": [self._last_event_id],
                    "decision_or_tool": tool_name,
                    "expected_result": "bounded sandbox lifecycle outcome",
                    "status": "pending",
                }
            )
            failure = object()

            def dispatch():
                try:
                    if operation == "create":
                        return source.create(snapshot, allowed_commands)
                    source.close()
                    return True
                except Exception:
                    return failure

            try:
                cursor, result = run_gated_dispatch(
                    self._store,
                    checkpoint=checkpoint,
                    intent_event=intent,
                    dispatch=dispatch,
                )
            except Exception:
                if operation == "close":
                    # Resource cleanup remains mandatory even when evidence cannot
                    # be persisted. Never strand a sandbox because the journal failed.
                    try:
                        source.close()
                    except Exception:
                        raise SandboxCallFailedError(
                            "sandbox journal: cleanup failed"
                        ) from None
                    raise SandboxOutcomeUnknownError(
                        "sandbox journal: cleanup outcome is unrecorded"
                    ) from None
                raise SandboxJournalError(
                    "sandbox journal: lifecycle gate refused"
                ) from None
            self._last_event_id = intent_id
            self._last_event_cursor = cursor
            self._sequence += 1
            if result is failure:
                self._append_sandbox_lifecycle_terminal(
                    event_type="tool_failed",
                    invocation_id=invocation_id,
                    intent_id=intent_id,
                    status="failed",
                    error_code=f"sandbox-{operation}-failed",
                )
                raise SandboxCallFailedError(
                    "sandbox journal: lifecycle call failed"
                ) from None
            try:
                self._append_sandbox_lifecycle_terminal(
                    event_type="tool_completed",
                    invocation_id=invocation_id,
                    intent_id=intent_id,
                    status="ok",
                )
            except SandboxOutcomeUnknownError:
                if operation == "create":
                    close = getattr(result, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            pass
                raise
            return result
        except (SandboxOutcomeUnknownError, SandboxCallFailedError, SandboxJournalError):
            raise
        except Exception:
            raise SandboxJournalError("sandbox journal: lifecycle gate unavailable") from None

    def _append_sandbox_lifecycle_terminal(
        self,
        *,
        event_type: str,
        invocation_id: str,
        intent_id: str,
        status: str,
        error_code: str | None = None,
    ) -> None:
        event = self._base_event(
            event_type=event_type,
            sequence=self._sequence,
            event_id=f"event-{self._next_id()}",
            agent_id="service-sandbox-lifecycle",
        )
        event.update(
            {
                "invocation_id": invocation_id,
                "causal_event_ids": [intent_id],
                "status": status,
            }
        )
        if error_code is not None:
            event["error_code"] = error_code
        try:
            cursor = self._store.append(event)
        except Exception:
            raise SandboxOutcomeUnknownError(
                "sandbox journal: lifecycle outcome is unknown"
            ) from None
        self._last_event_id = event["event_id"]
        self._last_event_cursor = cursor
        self._sequence += 1

    def _append_sandbox_terminal(
        self,
        *,
        event_type: str,
        invocation_id: str,
        intent_id: str,
        status: str,
        error_code: str | None,
        safe_parameters: dict[str, str | int] | None = None,
    ) -> None:
        event = self._base_event(
            event_type=event_type,
            sequence=self._sequence,
            event_id=f"event-{self._next_id()}",
            agent_id="service-sandbox",
        )
        event.update(
            {
                "invocation_id": invocation_id,
                "causal_event_ids": [intent_id],
                "status": status,
            }
        )
        if error_code is not None:
            event["error_code"] = error_code
        if safe_parameters is not None:
            event["safe_parameters"] = safe_parameters
        try:
            cursor = self._store.append(event)
        except Exception:
            raise SandboxOutcomeUnknownError(
                "sandbox journal: command outcome is unknown"
            ) from None
        self._last_event_id = event["event_id"]
        self._last_event_cursor = cursor
        self._sequence += 1


class JournaledModelChannel:
    """Record one host-side model-channel call without retaining its payload.

    The channel is bound to its execution run only after the observer journal
    has started. Neither request nor response data is copied into the journal.
    """

    __slots__ = ("_channel", "_run")

    def __init__(self, channel: object) -> None:
        if not callable(getattr(channel, "create_chat_completion", None)):
            raise ControlledPublicationJournalError(
                "model channel journal: configuration unavailable"
            )
        self._channel = channel
        self._run: JournaledProposalWorker | None = None

    def bind(self, run: JournaledProposalWorker) -> None:
        if type(run) is not JournaledProposalWorker or self._run is not None:
            raise ControlledPublicationJournalError(
                "model channel journal: run binding unavailable"
            )
        self._run = run

    def create_chat_completion(self, payload: dict, *, timeout_seconds: float):
        run = self._run
        if run is None:
            raise ControlledPublicationJournalError(
                "model channel journal: run binding unavailable"
            )
        return run.run_controlled_step(
            "ModelChannel.create_chat_completion",
            lambda: self._channel.create_chat_completion(
                payload, timeout_seconds=timeout_seconds
            ),
            process_id=run._process_id,
        )


class JournaledVerifier:
    """Record one independent-verifier call in its Worker's observer run."""

    __slots__ = ("_verifier", "_run")

    def __init__(self, verifier: object, run: JournaledProposalWorker) -> None:
        if (
            not callable(getattr(verifier, "verify", None))
            or type(run) is not JournaledProposalWorker
        ):
            raise VerifierJournalError("verifier journal: configuration unavailable")
        self._verifier = verifier
        self._run = run

    def verify(self, verifier_input: object):
        return self._run._invoke_verifier(self._verifier, verifier_input)


class JournaledSandboxSession:
    """Record sandbox commands and lease cleanup without retaining payloads."""

    __slots__ = ("_session", "_run", "_purpose", "_used", "_closed")

    def __init__(self, session: object, run: JournaledProposalWorker, *, purpose: str) -> None:
        if (
            not callable(getattr(session, "run", None))
            or type(run) is not JournaledProposalWorker
            or purpose not in {"target-tests", "verifier-replay"}
        ):
            raise SandboxJournalError("sandbox journal: configuration unavailable")
        self._session = session
        self._run = run
        self._purpose = purpose
        self._used = False
        self._closed = False

    def __getattr__(self, name: str):
        return getattr(self._session, name)

    def run(self, argv, timeout_seconds: int = 30):
        if self._used:
            raise SandboxJournalError("sandbox journal: command attempt already used")
        self._used = True
        return self._run._invoke_sandbox_run(
            self._session,
            purpose=self._purpose,
            argv=argv,
            timeout_seconds=timeout_seconds,
        )

    def close(self):
        if self._closed:
            return None
        self._closed = True
        return self._run._invoke_sandbox_lifecycle(
            self._session,
            operation="close",
            purpose=self._purpose,
        )


class JournaledSandboxBackend:
    """Journal the one target and optional one verifier-replay sandbox lease."""

    __slots__ = ("_backend", "_run", "_created", "_failed")

    def __init__(self, backend: object, run: JournaledProposalWorker) -> None:
        if (
            not callable(getattr(backend, "create", None))
            or type(run) is not JournaledProposalWorker
        ):
            raise SandboxJournalError("sandbox journal: backend is unavailable")
        self._backend = backend
        self._run = run
        self._created = 0
        self._failed = False

    def create(self, snapshot, allowed_commands):
        if self._failed or self._created >= 2:
            raise SandboxJournalError("sandbox journal: create attempt is unavailable")
        purpose = "target-tests" if self._created == 0 else "verifier-replay"
        self._created += 1
        try:
            session = self._run._invoke_sandbox_lifecycle(
                self._backend,
                operation="create",
                purpose=purpose,
                snapshot=snapshot,
                allowed_commands=allowed_commands,
            )
            return JournaledSandboxSession(session, self._run, purpose=purpose)
        except (SandboxOutcomeUnknownError, SandboxCallFailedError, SandboxJournalError):
            self._failed = True
            raise


class JournaledStageSink:
    """Record one save and one readback without retaining artifact content."""

    __slots__ = ("_sink", "_run", "_save_used", "_load_used")

    def __init__(self, sink: object, run: JournaledProposalWorker) -> None:
        if (
            not callable(getattr(sink, "save", None))
            or not callable(getattr(sink, "load", None))
            or type(run) is not JournaledProposalWorker
        ):
            raise StageJournalError("stage journal: configuration unavailable")
        self._sink = sink
        self._run = run
        self._save_used = False
        self._load_used = False

    def save(self, artifact: object):
        if self._save_used:
            raise StageJournalError("stage journal: save attempt already used")
        self._save_used = True
        return self._run._invoke_stage_operation(
            self._sink, operation="save", value=artifact
        )

    def load(self, staged_change_digest: str):
        if self._load_used:
            raise StageJournalError("stage journal: readback attempt already used")
        self._load_used = True
        if (
            type(staged_change_digest) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", staged_change_digest) is None
        ):
            raise StageJournalError("stage journal: digest is invalid")
        return self._run._invoke_stage_operation(
            self._sink, operation="load", value=staged_change_digest
        )


class JournaledGitHubSnapshotTransport:
    """Journal bounded anonymous GitHub snapshot GETs without retaining URLs."""

    __slots__ = ("_transport", "_run", "_calls", "_closed")

    _MAX_CALLS = 25

    def __init__(self, transport: object, run: JournaledProposalWorker) -> None:
        if not callable(transport) or type(run) is not JournaledProposalWorker:
            raise SnapshotJournalError("snapshot journal: configuration unavailable")
        self._transport = transport
        self._run = run
        self._calls = 0
        self._closed = False

    def __call__(
        self,
        method: str,
        url: str,
        headers: object,
        max_bytes: int,
        *,
        allow_redirects: bool,
    ):
        if self._closed or self._calls >= self._MAX_CALLS:
            raise SnapshotJournalError("snapshot journal: source is unavailable")
        tool_name = _snapshot_rest_tool_label(method, url, headers, max_bytes, allow_redirects)
        self._calls += 1
        try:
            return self._run._invoke_snapshot_source(
                tool_name=tool_name,
                dispatch=lambda: self._transport(
                    method,
                    url,
                    headers,
                    max_bytes,
                    allow_redirects=allow_redirects,
                ),
            )
        except (SnapshotJournalError, SnapshotOutcomeUnknownError, SnapshotCallFailedError):
            self._closed = True
            raise


class JournaledRawCommitObjectSource:
    """Journal one exact raw-commit proof without retaining its claim or bytes."""

    __slots__ = ("_source", "_run", "_used")

    def __init__(self, source: object, run: JournaledProposalWorker) -> None:
        if not callable(source) or type(run) is not JournaledProposalWorker:
            raise SnapshotJournalError("snapshot journal: configuration unavailable")
        self._source = source
        self._run = run
        self._used = False

    def __call__(self, claim: object):
        if self._used:
            raise SnapshotJournalError("snapshot journal: raw commit attempt already used")
        self._used = True
        return self._run._invoke_snapshot_source(
            tool_name="GitHubRawCommitObjectSource.read",
            dispatch=lambda: self._source(claim),
        )


class JournaledGitHubCodeloadArchiveTransport:
    """Journal one bounded fixed-host archive response without retaining bytes."""

    __slots__ = ("_transport", "_run", "_used")

    def __init__(self, transport: object, run: JournaledProposalWorker) -> None:
        if not callable(transport) or type(run) is not JournaledProposalWorker:
            raise SnapshotJournalError("snapshot journal: configuration unavailable")
        self._transport = transport
        self._run = run
        self._used = False

    def __repr__(self) -> str:
        return "JournaledGitHubCodeloadArchiveTransport(used=" + str(self._used) + ")"

    def __call__(self, owner: str, repository: str, commit_oid: str):
        if self._used:
            raise SnapshotJournalError(
                "snapshot journal: archive attempt already used"
            )
        self._used = True
        return self._run._invoke_snapshot_source(
            tool_name="GitHubCodeloadArchive.GET.archive",
            dispatch=lambda: self._transport(owner, repository, commit_oid),
        )


def _snapshot_rest_tool_label(
    method: object,
    url: object,
    headers: object,
    max_bytes: object,
    allow_redirects: object,
) -> str:
    if (
        type(method) is not str
        or method != "GET"
        or type(url) is not str
        or type(headers) is not dict
        or headers != {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        or type(max_bytes) is not int
        or not 0 < max_bytes <= 8_000_000
        or allow_redirects is not False
    ):
        raise SnapshotJournalError("snapshot journal: request is not allowlisted")
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.github.com"
            or parsed.fragment
        ):
            raise ValueError
        route = parsed.path.split("/")
        if (
            route[0] != ""
            or route[1] != "repos"
            or not route[2]
            or not route[3]
        ):
            raise ValueError
        if (
            len(route) == 6
            and route[4] == "commits"
            and re.fullmatch(r"[0-9a-f]{40}", route[5])
            and not parsed.query
        ):
            return "GitHubSnapshot.GET.commit"
        if (
            len(route) == 7
            and route[4] == "git"
            and route[5] == "trees"
            and re.fullmatch(r"[0-9a-f]{40}", route[6])
            and parsed.query == "recursive=1"
        ):
            return "GitHubSnapshot.GET.tree"
        if (
            len(route) == 7
            and route[4] == "git"
            and route[5] == "blobs"
            and re.fullmatch(r"[0-9a-f]{40}", route[6])
            and not parsed.query
        ):
            return "GitHubSnapshot.GET.blob"
        raise ValueError
    except Exception:
        raise SnapshotJournalError("snapshot journal: request is not allowlisted") from None
