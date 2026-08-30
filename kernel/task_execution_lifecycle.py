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


def _next_phase(task_set: TaskSet, current_phase: str) -> str:
    """Advance only after every task in the current phase is complete."""
    current_tasks = [task for task in task_set.tasks if task.get("phase") == current_phase]
    if any(str(task["id"]) not in task_set.completed for task in current_tasks):
        return current_phase

    for task in task_set.ready_tasks():
        phase = str(task.get("phase", ""))
        if phase and phase != current_phase:
            return phase
    return current_phase


def complete_successful_task(
    persistence: TaskSetPersistence,
    context: TaskExecutionContext,
    state: KernelState,
    evidence: Any,
) -> TaskExecutionContext:
    completed_state, completed_tasks = state.complete_current_task(context.task_set, evidence)
    next_phase = _next_phase(completed_tasks, context.phase)
    persistence.save(
        project_id=context.project_id,
        session_id=context.session_id,
        change_id=context.change_id,
        phase=next_phase,
        status=completed_state.current_status,
        task_set=completed_tasks,
        expected_version=context.version,
    )
    return TaskExecutionContext(
        project_id=context.project_id,
        session_id=context.session_id,
        change_id=context.change_id,
        phase=next_phase,
        status=completed_state.current_status,
        version=context.version + 1,
        task_set=completed_tasks,
    )
