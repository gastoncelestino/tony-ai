from kernel.state import KernelState
from kernel.task_set import TaskSet


def task(task_id, phase="explore", dependencies=()):
    return {
        "id": task_id,
        "description": task_id,
        "phase": phase,
        "dependencies": tuple(dependencies),
    }


def test_select_next_task_places_ready_task_in_next_task():
    task_set = TaskSet((task("A"), task("B", dependencies=("A",))))
    state = KernelState("explore", "pending")

    new_state = state.select_next_task(task_set)

    assert new_state.get_next_task() == task("A")


def test_select_next_task_filters_by_current_phase():
    task_set = TaskSet((task("A", "apply"), task("B", "explore")))
    state = KernelState("explore", "pending")

    new_state = state.select_next_task(task_set)

    assert new_state.get_next_task() == task("B")


def test_select_next_task_returns_empty_selection_when_phase_has_no_ready_task():
    task_set = TaskSet((task("A", "apply"),))
    state = KernelState("explore", "pending", task("old"))

    new_state = state.select_next_task(task_set)

    assert new_state.get_next_task() is None
    assert state.get_next_task() == task("old")


def test_select_next_task_does_not_mutate_original_state():
    task_set = TaskSet((task("A"),))
    state = KernelState("explore", "pending")

    new_state = state.select_next_task(task_set)
    selected = new_state.get_next_task()
    selected["description"] = "changed"

    assert state.get_next_task() is None
    assert new_state.get_next_task()["description"] == "A"


def test_selected_task_can_continue_through_kernel_lifecycle():
    task_set = TaskSet((task("A"),))
    state = KernelState("explore", "pending")

    selected = state.select_next_task(task_set)
    running = selected.start_task()
    completed = running.complete_task({"result": "ok"})

    assert selected.current_status == "pending"
    assert running.current_status == "running"
    assert completed.current_status == "completed"
    assert completed.get_next_task() == task("A")
