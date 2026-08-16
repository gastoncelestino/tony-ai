"""Tests for bounded evidence retrieval."""
from kernel import EvidenceType, Evidence, EvidenceState, retrieve_until_sufficient


def _evidence(exit_code=0):
    return Evidence(
        type=EvidenceType.COMMAND,
        claim="command result",
        command="true",
        exit_code=exit_code,
        stdout="ok" if exit_code == 0 else "failed",
    )


def test_retrieval_retries_when_first_attempt_has_no_evidence():
    calls = []

    def retrieve(attempt):
        calls.append(attempt)
        return () if attempt == 1 else (_evidence(),)

    decision = retrieve_until_sufficient(retrieve, max_attempts=2)
    assert calls == [1, 2]
    assert decision.assessment.state is EvidenceState.SUFFICIENT
    assert len(decision.attempts) == 2


def test_retrieval_stops_at_max_attempts():
    calls = []

    def retrieve(attempt):
        calls.append(attempt)
        return ()

    decision = retrieve_until_sufficient(retrieve, max_attempts=2)
    assert calls == [1, 2]
    assert decision.assessment.state is EvidenceState.NO_EVIDENCE
    assert decision.exhausted


def test_low_confidence_does_not_trigger_unbounded_retrieval():
    decision = retrieve_until_sufficient(
        lambda attempt: (_evidence(),),
        max_attempts=3,
        minimum_confidence=1.1,
    )
    assert decision.assessment.state is EvidenceState.LOW_CONFIDENCE
    assert len(decision.attempts) == 1
    assert not decision.should_retrieve
