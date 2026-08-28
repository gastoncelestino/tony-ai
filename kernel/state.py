"""Minimal in-memory Kernel state."""

from copy import deepcopy
from dataclasses import dataclass

from kernel.task_completion_transition import complete_task as transition_complete_task
from kernel.task_execution_transition import start_task as transition_start_task


@dataclass(frozen=True)
class KernelState:
    """Minimal Kernel-owned execution state."""

    current_phase: str
    current_status: str
    _next_task: dict | None = None

    def get_next_task(self) -> dict | None:
        """Return a detached copy of the selected task, if any."""
        return deepcopy(self._next_task)

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
