"""Minimal Kernel-owned task start policy."""
from __future__ import annotations


def can_start_task(status: str) -> bool:
    """Return whether a task in status may start execution."""
    return status == "pending"
