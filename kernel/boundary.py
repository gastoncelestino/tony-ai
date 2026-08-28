"""Transport-neutral boundary between callers and the Tony Kernel."""
from __future__ import annotations

from typing import Mapping, Sequence

from kernel.execution_order import resolve_execution
from kernel.state import KernelState
from kernel.task_set import TaskSet


def resolve_boundary(request: Mapping[str, object]) -> dict:
    """Resolve an execution decision from a complete, caller-supplied task snapshot."""
    phase = str(request.get("phase", ""))
    status = str(request.get("status", ""))
    tasks = request.get("tasks", ())
    completed = request.get("completed", ())

    if not phase:
        return _blocked("Missing required phase")
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)):
        return _blocked("tasks must be a sequence")
    if not isinstance(completed, Sequence) or isinstance(completed, (str, bytes)):
        return _blocked("completed must be a sequence")

    try:
        task_set = TaskSet(tuple(tasks), tuple(str(task_id) for task_id in completed))
        state = KernelState(phase, status).select_next_task(task_set)
        if state.get_next_task() is not None and state.current_status == "pending":
            state = state.start_task()
        return resolve_execution(state)
    except (TypeError, ValueError) as exc:
        return _blocked(str(exc))


def _blocked(reason: str) -> dict:
    return {
        "decision": "blocked",
        "allowed": False,
        "reason": reason,
        "current_phase": None,
        "execution_order": None,
    }
