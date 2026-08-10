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
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    args: tuple[str, ...] = field(default_factory=tuple)
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
# ============================================================================
# Task Ledger Schemas
# ============================================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    description: str
    phase: Phase
    status: TaskStatus = TaskStatus.PENDING
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    files: tuple[str, ...] = field(default_factory=tuple)
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_agent: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def is_ready(self, all_tasks: dict[str, "Task"]) -> bool:
        for dep_id in self.dependencies:
            dep = all_tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def can_start(self, all_tasks: dict[str, "Task"]) -> bool:
        return self.status == TaskStatus.PENDING and self.is_ready(all_tasks)


@dataclass(frozen=True, slots=True)
class TaskLedger:
    tasks: dict[str, Task] = field(default_factory=dict)

    def add_task(self, task: Task) -> "TaskLedger":
        return TaskLedger(tasks={**self.tasks, task.id: task})

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def get_pending(self) -> tuple[Task, ...]:
        return tuple(t for t in self.tasks.values() if t.status == TaskStatus.PENDING)

    def get_in_progress(self) -> tuple[Task, ...]:
        return tuple(t for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS)

    def get_completed(self) -> tuple[Task, ...]:
        return tuple(t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)

    def get_failed(self) -> tuple[Task, ...]:
        return tuple(t for t in self.tasks.values() if t.status == TaskStatus.FAILED)

    def get_blocked(self) -> tuple[Task, ...]:
        return tuple(t for t in self.tasks.values() if t.status == TaskStatus.BLOCKED)

    def get_next_ready(self) -> Optional[Task]:
        pending = self.get_pending()
        for task in pending:
            if task.can_start(self.tasks):
                return task
        return None

    def start_task(self, task_id: str) -> "TaskLedger":
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.PENDING:
            return self
        updated = Task(
            id=task.id,
            description=task.description,
            phase=task.phase,
            status=TaskStatus.IN_PROGRESS,
            dependencies=task.dependencies,
            files=task.files,
            evidence=task.evidence,
            started_at=datetime.now(),
            completed_at=task.completed_at,
            assigned_agent=task.assigned_agent,
            metadata=task.metadata,
        )
        return TaskLedger(tasks={**self.tasks, task_id: updated})

    def complete_task(self, task_id: str, evidence: tuple[Evidence, ...] = ()) -> "TaskLedger":
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.IN_PROGRESS:
            return self
        updated = Task(
            id=task.id,
            description=task.description,
            phase=task.phase,
            status=TaskStatus.COMPLETED,
            dependencies=task.dependencies,
            files=task.files,
            evidence=evidence,
            started_at=task.started_at,
            completed_at=datetime.now(),
            assigned_agent=task.assigned_agent,
            metadata=task.metadata,
        )
        return TaskLedger(tasks={**self.tasks, task_id: updated})

    def fail_task(self, task_id: str, error: str) -> "TaskLedger":
        task = self.tasks.get(task_id)
        if not task or task.status not in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
            return self
        updated = Task(
            id=task.id,
            description=task.description,
            phase=task.phase,
            status=TaskStatus.FAILED,
            dependencies=task.dependencies,
            files=task.files,
            evidence=task.evidence,
            started_at=task.started_at,
            completed_at=datetime.now(),
            assigned_agent=task.assigned_agent,
            metadata={**task.metadata, "error": error},
        )
        return TaskLedger(tasks={**self.tasks, task_id: updated})

    def get_stats(self) -> dict:
        total = len(self.tasks)
        completed = len(self.get_completed())
        pending = len(self.get_pending())
        in_progress = len(self.get_in_progress())
        failed = len(self.get_failed())
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "in_progress": in_progress,
            "failed": failed,
            "completion_rate": completed / total if total > 0 else 0.0,
        }

    def all_completed(self) -> bool:
        return all(t.status == TaskStatus.COMPLETED for t in self.tasks.values())


