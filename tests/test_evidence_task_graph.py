"""Integration tests for evidence-aware task completion."""
from datetime import datetime

from kernel.evidence_state import EvidenceState, assess_evidence
from kernel.task_graph import TaskNode, TaskStateGraph
from kernel.schemas import Evidence, EvidenceType, Phase, TaskStatus
from kernel.task_graph_orchestrator import TaskGraphKernelOrchestrator


def _evidence(claim="tests pass"):
    return Evidence(
        type=EvidenceType.TEST,
        claim=claim,
        command="pytest",
        exit_code=0,
        stdout="1 passed",
        timestamp=datetime.now(),
    )


def test_no_evidence_requires_retrieval():
    assessment = assess_evidence(())
    assert assessment.state is EvidenceState.NO_EVIDENCE
    assert assessment.needs_retrieval
    assert not assessment.can_progress


def test_valid_evidence_is_sufficient():
    assessment = assess_evidence((_evidence(),))
    assert assessment.state is EvidenceState.SUFFICIENT
    assert assessment.can_progress
    assert not assessment.needs_retrieval


def test_low_confidence_is_distinct_from_no_evidence():
    assessment = assess_evidence((_evidence(),), confidence=0.25)
    assert assessment.state is EvidenceState.LOW_CONFIDENCE
    assert not assessment.needs_retrieval
    assert assessment.needs_judgment


def test_contradictory_evidence_requires_judgment():
    first = _evidence("claim")
    second = Evidence(
        type=EvidenceType.TEST,
        claim="claim",
        command="pytest",
        exit_code=1,
        stdout="failed",
        timestamp=datetime.now(),
    )
    assessment = assess_evidence((first, second))
    assert assessment.state is EvidenceState.CONTRADICTORY
    assert assessment.needs_judgment
    assert not assessment.can_progress


def test_task_graph_completion_keeps_evidence_refs():
    graph = TaskStateGraph().add(
        TaskNode(task_id="t1", description="test", phase=Phase.APPLY)
    )
    graph = graph.start("t1")
    graph = graph.complete("t1", ("evidence:test:1",))
    node = graph.get("t1")
    assert node.status is TaskStatus.COMPLETED
    assert node.evidence_refs == ("evidence:test:1",)


def test_orchestrator_blocks_completion_without_evidence():
    orchestrator = TaskGraphKernelOrchestrator(
        change_id="change-1",
        project="test",
    )
    orchestrator.add_task("t1", "test", Phase.APPLY.value)
    assert orchestrator.start_task("t1")
    result = orchestrator.complete_task("t1", [])
    assert result.decision.value == "block_evidence_required"
    assert orchestrator.task_graph.get("t1").status is TaskStatus.IN_PROGRESS
