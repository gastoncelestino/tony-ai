"""
Tony Kernel — Shared Schemas

Machine-readable data structures for the Tony Kernel state machine,
phase gates, artifact gates, evidence ledger, and task ledger.

All types are frozen dataclasses for immutability and hashability.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Literal
from datetime import datetime
import hashlib
import json


class Phase(str, Enum):
    """SDD Phases in order."""
    EXPLORE = "explore"
    PROPOSE = "propose"
    SPEC = "spec"
    DESIGN = "design"
    TASKS = "tasks"
    APPLY = "apply"
    VERIFY = "verify"
    ARCHIVE = "archive"

    @classmethod
    def ordered(cls) -> list[Phase]:
        return [
            cls.EXPLORE,
            cls.PROPOSE,
            cls.SPEC,
            cls.DESIGN,
            cls.TASKS,
            cls.APPLY,
            cls.VERIFY,
            cls.ARCHIVE,
        ]

    @classmethod
    def index(cls, phase: Phase) -> int:
        return cls.ordered().index(phase)


class PhaseStatus(str, Enum):
    """Status of a phase."""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class GateResult(str, Enum):
    """Result of a gate check."""
    ALLOW = "allow"
    DENY = "deny"
    BLOCKED = "blocked"  # Missing artifacts, not a hard denial


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Reference to an artifact produced by a phase."""
    kind: str                    # e.g., "spec", "design", "tasks", "apply-progress"
    path: str                    # filesystem path or tonymem topic_key
    store: Literal["tonymem", "openspec", "hybrid", "inline"]
    hash: Optional[str] = None   # sha256 of content
    validated: bool = False      # passed schema/structure validation

    def compute_hash(self, content: str) -> ArtifactRef:
        """Return new ArtifactRef with computed hash."""
        h = hashlib.sha256(content.encode()).hexdigest()
        return ArtifactRef(
            kind=self.kind,
            path=self.path,
            store=self.store,
            hash=h,
            validated=self.validated,
        )


@dataclass(frozen=True, slots=True)
class PhaseState:
    """Current state of a single phase."""
    phase: Phase
    status: PhaseStatus = PhaseStatus.NOT_STARTED
    artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ChangeState:
    """Complete state of an SDD change."""
    change_id: str
    project: str
    current_phase: Phase = Phase.EXPLORE
    phases: dict[Phase, PhaseState] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def get_phase_state(self, phase: Phase) -> PhaseState:
        return self.phases.get(phase, PhaseState(phase=phase))

    def is_phase_completed(self, phase: Phase) -> bool:
        state = self.get_phase_state(phase)
        return state.status == PhaseStatus.COMPLETED

    def get_current_phase_state(self) -> PhaseState:
        return self.get_phase_state(self.current_phase)


@dataclass(frozen=True, slots=True)
class GateCheckResult:
    """Result of a phase gate check."""
    allowed: bool
    current_phase: Phase
    requested_phase: Phase
    reason: str
    missing_artifacts: tuple[str, ...] = field(default_factory=tuple)
    blocked_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def result(self) -> GateResult:
        if self.allowed:
            return GateResult.ALLOW
        if self.missing_artifacts:
            return GateResult.BLOCKED
        return GateResult.DENY


# Phase transition rules
PHASES = Phase.ordered()

ALLOWED_TRANSITIONS: dict[Phase, tuple[Phase, ...]] = {
    Phase.EXPLORE: (Phase.PROPOSE,),
    Phase.PROPOSE: (Phase.SPEC,),
    Phase.SPEC: (Phase.DESIGN,),
    Phase.DESIGN: (Phase.TASKS,),
    Phase.TASKS: (Phase.APPLY,),
    Phase.APPLY: (Phase.VERIFY,),
    Phase.VERIFY: (Phase.ARCHIVE,),
    Phase.ARCHIVE: (),
}

