from kernel.phase_policy import can_transition


class TestPhasePolicy:
    def test_immediate_successor_is_allowed(self):
        assert can_transition("spec", "design") is True

    def test_phase_skip_is_blocked(self):
        assert can_transition("spec", "apply") is False

    def test_unknown_phase_is_blocked(self):
        assert can_transition("unknown", "design") is False

    def test_backward_transition_is_blocked(self):
        assert can_transition("design", "spec") is False
