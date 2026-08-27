import pytest

from kernel.phase_transition import transition_phase


def test_immediate_successor_transitions():
    assert transition_phase("spec", "design") == "design"


def test_phase_skip_is_blocked():
    with pytest.raises(ValueError):
        transition_phase("spec", "apply")


def test_backward_transition_is_blocked():
    with pytest.raises(ValueError):
        transition_phase("design", "spec")


def test_unknown_phase_is_blocked():
    with pytest.raises(ValueError):
        transition_phase("unknown", "design")
