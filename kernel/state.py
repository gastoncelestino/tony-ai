"""Minimal in-memory Kernel state."""

from dataclasses import dataclass
from copy import deepcopy


@dataclass(frozen=True)
class KernelState:
    """Minimal Kernel-owned execution state."""

    current_phase: str
    current_status: str
    _next_task: dict | None = None

    def get_next_task(self) -> dict | None:
        """Return a detached copy of the selected task, if any."""
        return deepcopy(self._next_task)
