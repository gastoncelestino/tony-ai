"""Immutable task-set model for dependency readiness."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping

from kernel.dependency_policy import are_dependencies_satisfied


@dataclass(frozen=True, slots=True)
class TaskSet:
    """Immutable collection of tasks and their completed task IDs."""

    tasks: tuple[dict, ...]
    completed: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        tasks = tuple(deepcopy(task) for task in self.tasks)
        object.__setattr__(self, "tasks", tasks)
        completed = tuple(self.completed)
        object.__setattr__(self, "completed", completed)

        ids = [str(task.get("id", "")) for task in tasks]
        if any(not task_id for task_id in ids):
            raise ValueError("Every task must have a non-empty id")
        if len(ids) != len(set(ids)):
            raise ValueError("Task IDs must be unique")

        task_ids = set(ids)
        for task in tasks:
            for dependency in task.get("dependencies", ()):
                if dependency not in task_ids:
                    raise ValueError(f"Unknown task dependency: {dependency}")
                if dependency == task["id"]:
                    raise ValueError(f"Task cannot depend on itself: {dependency}")

        if not set(completed) <= task_ids:
            raise ValueError("Completed task IDs must exist in the task set")
        if len(completed) != len(set(completed)):
            raise ValueError("Completed task IDs must be unique")

        self._validate_acyclic(tasks)

    @staticmethod
    def _validate_acyclic(tasks: tuple[dict, ...]) -> None:
        graph = {
            str(task["id"]): tuple(str(dep) for dep in task.get("dependencies", ()))
            for task in tasks
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("Task dependencies must be acyclic")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in graph[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in graph:
            visit(task_id)

    def ready_tasks(self) -> tuple[dict, ...]:
        """Return pending tasks whose dependencies are all completed."""
        ready = []
        for task in self.tasks:
            task_id = str(task["id"])
            if task_id in self.completed:
                continue
            dependencies = tuple(str(dep) for dep in task.get("dependencies", ()))
            if are_dependencies_satisfied(dependencies, self.completed):
                ready.append(deepcopy(task))
        return tuple(ready)

    def get(self, task_id: str) -> dict | None:
        """Return a detached copy of a task by ID."""
        for task in self.tasks:
            if task["id"] == task_id:
                return deepcopy(task)
        return None

    def complete(self, task_id: str) -> "TaskSet":
        """Return a new set with a ready task marked completed."""
        task = self.get(task_id)
        if task is None:
            raise ValueError(f"Unknown task: {task_id}")
        if task_id in self.completed:
            raise ValueError(f"Task is already completed: {task_id}")
        if task not in self.ready_tasks():
            raise ValueError(f"Task dependencies are not satisfied: {task_id}")
        return TaskSet(self.tasks, self.completed + (task_id,))
