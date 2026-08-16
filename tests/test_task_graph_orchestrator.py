"""Integration tests for the incremental Task State Graph orchestration layer."""

from datetime import datetime

import pytest

from kernel import (
    Evidence,
    EvidenceType,
    OrchestrationDecision,
    Phase,
    TaskGraphError,
    TaskGraphKernelOrchestrator,
    TaskNode,
    TaskStateGraph,
    TaskStatus,
)


def _kernel() -> TaskGraphKernelOrchestrator:
    return TaskGraphKernelOrchestrator("change-graph", "test-project")


def _evidence() -> Evidence:
    return Evidence(
        type=EvidenceType.COMMAND,
        claim="task command passed",
        command="true",
        exit_code=0,
        stdout="ok",
    )


def test_start_task_is_gated_by_graph_dependencies():
    kernel = _kernel()
    kernel.add_task("parent", "parent", Phase.APPLY.value)
    kernel.add_task("child", "child", Phase.APPLY.value, dependencies=("parent",))

    assert kernel.start_task("child") is False
    assert kernel.task_graph.nodes["child"].status == TaskStatus.PENDING

    assert kernel.start_task("parent") is True
    completed = kernel.complete_task("parent", [_evidence()])
    assert completed.decision == OrchestrationDecision.PROCEED

    assert kernel.start_task("child") is True
    assert kernel.task_graph.nodes["child"].status == TaskStatus.IN_PROGRESS


def test_complete_task_requires_graph_in_progress_state():
    kernel = _kernel()
    kernel.add_task("task", "task", Phase.APPLY.value)

    result = kernel.complete_task("task", [_evidence()])

    assert result.decision == OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED
    assert "not in progress" in result.reason


def test_completed_task_has_graph_evidence_refs():
    kernel = _kernel()
    kernel.add_task("task", "task", Phase.APPLY.value)
    assert kernel.start_task("task") is True

    result = kernel.complete_task("task", [_evidence()])

    assert result.decision == OrchestrationDecision.PROCEED
    node = kernel.get_task_graph().nodes["task"]
    assert node.status == TaskStatus.COMPLETED
    assert node.evidence_refs
    assert node.attempts[-1].status == "completed"


def test_graph_rejects_unknown_dependency_during_task_addition():
    kernel = _kernel()

    try:
        kernel.add_task("task", "task", Phase.APPLY.value, dependencies=("missing",))
    except ValueError:
        pass
    else:
        raise AssertionError("unknown task dependency must be rejected")


def _graph() -> TaskStateGraph:
    return TaskStateGraph().add(
        TaskNode(task_id="task", description="task", phase=Phase.APPLY)
    )


def test_failed_task_can_retry_without_losing_attempt_history():
    now = datetime(2026, 1, 1)
    graph = _graph().start("task", now=now)
    graph = graph.fail("task", "command failed", now=datetime(2026, 1, 1, 0, 1))

    assert graph.nodes["task"].status == TaskStatus.FAILED
    assert graph.nodes["task"].attempt_count == 1
    assert graph.nodes["task"].attempts[0].status == "failed"
    assert graph.nodes["task"].attempts[0].error == "command failed"

    graph = graph.retry("task")
    assert graph.nodes["task"].status == TaskStatus.PENDING
    graph = graph.start("task", now=datetime(2026, 1, 1, 0, 2))

    assert graph.nodes["task"].status == TaskStatus.IN_PROGRESS
    assert graph.nodes["task"].attempt_count == 2
    assert graph.nodes["task"].attempts[0].status == "failed"
    assert graph.nodes["task"].attempts[1].status == "running"


def test_rollback_is_terminal_for_failed_task():
    graph = _graph().start("task")
    graph = graph.fail("task", "irrecoverable", rollback={"action": "restore"})
    graph = graph.rollback_task("task")

    node = graph.nodes["task"]
    assert node.status == TaskStatus.BLOCKED
    assert node.rollback == {"action": "restore"}
    assert node.attempt_count == 1

    with pytest.raises(TaskGraphError):
        graph.retry("task")


def test_invalid_transitions_are_rejected_deterministically():
    graph = _graph()

    with pytest.raises(TaskGraphError):
        graph.complete("task", ("evidence:1",))
    with pytest.raises(TaskGraphError):
        graph.fail("task", "not started")
    with pytest.raises(TaskGraphError):
        graph.retry("task")
    with pytest.raises(TaskGraphError):
        graph.rollback_task("task")