# Required artifacts for each phase transition
REQUIRED_ARTIFACTS_FOR_TRANSITION: dict[tuple[Phase, Phase], tuple[str, ...]] = {
    (Phase.EXPLORE, Phase.PROPOSE): ("explore",),
    (Phase.PROPOSE, Phase.SPEC): ("proposal",),
    (Phase.SPEC, Phase.DESIGN): ("spec",),
    (Phase.DESIGN, Phase.TASKS): ("spec", "design"),
    (Phase.TASKS, Phase.APPLY): ("tasks", "spec", "design"),
    (Phase.APPLY, Phase.VERIFY): ("apply-progress", "tasks", "spec"),
    (Phase.VERIFY, Phase.ARCHIVE): ("verify-report", "apply-progress", "tasks", "spec", "design", "proposal"),
}

# Minimal required artifacts to consider a phase "completed"
PHASE_COMPLETION_ARTIFACTS: dict[Phase, tuple[str, ...]] = {
    Phase.EXPLORE: ("explore",),
    Phase.PROPOSE: ("proposal",),
    Phase.SPEC: ("spec",),
    Phase.DESIGN: ("design",),
    Phase.TASKS: ("tasks",),
    Phase.APPLY: ("apply-progress",),
    Phase.VERIFY: ("verify-report",),
    Phase.ARCHIVE: ("archive-report",),
}


# ============================================================================
# Evidence & Task Ledger Schemas (Commit 2)
# ============================================================================

class EvidenceType(str, Enum):
    """Types of evidence that can support a claim."""
    TEST = "test"
    BUILD = "build"
    LINT = "lint"
    COMMAND = "command"
    GIT_DIFF = "git_diff"
    FILE_EXISTS = "file_exists"
    FILE_CONTENT = "file_content"
    MANUAL = "manual"


class EvidenceStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    PENDING = "pending"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class Evidence:
    type: EvidenceType
    claim: str
    command: Optional[str] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    stdout_hash: Optional[str] = None
    stdout_path: Optional[str] = None
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    status: EvidenceStatus = EvidenceStatus.PENDING

    def validate(self) -> EvidenceStatus:
        if self.type in (EvidenceType.TEST, EvidenceType.BUILD, EvidenceType.LINT, EvidenceType.COMMAND):
            if self.exit_code is None:
                return EvidenceStatus.INVALID
            return EvidenceStatus.VALID if self.exit_code == 0 else EvidenceStatus.INVALID
        elif self.type == EvidenceType.GIT_DIFF:
            return EvidenceStatus.VALID if self.stdout else EvidenceStatus.INVALID
        elif self.type in (EvidenceType.FILE_EXISTS, EvidenceType.FILE_CONTENT):
            return EvidenceStatus.VALID if self.file_path else EvidenceStatus.INVALID
        return EvidenceStatus.PENDING


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    command: str
    args: tuple[str, ...] = field(default_factory=tuple)
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timestamp: datetime = field(default_factory=datetime.now)
    working_dir: Optional[str] = None
    env: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_evidence(self, claim: str) -> Evidence:
        return Evidence(
            type=EvidenceType.COMMAND,
            claim=claim,
            command=self.command,
            exit_code=self.exit_code,
            stdout=self.stdout,
            stderr=self.stderr,
            stdout_hash=hashlib.sha256(self.stdout.encode()).hexdigest() if self.stdout else None,
        )


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    description: str
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    status: ClaimStatus = ClaimStatus.INSUFFICIENT
    required: bool = True
    metadata: dict = field(default_factory=dict)

    def evaluate(self) -> ClaimStatus:
        if not self.evidence:
            return ClaimStatus.INSUFFICIENT
        validated = [e for e in self.evidence if e.validate() == EvidenceStatus.VALID]
        if not validated:
            return ClaimStatus.INSUFFICIENT
        # Simple: if any valid evidence supports, consider supported
        # In reality, would need more sophisticated logic
        return ClaimStatus.SUPPORTED