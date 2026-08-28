import pytest

from kernel.task_set import TaskSet


def task(task_id, dependencies=()):
    return {"id": task_id, "description": task_id, "phase": "explore", "dependencies": tuple(dependencies)}


def test_tasks_without_dependencies_are_ready():
    state = TaskSet((task("A"), task("B", ("A",))))
    assert [item["id"] for item in state.ready_tasks()] == ["A"]


def test_multiple_dependencies_require_all_to_be_completed():
    state = TaskSet((task("A"), task("B"), task("C", ("A", "B"))))
    assert [item["id"] for item in state.complete("A").ready_tasks()] == ["B"]
    state = state.complete("A").complete("B")
    assert [item["id"] for item in state.ready_tasks()] == ["C"]


def test_completing_dependency_enables_dependent_task():
    state = TaskSet((task("A"), task("B", ("A",))))
    next_state = state.complete("A")
    assert [item["id"] for item in next_state.ready_tasks()] == ["B"]
    assert state.completed == ()


def test_unrelated_completed_task_does_not_satisfy_dependency():
    state = TaskSet((task("A"), task("B", ("A",)), task("C")))
    state = state.complete("C")
    assert [item["id"] for item in state.ready_tasks()] == ["A"]


def test_unknown_dependency_is_rejected():
    with pytest.raises(ValueError, match="Unknown task dependency"):
        TaskSet((task("A", ("missing",)),))


def test_duplicate_task_ids_are_rejected():
    with pytest.raises(ValueError, match="Task IDs must be unique"):
        TaskSet((task("A"), task("A")))


def test_cycles_are_rejected():
    with pytest.raises(ValueError, match="acyclic"):
        TaskSet((task("A", ("B",)), task("B", ("A",))))


def test_self_dependency_is_rejected():
    with pytest.raises(ValueError, match="cannot depend on itself"):
        TaskSet((task("A", ("A",)),))


def test_complete_requires_ready_task():
    state = TaskSet((task("A"), task("B", ("A",))))
    with pytest.raises(ValueError, match="dependencies are not satisfied"):
        state.complete("B")


def test_ready_tasks_are_detached_from_internal_storage():
    state = TaskSet((task("A"),))
    ready = state.ready_tasks()
    ready[0]["description"] = "changed"
    assert state.get("A")["description"] == "A"


def test_complete_returns_immutable_new_state():
    state = TaskSet((task("A"),))
    next_state = state.complete("A")
    assert state.completed == ()
    assert next_state.completed == ("A",)
    with pytest.raises(Exception):
        next_state.completed = ()
