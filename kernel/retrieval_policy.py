"""Deterministic retrieval policy for evidence-aware orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .evidence_state import EvidenceAssessment, EvidenceState, assess_evidence
from .schemas import Evidence


@dataclass(frozen=True, slots=True)
class RetrievalAttempt:
    """One retrieval evaluation cycle."""

    attempt: int
    state: EvidenceState
    evidence_count: int
    evidence_refs: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RetrievalDecision:
    """Final deterministic decision after bounded retrieval."""

    assessment: EvidenceAssessment
    attempts: tuple[RetrievalAttempt, ...]

    @property
    def should_retrieve(self) -> bool:
        return self.assessment.needs_retrieval

    @property
    def exhausted(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].state in (
            EvidenceState.NO_EVIDENCE,
            EvidenceState.INSUFFICIENT,
        )


def retrieve_until_sufficient(
    retriever: Callable[[int], Sequence[Evidence]],
    *,
    max_attempts: int = 2,
    minimum_valid: int = 1,
    minimum_confidence: float = 0.75,
) -> RetrievalDecision:
    """Run bounded retrieval until evidence is sufficient or retrieval is exhausted.

    The retriever receives a 1-based attempt number. Retrieval is only repeated
    for ``NO_EVIDENCE`` or ``INSUFFICIENT``; low-confidence and contradictory
    evidence are handed to judgment instead of blindly retrieving forever.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    attempts: list[RetrievalAttempt] = []
    assessment = assess_evidence(
        (), minimum_valid=minimum_valid, minimum_confidence=minimum_confidence
    )

    for attempt_no in range(1, max_attempts + 1):
        evidence = tuple(retriever(attempt_no))
        refs = tuple(f"retrieval:{attempt_no}:{index}" for index, _ in enumerate(evidence, 1))
        assessment = assess_evidence(
            evidence,
            evidence_refs=refs,
            minimum_valid=minimum_valid,
            minimum_confidence=minimum_confidence,
        )
        attempts.append(
            RetrievalAttempt(
                attempt=attempt_no,
                state=assessment.state,
                evidence_count=len(evidence),
                evidence_refs=refs,
                reason=assessment.reason,
            )
        )
        if not assessment.needs_retrieval:
            break

    return RetrievalDecision(assessment=assessment, attempts=tuple(attempts))


__all__ = ["RetrievalAttempt", "RetrievalDecision", "retrieve_until_sufficient"]
