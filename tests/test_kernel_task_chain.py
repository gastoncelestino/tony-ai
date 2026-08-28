from kernel.state import KernelState
from kernel.task_set import TaskSet


def task(task_id, dependencies=()):
    return {
        "id": task_id,
        "description": task_id,
        "phase": "explore",
        "dependencies": tuple(dependencies),
    }


def test_kernel_executes_a_linear_task_chain():
    tasks = TaskSet((task("A"), task("B", ("A",)), task("C", ("B",))))
    state = KernelState("explore", "pending")

    state = state.select_next_task(tasks)
    assert state.get_next_task()["id"] == "A"
    state = state.start_task()
    state, tasks = state.complete_current_task(tasks, {"task": "A"})

    state = state.select_next_task(tasks)
    assert state.get_next_task()["id"] == "B"
    state = state.start_task()
    state, tasks = state.complete_current_task(tasks, {"task": "B"})

    state = state.select_next_task(tasks)
    assert state.get_next_task()["id"] == "C"
    state = state.start_task()
    state, tasks = state.complete_current_task(tasks, {"task": "C"})

    assert tasks.completed == ("A", "B", "C")
    assert tasks.ready_tasks() == ()
    assert state.current_status == "completed"


def test_kernel_does_not_select_blocked_successor():
    tasks = TaskSet((task("A"), task("B", ("A",)), task("C", ("B",))))
    state = KernelState("explore", "pending")

    state = state.select_next_task(tasks)
    assert state.get_next_task()["id"] == "A"

    blocked = tasks.ready_tasks()
    assert tuple(t["id"] for t in blocked) == ("A",)


def test_kernel_chain_preserves_task_set_immutability():
    original = TaskSet((task("A"), task("B", ("A",))))
    state = KernelState("explore", "pending").select_next_task(original).start_task()
    new_state, new_tasks = state.complete_current_task(original, {"ok": True})

    assert original.completed == ()
    assert new_tasks.completed == ("A",)
    assert state.current_status == "running"
    assert new_state.current_status == "completed"
