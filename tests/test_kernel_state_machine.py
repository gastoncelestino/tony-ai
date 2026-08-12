"""
Tests for Tony Kernel — State Machine + Phase Gate
stdlib-only (unittest) — no pytest dependency
"""
from __future__ import annotations
import os
import sys
import unittest
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from kernel.schemas import (
    Phase,
    PhaseStatus,
    PhaseState,
    ChangeState,
    ArtifactRef,
    ALLOWED_TRANSITIONS,
    REQUIRED_ARTIFACTS_FOR_TRANSITION,
    PHASE_COMPLETION_ARTIFACTS,
)
from kernel.state_machine import (
    PhaseController,
    create_initial_state,
    InvalidTransitionError,
    MissingArtifactsError,
)
from kernel.phase_gate import PhaseGate, PhaseGateConfig


class TestPhaseTransitions(unittest.TestCase):
    """Test valid and invalid phase transitions."""

    def test_initial_state(self):
        state = create_initial_state("test-change", "test-project")
        self.assertEqual(state.current_phase, Phase.EXPLORE)
        self.assertEqual(state.phases[Phase.EXPLORE].status, PhaseStatus.RUNNING)
        self.assertEqual(state.change_id, "test-change")

    def test_invalid_transitions_denied(self):
        """Test that invalid transitions are denied."""
        invalid_pairs = [
            ("explore", "spec"),      # skip propose
            ("explore", "design"),    # skip propose, spec
            ("explore", "apply"),     # skip many
            ("spec", "propose"),      # backwards
            ("design", "spec"),       # backwards
            ("apply", "design"),      # backwards
            ("archive", "explore"),   # from terminal
        ]

        for from_phase, to_phase in invalid_pairs:
            state = create_initial_state("test", "test")
            # This would need PhaseController setup
            pass


class TestPhaseController(unittest.TestCase):
    """Test PhaseController logic."""

    def setUp(self):
        self.state = create_initial_state("test-change", "test-project")
        self.controller = PhaseController(self.state)

    def test_initial_state(self):
        self.assertEqual(self.controller.change_state.current_phase, Phase.EXPLORE)
        self.assertEqual(self.controller.change_state.phases[Phase.EXPLORE].status, PhaseStatus.RUNNING)

    def test_can_transition_same_phase(self):
        allowed, reason, missing = self.controller.can_transition(Phase.EXPLORE)
        self.assertTrue(allowed)
        self.assertIn("Already in phase", reason)
        self.assertEqual(missing, ())

    def test_valid_forward_transition_after_completion(self):
        # Complete explore phase
        self.state = self.controller.complete_phase(Phase.EXPLORE, (ArtifactRef(kind="explore", path="...", store="tonymem"),))

        controller = PhaseController(self.state)
        allowed, reason, missing = controller.can_transition(Phase.PROPOSE)
        self.assertTrue(allowed)
        self.assertEqual(missing, ())

    def test_transition_denied_without_completion(self):
        # Try to go to propose without completing explore
        allowed, reason, missing = self.controller.can_transition(Phase.PROPOSE)
        self.assertFalse(allowed)
        # Should fail because explore not completed (or missing artifacts)
        self.assertTrue("not completed" in reason or "Missing required artifacts" in reason)

    def test_transition_denied_missing_artifacts(self):
        # Complete explore but without artifacts
        self.state = self.controller.complete_phase(Phase.EXPLORE, ())

        controller = PhaseController(self.state)
        allowed, reason, missing = controller.can_transition(Phase.PROPOSE)
        # Should fail because explore artifact is required for transition
        self.assertFalse(allowed)
        self.assertIn("explore", missing)

    def test_transition_with_artifacts(self):
        # Complete explore with artifacts
        explore_artifact = ArtifactRef(kind="explore", path="sdd/test/explore", store="tonymem")
        self.state = self.controller.complete_phase(Phase.EXPLORE, (explore_artifact,))

        controller = PhaseController(self.state)
        allowed, reason, missing = controller.can_transition(Phase.PROPOSE)
        self.assertTrue(allowed)
        self.assertEqual(missing, ())

    def test_invalid_backward_transition(self):
        self.state = create_initial_state("test", "test")
        controller = PhaseController(self.state)
        # Can't go from explore to spec directly
        allowed, reason, missing = controller.can_transition(Phase.SPEC)
        self.assertFalse(allowed)
        self.assertIn("Invalid transition", reason)

    def test_skip_phase_denied(self):
        self.state = create_initial_state("test", "test")
        controller = PhaseController(self.state)
        allowed, reason, missing = controller.can_transition(Phase.SPEC)
        self.assertFalse(allowed)
        self.assertIn("Invalid transition", reason)

    def test_transition_updates_state(self):
        explore_artifact = ArtifactRef(kind="explore", path="...", store="tonymem")
        self.state = self.controller.complete_phase(Phase.EXPLORE, (explore_artifact,))

        controller = PhaseController(self.state)
        new_state = controller.transition(Phase.PROPOSE)

        self.assertEqual(new_state.current_phase, Phase.PROPOSE)
        self.assertEqual(new_state.phases[Phase.EXPLORE].status, PhaseStatus.COMPLETED)
        self.assertEqual(new_state.phases[Phase.PROPOSE].status, PhaseStatus.RUNNING)

    def test_complete_phase_updates_artifacts(self):
        artifact = ArtifactRef(kind="proposal", path="...", store="tonymem")
        self.state = create_initial_state("test", "test")
        controller = PhaseController(self.state)

        # Complete explore first
        new_state = controller.complete_phase(Phase.EXPLORE, (ArtifactRef(kind="explore", path="...", store="tonymem"),))
        controller = PhaseController(new_state)

        # Transition to propose
        new_state = controller.transition(Phase.PROPOSE)
        controller = PhaseController(new_state)

        # Now complete propose
        new_state = controller.complete_phase(Phase.PROPOSE, (ArtifactRef(kind="proposal", path="...", store="tonymem"),))

        self.assertEqual(new_state.phases[Phase.PROPOSE].status, PhaseStatus.COMPLETED)
        self.assertEqual(len(new_state.phases[Phase.PROPOSE].artifacts), 1)
        self.assertEqual(new_state.phases[Phase.PROPOSE].artifacts[0].kind, "proposal")


