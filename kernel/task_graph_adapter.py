"""Compatibility bridge from the legacy TaskLedger to TaskStateGraph.

The ledger remains the public storage model for existing callers.  This adapter
lets the Kernel consume the same tasks as explicit DAG nodes without forcing a
big-bang migration.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from .schemas import Evidence, Task, TaskLedger, TaskStatus
from .task_graph import TaskAttempt, TaskNode, TaskStateGraph


def _evidence_ref(evidence: Evidence) -> str:
    """Return a stable reference for legacy evidence without inventing a DB id."""
    payload = "|".join(
        (
            evidence.type.value,
            evidence.claim,
            evidence.command or "",
            str(evidence.exit_code) if evidence.exit_code is not None else "",
            evidence.file_path or "",
            evidence.file_hash or "",
        )
    )
    return f"evidence:{hashlib.sha256(payload.encode()).hexdigest()}"


def task_to_node(task: Task) -> TaskNode:
    """Convert one legacy Task into its graph representation."""
    metadata = task.metadata or {}
    refs = tuple(metadata.get("evidence_refs", ()))
    if not refs and task.evidence:
        refs = tuple(_evidence_ref(e) for e in task.evidence)

    attempts: tuple[TaskAttempt, ...] = ()
    if task.started_at is not None:
        attempt_status = {
            TaskStatus.IN_PROGRESS: "running",
            TaskStatus.COMPLETED: "completed",
            TaskStatus.FAILED: "failed",
        }.get(task.status, "completed")
        attempts = (
            TaskAttempt(
                attempt_id=1,
                started_at=task.started_at,
                completed_at=task.completed_at,
                status=attempt_status,
                evidence_refs=refs,
                error=metadata.get("error"),
            ),
        )

    return TaskNode(
        task_id=task.id,
        description=task.description,
        phase=task.phase,
        parent=metadata.get("parent"),
        dependencies=task.dependencies,
        status=task.status,
        attempts=attempts,
        evidence_refs=refs,
        result=metadata.get("result"),
        rollback=metadata.get("rollback"),
    )


def ledger_to_graph(ledger: TaskLedger) -> TaskStateGraph:
    """Build and validate a graph from the current TaskLedger."""
    graph = TaskStateGraph()
    for task in ledger.tasks.values():
        graph = graph.add(task_to_node(task))
    graph.validate()
    return graph
