"""Compatibility bridge between TaskLedger and the Task State Graph.

The Graph is the authoritative task-state model. The ledger remains a
compatibility projection for existing callers, so graph history is preserved
when the projection is rebuilt.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
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

    raw_attempts = metadata.get("graph_attempts")
    if raw_attempts:
        attempts = tuple(TaskAttempt(**attempt) for attempt in raw_attempts)
    elif task.started_at is not None:
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
    else:
        attempts = ()

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


def graph_to_ledger(graph: TaskStateGraph, ledger: TaskLedger) -> TaskLedger:
    """Project authoritative graph state back into the legacy ledger.

    Existing evidence objects and task metadata are retained. Graph attempts,
    refs, result, rollback and parent are serialized into metadata so a later
    ledger-to-graph conversion cannot erase execution history.
    """
    tasks: dict[str, Task] = {}
    for task_id, node in graph.nodes.items():
        previous = ledger.tasks.get(task_id)
        if previous is None:
            raise ValueError(f"Cannot project unknown graph task: {task_id}")

        latest = node.attempts[-1] if node.attempts else None
        metadata = dict(previous.metadata or {})
        metadata.update({
            "evidence_refs": node.evidence_refs,
            "result": node.result,
            "rollback": node.rollback,
            "parent": node.parent,
            "graph_attempts": [
                {
                    "attempt_id": a.attempt_id,
                    "started_at": a.started_at,
                    "completed_at": a.completed_at,
                    "status": a.status,
                    "evidence_refs": a.evidence_refs,
                    "error": a.error,
                }
                for a in node.attempts
            ],
        })
        tasks[task_id] = replace(
            previous,
            status=node.status,
            started_at=latest.started_at if latest else previous.started_at,
            completed_at=latest.completed_at if latest else previous.completed_at,
            metadata=metadata,
        )
    return TaskLedger(tasks=tasks)
