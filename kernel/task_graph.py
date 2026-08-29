"""Validated task-graph proposals for atomic execution.

The decomposer proposes work; this module validates the proposal and turns it
into the existing canonical TaskSet. It deliberately does not authorize
execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .task_set import TaskSet


class TaskGraphProposalError(ValueError):
    """Raised when a task graph proposal cannot become a valid TaskSet."""


@dataclass(frozen=True, slots=True)
class TaskProposal:
    id: str
    description: str
    phase: str
    dependencies: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    objective: str = ""
    expected_result: str = ""
    verification: str = ""

    def to_task_dict(self) -> dict:
        """Convert the proposal to the dictionary schema used by TaskSet."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TaskGraphProposal:
    tasks: tuple[TaskProposal, ...]
    max_tasks: int = 100

    @classmethod
    def from_iterable(
        cls,
        tasks: Iterable[TaskProposal],
        *,
        max_tasks: int = 100,
    ) -> "TaskGraphProposal":
        return cls(tuple(tasks), max_tasks=max_tasks)

    @staticmethod
    def _validate_atomicity(task: TaskProposal) -> None:
        """Require an explicit, bounded and verifiable atomic-task contract."""
        if not task.description.strip():
            raise TaskGraphProposalError(f"Task {task.id!r} has an empty description")
        if not task.phase.strip():
            raise TaskGraphProposalError(f"Task {task.id!r} has an empty phase")
        if not task.objective.strip():
            raise TaskGraphProposalError(f"Task {task.id!r} has no atomic objective")
        if not task.expected_result.strip():
            raise TaskGraphProposalError(f"Task {task.id!r} has no expected result")
        if not task.verification.strip():
            raise TaskGraphProposalError(f"Task {task.id!r} has no verification criterion")

    def to_task_set(self) -> TaskSet:
        if self.max_tasks < 1:
            raise TaskGraphProposalError("max_tasks must be positive")
        if not self.tasks:
            raise TaskGraphProposalError("task graph cannot be empty")
        if len(self.tasks) > self.max_tasks:
            raise TaskGraphProposalError("task graph exceeds maximum task count")

        ids = [task.id for task in self.tasks]
        if any(not task_id or not task_id.strip() for task_id in ids):
            raise TaskGraphProposalError("task ids must be non-empty")
        if len(ids) != len(set(ids)):
            raise TaskGraphProposalError("task ids must be unique")

        for task in self.tasks:
            self._validate_atomicity(task)

        canonical = tuple(task.to_task_dict() for task in self.tasks)

        try:
            return TaskSet(canonical)
        except (TypeError, ValueError) as exc:
            raise TaskGraphProposalError(str(exc)) from exc
