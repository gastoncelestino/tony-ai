"""Task-graph aware orchestration facade.

This is the incremental integration layer between the legacy TaskLedger and
TaskStateGraph. The graph is consulted first for task-level transitions; the
ledger remains synchronized for backwards compatibility.
"""
from __future__ import annotations

from .orchestrator_integration import (
    KernelOrchestrator,
    OrchestrationDecision,
    OrchestrationResult,
)
from .task_graph import TaskGraphError, TaskStateGraph
from .task_graph_adapter import ledger_to_graph


class TaskGraphKernelOrchestrator(KernelOrchestrator):
    """Kernel orchestrator with deterministic task-graph transitions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_graph = TaskStateGraph()

    def _sync_task_graph(self) -> None:
        """Refresh the graph from legacy storage after compatible mutations."""
        self.task_graph = ledger_to_graph(self.task_ledger)

    def add_task(self, task_id: str, description: str, phase: str,
                 dependencies: tuple = (), files: tuple = ()) -> None:
        super().add_task(task_id, description, phase, dependencies, files)
        self._sync_task_graph()

    def start_task(self, task_id: str) -> bool:
        """Use the graph as the authoritative readiness/transition check."""
        try:
            self.task_graph.start(task_id)
        except TaskGraphError:
            return False

        # Keep the legacy ledger synchronized for existing consumers.
        if not super().start_task(task_id):
            return False
        self._sync_task_graph()
        return True

    def complete_task(self, task_id: str, evidence: list = None) -> OrchestrationResult:
        """Require an in-progress graph node, then synchronize completion."""
        node = self.task_graph.get(task_id)
        if node is None or node.status.value != "in_progress":
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} is not in progress in the task graph",
                current_phase=self.change_state.current_phase.value,
            )

        result = super().complete_task(task_id, evidence)
        if result.decision != OrchestrationDecision.PROCEED:
            return result

        self._sync_task_graph()
        node = self.task_graph.get(task_id)
        if node is None or not node.evidence_refs:
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} completed without graph evidence references",
                current_phase=self.change_state.current_phase.value,
            )
        return result

    def get_task_graph(self) -> TaskStateGraph:
        """Return the current validated task graph."""
        self._sync_task_graph()
        return self.task_graph


__all__ = ["TaskGraphKernelOrchestrator"]
