import pytest

from kernel.state import KernelState
from kernel.task_set import TaskSet


def task(task_id, phase="explore", dependencies=()):
    return {
        "id": task_id,
        "description": task_id,
        "phase": phase,
        "dependencies": tuple(dependencies),
    }


def test_complete_current_task_updates_task_set_and_state():
    tasks = TaskSet((task("A"), task("B", dependencies=("A",))))
    state = KernelState("explore", "running", task("A"))

    new_state, new_tasks = state.complete_current_task(tasks, {"result": "ok"})

    assert new_state.current_status == "completed"
    assert new_state.get_next_task() == task("A")
    assert new_tasks.completed == ("A",)
    assert new_tasks.ready_tasks() == (task("B", dependencies=("A",)),)
    assert tasks.completed == ()


def test_complete_current_task_rejects_missing_selected_task():
    tasks = TaskSet((task("A"),))
    state = KernelState("explore", "running", None)

    with pytest.raises(ValueError):
        state.complete_current_task(tasks, {"result": "ok"})


def test_complete_current_task_rejects_task_not_in_set():
    tasks = TaskSet((task("A"),))
    state = KernelState("explore", "running", task("B"))

    with pytest.raises(ValueError):
        state.complete_current_task(tasks, {"result": "ok"})


def test_complete_current_task_requires_running_state():
    tasks = TaskSet((task("A"),))
    state = KernelState("explore", "pending", task("A"))

    with pytest.raises(ValueError):
        state.complete_current_task(tasks, {"result": "ok"})


def test_complete_current_task_does_not_mutate_original_state():
    tasks = TaskSet((task("A"), task("B", dependencies=("A",))))
    state = KernelState("explore", "running", task("A"))

    new_state, new_tasks = state.complete_current_task(tasks, {"result": "ok"})

    assert state.current_status == "running"
    assert state.get_next_task() == task("A")
    assert new_state.current_status == "completed"
    assert new_tasks.completed == ("A",)
