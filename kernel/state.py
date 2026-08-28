"""Minimal in-memory Kernel state."""

from copy import deepcopy
from dataclasses import dataclass

from kernel.task_completion_transition import complete_task as transition_complete_task
from kernel.task_execution_transition import start_task as transition_start_task
from kernel.task_selection import select_ready_task


@dataclass(frozen=True)
class KernelState:
    """Minimal Kernel-owned execution state."""

    current_phase: str
    current_status: str
    _next_task: dict | None = None

    def get_next_task(self) -> dict | None:
        """Return a detached copy of the selected task, if any."""
        return deepcopy(self._next_task)

    def select_next_task(self, task_set: object) -> "KernelState":
        """Select the first ready task for this phase as a new pending task state."""
        selected_task = select_ready_task(task_set, self.current_phase)
        return KernelState(
            self.current_phase,
            "pending" if selected_task is not None else self.current_status,
            selected_task,
        )

    def start_task(self) -> "KernelState":
        """Return a new state with the current task transitioned to running."""
        return KernelState(
            self.current_phase,
            transition_start_task(self.current_status),
            self.get_next_task(),
        )

    def complete_task(self, evidence: object) -> "KernelState":
        """Return a new state with the current task transitioned to completed."""
        return KernelState(
            self.current_phase,
            transition_complete_task(self.current_status, evidence),
            self.get_next_task(),
        )

    def complete_current_task(self, task_set: object, evidence: object):
        """Complete the selected task and return the new state and task set."""
        selected_task = self.get_next_task()
        if selected_task is None or not selected_task.get("id"):
            raise ValueError("No current task is selected")
        if self.current_status != "running":
            raise ValueError("Current task must be running")

        task_id = selected_task["id"]
        try:
            task_set.get(task_id)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"Task is not present in task set: {task_id}") from exc

        new_state = self.complete_task(evidence)
        new_task_set = task_set.complete(task_id)
        return new_state, new_task_set
