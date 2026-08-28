import pytest

from kernel.task_selection import select_ready_task
from kernel.task_set import TaskSet


def task(task_id, phase="explore", dependencies=()):
    return {
        "id": task_id,
        "description": task_id,
        "phase": phase,
        "dependencies": tuple(dependencies),
    }


def test_selects_only_ready_task_in_current_phase():
    state = TaskSet((task("A", "explore"), task("B", "apply", ("A",))))
    assert select_ready_task(state, "explore")["id"] == "A"


def test_returns_none_when_no_ready_task_exists_in_current_phase():
    state = TaskSet((task("A", "apply"),))
    assert select_ready_task(state, "explore") is None


def test_returns_first_ready_task_in_declared_order():
    state = TaskSet((task("A"), task("B"), task("C", "apply")))
    assert select_ready_task(state, "explore")["id"] == "A"


def test_blocked_task_is_never_selected():
    state = TaskSet((task("A", "explore"), task("B", "explore", ("A",))))
    state = state.complete("A")
    assert select_ready_task(state, "explore")["id"] == "B"


def test_completed_task_is_never_selected():
    state = TaskSet((task("A"), task("B")))
    state = state.complete("A")
    assert select_ready_task(state, "explore")["id"] == "B"


def test_selection_does_not_mutate_task_set():
    state = TaskSet((task("A"),))
    selected = select_ready_task(state, "explore")
    selected["description"] = "changed"
    assert state.get("A")["description"] == "A"


def test_selection_is_deterministic():
    state = TaskSet((task("B"), task("A")))
    assert select_ready_task(state, "explore")["id"] == "B"


def test_selection_requires_task_set():
    with pytest.raises(AttributeError):
        select_ready_task(None, "explore")
