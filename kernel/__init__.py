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
    PHASES,
    ALLOWED_TRANSITIONS,
    REQUIRED_ARTIFACTS_FOR_TRANSITION,
    PHASE_COMPLETION_ARTIFACTS,
    # Evidence & Task Ledger
    Evidence,
    EvidenceType,
    EvidenceStatus,
    ExecutionRecord,
    Claim,
    ClaimStatus,
    Task,
    TaskStatus,
    TaskLedger,
    # Artifact Gate
    ArtifactGateResult,
    ArtifactValidationResult,
    ArtifactGateResult as ArtifactGateResultEnum,
    # Retry Budget
    RetryBudget,
    AttemptRecord,
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
from .evidence_ledger import (
    EvidenceLedger,
)
from .task_ledger import (
    TaskLedger,
)
from .artifact_gate import (
    ArtifactGate,
)
from .retry_budget import (
    RetryBudget,
    AttemptRecord,
)
from .orchestrator_integration import (
    KernelOrchestrator,
    OrchestrationDecision,
    OrchestrationResult,
    create_kernel_orchestrator,
)
from .scope_guard import (
    ScopeGuard,
    ScopeCheckResult,
    ScopeViolation,
    ScopeViolationType,
    create_sdd_scope_guard,
)
from .phase_checksum import (
    PhaseChecksumRegistry,
    PhaseChecksum,
    PhaseChecksumResult,
    get_global_registry,
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
    # Evidence & Task Ledger
    "Evidence",
    "EvidenceType",
    "EvidenceStatus",
    "ExecutionRecord",
    "Claim",
    "ClaimStatus",
    "Task",
    "TaskStatus",
    "TaskLedger",
    # Artifact Gate
    "ArtifactGateResult",
    "ArtifactValidationResult",
    "ArtifactGateResultEnum",
    # Retry Budget
    "RetryBudget",
    "AttemptRecord",
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
    # Evidence & Task Ledger
    "EvidenceLedger",
    "TaskLedger",
    # Artifact Gate
    "ArtifactGate",
    # Retry Budget
    "RetryBudget",
    "AttemptRecord",
    # Orchestrator Integration
    "KernelOrchestrator",
    "OrchestrationDecision",
    "OrchestrationResult",
    "create_kernel_orchestrator",
    # Scope Guard
    "ScopeGuard",
    "ScopeCheckResult",
    "ScopeViolation",
    "ScopeViolationType",
    "create_sdd_scope_guard",
    # Phase Checksum
    "PhaseChecksumRegistry",
    "PhaseChecksum",
    "PhaseChecksumResult",
    "get_global_registry",
]