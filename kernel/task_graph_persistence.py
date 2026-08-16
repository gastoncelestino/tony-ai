"""Compatibility adapter for applying task mutations through the Task Graph."""
from __future__ import annotations

from typing import Callable, TypeVar

from .orchestrator_integration import KernelOrchestrator
from .task_graph_adapter import ledger_to_graph
from .task_graph_orchestrator import TaskGraphKernelOrchestrator

T = TypeVar("T")


def mutate_with_task_graph(
    orchestrator: KernelOrchestrator,
    mutator: Callable[[TaskGraphKernelOrchestrator], T],
) -> T:
    """Apply one task mutation through the graph while preserving legacy state.

    The persisted state format is still the legacy orchestrator projection.
    This adapter reconstructs the authoritative graph from that projection,
    executes the mutation through the graph-aware orchestrator, then projects
    the result back before the caller persists the state.
    """
    graph_orchestrator = TaskGraphKernelOrchestrator(
        orchestrator.change_state.change_id,
        orchestrator.change_state.project,
        artifact_store=orchestrator.artifact_store,
        artifact_hasher=orchestrator.artifact_hasher,
    )
    graph_orchestrator.change_state = orchestrator.change_state
    graph_orchestrator.controller = orchestrator.controller
    graph_orchestrator.gate = orchestrator.gate
    graph_orchestrator.evidence_ledger = orchestrator.evidence_ledger
    graph_orchestrator.task_ledger = orchestrator.task_ledger
    graph_orchestrator.retry_budget = orchestrator.retry_budget
    graph_orchestrator.checksum_registry = orchestrator.checksum_registry
    graph_orchestrator.delegation_log = orchestrator.delegation_log
    graph_orchestrator.task_graph = ledger_to_graph(orchestrator.task_ledger)

    result = mutator(graph_orchestrator)

    orchestrator.change_state = graph_orchestrator.change_state
    orchestrator.controller = graph_orchestrator.controller
    orchestrator.gate = graph_orchestrator.gate
    orchestrator.evidence_ledger = graph_orchestrator.evidence_ledger
    orchestrator.task_ledger = graph_orchestrator.task_ledger
    orchestrator.retry_budget = graph_orchestrator.retry_budget
    orchestrator.checksum_registry = graph_orchestrator.checksum_registry
    orchestrator.delegation_log = graph_orchestrator.delegation_log
    return result


__all__ = ["mutate_with_task_graph"]
