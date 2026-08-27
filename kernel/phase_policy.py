"""Minimal Kernel-owned phase transition policy."""
from __future__ import annotations


PHASE_ORDER = (
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "archive",
)


def can_transition(current_phase: str, next_phase: str) -> bool:
    """Return whether next_phase is the immediate successor of current_phase."""
    try:
        return PHASE_ORDER.index(next_phase) == PHASE_ORDER.index(current_phase) + 1
    except ValueError:
        return False
