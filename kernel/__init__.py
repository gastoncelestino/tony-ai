"""
Tony Kernel — Public API

Main entry point for the Tony Kernel.
"""
from __future__ import annotations

from .schemas import (
    Phase,
    PhaseStatus,
    PhaseState,
    ChangeState,
    ArtifactRef,
    GateCheckResult,
    GateResult,
    GateResult,
    PHASES,
    ALLOWED_TRANSITIONS,
    REQUIRED_ARTIFACTS_FOR_TRANSITION,
    PHASE_COMPLETION_ARTIFACTS,
)
from .state_machine import (
    PhaseController,
    create_initial_state,
    InvalidTransitionError,
    MissingArtifactsError,
    StateMachineError,
    PhaseNotFoundError,
)
from .phase_gate import (
    PhaseGate,
    PhaseGateConfig,
    GateCheckResult,
)

__all__ = [
    # Schemas
    "Phase",
    "PhaseStatus",
    "PhaseState",
    "ChangeState",
    "ArtifactRef",
    "GateCheckResult",
    "GateResult",
    "PHASES",
    "ALLOWED_TRANSITIONS",
    "REQUIRED_ARTIFACTS_FOR_TRANSITION",
    "PHASE_COMPLETION_ARTIFACTS",
    # State Machine
    "PhaseController",
    "create_initial_state",
    "InvalidTransitionError",
    "MissingArtifactsError",
    "StateMachineError",
    "PhaseNotFoundError",
    # Phase Gate
    "PhaseGate",
    "PhaseGateConfig",
    "GateCheckResult",
]