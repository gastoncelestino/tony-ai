"""Deterministic execution-order resolution for Tony Kernel."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class KernelState(Protocol):
    """Minimal Kernel state surface required to resolve an execution order."""

    current_phase: str
    current_status: str

    def get_next_task(self) -> dict | None:
        ...


@dataclass(frozen=True, slots=True)
class ExecutionOrder:
    """Minimal immutable execution instruction emitted by the Kernel."""

    phase: str
    task_id: str
    description: str
    files: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "task_id": self.task_id,
            "description": self.description,
            "files": list(self.files),
        }


def resolve_execution(kernel: KernelState) -> dict:
    """Resolve the next execution order from Kernel-owned state only."""
    current_phase = kernel.current_phase
    current_status = kernel.current_status

    if current_status != "running":
        return {"decision": "blocked", "allowed": False, "reason": f"Current phase is not executable: {current_status}", "current_phase": current_phase, "execution_order": None}

    task = kernel.get_next_task()
    if task is None:
        return {"decision": "blocked", "allowed": False, "reason": f"No ready task for current phase: {current_phase}", "current_phase": current_phase, "execution_order": None}

    task_phase = str(task.get("phase", ""))
    if task_phase != current_phase:
        return {"decision": "blocked", "allowed": False, "reason": f"Ready task {task.get('id', '')} belongs to phase {task_phase}, current phase is {current_phase}", "current_phase": current_phase, "execution_order": None}

    task_id = str(task.get("id", ""))
    description = str(task.get("description", ""))
    if not task_id or not description:
        return {"decision": "blocked", "allowed": False, "reason": "Task is missing required id or description", "current_phase": current_phase, "execution_order": None}

    order = ExecutionOrder(current_phase, task_id, description, tuple(str(value) for value in task.get("files", ())))
    return {"decision": "proceed", "allowed": True, "reason": f"Execution order resolved for task {task_id}", "current_phase": current_phase, "execution_order": order.to_dict()}


def authorize_execution_order(order: ExecutionOrder, requested_task_id: str) -> bool:
    """Allow runtime execution only for the task selected by Kernel."""
    return requested_task_id == order.task_id


def authorize_file_access(order: ExecutionOrder, file_path: str) -> bool:
    """Allow access only to a file explicitly included in the Kernel order."""
    return file_path in order.files
