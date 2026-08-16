"""Compatibility adapter for applying graph-authoritative task transitions.

The persisted state format still stores the legacy TaskLedger. This adapter
reconstructs the Task State Graph from that ledger for a single mutation, then
projects the authoritative graph state back into the ledger so existing
persistence and CLI callers remain compatible.
"""
from __future__ import annotations

from typing import Callable, TypeVar

from .orchestrator_integration import KernelOrchestrator
from .task_graph_adapter import graph_to_ledger, ledger_to_graph
from .task_graph_orchestrator import TaskGraphKernelOrchestrator

T = TypeVar("T")


def _as_task_graph_orchestrator(
    orchestrator: KernelOrchestrator,
) -> TaskGraphKernelOrchestrator:
    """Wrap existing persisted state without changing its legacy shape."""
    graph_orchestrator = TaskGraphKernelOrchestrator.__new__(TaskGraphKernelOrchestrator)
    graph_orchestrator.__dict__.update(orchestrator.__dict__)
    graph_orchestrator.task_graph = ledger_to_graph(orchestrator.task_ledger)
    return graph_orchestrator


def mutate_with_task_graph(
    orchestrator: KernelOrchestrator,
    mutator: Callable[[TaskGraphKernelOrchestrator], T],
) -> T:
    """Run one task mutation through the graph and project it back to legacy state."""
    graph_orchestrator = _as_task_graph_orchestrator(orchestrator)
    result = mutator(graph_orchestrator)
    orchestrator.task_ledger = graph_to_ledger(
        graph_orchestrator.task_graph,
        orchestrator.task_ledger,
    )
    return result


__all__ = ["mutate_with_task_graph"]
