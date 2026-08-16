"""Integration tests for retrieval-driven task completion."""

from kernel import Evidence, EvidenceState, EvidenceType, Phase, TaskGraphKernelOrchestrator, TaskStatus


def _evidence(exit_code=0):
    return Evidence(
        type=EvidenceType.COMMAND,
        claim="retrieved command evidence",
        command="true",
        exit_code=exit_code,
        stdout="ok" if exit_code == 0 else "failed",
    )


def _kernel():
    kernel = TaskGraphKernelOrchestrator("retrieval-change", "test-project")
    kernel.add_task("task", "retrieve evidence", Phase.APPLY)
    assert kernel.start_task("task")
    return kernel


def test_retrieval_completes_task_after_second_attempt():
    kernel = _kernel()
    calls = []
    retrieved = _evidence()

    def retriever(attempt):
        calls.append(attempt)
        return () if attempt == 1 else (retrieved,)

    decision = kernel.retrieve_task_evidence("task", retriever, max_attempts=2)

    assert calls == [1, 2]
    assert decision.assessment.state is EvidenceState.SUFFICIENT
    assert kernel.task_graph.get("task").status is TaskStatus.COMPLETED
    assert kernel.task_graph.get("task").evidence_refs
    assert kernel.task_ledger.tasks["task"].evidence == (retrieved,)


def test_retrieval_exhaustion_does_not_complete_task():
    kernel = _kernel()
    decision = kernel.retrieve_task_evidence("task", lambda _: (), max_attempts=2)

    assert decision.exhausted
    assert decision.assessment.state is EvidenceState.NO_EVIDENCE
    assert kernel.task_graph.get("task").status is TaskStatus.IN_PROGRESS


def test_low_confidence_is_returned_for_judgment_without_retry():
    kernel = _kernel()
    decision = kernel.retrieve_task_evidence(
        "task",
        lambda _: (_evidence(),),
        max_attempts=3,
        minimum_confidence=1.1,
    )

    assert decision.assessment.state is EvidenceState.LOW_CONFIDENCE
    assert len(decision.attempts) == 1
    assert kernel.task_graph.get("task").status is TaskStatus.IN_PROGRESS
