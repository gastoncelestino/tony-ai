"""Tests for the Kernel phase state machine."""
from __future__ import annotations
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from kernel.schemas import ArtifactRef, Phase, PhaseStatus
from kernel.state_machine import (
    InvalidTransitionError,
    MissingArtifactsError,
    PhaseController,
    create_initial_state,
)


def artifact(kind: str) -> ArtifactRef:
    return ArtifactRef(kind=kind, path=f"sdd/test/{kind}", store="tonymem", hash="hash", validated=True)


class TestStateMachine(unittest.TestCase):
    def controller(self) -> PhaseController:
        return PhaseController(create_initial_state("state-test", "test-project"))

    def test_initial_state_starts_in_explore(self):
        controller = self.controller()
        self.assertEqual(controller.change_state.current_phase, Phase.EXPLORE)
        self.assertEqual(controller.change_state.get_phase_state(Phase.EXPLORE).status, PhaseStatus.RUNNING)

    def test_valid_transition_after_completion(self):
        controller = self.controller()
        controller.complete_phase(Phase.EXPLORE, (artifact("explore"),))
        new_state = controller.transition(Phase.PROPOSE)
        self.assertEqual(new_state.current_phase, Phase.PROPOSE)
        self.assertEqual(new_state.get_phase_state(Phase.EXPLORE).status, PhaseStatus.COMPLETED)
        self.assertEqual(new_state.get_phase_state(Phase.PROPOSE).status, PhaseStatus.RUNNING)

    def test_invalid_transition_is_rejected(self):
        controller = self.controller()
        with self.assertRaises(InvalidTransitionError):
            controller.transition(Phase.APPLY)

    def test_incomplete_phase_cannot_advance(self):
        controller = self.controller()
        allowed, reason, missing = controller.can_transition(Phase.PROPOSE)
        self.assertFalse(allowed)
        self.assertIn("not completed", reason)
        self.assertEqual(missing, ())

    def test_missing_required_artifact_blocks_transition(self):
        controller = self.controller()
        controller.complete_phase(Phase.EXPLORE, ())
        allowed, _, missing = controller.can_transition(Phase.PROPOSE)
        self.assertFalse(allowed)
        self.assertEqual(missing, ("explore",))
        with self.assertRaises(MissingArtifactsError) as ctx:
            controller.transition(Phase.PROPOSE)
        self.assertEqual(ctx.exception.missing, ("explore",))

    def test_complete_phase_updates_state(self):
        controller = self.controller()
        state = controller.complete_phase(Phase.EXPLORE, (artifact("explore"),))
        phase_state = state.get_phase_state(Phase.EXPLORE)
        self.assertEqual(phase_state.status, PhaseStatus.COMPLETED)
        self.assertIsNotNone(phase_state.completed_at)

    def test_phase_summary_reflects_state(self):
        controller = self.controller()
        controller.complete_phase(Phase.EXPLORE, (artifact("explore"),))
        summary = controller.get_phase_summary()
        self.assertEqual(summary["current_phase"], "explore")
        self.assertEqual(summary["phases"]["explore"]["status"], "completed")
        self.assertIn("propose", summary["next_allowed"])


if __name__ == "__main__":
    unittest.main()
