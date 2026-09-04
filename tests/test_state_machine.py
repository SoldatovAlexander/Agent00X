from pathlib import Path
import sys
import unittest


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

    def test_unknown_shortcut_is_rejected(self):
        with self.assertRaisesRegex(InvalidTransition, "is not allowed"):
            transition(ProcessState.RECEIVED, ProcessState.APPLYING, TransitionEvidence())


if __name__ == "__main__":
    unittest.main()
