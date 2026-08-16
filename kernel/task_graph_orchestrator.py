"""Task-graph aware orchestration facade.

The Task State Graph is authoritative for task transitions. The legacy
TaskLedger is maintained as a compatibility projection for existing callers.
"""
from __future__ import annotations

from dataclasses import replace

from .orchestrator_integration import (
    KernelOrchestrator,
    OrchestrationDecision,
    OrchestrationResult,
)
from .schemas import TaskStatus
from .task_graph import TaskGraphError, TaskStateGraph
from .task_graph_adapter import _evidence_ref, graph_to_ledger, ledger_to_graph


class TaskGraphKernelOrchestrator(KernelOrchestrator):
    """Kernel orchestrator whose task-state authority is the DAG."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_graph = TaskStateGraph()

    def _project_ledger(self) -> None:
        """Keep the legacy ledger synchronized from authoritative graph state."""
        self.task_ledger = graph_to_ledger(self.task_graph, self.task_ledger)

    def add_task(self, task_id: str, description: str, phase: str,
                 dependencies: tuple = (), files: tuple = ()) -> None:
        super().add_task(task_id, description, phase, dependencies, files)
        self.task_graph = ledger_to_graph(self.task_ledger)

    def start_task(self, task_id: str) -> bool:
        """Start a task only if the authoritative graph permits the transition."""
        try:
            self.task_graph = self.task_graph.start(task_id)
            self._project_ledger()
            return True
        except TaskGraphError:
            return False

    def complete_task(self, task_id: str, evidence: list = None) -> OrchestrationResult:
        """Validate evidence, then complete the authoritative graph node."""
        node = self.task_graph.get(task_id)
        if node is None:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} not found",
                current_phase=self.change_state.current_phase.value,
            )
        if node.status != TaskStatus.IN_PROGRESS:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} is not in progress",
                current_phase=self.change_state.current_phase.value,
            )

        validated_evidence, invalid_evidence = self._validate_evidence_items(evidence or [])
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

        refs = tuple(_evidence_ref(e) for e in validated_evidence)
        self.task_graph = self.task_graph.complete(task_id, refs)

        # Preserve concrete Evidence objects in the compatibility projection.
        existing = self.task_ledger.tasks[task_id]
        self.task_ledger = self.task_ledger.__class__(
            tasks={**self.task_ledger.tasks,
                   task_id: replace(existing, evidence=tuple(validated_evidence))}
        )
        self._project_ledger()

        return OrchestrationResult(
            decision=OrchestrationDecision.PROCEED,
            reason=f"Task {task_id} completed with {len(validated_evidence)} evidence items",
            current_phase=self.change_state.current_phase.value,
            metadata={"task_id": task_id, "evidence_count": len(validated_evidence)},
        )

    def fail_task(self, task_id: str, error: str, rollback: dict = None) -> bool:
        """Record a failed attempt in the graph and project it to the ledger."""
        try:
            self.task_graph = self.task_graph.fail(task_id, error, rollback=rollback)
            self._project_ledger()
            return True
        except TaskGraphError:
            return False

    def retry_task(self, task_id: str) -> bool:
        """Move a failed graph node back to pending without losing attempts."""
        try:
            self.task_graph = self.task_graph.retry(task_id)
            self._project_ledger()
            return True
        except TaskGraphError:
            return False

    def rollback_task(self, task_id: str, rollback: dict = None) -> bool:
        """Move a failed graph node to BLOCKED and preserve rollback metadata."""
        try:
            self.task_graph = self.task_graph.rollback_task(task_id, rollback=rollback)
            self._project_ledger()
            return True
        except TaskGraphError:
            return False

    def get_next_task(self) -> dict | None:
        """Return the next graph-ready node."""
        ready = self.task_graph.ready()
        if not ready:
            return None
        node = ready[0]
        return {
            "id": node.task_id,
            "description": node.description,
            "phase": node.phase.value,
            "dependencies": node.dependencies,
            "files": self.task_ledger.tasks[node.task_id].files,
        }

    def get_task_graph(self) -> TaskStateGraph:
        """Return the authoritative task graph without rebuilding it."""
        return self.task_graph

    def get_task_summary(self) -> dict:
        """Summarize authoritative graph state."""
        counts = {status.value: 0 for status in TaskStatus}
        for node in self.task_graph.nodes.values():
            counts[node.status.value] += 1
        total = len(self.task_graph.nodes)
        completed = counts[TaskStatus.COMPLETED.value]
        return {
            "total": total,
            "completed": completed,
            "pending": counts[TaskStatus.PENDING.value],
            "in_progress": counts[TaskStatus.IN_PROGRESS.value],
            "failed": counts[TaskStatus.FAILED.value],
            "blocked": counts[TaskStatus.BLOCKED.value],
            "completion_rate": completed / total if total else 0.0,
        }


__all__ = ["TaskGraphKernelOrchestrator"]
