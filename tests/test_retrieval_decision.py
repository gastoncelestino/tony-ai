from kernel import EvidenceAssessment, EvidenceState
from kernel.retrieval_decision import RetrievalAction, arbitrate_retrieval


def assessment(state: EvidenceState) -> EvidenceAssessment:
    return EvidenceAssessment(state=state, reason=state.value)


def test_sufficient_transitions():
    result = arbitrate_retrieval(assessment(EvidenceState.SUFFICIENT))
    assert result.action is RetrievalAction.TRANSITION


def test_no_evidence_retrieves_again():
    result = arbitrate_retrieval(assessment(EvidenceState.NO_EVIDENCE))
    assert result.action is RetrievalAction.RETRIEVE_AGAIN


def test_insufficient_retrieves_again():
    result = arbitrate_retrieval(assessment(EvidenceState.INSUFFICIENT))
    assert result.action is RetrievalAction.RETRIEVE_AGAIN


def test_low_confidence_goes_to_judgment():
    result = arbitrate_retrieval(assessment(EvidenceState.LOW_CONFIDENCE))
    assert result.action is RetrievalAction.JUDGMENT


def test_contradictory_goes_to_judgment():
    result = arbitrate_retrieval(assessment(EvidenceState.CONTRADICTORY))
    assert result.action is RetrievalAction.JUDGMENT
