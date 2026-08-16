"""Integration tests for bounded retrieval through the Kernel orchestrator."""
from kernel import Evidence, EvidenceType, EvidenceState, Phase, TaskGraphKernelOrchestrator, TaskStatus


def _evidence(exit_code=0):
    return Evidence(
        type=EvidenceType.COMMAND,
        claim="retrieval result",
        command="true",
        exit_code=exit_code,
        stdout="ok" if exit_code == 0 else "failed",
    )


def _kernel():
    kernel = TaskGraphKernelOrchestrator("retrieval-change", "test-project")
    kernel.add_task("task", "retrieve evidence", Phase.APPLY.value)
    assert kernel.start_task("task")
    return kernel


def test_orchestrator_retrieves_again_after_no_evidence():
    kernel = _kernel()
    calls = []

    def retrieve(attempt):
        calls.append(attempt)
        return () if attempt == 1 else (_evidence(),)

    decision = kernel.retrieve_task_evidence("task", retrieve, max_attempts=2)
    assert calls == [1, 2]
    assert decision.assessment.state is EvidenceState.SUFFICIENT
    assert kernel.get_task_graph().get("task").status is TaskStatus.COMPLETED
    assert kernel.task_ledger.tasks["task"].evidence


def test_orchestrator_leaves_low_confidence_for_judgment():
    kernel = _kernel()
    decision = kernel.retrieve_task_evidence(
        "task",
        lambda attempt: (_evidence(),),
        max_attempts=2,
        minimum_confidence=1.1,
    )
    assert decision.assessment.state is EvidenceState.LOW_CONFIDENCE
    assert decision.assessment.needs_judgment
    assert kernel.get_task_graph().get("task").status is TaskStatus.IN_PROGRESS


def test_orchestrator_exhausts_retrieval_without_completing():
    kernel = _kernel()
    decision = kernel.retrieve_task_evidence("task", lambda attempt: (), max_attempts=2)
    assert decision.exhausted
    assert decision.assessment.state is EvidenceState.NO_EVIDENCE
    assert kernel.get_task_graph().get("task").status is TaskStatus.IN_PROGRESS
