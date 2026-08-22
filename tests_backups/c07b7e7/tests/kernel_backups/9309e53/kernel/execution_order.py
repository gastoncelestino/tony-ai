"""Deterministic execution-order resolution for Tony Kernel.

The Kernel selects the next executable task. Callers do not choose a phase,
agent, or workflow step through this resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True, slots=True)
class ExecutionOrder:
    """The only execution instruction the runtime should receive from Kernel."""

    phase: str
    task_id: str
    description: str
    files: tuple[str, ...]
    dependencies: tuple[str, ...]
    executor: str = "opencode"
    worker: str = "llm"

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "task_id": self.task_id,
            "description": self.description,
            "files": list(self.files),
            "dependencies": list(self.dependencies),
            "executor": self.executor,
            "worker": self.worker,
        }


def resolve_execution(
    current_phase: str,
    current_phase_status: str,
    task: Optional[Mapping[str, object]],
) -> dict:
    """Resolve the next execution order from Kernel-owned state.

    No requested phase, agent, or workflow decision is accepted from the
    caller. A task is executable only when the current phase is active and the
    task belongs to that phase.
    """
    if current_phase_status != "running":
        return {
            "decision": "blocked",
            "allowed": False,
            "reason": f"Current phase is not executable: {current_phase_status}",
            "current_phase": current_phase,
            "execution_order": None,
        }

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

    order = ExecutionOrder(
        phase=current_phase,
        task_id=task_id,
        description=description,
        files=tuple(str(value) for value in task.get("files", ())),
        dependencies=tuple(str(value) for value in task.get("dependencies", ())),
    )
    return {
        "decision": "proceed",
        "allowed": True,
        "reason": f"Execution order resolved for task {task_id}",
        "current_phase": current_phase,
        "execution_order": order.to_dict(),
    }
