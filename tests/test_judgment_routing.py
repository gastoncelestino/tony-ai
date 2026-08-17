from kernel import EvidenceAssessment, EvidenceState
from kernel.judgment_routing import route_to_judgment


def test_low_confidence_requires_judgment():
    result = route_to_judgment(EvidenceAssessment(state=EvidenceState.LOW_CONFIDENCE, reason="weak evidence"))
    assert result.required is True
    assert result.evidence_state is EvidenceState.LOW_CONFIDENCE


def test_contradictory_requires_judgment():
    result = route_to_judgment(EvidenceAssessment(state=EvidenceState.CONTRADICTORY, reason="conflicting evidence"))
    assert result.required is True
    assert result.evidence_state is EvidenceState.CONTRADICTORY


def test_sufficient_does_not_require_judgment():
    result = route_to_judgment(EvidenceAssessment(state=EvidenceState.SUFFICIENT))
    assert result.required is False
