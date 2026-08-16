"""Tests for the deterministic evidence assessment contract."""

from kernel import Evidence, EvidenceState, EvidenceType, assess_evidence


def _command(exit_code: int) -> Evidence:
    return Evidence(
        type=EvidenceType.COMMAND,
        claim="command completed",
        command="true",
        exit_code=exit_code,
        stdout="ok" if exit_code == 0 else "failed",
    )


def test_no_evidence_is_distinct_from_insufficient():
    no_evidence = assess_evidence([])
    insufficient = assess_evidence([Evidence(
        type=EvidenceType.MANUAL,
        claim="unverified observation",
    )])

    assert no_evidence.state == EvidenceState.NO_EVIDENCE
    assert insufficient.state == EvidenceState.INSUFFICIENT
    assert no_evidence.needs_retrieval is True
    assert insufficient.needs_retrieval is True


def test_valid_evidence_is_sufficient():
    assessment = assess_evidence([_command(0)], evidence_refs=("evidence:1",))

    assert assessment.state == EvidenceState.SUFFICIENT
    assert assessment.can_progress is True
    assert assessment.evidence_refs == ("evidence:1",)
    assert assessment.confidence == 1.0


def test_low_confidence_is_not_no_evidence():
    assessment = assess_evidence(
        [_command(0), _command(0)],
        minimum_confidence=1.1,
    )

    assert assessment.state == EvidenceState.LOW_CONFIDENCE
    assert assessment.state != EvidenceState.NO_EVIDENCE
    assert assessment.needs_judgment is True
    assert assessment.can_progress is False


def test_invalid_evidence_is_insufficient():
    assessment = assess_evidence([_command(None)])

    assert assessment.state == EvidenceState.INSUFFICIENT
    assert assessment.needs_retrieval is True


def test_contradictory_valid_manual_evidence_requires_judgment():
    first = Evidence(
        type=EvidenceType.MANUAL,
        claim="claim is true",
        metadata={"supports": True},
        status="valid",
    )
    second = Evidence(
        type=EvidenceType.MANUAL,
        claim="claim is false",
        metadata={"supports": False},
        status="valid",
    )

    # Manual evidence has no automatic validator, so the assessment contract
    # conservatively classifies it as insufficient rather than inventing a
    # confidence score. Contradiction is reserved for machine-valid evidence.
    assessment = assess_evidence([first, second])
    assert assessment.state == EvidenceState.INSUFFICIENT
    assert assessment.needs_retrieval is True
