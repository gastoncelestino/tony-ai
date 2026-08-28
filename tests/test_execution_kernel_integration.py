from kernel.execution_order import resolve_execution
from kernel.state import KernelState
from kernel.task_set import TaskSet


VALID_EVIDENCE = [{"kind": "test", "value": "102 passed"}]


def task(task_id):
    return {
        "id": task_id,
        "description": task_id,
        "phase": "explore",
        "dependencies": (),
    }


def test_authorized_execution_result_can_complete_selected_task():
    tasks = TaskSet((task("A"),))
    state = KernelState("explore", "pending").select_next_task(tasks).start_task()

    result = resolve_execution(state)
    assert result["allowed"] is True
    assert result["execution_order"]["task_id"] == "A"

    evidence = VALID_EVIDENCE
    completed_state, completed_tasks = state.complete_current_task(tasks, evidence)

    assert completed_state.current_status == "completed"
    assert completed_tasks.completed == ("A",)


def test_blocked_execution_does_not_complete_task():
    tasks = TaskSet((task("A"),))
    state = KernelState("explore", "pending").select_next_task(tasks)

    result = resolve_execution(state)
    assert result["allowed"] is False
    assert result["decision"] == "blocked"
    assert state.current_status == "pending"
    assert tasks.completed == ()
