"""Tony Kernel — Evidence assessment state machine.

Separates absence of evidence from weak evidence so orchestration can choose
between retrieval, corroboration, judgment, and progression deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from .schemas import Evidence, EvidenceStatus


class EvidenceState(str, Enum):
    """Machine-readable outcome of an evidence assessment."""

    NO_EVIDENCE = "no_evidence"
    INSUFFICIENT = "insufficient"
    LOW_CONFIDENCE = "low_confidence"
    SUFFICIENT = "sufficient"
    CONTRADICTORY = "contradictory"


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    """Deterministic assessment of evidence supporting a claim."""

    state: EvidenceState
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    reason: str = ""

    @property
    def can_progress(self) -> bool:
        return self.state == EvidenceState.SUFFICIENT

    @property
    def needs_retrieval(self) -> bool:
        return self.state in (EvidenceState.NO_EVIDENCE, EvidenceState.INSUFFICIENT)

    @property
    def needs_judgment(self) -> bool:
        return self.state in (EvidenceState.LOW_CONFIDENCE, EvidenceState.CONTRADICTORY)


def assess_evidence(
    evidence: Sequence[Evidence],
    *,
    evidence_refs: Sequence[str] = (),
    minimum_valid: int = 1,
    minimum_confidence: float = 0.75,
) -> EvidenceAssessment:
    """Assess evidence without performing retrieval.

    This function deliberately treats ``NO_EVIDENCE`` differently from weak
    or conflicting evidence. Retrieval policy can therefore be layered on top
    without changing the underlying evidence contract.
    """
    refs = tuple(evidence_refs)
    if not evidence:
        return EvidenceAssessment(
            state=EvidenceState.NO_EVIDENCE,
            evidence_refs=refs,
            reason="No evidence was provided",
        )

    valid = tuple(item for item in evidence if item.validate() == EvidenceStatus.VALID)
    if len(valid) < minimum_valid:
        return EvidenceAssessment(
            state=EvidenceState.INSUFFICIENT,
            evidence_refs=refs,
            reason="Evidence exists but does not meet the minimum valid evidence threshold",
        )

    successful = sum(1 for item in valid if item.exit_code in (None, 0))
    failed = sum(1 for item in valid if item.exit_code not in (None, 0))
    if successful and failed:
        return EvidenceAssessment(
            state=EvidenceState.CONTRADICTORY,
            evidence_refs=refs,
            confidence=0.0,
            reason="Valid evidence contains contradictory execution outcomes",
        )

    confidence = min(1.0, successful / max(1, len(valid)))
    if confidence < minimum_confidence:
        return EvidenceAssessment(
            state=EvidenceState.LOW_CONFIDENCE,
            evidence_refs=refs,
            confidence=confidence,
            reason="Evidence is valid but below the confidence threshold",
        )

    return EvidenceAssessment(
        state=EvidenceState.SUFFICIENT,
        evidence_refs=refs,
        confidence=confidence,
        reason="Evidence meets the configured validity and confidence thresholds",
    )
