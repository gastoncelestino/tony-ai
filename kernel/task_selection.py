"""Deterministic selection of the next ready task."""
from __future__ import annotations

from kernel.task_set import TaskSet


def select_ready_task(task_set: TaskSet, current_phase: str) -> dict | None:
    """Return the first ready task belonging to the current phase."""
    for task in task_set.ready_tasks():
        if task.get("phase") == current_phase:
            return task
    return None
