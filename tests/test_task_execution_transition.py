import pytest

from kernel.task_execution_transition import start_task


def test_pending_transitions_to_running():
    assert start_task("pending") == "running"


def test_running_cannot_start_again():
    with pytest.raises(ValueError):
        start_task("running")


def test_completed_cannot_start():
    with pytest.raises(ValueError):
        start_task("completed")


def test_unknown_status_cannot_start():
    with pytest.raises(ValueError):
        start_task("unknown")
