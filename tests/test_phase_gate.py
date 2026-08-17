import unittest

from kernel.phase_gate import PhaseGate
from kernel.schemas import ArtifactRef, ChangeState, Phase, PhaseState, PhaseStatus
from kernel.state_machine import InvalidTransitionError, MissingArtifactsError, PhaseController


def artifact(kind: str, path: str = "artifact.md") -> ArtifactRef:
    return ArtifactRef(
        kind=kind,
        path=path,
        store="inline",
        hash="hash",
        validated=True,
    )


def completed_explore() -> ChangeState:
    return ChangeState(
        change_id="phase-gate",
        project="test-project",
        current_phase=Phase.EXPLORE,
        phases={
            Phase.EXPLORE: PhaseState(
                phase=Phase.EXPLORE,
                status=PhaseStatus.COMPLETED,
                artifacts=(artifact("explore"),),
            )
        },
    )


class PhaseGateTests(unittest.TestCase):
    def test_allows_valid_transition_with_required_artifact(self):
        controller = PhaseController(completed_explore())
        gate = PhaseGate(controller)

        result = gate.check_transition(
            Phase.PROPOSE,
            lambda kind: artifact(kind),
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.result.value, "allow")

    def test_blocks_when_current_phase_is_not_completed(self):
        state = completed_explore()
        state = ChangeState(
            change_id=state.change_id,
            project=state.project,
            current_phase=Phase.EXPLORE,
            phases={
                Phase.EXPLORE: PhaseState(
                    phase=Phase.EXPLORE,
                    status=PhaseStatus.RUNNING,
                )
            },
        )
        gate = PhaseGate(PhaseController(state))

        result = gate.check_transition(Phase.PROPOSE, lambda kind: artifact(kind))

        self.assertFalse(result.allowed)
        self.assertIn("not completed", result.reason)

    def test_blocks_invalid_transition(self):
        gate = PhaseGate(PhaseController(completed_explore()))

        result = gate.check_transition(Phase.DESIGN)

        self.assertFalse(result.allowed)
        self.assertEqual(result.result.value, "deny")
        self.assertIn("Invalid transition", result.reason)

    def test_blocks_missing_required_artifact(self):
        gate = PhaseGate(PhaseController(completed_explore()))

        result = gate.check_transition(Phase.PROPOSE, lambda kind: None)

        self.assertFalse(result.allowed)
        self.assertEqual(result.missing_artifacts, ("explore",))
        self.assertEqual(result.result.value, "blocked")

    def test_blocks_invalid_required_artifact(self):
        gate = PhaseGate(PhaseController(completed_explore()))

        result = gate.check_transition(
            Phase.PROPOSE,
            lambda kind: ArtifactRef(
                kind=kind,
                path="artifact.md",
                store="inline",
                hash=None,
                validated=False,
            ),
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.missing_artifacts, ("explore",))

    def test_assert_can_transition_raises_for_missing_artifact(self):
        gate = PhaseGate(PhaseController(completed_explore()))

        with self.assertRaises(MissingArtifactsError):
            gate.assert_can_transition(Phase.PROPOSE, lambda kind: None)

    def test_assert_can_transition_raises_for_invalid_transition(self):
        gate = PhaseGate(PhaseController(completed_explore()))

        with self.assertRaises(InvalidTransitionError):
            gate.assert_can_transition(Phase.DESIGN)


if __name__ == "__main__":
    unittest.main()
