"""Small, read-only validation helpers for evidence lineage.

Judgment Memory may persist evidence references, but the Task State Graph remains
 the authority for which references belong to a task.
"""
from __future__ import annotations

from .task_graph import TaskStateGraph


class EvidenceLineageError(ValueError):
    """Raised when a judgment references evidence absent from the task graph."""


def validate_evidence_refs(
    graph: TaskStateGraph,
    task_id: str,
    evidence_refs: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    """Validate that all supplied references belong to the graph task.

    This is intentionally read-only: it does not mutate the graph or memory.
    """
    node = graph.get(task_id)
    if node is None:
        raise EvidenceLineageError(f"Unknown task: {task_id}")

    refs = tuple(dict.fromkeys(evidence_refs))
    missing = tuple(ref for ref in refs if ref not in node.evidence_refs)
    if missing:
        raise EvidenceLineageError(
            f"Evidence refs are not attached to task {task_id}: {missing}"
        )
    return refs
