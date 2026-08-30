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


def complete_successful_task(
    persistence: TaskSetPersistence,
    context: TaskExecutionContext,
    state: KernelState,
    evidence: Any,
) -> TaskExecutionContext:
    completed_state, completed_tasks = state.complete_current_task(context.task_set, evidence)
    persistence.save(
        project_id=context.project_id,
        session_id=context.session_id,
        change_id=context.change_id,
        phase=completed_state.current_phase,
        status=completed_state.current_status,
        task_set=completed_tasks,
        expected_version=context.version,
    )
    return TaskExecutionContext(
        project_id=context.project_id,
        session_id=context.session_id,
        change_id=context.change_id,
        phase=completed_state.current_phase,
        status=completed_state.current_status,
        version=context.version + 1,
        task_set=completed_tasks,
    )
