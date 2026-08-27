import pytest

from kernel.task_completion_transition import complete_task


VALID_EVIDENCE = [{"kind": "test", "value": "52 passed"}]


def test_running_transitions_to_completed():
    assert complete_task("running", VALID_EVIDENCE) == "completed"


def test_running_with_invalid_evidence_is_blocked():
    with pytest.raises(ValueError, match="task cannot complete"):
        complete_task("running", [])


def test_pending_cannot_complete():
    with pytest.raises(ValueError, match="task cannot complete"):
        complete_task("pending", VALID_EVIDENCE)


def test_completed_cannot_complete_again():
    with pytest.raises(ValueError, match="task cannot complete"):
        complete_task("completed", VALID_EVIDENCE)


def test_unknown_status_cannot_complete():
    with pytest.raises(ValueError, match="task cannot complete"):
        complete_task("unknown", VALID_EVIDENCE)
