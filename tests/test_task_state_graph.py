from datetime import datetime

import pytest

from kernel.schemas import Phase, TaskStatus
from kernel.task_graph import TaskGraphError, TaskNode, TaskStateGraph


def node(task_id: str, dependencies=(), parent=None):
    return TaskNode(
        task_id=task_id,
        description=task_id,
        phase=Phase.APPLY,
        dependencies=tuple(dependencies),
        parent=parent,
    )


def test_builds_dag_and_returns_ready_nodes():
    graph = TaskStateGraph().add(node("a")).add(node("b", ["a"]))

    assert [n.task_id for n in graph.ready()] == ["a"]


def test_dependency_must_complete_before_start():
    graph = TaskStateGraph().add(node("a")).add(node("b", ["a"]))

    with pytest.raises(TaskGraphError, match="incomplete dependencies"):
        graph.start("b")

    graph = graph.start("a", datetime(2026, 1, 1))
    graph = graph.complete("a", ("evidence:a",), now=datetime(2026, 1, 1))
    assert [n.task_id for n in graph.ready()] == ["b"]


def test_completion_requires_evidence_refs():
    graph = TaskStateGraph().add(node("a")).start("a")

    with pytest.raises(TaskGraphError, match="without evidence_refs"):
        graph.complete("a", ())


def test_attempts_and_failure_are_preserved_for_retry():
    graph = TaskStateGraph().add(node("a")).start("a")
    graph = graph.fail("a", "test failed", rollback={"command": "git restore"})

    task = graph.get("a")
    assert task.status == TaskStatus.FAILED
    assert task.attempt_count == 1
    assert task.attempts[0].status == "failed"
    assert task.attempts[0].error == "test failed"
    assert task.rollback == {"command": "git restore"}

    graph = graph.retry("a").start("a")
    task = graph.get("a")
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.attempt_count == 2


def test_detects_dependency_cycles():
    graph = TaskStateGraph().add(node("a"))
    graph = TaskStateGraph({
        "a": node("a", ["b"]),
        "b": node("b", ["a"]),
    })

    with pytest.raises(TaskGraphError, match="cycle"):
        graph.validate()


def test_rejects_unknown_dependencies_and_parents():
    with pytest.raises(TaskGraphError, match="Unknown dependency"):
        TaskStateGraph().add(node("a", ["missing"]))

    with pytest.raises(TaskGraphError, match="Unknown parent"):
        TaskStateGraph().add(node("a", parent="missing"))


def test_completed_node_records_result_and_evidence():
    graph = TaskStateGraph().add(node("a")).start("a")
    graph = graph.complete("a", ("test:123", "diff:456"), result={"changed": 2})

    task = graph.get("a")
    assert task.status == TaskStatus.COMPLETED
    assert task.evidence_refs == ("test:123", "diff:456")
    assert task.result == {"changed": 2}
    assert task.attempts[-1].evidence_refs == task.evidence_refs
