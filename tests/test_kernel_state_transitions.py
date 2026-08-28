import pytest

from kernel.state import KernelState


def test_start_task_returns_new_state_with_running_status():
    task = {"id": "explore-1", "description": "Inspect", "phase": "explore"}
    state = KernelState("explore", "pending", task)

    new_state = state.start_task()

    assert new_state.current_phase == "explore"
    assert new_state.current_status == "running"
    assert new_state.get_next_task() == task


def test_start_task_does_not_mutate_original_state():
    state = KernelState("explore", "pending", {"id": "explore-1"})

    new_state = state.start_task()

    assert state.current_status == "pending"
    assert new_state.current_status == "running"


def test_complete_task_returns_new_state_with_completed_status():
    task = {"id": "explore-1", "description": "Inspect", "phase": "explore"}
    state = KernelState("explore", "running", task)

    new_state = state.complete_task({"result": "ok"})

    assert new_state.current_phase == "explore"
    assert new_state.current_status == "completed"
    assert new_state.get_next_task() == task


def test_complete_task_does_not_mutate_original_state():
    state = KernelState("explore", "running", {"id": "explore-1"})

    new_state = state.complete_task({"result": "ok"})

    assert state.current_status == "running"
    assert new_state.current_status == "completed"


@pytest.mark.parametrize("status", ["running", "completed"])
def test_start_task_rejects_invalid_status(status):
    state = KernelState("explore", status, {"id": "explore-1"})

    with pytest.raises(ValueError):
        state.start_task()


@pytest.mark.parametrize("status", ["pending", "completed", "unknown"])
def test_complete_task_rejects_invalid_status(status):
    state = KernelState("explore", status, {"id": "explore-1"})

    with pytest.raises(ValueError):
        state.complete_task({"result": "ok"})


def test_complete_task_rejects_invalid_evidence():
    state = KernelState("explore", "running", {"id": "explore-1"})

    with pytest.raises(ValueError):
        state.complete_task(None)
