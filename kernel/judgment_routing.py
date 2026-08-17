"""Kernel contract for routing uncertain evidence to judgment."""
from __future__ import annotations

from dataclasses import dataclass

from .evidence_state import EvidenceAssessment, EvidenceState


@dataclass(frozen=True, slots=True)
class JudgmentRouting:
    required: bool
    reason: str
    evidence_state: EvidenceState


def route_to_judgment(assessment: EvidenceAssessment) -> JudgmentRouting:
    """Return an explicit judgment requirement for uncertain evidence states."""
    if assessment.state in (EvidenceState.LOW_CONFIDENCE, EvidenceState.CONTRADICTORY):
        return JudgmentRouting(True, assessment.reason or assessment.state.value, assessment.state)
    return JudgmentRouting(False, "evidence does not require judgment", assessment.state)


__all__ = ["JudgmentRouting", "route_to_judgment"]
