"""Minimal Kernel-owned task execution transition."""
from __future__ import annotations


def start_task(status: str) -> str:
    """Transition a pending task to running; reject all other states."""
    if status != "pending":
        raise ValueError("task cannot start from current status")
    return "running"
