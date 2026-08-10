"""
Tony Kernel — State Machine

Core phase state machine for SDD workflow.
Enforces valid phase transitions and tracks phase state.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .schemas import (
    Phase,
    PhaseStatus,
    PhaseState,
    ChangeState,
    ArtifactRef,
    PHASES,
    ALLOWED_TRANSITIONS,
    REQUIRED_ARTIFACTS_FOR_TRANSITION,
    PHASE_COMPLETION_ARTIFACTS,
)


class StateMachineError(Exception):
    """Base exception for state machine errors."""
    pass


class InvalidTransitionError(StateMachineError):
    """Raised when a phase transition is not allowed."""
    pass


class MissingArtifactsError(StateMachineError):
    """Raised when required artifacts are missing for a transition."""
    def __init__(self, message: str, missing: tuple[str, ...]):
        super().__init__(message)
        self.missing = missing


class PhaseNotFoundError(StateMachineError):
    """Raised when a phase is not found in the change state."""
    pass


@dataclass
class PhaseController:
    """
    Controls phase transitions for an SDD change.
    Enforces valid transitions and artifact requirements.
    """
    change_state: ChangeState

    def can_transition(self, to_phase: Phase) -> tuple[bool, str, tuple[str, ...]]:
        """
        Check if transition to `to_phase` is allowed.

        Returns:
            (allowed, reason, missing_artifacts)
        """
        from_phase = self.change_state.current_phase

        # Same phase - no transition needed
        if from_phase == to_phase:
            return True, f"Already in phase {to_phase.value}", ()

        # Check if transition is allowed
        allowed_next = ALLOWED_TRANSITIONS.get(from_phase, ())
        if to_phase not in allowed_next:
            return False, f"Invalid transition: {from_phase.value} → {to_phase.value}. Allowed: {[p.value for p in allowed_next]}", ()

        # Check required artifacts for this transition
        required = REQUIRED_ARTIFACTS_FOR_TRANSITION.get((from_phase, to_phase), ())
        if required:
            missing = self._check_artifacts_exist(required)
            if missing:
                return False, f"Missing required artifacts for {from_phase.value} → {to_phase.value}", missing

        # Check that current phase is completed
        current_state = self.change_state.get_phase_state(from_phase)
        if current_state.status != PhaseStatus.COMPLETED:
            return False, f"Current phase {from_phase.value} not completed (status: {current_state.status.value})", ()

        return True, f"Transition allowed: {from_phase.value} → {to_phase.value}", ()

    def _check_artifacts_exist(self, required: tuple[str, ...]) -> tuple[str, ...]:
        """Check if required artifacts exist in tonymem/openspec."""
        # This is a stub - actual implementation would query tonymem/openspec
        # For now, we assume artifacts exist if they're in the change state
        existing = set()
        for phase_state in self.change_state.phases.values():
            for artifact in phase_state.artifacts:
                existing.add(artifact.kind)

        return tuple(r for r in required if r not in existing)

    def transition(self, to_phase: Phase, artifacts: tuple[ArtifactRef, ...] = ()) -> ChangeState:
        """
        Perform the phase transition.

        Returns new ChangeState with updated phase.
        """
        allowed, reason, missing = self.can_transition(to_phase)
        if not allowed:
            if missing:
                raise MissingArtifactsError(reason, missing)
            raise InvalidTransitionError(reason)

        from_phase = self.change_state.current_phase

        # Update from_phase status to COMPLETED if not already
        from_state = self.change_state.get_phase_state(from_phase)
        updated_phases = dict(self.change_state.phases)

        if from_state.status != PhaseStatus.COMPLETED:
            updated_phases[from_phase] = PhaseState(
                phase=from_phase,
                status=PhaseStatus.COMPLETED,
                artifacts=from_state.artifacts,
                started_at=from_state.started_at,
                completed_at=datetime.now(),
            )

        # Create or update to_phase state
        to_state = self.change_state.get_phase_state(to_phase)
        updated_phases[to_phase] = PhaseState(
            phase=to_phase,
            status=PhaseStatus.RUNNING,
            artifacts=artifacts or to_state.artifacts,
            started_at=datetime.now(),
        )

        return ChangeState(
            change_id=self.change_state.change_id,
            project=self.change_state.project,
            current_phase=to_phase,
            phases=updated_phases,
            created_at=self.change_state.created_at,
            updated_at=datetime.now(),
            metadata=self.change_state.metadata,
        )

    def complete_phase(self, phase: Phase, artifacts: tuple[ArtifactRef, ...]) -> ChangeState:
        """
        Mark a phase as completed with its artifacts.
        """
        if phase not in self.change_state.phases:
            raise PhaseNotFoundError(f"Phase {phase.value} not found in change state")

        current_state = self.change_state.get_phase_state(phase)
        if current_state.status == PhaseStatus.COMPLETED:
            # Already completed - just update artifacts
            return ChangeState(
                change_id=self.change_state.change_id,
                project=self.change_state.project,
                current_phase=self.change_state.current_phase,
                phases={
                    **self.change_state.phases,
                    phase: PhaseState(
                        phase=phase,
                        status=PhaseStatus.COMPLETED,
                        artifacts=artifacts,
                        started_at=current_state.started_at,
                        completed_at=datetime.now(),
                    ),
                },
                created_at=self.change_state.created_at,
                updated_at=datetime.now(),
                metadata=self.change_state.metadata,
            )

        updated_phases = dict(self.change_state.phases)
        updated_phases[phase] = PhaseState(
            phase=phase,
            status=PhaseStatus.COMPLETED,
            artifacts=artifacts,
            started_at=current_state.started_at,
            completed_at=datetime.now(),
        )

        return ChangeState(
            change_id=self.change_state.change_id,
            project=self.change_state.project,
            current_phase=self.change_state.current_phase,
            phases=updated_phases,
            created_at=self.change_state.created_at,
            updated_at=datetime.now(),
            metadata=self.change_state.metadata,
        )

    def get_missing_artifacts_for_next_phase(self) -> tuple[str, ...]:
        """Get artifacts missing for the next allowed phase."""
        next_phases = ALLOWED_TRANSITIONS.get(self.change_state.current_phase, ())
        if not next_phases:
            return ()

        next_phase = next_phases[0]
        required = REQUIRED_ARTIFACTS_FOR_TRANSITION.get(
            (self.change_state.current_phase, next_phase), ()
        )
        return self._check_artifacts_exist(required)

    def get_phase_summary(self) -> dict:
        """Get a summary of all phases for this change."""
        return {
            "change_id": self.change_state.change_id,
            "project": self.change_state.project,
            "current_phase": self.change_state.current_phase.value,
            "phases": {
                p.value: {
                    "status": s.status.value,
                    "artifacts": [a.kind for a in s.artifacts],
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for p, s in self.change_state.phases.items()
            },
            "next_allowed": [p.value for p in ALLOWED_TRANSITIONS.get(self.change_state.current_phase, ())],
            "missing_for_next": self.get_missing_artifacts_for_next_phase(),
        }


def create_initial_state(change_id: str, project: str) -> ChangeState:
    """Create initial change state for a new SDD change."""
    initial_phase = Phase.EXPLORE
    return ChangeState(
        change_id=change_id,
        project=project,
        current_phase=initial_phase,
        phases={
            initial_phase: PhaseState(
                phase=initial_phase,
                status=PhaseStatus.RUNNING,
                started_at=datetime.now(),
            ),
        },
    )