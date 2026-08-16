"""Tony Kernel — Task State Graph.

The graph is the structural layer for task-level orchestration.  It is kept
separate from the existing phase state machine so the first migration can be
incremental: existing Task/TaskLedger callers remain valid while new code can
use explicit DAG semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Optional

from .schemas import Phase, TaskStatus


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    """One execution attempt for a task."""

    attempt_id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    error: Optional[str] = None


@dataclass(frozen=True, slots=True)
class TaskNode:
    """A task as a node in the Kernel task graph."""

    task_id: str
    description: str
    phase: Phase
    parent: Optional[str] = None
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    status: TaskStatus = TaskStatus.PENDING
    attempts: tuple[TaskAttempt, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    result: Optional[dict] = None
    rollback: Optional[dict] = None

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)


class TaskGraphError(ValueError):
    """Invalid graph structure or state transition."""


@dataclass(frozen=True, slots=True)
class TaskStateGraph:
    """Immutable task DAG with deterministic transition rules."""

    nodes: dict[str, TaskNode] = field(default_factory=dict)

    def add(self, node: TaskNode) -> "TaskStateGraph":
        if not node.task_id:
            raise TaskGraphError("task_id must not be empty")
        if node.task_id in self.nodes:
            raise TaskGraphError(f"Task already exists: {node.task_id}")
        updated = {**self.nodes, node.task_id: node}
        graph = TaskStateGraph(updated)
        graph.validate()
        return graph

    def get(self, task_id: str) -> Optional[TaskNode]:
        return self.nodes.get(task_id)

    def children(self, task_id: str) -> tuple[TaskNode, ...]:
        return tuple(n for n in self.nodes.values() if n.parent == task_id)

    def validate(self) -> None:
        """Validate references and reject dependency/parent cycles."""
        for node in self.nodes.values():
            if node.parent is not None and node.parent not in self.nodes:
                raise TaskGraphError(f"Unknown parent {node.parent!r} for {node.task_id!r}")
            for dep in node.dependencies:
                if dep not in self.nodes:
                    raise TaskGraphError(f"Unknown dependency {dep!r} for {node.task_id!r}")
                if dep == node.task_id:
                    raise TaskGraphError(f"Task cannot depend on itself: {node.task_id}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise TaskGraphError(f"Dependency cycle detected at task: {task_id}")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dep in self.nodes[task_id].dependencies:
                visit(dep)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in self.nodes:
            visit(task_id)

    def ready(self) -> tuple[TaskNode, ...]:
        """Return pending nodes whose dependencies are completed, in insertion order."""
        return tuple(
            node for node in self.nodes.values()
            if node.status == TaskStatus.PENDING
            and all(self.nodes[dep].status == TaskStatus.COMPLETED for dep in node.dependencies)
        )

    def start(self, task_id: str, now: Optional[datetime] = None) -> "TaskStateGraph":
        node = self._require(task_id)
        if node.status != TaskStatus.PENDING:
            raise TaskGraphError(f"Task {task_id} is not pending")
        if not all(self.nodes[dep].status == TaskStatus.COMPLETED for dep in node.dependencies):
            raise TaskGraphError(f"Task {task_id} has incomplete dependencies")
        timestamp = now or datetime.now()
        attempt = TaskAttempt(attempt_id=node.attempt_count + 1, started_at=timestamp)
        return self._replace(replace(node, status=TaskStatus.IN_PROGRESS, attempts=node.attempts + (attempt,)))

    def complete(
        self,
        task_id: str,
        evidence_refs: tuple[str, ...],
        result: Optional[dict] = None,
        now: Optional[datetime] = None,
    ) -> "TaskStateGraph":
        node = self._require(task_id)
        if node.status != TaskStatus.IN_PROGRESS:
            raise TaskGraphError(f"Task {task_id} is not in progress")
        if not evidence_refs:
            raise TaskGraphError(f"Task {task_id} cannot complete without evidence_refs")
        timestamp = now or datetime.now()
        attempt = node.attempts[-1]
        completed_attempt = replace(
            attempt,
            completed_at=timestamp,
            status="completed",
            evidence_refs=tuple(evidence_refs),
        )
        updated = replace(
            node,
            status=TaskStatus.COMPLETED,
            attempts=node.attempts[:-1] + (completed_attempt,),
            evidence_refs=tuple(evidence_refs),
            result=result,
        )
        return self._replace(updated)

    def fail(
        self,
        task_id: str,
        error: str,
        rollback: Optional[dict] = None,
        now: Optional[datetime] = None,
    ) -> "TaskStateGraph":
        node = self._require(task_id)
        if node.status != TaskStatus.IN_PROGRESS:
            raise TaskGraphError(f"Task {task_id} is not in progress")
        timestamp = now or datetime.now()
        attempt = node.attempts[-1]
        failed_attempt = replace(attempt, completed_at=timestamp, status="failed", error=error)
        updated = replace(
            node,
            status=TaskStatus.FAILED,
            attempts=node.attempts[:-1] + (failed_attempt,),
            rollback=rollback,
        )
        return self._replace(updated)

    def retry(self, task_id: str) -> "TaskStateGraph":
        node = self._require(task_id)
        if node.status != TaskStatus.FAILED:
            raise TaskGraphError(f"Task {task_id} is not failed")
        return self._replace(replace(node, status=TaskStatus.PENDING))

    def _require(self, task_id: str) -> TaskNode:
        node = self.nodes.get(task_id)
        if node is None:
            raise TaskGraphError(f"Unknown task: {task_id}")
        return node

    def _replace(self, node: TaskNode) -> "TaskStateGraph":
        return TaskStateGraph({**self.nodes, node.task_id: node})
