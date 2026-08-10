"""
Tony Kernel — Orchestrator Integration

Connects the Kernel (state machine, phase gates, evidence, tasks, artifacts, retry)
with the tony-orchestrator agent and SDD workflow.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Callable, Any
from enum import Enum

from .schemas import (
    Phase,
    PhaseStatus,
    ChangeState,
    ArtifactRef,
    Task,
    TaskStatus,
    TaskLedger,
    Evidence,
    EvidenceType,
    EvidenceStatus,
    Claim,
    ClaimStatus,
)
from .state_machine import PhaseController, create_initial_state
from .phase_gate import PhaseGate, PhaseGateConfig
from .evidence_ledger import EvidenceLedger
from .task_ledger import TaskLedger
from .artifact_gate import ArtifactGate
from .retry_budget import RetryBudget
from .phase_checksum import PhaseChecksumRegistry, get_global_registry


class OrchestrationDecision(str, Enum):
    """Decisions the kernel can make about orchestration."""
    PROCEED = "proceed"           # Allow phase transition, delegate to sub-agent
    BLOCK_MISSING_ARTIFACTS = "block_missing_artifacts"  # Missing required artifacts
    BLOCK_PHASE_INCOMPLETE = "block_phase_incomplete"    # Current phase not completed
    BLOCK_INVALID_TRANSITION = "block_invalid_transition"  # Invalid phase transition
    BLOCK_EVIDENCE_REQUIRED = "block_evidence_required"  # Required claim lacks evidence
    BLOCK_RETRY_EXHAUSTED = "block_retry_exhausted"      # Retry budget exhausted
    BLOCK_SCOPE_VIOLATION = "block_scope_violation"      # Diff scope exceeds task files
    BLOCK_ARTIFACT_INVALID = "block_artifact_invalid"    # Artifact validation failed
    HUMAN_REQUIRED = "human_required"  # Retry budget exhausted, need human
    PHASE_COMPLETE = "phase_complete"  # Phase completed successfully


@dataclass
class OrchestrationResult:
    """Result of an orchestration check."""
    decision: OrchestrationDecision
    reason: str
    current_phase: str
    requested_phase: Optional[str] = None
    missing_artifacts: tuple = ()
    missing_evidence: tuple = ()
    blocked_reasons: tuple = ()
    scope_violations: tuple = ()
    retry_status: Optional[dict] = None
    next_action: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    artifact_validation: dict = field(default_factory=dict)


class KernelOrchestrator:
    """
    Main integration point between the Tony Orchestrator and the Kernel.
    
    The orchestrator uses this to:
    1. Check if a phase transition is allowed before delegating
    2. Track task progress and evidence
    3. Validate artifacts before transitions
    4. Manage retry budgets
    4. Enforce scope guards
    """
    
    def __init__(self, change_id: str, project: str):
        # Core state
        self.change_state = create_initial_state(change_id, project)
        
        # Kernel components
        self.controller = PhaseController(self.change_state)
        self.gate = PhaseGate(self.controller)
        self.evidence_ledger = EvidenceLedger()
        self.task_ledger = TaskLedger()
        self.artifact_gate = ArtifactGate()
        self.retry_budget = RetryBudget()
        self.checksum_registry = get_global_registry()
        
        # Tracking
        self.delegation_log: List[dict] = []
        self.phase_checksums: Dict[str, str] = {}
        
    def can_start_phase(self, requested_phase: str) -> OrchestrationResult:
        """
        Check if we can start the requested phase.
        This is the main entry point before delegating to a sub-agent.
        """
        try:
            requested = Phase(requested_phase)
        except ValueError:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_INVALID_TRANSITION,
                reason=f"Unknown phase: {requested_phase}",
                current_phase=self.change_state.current_phase.value,
                requested_phase=requested_phase,
            )
        
        # Check phase gate
        gate_result = self.gate.check_transition(Phase(requested_phase))
        if not gate_result.allowed:
            if gate_result.missing_artifacts:
                return OrchestrationResult(
                    decision=OrchestrationDecision.BLOCK_MISSING_ARTIFACTS,
                    reason=gate_result.reason,
                    current_phase=self.change_state.current_phase.value,
                    requested_phase=requested_phase,
                    missing_artifacts=gate_result.missing_artifacts,
                )
            if gate_result.blocked_reasons:
                return OrchestrationResult(
                    decision=OrchestrationDecision.BLOCK_PHASE_INCOMPLETE,
                    reason=gate_result.reason,
                    current_phase=self.change_state.current_phase.value,
                    requested_phase=requested_phase,
                    blocked_reasons=gate_result.blocked_reasons,
                )
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_INVALID_TRANSITION,
                reason=gate_result.reason,
                current_phase=self.change_state.current_phase.value,
                requested_phase=requested_phase,
            )
        
        # Check retry budget for this phase
        retry_status = self.retry_budget.get_status(requested_phase)
        if retry_status["exhausted"]:
            return OrchestrationResult(
                decision=OrchestrationDecision.HUMAN_REQUIRED,
                reason=f"Retry budget exhausted for phase {requested_phase}",
                current_phase=self.change_state.current_phase.value,
                requested_phase=requested_phase,
                retry_status=retry_status,
                next_action="human_required",
            )
        
        return OrchestrationResult(
            decision=OrchestrationDecision.PROCEED,
            reason=f"Phase transition allowed: {self.change_state.current_phase.value} → {requested_phase}",
            current_phase=self.change_state.current_phase.value,
            requested_phase=requested_phase,
            retry_status=retry_status,
            next_action=self.retry_budget.get_next_action(requested_phase),
        )
    
    def record_delegation(self, phase: str, sub_agent: str, task_id: Optional[str] = None) -> None:
        """Record that we delegated a phase to a sub-agent."""
        self.delegation_log.append({
            "phase": phase,
            "sub_agent": sub_agent,
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
        })
    
    def record_phase_completion(self, phase: str, artifacts: list, evidence: list = None) -> OrchestrationResult:
        """
        Record that a phase has completed with its artifacts.
        Validates artifacts and updates state.
        """
        try:
            phase_enum = Phase(phase)
        except ValueError:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_INVALID_TRANSITION,
                reason=f"Unknown phase: {phase}",
                current_phase=self.change_state.current_phase.value,
            )
        
        # Validate artifacts
        artifact_refs = []
        for art in artifacts:
            if isinstance(art, dict):
                artifact_ref = ArtifactRef(
                    kind=art.get("kind", ""),
                    path=art.get("path", ""),
                    store=art.get("store", "tonymem"),
                    hash=art.get("hash"),
                    validated=art.get("validated", False),
                )
            else:
                artifact_ref = art
            artifact_refs.append(artifact_ref)
        
        # Validate artifacts via artifact gate
        validation_results = {}
        for art_ref in artifact_refs:
            result = self.artifact_gate.validate(art_ref.kind, art_ref)
            if not result.get("passed", False):
                return OrchestrationResult(
                    decision=OrchestrationDecision.BLOCK_ARTIFACT_INVALID,
                    reason=f"Artifact {art_ref.kind} validation failed: {result.get('message', 'unknown')}",
                    current_phase=self.change_state.current_phase.value,
                    artifact_validation=result,
                )
            validation_results[art_ref.kind] = result
        
        # Update phase state
        self.change_state = self.controller.complete_phase(
            Phase(phase), 
            tuple(artifact_refs)
        )
        
        # Recreate controller and gate with updated state
        self.controller = PhaseController(self.change_state)
        self.gate = PhaseGate(self.controller)
        
        # Record phase checksum
        self._record_phase_checksum(phase, artifact_refs)
        
        return OrchestrationResult(
            decision=OrchestrationDecision.PHASE_COMPLETE,
            reason=f"Phase {phase} completed successfully",
            current_phase=self.change_state.current_phase.value,
            metadata={"artifacts": [a.kind for a in artifact_refs]},
        )
    
    def _record_phase_checksum(self, phase: str, artifacts: list) -> None:
        """Record checksum of phase artifacts for drift detection."""
        artifact_refs = []
        for art in artifacts:
            if isinstance(art, dict):
                artifact_refs.append(ArtifactRef(
                    kind=art.get("kind", ""),
                    path=art.get("path", ""),
                    store=art.get("store", "tonymem"),
                    hash=art.get("hash"),
                    validated=art.get("validated", False),
                ))
            else:
                artifact_refs.append(art)
        self.checksum_registry.record_phase(phase, artifact_refs, recorded_by="kernel")
    
    def verify_phase_checksum(self, phase: str, artifacts: list = None) -> dict:
        """Verify phase artifacts haven't been modified since completion."""
        if artifacts is None:
            artifacts = []
        artifact_refs = []
        for art in artifacts:
            if isinstance(art, dict):
                artifact_refs.append(ArtifactRef(
                    kind=art.get("kind", ""),
                    path=art.get("path", ""),
                    store=art.get("store", "tonymem"),
                    hash=art.get("hash"),
                    validated=art.get("validated", False),
                ))
            else:
                artifact_refs.append(art)
        result = self.checksum_registry.verify_phase(phase, artifact_refs)
        return result
    
    def add_task(self, task_id: str, description: str, phase: str, 
                 dependencies: tuple = (), files: tuple = ()) -> None:
        """Add a task to the task ledger."""
        from .schemas import Task, TaskStatus, Phase
        task = Task(
            id=task_id,
            description=description,
            phase=Phase(phase),
            status=TaskStatus.PENDING,
            dependencies=dependencies,
            files=files,
        )
        self.task_ledger = self.task_ledger.add_task(Task(
            id=task_id,
            description=description,
            phase=Phase(phase),
            status=TaskStatus.PENDING,
            dependencies=dependencies,
            files=files,
        ))
    
    def start_task(self, task_id: str) -> bool:
        """Mark a task as in progress."""
        if task_id not in self.task_ledger.tasks:
            return False
        task = self.task_ledger.tasks[task_id]
        if task.status != TaskStatus.PENDING:
            return False
        if not task.can_start(self.task_ledger.tasks):
            return False
        self.task_ledger = self.task_ledger.start_task(task_id)
        return True
    
    def complete_task(self, task_id: str, evidence: list = None) -> OrchestrationResult:
        """Complete a task with evidence. Evidence must be valid."""
        if task_id not in self.task_ledger.tasks:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} not found",
                current_phase=self.change_state.current_phase.value,
            )
        
        task = self.task_ledger.tasks[task_id]
        if task.status != TaskStatus.IN_PROGRESS:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} not in progress",
                current_phase=self.change_state.current_phase.value,
            )
        
        evidence_objs = evidence or []
        validated_evidence = []
        invalid_evidence = []
        for ev in evidence_objs:
            if isinstance(ev, Evidence):
                status = ev.validate()
                if status == EvidenceStatus.VALID:
                    validated_evidence.append(ev)
                else:
                    invalid_evidence.append((ev, status))
            elif isinstance(ev, dict):
                try:
                    ev_obj = Evidence(
                        type=EvidenceType(ev.get("type", "manual")),
                        claim=ev.get("claim", ""),
                        command=ev.get("command"),
                        exit_code=ev.get("exit_code"),
                        stdout=ev.get("stdout"),
                        stderr=ev.get("stderr"),
                        file_path=ev.get("file_path"),
                    )
                    status = ev_obj.validate()
                    if status == EvidenceStatus.VALID:
                        validated_evidence.append(ev_obj)
                    else:
                        invalid_evidence.append((ev_obj, status))
                except Exception:
                    invalid_evidence.append((ev, "invalid_format"))
            else:
                invalid_evidence.append((ev, "unknown_type"))
        
        if invalid_evidence:
            reasons = [f"{type(ev).__name__}: {status}" for ev, status in invalid_evidence[:3]]
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Invalid evidence for task {task_id}: {', '.join(reasons)}",
                current_phase=self.change_state.current_phase.value,
                missing_evidence=tuple(str(e) for e, _ in invalid_evidence[:5]),
            )
        
        if not validated_evidence:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"No valid evidence provided for task {task_id}",
                current_phase=self.change_state.current_phase.value,
            )
        
        self.task_ledger = self.task_ledger.complete_task(task_id, tuple(validated_evidence))
        
        return OrchestrationResult(
            decision=OrchestrationDecision.PROCEED,
            reason=f"Task {task_id} completed with {len(validated_evidence)} evidence items",
            current_phase=self.change_state.current_phase.value,
            metadata={"task_id": task_id, "evidence_count": len(validated_evidence)},
        )
    
    def get_next_task(self) -> Optional[dict]:
        """Get the next task that can be started."""
        task = self.task_ledger.get_next_ready()
        if not task:
            return None
        return {
            "id": task.id,
            "description": task.description,
            "phase": task.phase.value,
            "dependencies": task.dependencies,
            "files": task.files,
        }
    
    def get_phase_status(self) -> dict:
        """Get current phase status for the orchestrator."""
        return self.gate.get_status_summary()
    
    def get_task_summary(self) -> dict:
        """Get task ledger summary."""
        return self.task_ledger.get_stats()
    
    def get_retry_status(self, phase: str) -> dict:
        """Get retry budget status for a phase."""
        return self.retry_budget.get_status(phase)
    
    def check_scope(self, git_diff: str, allowed_files: tuple) -> OrchestrationResult:
        """
        Check if git diff stays within allowed files (Scope Guard).
        """
        if not git_diff:
            return OrchestrationResult(
                decision=OrchestrationDecision.PROCEED,
                reason="No diff to check",
                current_phase=self.change_state.current_phase.value,
            )
        
        # Parse diff to get modified files
        modified_files = self._parse_diff_files(git_diff)
        
        # Check against allowed files
        violations = []
        for file in modified_files:
            allowed = False
            for allowed_pattern in allowed_files:
                if self._match_pattern(file, allowed_pattern):
                    allowed = True
                    break
            if not allowed:
                violations.append(file)
        
        if violations:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_SCOPE_VIOLATION,
                reason=f"Modified files outside allowed scope: {', '.join(violations)}",
                current_phase=self.change_state.current_phase.value,
                scope_violations=tuple(violations),
            )
        
        return OrchestrationResult(
            decision=OrchestrationDecision.PROCEED,
            reason="Scope check passed",
            current_phase=self.change_state.current_phase.value,
        )
    
    def _parse_diff_files(self, git_diff: str) -> list:
        """Parse git diff to extract modified file paths."""
        import re
        files = []
        for line in git_diff.split('\n'):
            if line.startswith('+++') or line.startswith('---'):
                # Extract file path from diff header
                parts = line.split('\t')
                if len(parts) > 1:
                    file_path = parts[1].lstrip('b/').lstrip('a/')
                    if file_path != '/dev/null':
                        files.append(file_path)
        return list(set(files))
    
    def _match_pattern(self, file_path: str, pattern: str) -> bool:
        """Match file path against glob pattern."""
        import fnmatch
        return fnmatch.fnmatch(file_path, pattern)
    
    def get_status(self) -> dict:
        """Get complete status for debugging/logging."""
        return {
            "change_id": self.change_state.change_id,
            "project": self.change_state.project,
            "current_phase": self.change_state.current_phase.value,
            "phase_summary": self.get_phase_status(),
            "task_summary": self.get_task_summary(),
            "retry_budgets": {k: v for k, v in self.retry_budget.attempts.items()},
            "phase_checksums": self.phase_checksums,
            "delegation_count": len(self.delegation_log),
        }


def create_kernel_orchestrator(change_id: str, project: str) -> KernelOrchestrator:
    """Factory function to create a KernelOrchestrator."""
    return KernelOrchestrator(change_id, project)