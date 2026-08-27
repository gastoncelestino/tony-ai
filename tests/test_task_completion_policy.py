from kernel.completion_gate import validate_completion
from kernel.task_completion_policy import can_complete_task


VALID_EVIDENCE = [{"kind": "test", "value": "45 passed"}]


class TestTaskCompletionPolicy:
    def test_running_task_with_valid_evidence_can_complete(self):
        assert can_complete_task("running", VALID_EVIDENCE) is True

    def test_running_task_with_empty_evidence_cannot_complete(self):
        assert can_complete_task("running", []) is False

    def test_running_task_without_evidence_cannot_complete(self):
        assert can_complete_task("running", None) is False

    def test_pending_task_with_valid_evidence_cannot_complete(self):
        assert can_complete_task("pending", VALID_EVIDENCE) is False

    def test_completed_task_with_valid_evidence_cannot_complete(self):
        assert can_complete_task("completed", VALID_EVIDENCE) is False

    def test_unknown_status_with_valid_evidence_cannot_complete(self):
        assert can_complete_task("unknown", VALID_EVIDENCE) is False

    def test_policy_uses_completion_gate_for_evidence(self):
        assert validate_completion(VALID_EVIDENCE) is True
        assert validate_completion([]) is False