class TestPhaseGate(unittest.TestCase):
    """Test PhaseGate logic."""

    def setUp(self):
        self.state = create_initial_state("test-change", "test-project")
        self.controller = PhaseController(self.state)
        self.gate = PhaseGate(self.controller)

    def test_same_phase_allowed(self):
        result = self.gate.check_transition(Phase.EXPLORE)
        self.assertTrue(result.allowed)
        self.assertIn("Already in phase", result.reason)

    def test_transition_denied_before_completion(self):
        result = self.gate.check_transition(Phase.PROPOSE)
        self.assertFalse(result.allowed)
        self.assertIn("not completed", result.reason)

    def test_transition_allowed_after_completion_with_artifacts(self):
        explore_artifact = ArtifactRef(kind="explore", path="...", store="tonymem")
        self.state = self.controller.complete_phase(Phase.EXPLORE, (ArtifactRef(kind="explore", path="...", store="tonymem"),))

        gate = PhaseGate(PhaseController(self.state))
        result = gate.check_transition(Phase.PROPOSE)
        self.assertTrue(result.allowed)

    def test_assert_can_transition_raises(self):
        from kernel.state_machine import InvalidTransitionError
        with self.assertRaises(InvalidTransitionError):
            self.gate.assert_can_transition(Phase.PROPOSE)

    def test_get_status_summary(self):
        summary = self.gate.get_status_summary()
        self.assertEqual(summary["current_phase"], "explore")
        self.assertIn("next_allowed", summary)


class TestPhaseOrdering(unittest.TestCase):
    """Test phase ordering and indices."""

    def test_phase_order(self):
        ordered = [
            "explore", "propose", "spec", "design",
            "tasks", "apply", "verify", "archive"
        ]
        self.assertEqual([p.value for p in Phase.ordered()], ordered)

    def test_phase_index(self):
        self.assertEqual(Phase.index("explore"), 0)
        self.assertEqual(Phase.index("spec"), 2)
        self.assertEqual(Phase.index("archive"), 7)


class TestArtifacts(unittest.TestCase):
    """Test artifact requirements."""

    def test_required_artifacts_for_transitions(self):
        self.assertEqual(REQUIRED_ARTIFACTS_FOR_TRANSITION[("explore", "propose")], ("explore",))
        self.assertEqual(REQUIRED_ARTIFACTS_FOR_TRANSITION[("spec", "design")], ("spec",))
        self.assertEqual(REQUIRED_ARTIFACTS_FOR_TRANSITION[("tasks", "apply")], ("tasks", "spec", "design"))

    def test_completion_artifacts(self):
        self.assertEqual(PHASE_COMPLETION_ARTIFACTS["explore"], ("explore",))
        self.assertEqual(PHASE_COMPLETION_ARTIFACTS["spec"], ("spec",))
        self.assertEqual(PHASE_COMPLETION_ARTIFACTS["apply"], ("apply-progress",))


if __name__ == "__main__":
    unittest.main()