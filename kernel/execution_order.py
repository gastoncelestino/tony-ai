"""Deterministic execution-order resolution for Tony Kernel.

The Kernel selects the next executable task. Callers do not choose a phase,
agent, task, or workflow step through this resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


ALLOWED_CAPABILITIES = frozenset({"read", "search"})


class KernelState(Protocol):
    """Minimal Kernel surface required to resolve an execution order."""

    change_state: object

    def get_next_task(self) -> dict | None:
        ...


@dataclass(frozen=True, slots=True)
class ExecutionOrder:
    """The only execution instruction the runtime should receive from Kernel."""

    phase: str
    task_id: str
    description: str
    files: tuple[str, ...]
    dependencies: tuple[str, ...]
    capabilities: tuple[str, ...]
    executor: str = "opencode"
    worker: str = "llm"

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "task_id": self.task_id,
            "description": self.description,
            "files": list(self.files),
            "dependencies": list(self.dependencies),
            "capabilities": list(self.capabilities),
            "executor": self.executor,
            "worker": self.worker,
        }


def resolve_execution(kernel: KernelState) -> dict:
    """Resolve the next execution order from Kernel-owned state only.

    The caller supplies the Kernel, not a phase or task. Phase status and the
    next task are read from Kernel state and validated here before an order is
    produced.
    """
    current_phase = kernel.change_state.current_phase.value
    current_status = kernel.change_state.get_current_phase_state().status.value

    if current_status != "running":
        return {
            "decision": "blocked",
            "allowed": False,
            "reason": f"Current phase is not executable: {current_status}",
            "current_phase": current_phase,
            "execution_order": None,
        }

    task = kernel.get_next_task()
    if task is None:
        return {
            "decision": "blocked",
            "allowed": False,
            "reason": f"No ready task for current phase: {current_phase}",
            "current_phase": current_phase,
            "execution_order": None,
        }

    task_phase = str(task.get("phase", ""))
    if task_phase != current_phase:
        return {
            "decision": "blocked",
            "allowed": False,
            "reason": (
                f"Ready task {task.get('id', '')} belongs to phase "
                f"{task_phase}, current phase is {current_phase}"
            ),
            "current_phase": current_phase,
            "execution_order": None,
        }

    task_id = str(task.get("id", ""))
    description = str(task.get("description", ""))
    if not task_id or not description:
        return {
            "decision": "blocked",
            "allowed": False,
            "reason": "Task is missing required id or description",
            "current_phase": current_phase,
            "execution_order": None,
        }

    capabilities = tuple(str(value) for value in task.get("capabilities", ()))
    invalid_capabilities = sorted(set(capabilities) - ALLOWED_CAPABILITIES)
    if invalid_capabilities:
        return {
            "decision": "blocked",
            "allowed": False,
            "reason": f"Unsupported capabilities: {invalid_capabilities}",
            "current_phase": current_phase,
            "execution_order": None,
        }

    order = ExecutionOrder(
        phase=current_phase,
        task_id=task_id,
        description=description,
        files=tuple(str(value) for value in task.get("files", ())),
        dependencies=tuple(str(value) for value in task.get("dependencies", ())),
        capabilities=capabilities,
    )
    return {
        "decision": "proceed",
        "allowed": True,
        "reason": f"Execution order resolved for task {task_id}",
        "current_phase": current_phase,
        "execution_order": order.to_dict(),
    }


def authorize_execution_order(order: ExecutionOrder, requested_task_id: str) -> bool:
    """Allow runtime execution only for the task selected by Kernel.

    The runtime cannot substitute another task for the immutable order emitted
    by Kernel. No runtime-side task selection or fallback is performed here.
    """
    return requested_task_id == order.task_id
