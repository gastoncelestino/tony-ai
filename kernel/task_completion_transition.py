"""Minimal Kernel-owned task completion transition."""

from kernel.task_completion_policy import can_complete_task


def complete_task(status: str, evidence: object) -> str:
    """Transition a running task to completed when completion is authorized."""
    if not can_complete_task(status, evidence):
        raise ValueError("task cannot complete from current status or evidence")
    return "completed"
