from kernel.state import KernelState


def test_state_preserves_phase_and_status():
    state = KernelState("explore", "running", None)

    assert state.current_phase == "explore"
    assert state.current_status == "running"


def test_state_returns_none_when_no_next_task_exists():
    state = KernelState("explore", "running", None)

    assert state.get_next_task() is None


def test_state_returns_next_task():
    task = {"id": "explore-1", "description": "Inspect", "phase": "explore"}
    state = KernelState("explore", "running", task)

    assert state.get_next_task() == task


def test_state_does_not_expose_mutable_task_storage():
    task = {"id": "explore-1", "files": ["kernel/"]}
    state = KernelState("explore", "running", task)

    returned = state.get_next_task()
    returned["files"].append("plugins/")

    assert state.get_next_task() == task


def test_state_object_is_immutable():
    state = KernelState("explore", "running", None)

    try:
        state.current_phase = "apply"
    except Exception:
        pass
    else:
        raise AssertionError("KernelState must be immutable")
