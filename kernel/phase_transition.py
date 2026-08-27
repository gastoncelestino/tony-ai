"""Minimal Kernel-owned phase transition."""
from __future__ import annotations

from .phase_policy import can_transition


def transition_phase(current_phase: str, next_phase: str) -> str:
    """Return the next phase only when it is the immediate allowed successor."""
    if not can_transition(current_phase, next_phase):
        raise ValueError("phase transition is not allowed")
    return next_phase
