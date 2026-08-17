"""Kernel-level arbitration for evidence retrieval outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .evidence_state import EvidenceAssessment, EvidenceState


class RetrievalAction(str, Enum):
    TRANSITION = "transition"
    RETRIEVE_AGAIN = "retrieve_again"
    JUDGMENT = "judgment"


@dataclass(frozen=True, slots=True)
class RetrievalArbitration:
    assessment: EvidenceAssessment
    action: RetrievalAction
    reason: str


def arbitrate_retrieval(assessment: EvidenceAssessment) -> RetrievalArbitration:
    """Map an evidence assessment to the next deterministic Kernel action."""
    if assessment.state is EvidenceState.SUFFICIENT:
        return RetrievalArbitration(assessment, RetrievalAction.TRANSITION, "evidence is sufficient")
    if assessment.state in (EvidenceState.NO_EVIDENCE, EvidenceState.INSUFFICIENT):
        return RetrievalArbitration(assessment, RetrievalAction.RETRIEVE_AGAIN, "more evidence is required")
    if assessment.state in (EvidenceState.LOW_CONFIDENCE, EvidenceState.CONTRADICTORY):
        return RetrievalArbitration(assessment, RetrievalAction.JUDGMENT, "evidence requires judgment")
    raise ValueError(f"Unsupported evidence state: {assessment.state!r}")


__all__ = ["RetrievalAction", "RetrievalArbitration", "arbitrate_retrieval"]
