from pathlib import Path
import sys
import unittest
from dataclasses import FrozenInstanceError, replace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.state_machine import (
    InvalidTransition,
    ProcessState,
    TransitionEvidence,
    transition,
)


class StateMachineTests(unittest.TestCase):
    def test_happy_path_requires_evidence(self):
        state = ProcessState.RECEIVED
        steps = [
            (ProcessState.SPECIFIED, TransitionEvidence(contract_complete=True)),
            (ProcessState.AUTHORIZED, TransitionEvidence(policy_allowed=True)),
            (ProcessState.EXECUTING, TransitionEvidence()),
            (ProcessState.VERIFYING, TransitionEvidence(artifact_digest=True)),
            (ProcessState.STAGED, TransitionEvidence(verification_passed=True, staged_digest=True)),
            (ProcessState.WAITING_APPROVAL, TransitionEvidence(staged_digest=True)),
            (ProcessState.APPLYING, TransitionEvidence(approval_valid=True, staged_digest=True)),
            (ProcessState.COMPLETED, TransitionEvidence(receipt_present=True, postcondition_verified=True)),
        ]
        for target, evidence in steps:
            state = transition(state, target, evidence)
        self.assertEqual(state, ProcessState.COMPLETED)

    def test_publish_without_approval_is_rejected(self):
        with self.assertRaisesRegex(InvalidTransition, "lacks required evidence"):
            transition(
                ProcessState.WAITING_APPROVAL,
                ProcessState.APPLYING,
                TransitionEvidence(staged_digest=True),
            )

    def test_completion_without_receipt_is_rejected(self):
        with self.assertRaisesRegex(InvalidTransition, "lacks required evidence"):
            transition(
                ProcessState.APPLYING,
                ProcessState.COMPLETED,
                TransitionEvidence(postcondition_verified=True),
            )

    def test_terminal_state_cannot_restart(self):
        with self.assertRaisesRegex(InvalidTransition, "terminal state"):
            transition(ProcessState.COMPLETED, ProcessState.EXECUTING, TransitionEvidence())

    def test_no_terminal_state_can_reopen(self):
        full_evidence = TransitionEvidence(
            contract_complete=True, policy_allowed=True, artifact_digest=True,
            verification_passed=True, staged_digest=True, approval_valid=True,
            receipt_present=True, postcondition_verified=True,
        )
        terminals = (ProcessState.COMPLETED, ProcessState.REJECTED, ProcessState.FAILED, ProcessState.CANCELLED)
        targets = (ProcessState.RECEIVED, ProcessState.EXECUTING, ProcessState.APPLYING, ProcessState.COMPLETED)
        for terminal in terminals:
            for target in targets:
                for evidence in (TransitionEvidence(), full_evidence):
                    with self.subTest(current=terminal, target=target):
                        with self.assertRaisesRegex(InvalidTransition, "terminal state") as raised:
                            transition(terminal, target, evidence)
                        self.assertNotIn("payload", str(raised.exception))
                        self.assertIn(str(terminal), str(raised.exception))

    def test_evidence_is_frozen_and_reusable(self):
        evidence = TransitionEvidence(contract_complete=True)
        with self.assertRaises(FrozenInstanceError):
            evidence.contract_complete = False  # type: ignore[misc]
        first = transition(ProcessState.RECEIVED, ProcessState.SPECIFIED, evidence)
        second = transition(ProcessState.RECEIVED, ProcessState.SPECIFIED, evidence)
        self.assertEqual((first, second), (ProcessState.SPECIFIED, ProcessState.SPECIFIED))
        derived = replace(evidence, contract_complete=False)
        with self.assertRaisesRegex(InvalidTransition, "lacks required evidence"):
            transition(ProcessState.RECEIVED, ProcessState.SPECIFIED, derived)
        self.assertTrue(evidence.contract_complete)

    def test_transition_errors_carry_no_evidence_payload(self):
        with self.assertRaises(InvalidTransition) as raised:
            transition(
                ProcessState.WAITING_APPROVAL,
                ProcessState.APPLYING,
                TransitionEvidence(staged_digest=True),
            )
        message = str(raised.exception)
        self.assertNotIn("True", message)
        self.assertNotIn("contract_complete", message)
        self.assertNotIn("staged_digest", message)

    def test_unknown_shortcut_is_rejected(self):
        with self.assertRaisesRegex(InvalidTransition, "is not allowed"):
            transition(ProcessState.RECEIVED, ProcessState.APPLYING, TransitionEvidence())


if __name__ == "__main__":
    unittest.main()
