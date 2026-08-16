from datetime import datetime

import pytest

from kernel.schemas import Evidence, EvidenceType, Phase, Task, TaskLedger, TaskStatus
from kernel.task_graph import TaskGraphError
from kernel.task_graph_adapter import ledger_to_graph, task_to_node


def make_task(task_id, status=TaskStatus.PENDING, dependencies=(), metadata=None, evidence=()):
    return Task(
        id=task_id,
        description=task_id,
        phase=Phase.APPLY,
        status=status,
        dependencies=tuple(dependencies),
        evidence=evidence,
        started_at=datetime(2026, 1, 1) if status != TaskStatus.PENDING else None,
        completed_at=datetime(2026, 1, 2) if status in (TaskStatus.COMPLETED, TaskStatus.FAILED) else None,
        metadata=metadata or {},
    )


def test_legacy_ledger_becomes_graph_with_dependencies_and_status():
    ledger = TaskLedger(tasks={
        "a": make_task("a", TaskStatus.COMPLETED, metadata={"evidence_refs": ("test:a",)}),
        "b": make_task("b", TaskStatus.PENDING, dependencies=("a",)),
    })

    graph = ledger_to_graph(ledger)

    assert graph.get("a").status == TaskStatus.COMPLETED
    assert graph.get("a").evidence_refs == ("test:a",)
    assert [task.task_id for task in graph.ready()] == ["b"]


def test_legacy_evidence_gets_stable_reference():
    evidence = Evidence(type=EvidenceType.TEST, claim="tests pass", exit_code=0)
    node = task_to_node(make_task("a", TaskStatus.COMPLETED, evidence=(evidence,)))

    assert len(node.evidence_refs) == 1
    assert node.evidence_refs[0].startswith("evidence:")
    assert node.evidence_refs == task_to_node(make_task("a", TaskStatus.COMPLETED, evidence=(evidence,))).evidence_refs


def test_ledger_graph_rejects_invalid_dependency_structure():
    ledger = TaskLedger(tasks={
        "a": make_task("a", dependencies=("missing",)),
    })

    with pytest.raises(TaskGraphError, match="Unknown dependency"):
        ledger_to_graph(ledger)


def test_metadata_preserves_parent_result_rollback_and_error():
    node = task_to_node(make_task(
        "a",
        TaskStatus.FAILED,
        metadata={
            "parent": "root",
            "result": {"changed": 1},
            "rollback": {"command": "git restore"},
            "error": "boom",
        },
    ))

    assert node.parent == "root"
    assert node.result == {"changed": 1}
    assert node.rollback == {"command": "git restore"}
    assert node.attempts[0].error == "boom"