# ============================================================================
# Artifact Gate Schemas
# ============================================================================

class ArtifactGateResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ArtifactValidationResult:
    artifact_kind: str
    result: str
    message: str
    details: dict = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class ArtifactGateResult:
    artifact_kind: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)
    required: bool = True


# ============================================================================
# Retry Budget Schemas
# ============================================================================

class RetryAction(str, Enum):
    IMPLEMENT = "implement"
    TARGETED_FIX = "targeted_fix"
    HUMAN_REQUIRED = "human_required"


@dataclass
class AttemptRecord:
    """Record of a single attempt."""
    attempt_number: int
    action: str
    phase: str
    task_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None
    evidence: dict = field(default_factory=dict)


@dataclass
class RetryBudget:
    """
    Tracks retry attempts per task/phase.
    Max 3 attempts: implement → targeted fix → targeted fix → human required.
    """
    max_attempts: int = 3
    attempts: Dict[str, List[dict]] = field(default_factory=dict)
    
    def get_key(self, phase: str, task_id: Optional[str] = None) -> str:
        return f"{phase}:{task_id or 'phase'}"
    
    def get_attempts(self, phase: str, task_id: Optional[str] = None) -> list:
        key = self.get_key(phase, task_id)
        return self.attempts.get(key, [])
    
    def record_attempt(self, phase: str, task_id: Optional[str], success: bool, 
                       error: Optional[str] = None, evidence: dict = None) -> dict:
        key = f"{phase}:{task_id or 'phase'}"
        attempts = self.attempts.get(key, [])
        attempt_num = len(attempts) + 1
        
        record = {
            "attempt_number": len(self.attempts.get(key, [])) + 1,
            "phase": phase,
            "task_id": task_id,
            "success": success,
            "error": None,
            "evidence": evidence or {},
            "timestamp": __import__('datetime').datetime.now().isoformat(),
        }
        
        if key not in self.attempts:
            self.attempts[key] = []
        self.attempts[key].append(record)
        
        return {
            "attempt": len(self.attempts[key]),
            "action": "human_required" if len(self.attempts[key]) >= 3 else ("targeted_fix" if len(self.attempts[key]) > 1 else "implement"),
            "max_reached": len(self.attempts[key]) >= 3,
            "next_action": "human_required" if len(self.attempts[key]) >= 3 else ("targeted_fix" if len(self.attempts[key]) > 0 else "implement"),
        }
    
    def get_status(self, phase: str, task_id: Optional[str] = None) -> dict:
        key = f"{phase}:{task_id or 'phase'}"
        attempts = self.attempts.get(key, [])
        attempt_num = len(attempts)
        
        return {
            "attempts_used": len(self.attempts.get(key, [])),
            "max_attempts": 3,
            "remaining": max(0, 3 - len(self.attempts.get(key, []))),
            "exhausted": len(self.attempts.get(key, [])) >= 3,
            "next_action": "human_required" if len(self.attempts.get(key, [])) >= 3 else ("targeted_fix" if len(self.attempts[key]) > 0 else "implement"),
            "last_attempt": self.attempts.get(key, [])[-1] if self.attempts.get(key) else None,
        }
    
    def is_exhausted(self, phase: str, task_id: Optional[str] = None) -> bool:
        key = f"{phase}:{task_id or 'phase'}"
        return len(self.attempts.get(key, [])) >= 3
    
    def get_next_action(self, phase: str, task_id: Optional[str] = None) -> str:
        key = f"{phase}:{task_id or 'phase'}"
        attempts = len(self.attempts.get(key, []))
        
        if attempts >= 3:
            return "human_required"
        elif attempts == 0:
            return "implement"
        else:
            return "targeted_fix"
    
    def reset(self, phase: str, task_id: Optional[str] = None) -> None:
        key = f"{phase}:{task_id or 'phase'}"
        if key in self.attempts:
            del self.attempts[key]
