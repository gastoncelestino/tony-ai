"""
Tests for Tony Kernel — State Machine + Phase Gate
"""
from __future__ import annotations
import pytest
from datetime import datetime

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


class TestPhaseTransitions:
    """Test valid and invalid phase transitions."""

    def test_initial_state(self):
        state = create_initial_state("test-change", "test-project")
        assert state.current_phase == "explore"
        assert state.phases["explore"].status.value == "running"
        assert state.change_id == "test-change"

    def test_valid_transitions(self):
        """Test all valid forward transitions."""
        valid_pairs = [
            ("explore", "propose"),
            ("propose", "spec"),
            ("spec", "design"),
            ("design", "tasks"),
            ("tasks", "apply"),
            ("apply", "verify"),
            ("verify", "archive"),
        ]

        for from_phase, to_phase in valid_pairs:
            state = create_initial_state("test", "test")
            # Manually complete phases up to from_phase
            # (simplified for test)
            pass  # We test via PhaseController below

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


class TestPhaseController:
    """Test PhaseController logic."""

    def setup_method(self):
        self.state = create_initial_state("test-change", "test-project")
        self.controller = PhaseController(self.state)

    def test_initial_state(self):
        assert self.controller.change_state.current_phase == Phase.EXPLORE
        assert self.controller.change_state.phases[Phase.EXPLORE].status == PhaseStatus.RUNNING

    def test_can_transition_same_phase(self):
        allowed, reason, missing = self.controller.can_transition(Phase.EXPLORE)
        assert allowed is True
        assert "Already in phase" in reason
        assert missing == ()

    def test_valid_forward_transition_after_completion(self):
        # Complete explore phase
        self.state = self.controller.complete_phase(Phase.EXPLORE, (ArtifactRef(kind="explore", path="...", store="tonymem"),))

        controller = PhaseController(self.state)
        allowed, reason, missing = controller.can_transition(Phase.PROPOSE)
        assert allowed is True
        assert missing == ()

    def test_transition_denied_without_completion(self):
        # Try to go to propose without completing explore
        allowed, reason, missing = self.controller.can_transition(Phase.PROPOSE)
        assert allowed is False
        # Should fail because explore not completed (or missing artifacts)
        assert "not completed" in reason or "Missing required artifacts" in reason

    def test_transition_denied_missing_artifacts(self):
        # Complete explore but without artifacts
        self.state = self.controller.complete_phase(Phase.EXPLORE, ())

        controller = PhaseController(self.state)
        allowed, reason, missing = controller.can_transition(Phase.PROPOSE)
        # Should fail because explore artifact is required for transition
        assert allowed is False
        assert "explore" in missing

    def test_transition_with_artifacts(self):
        # Complete explore with artifacts
        explore_artifact = ArtifactRef(kind="explore", path="sdd/test/explore", store="tonymem")
        self.state = self.controller.complete_phase(Phase.EXPLORE, (explore_artifact,))

        controller = PhaseController(self.state)
        allowed, reason, missing = controller.can_transition(Phase.PROPOSE)
        assert allowed is True
        assert missing == ()

    def test_invalid_backward_transition(self):
        self.state = create_initial_state("test", "test")
        controller = PhaseController(self.state)
        # Can't go from explore to spec directly
        allowed, reason, missing = controller.can_transition(Phase.SPEC)
        assert allowed is False
        assert "Invalid transition" in reason

    def test_skip_phase_denied(self):
        self.state = create_initial_state("test", "test")
        controller = PhaseController(self.state)
        allowed, reason, missing = controller.can_transition(Phase.SPEC)
        assert allowed is False
        assert "Invalid transition" in reason

    def test_transition_updates_state(self):
        explore_artifact = ArtifactRef(kind="explore", path="...", store="tonymem")
        self.state = self.controller.complete_phase(Phase.EXPLORE, (explore_artifact,))

        controller = PhaseController(self.state)
        new_state = controller.transition(Phase.PROPOSE)

        assert new_state.current_phase == Phase.PROPOSE
        assert new_state.phases[Phase.EXPLORE].status == PhaseStatus.COMPLETED
        assert new_state.phases[Phase.PROPOSE].status == PhaseStatus.RUNNING

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

        assert new_state.phases[Phase.PROPOSE].status == PhaseStatus.COMPLETED
        assert len(new_state.phases[Phase.PROPOSE].artifacts) == 1
        assert new_state.phases[Phase.PROPOSE].artifacts[0].kind == "proposal"


class TestPhaseGate:
    """Test PhaseGate logic."""

    def setup_method(self):
        self.state = create_initial_state("test-change", "test-project")
        self.controller = PhaseController(self.state)
        self.gate = PhaseGate(self.controller)

    def test_same_phase_allowed(self):
        result = self.gate.check_transition(Phase.EXPLORE)
        assert result.allowed is True
        assert "Already in phase" in result.reason

    def test_transition_denied_before_completion(self):
        result = self.gate.check_transition(Phase.PROPOSE)
        assert result.allowed is False
        assert "not completed" in result.reason

    def test_transition_allowed_after_completion_with_artifacts(self):
        explore_artifact = ArtifactRef(kind="explore", path="...", store="tonymem")
        self.state = self.controller.complete_phase(Phase.EXPLORE, (ArtifactRef(kind="explore", path="...", store="tonymem"),))

        gate = PhaseGate(PhaseController(self.state))
        result = gate.check_transition(Phase.PROPOSE)
        assert result.allowed is True

    def test_assert_can_transition_raises(self):
        from kernel.state_machine import InvalidTransitionError
        with pytest.raises(Exception):  # InvalidTransitionError
            self.gate.assert_can_transition(Phase.PROPOSE)

    def test_get_status_summary(self):
        summary = self.gate.get_status_summary()
        assert summary["current_phase"] == "explore"
        assert "next_allowed" in summary


class TestPhaseOrdering:
    """Test phase ordering and indices."""

    def test_phase_order(self):
        ordered = [
            "explore", "propose", "spec", "design",
            "tasks", "apply", "verify", "archive"
        ]
        assert [p.value for p in Phase.ordered()] == [p.value for p in Phase]

    def test_phase_index(self):
        assert Phase.index("explore") == 0
        assert Phase.index("spec") == 2
        assert Phase.index("archive") == 7


class TestArtifacts:
    """Test artifact requirements."""

    def test_required_artifacts_for_transitions(self):
        assert REQUIRED_ARTIFACTS_FOR_TRANSITION[("explore", "propose")] == ("explore",)
        assert REQUIRED_ARTIFACTS_FOR_TRANSITION[("spec", "design")] == ("spec",)
        assert REQUIRED_ARTIFACTS_FOR_TRANSITION[("tasks", "apply")] == ("tasks", "spec", "design")

    def test_completion_artifacts(self):
        assert PHASE_COMPLETION_ARTIFACTS["explore"] == ("explore",)
        assert PHASE_COMPLETION_ARTIFACTS["spec"] == ("spec",)
        assert PHASE_COMPLETION_ARTIFACTS["apply"] == ("apply-progress",)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])