"""Integration tests for the incremental Task State Graph orchestration layer."""

from kernel import (
    Evidence,
    EvidenceType,
    OrchestrationDecision,
    Phase,
    TaskGraphKernelOrchestrator,
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


def test_graph_rejects_dependency_cycle_during_task_addition():
    kernel = _kernel()
    kernel.add_task("a", "a", Phase.APPLY.value, dependencies=("b",))

    try:
        kernel.add_task("b", "b", Phase.APPLY.value, dependencies=("a",))
    except ValueError:
        pass
    else:
        raise AssertionError("cyclic task graph must be rejected")
