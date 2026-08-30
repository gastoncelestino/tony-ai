from dataclasses import dataclass
from typing import Any

from kernel.state import KernelState
from kernel.task_set import TaskSet
from kernel.task_set_persistence import TaskSetPersistence


@dataclass(frozen=True)
class TaskExecutionContext:
    project_id: str
    session_id: str
    change_id: str
    phase: str
    status: str
    version: int
    task_set: TaskSet


def _next_execution_state(task_set: TaskSet, current_phase: str) -> tuple[str, str]:
    """Return the next executable phase and a resumable status.

    A single task completion is not a terminal execution state. The pure
    KernelState transition remains ``running -> completed`` for the current
    task, but the persisted TaskSet must become ``pending`` whenever another
    ready task can still be delegated.
    """
    current_tasks = [task for task in task_set.tasks if task.get("phase") == current_phase]
    if any(str(task["id"]) not in task_set.completed for task in current_tasks):
        return current_phase, "pending"

    for task in task_set.ready_tasks():
        phase = str(task.get("phase", ""))
        if phase and phase != current_phase:
            return phase, "pending"

    if len(task_set.completed) == len(task_set.tasks):
        return current_phase, "completed"
    return current_phase, "pending"


def complete_successful_task(
    persistence: TaskSetPersistence,
    context: TaskExecutionContext,
    state: KernelState,
    evidence: Any,
) -> TaskExecutionContext:
    completed_state, completed_tasks = state.complete_current_task(context.task_set, evidence)
    next_phase, next_status = _next_execution_state(completed_tasks, context.phase)
    persistence.save(
        project_id=context.project_id,
        session_id=context.session_id,
        change_id=context.change_id,
        phase=next_phase,
        status=next_status,
        task_set=completed_tasks,
        expected_version=context.version,
    )
    return TaskExecutionContext(
        project_id=context.project_id,
        session_id=context.session_id,
        change_id=context.change_id,
        phase=next_phase,
        status=next_status,
        version=context.version + 1,
        task_set=completed_tasks,
    )
