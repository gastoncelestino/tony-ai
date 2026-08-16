"""Task-graph aware orchestration facade.

This is the incremental integration layer between the legacy TaskLedger and
TaskStateGraph.  The graph is consulted first for task-level transitions;
the ledger remains synchronized for backwards compatibility.
"""
from __future__ import annotations

from typing import Optional

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
        """Validate the legacy evidence, then require a graph transition."""
        result = super().complete_task(task_id, evidence)
        if result.decision != OrchestrationDecision.PROCEED:
            return result

        task = self.task_ledger.tasks[task_id]
        refs = tuple(self.task_graph.nodes[task_id].evidence_refs)
        if not refs:
            # The legacy completion succeeded, but the graph must never accept
            # a completion without stable evidence references.
            return OrchestrationResult(
                decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} has no graph evidence references",
                current_phase=self.change_state.current_phase.value,
            )

        # The ledger has already completed the task; rebuild the graph so its
        # node reflects the durable legacy state and evidence refs.
        self._sync_task_graph()
        return result

    def get_task_graph(self) -> TaskStateGraph:
        """Return the current validated task graph."""
        self._sync_task_graph()
        return self.task_graph


__all__ = ["TaskGraphKernelOrchestrator"]
