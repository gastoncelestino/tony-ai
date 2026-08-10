"""
Tony Kernel — Phase Gate

Gate logic for validating phase transitions and artifact readiness.
This is the main entry point for the orchestrator to check if a phase transition is allowed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .schemas import (
    Phase,
    PhaseStatus,
    ChangeState,
    ArtifactRef,
    GateCheckResult,
    GateResult,
    PHASES,
    ALLOWED_TRANSITIONS,
    REQUIRED_ARTIFACTS_FOR_TRANSITION,
    PHASE_COMPLETION_ARTIFACTS,
)
from .state_machine import PhaseController, InvalidTransitionError, MissingArtifactsError


@dataclass(frozen=True, slots=True)
class PhaseGateConfig:
    """Configuration for the phase gate."""
    # If True, enforce strict artifact validation (query tonymem/openspec)
    strict_artifact_check: bool = True
    # If True, require phase completion artifacts before allowing next phase
    require_completion_artifacts: bool = True


@dataclass
class PhaseGate:
    """
    Gate that validates phase transitions and artifact readiness.

    This is the main entry point for the orchestrator to check if a phase
    transition is allowed before delegating to a sub-agent.
    """
    controller: PhaseController
    config: PhaseGateConfig = field(default_factory=PhaseGateConfig)

    def check_transition(self, requested_phase: Phase) -> GateCheckResult:
        """
        Check if transition to `requested_phase` is allowed.

        Returns GateCheckResult with allowed/denied and detailed reasons.
        """
        from_phase = self.controller.change_state.current_phase

        # Same phase - allow (idempotent)
        if from_phase == requested_phase:
            return GateCheckResult(
                allowed=True,
                current_phase=from_phase,
                requested_phase=requested_phase,
                reason=f"Already in phase {requested_phase.value}",
            )

        # Check if transition is allowed by state machine
        allowed_next = ALLOWED_TRANSITIONS.get(from_phase, ())
        if requested_phase not in allowed_next:
            return GateCheckResult(
                allowed=False,
                current_phase=from_phase,
                requested_phase=requested_phase,
                reason=f"Invalid transition: {from_phase.value} → {requested_phase.value}. Allowed: {[p.value for p in ALLOWED_TRANSITIONS.get(from_phase, ())]}",
            )

        # Check current phase is completed
        current_state = self.controller.change_state.get_phase_state(from_phase)
        if current_state.status != PhaseStatus.COMPLETED:
            return GateCheckResult(
                allowed=False,
                current_phase=from_phase,
                requested_phase=requested_phase,
                reason=f"Current phase {from_phase.value} not completed (status: {current_state.status.value})",
                blocked_reasons=(f"Phase {from_phase.value} must be completed first",),
            )

        # Check required artifacts for transition
        required = REQUIRED_ARTIFACTS_FOR_TRANSITION.get((from_phase, requested_phase), ())
        if required:
            missing = self._check_artifacts(required)
            if missing:
                return GateCheckResult(
                    allowed=False,
                    current_phase=from_phase,
                    requested_phase=requested_phase,
                    reason=f"Missing required artifacts for {from_phase.value} → {requested_phase.value}",
                    missing_artifacts=missing,
                )

        # Check completion artifacts if configured
        if self.config.require_completion_artifacts:
            completion_required = PHASE_COMPLETION_ARTIFACTS.get(from_phase, ())
            if completion_required:
                missing = self._check_artifacts(completion_required)
                if missing:
                    return GateCheckResult(
                        allowed=False,
                        current_phase=from_phase,
                        requested_phase=requested_phase,
                        reason=f"Phase {from_phase.value} completion artifacts missing",
                        missing_artifacts=missing,
                    )

        return GateCheckResult(
            allowed=True,
            current_phase=from_phase,
            requested_phase=requested_phase,
            reason=f"Transition allowed: {from_phase.value} → {requested_phase.value}",
        )

    def _check_artifacts(self, required: tuple[str, ...]) -> tuple[str, ...]:
        """Check if required artifacts exist."""
        # In a real implementation, this would query tonymem/openspec
        # For now, check against tracked artifacts in change state
        existing = set()
        for phase_state in self.controller.change_state.phases.values():
            for artifact in phase_state.artifacts:
                existing.add(artifact.kind)

        return tuple(r for r in required if r not in existing)

    def assert_can_transition(self, requested_phase: Phase) -> None:
        """
        Assert that transition is allowed, raise exception if not.

        Use this in orchestrator before delegating to a sub-agent.
        """
        result = self.check_transition(requested_phase)
        if not result.allowed:
            if result.missing_artifacts:
                from .state_machine import MissingArtifactsError
                raise MissingArtifactsError(result.reason, result.missing_artifacts)
            raise InvalidTransitionError(result.reason)

    def get_status_summary(self) -> dict:
        """Get a summary for debugging/logging."""
        return {
            "change_id": self.controller.change_state.change_id,
            "project": self.controller.change_state.project,
            "current_phase": self.controller.change_state.current_phase.value,
            "next_allowed": [p.value for p in ALLOWED_TRANSITIONS.get(self.controller.change_state.current_phase, ())],
            "missing_for_next": self.controller.get_missing_artifacts_for_next_phase(),
            "phase_summary": self.controller.get_phase_summary(),
        }