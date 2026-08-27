"""Minimal Kernel-owned task completion policy."""

from kernel.completion_gate import validate_completion


def can_complete_task(status: str, evidence: object) -> bool:
    """Return whether a task may complete from its current status with evidence."""
    return status == "running" and validate_completion(evidence)
