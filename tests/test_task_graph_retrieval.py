"""Task State Graph integration tests for evidence-aware retrieval."""

from kernel import Evidence, EvidenceState, EvidenceType, Phase, TaskGraphKernelOrchestrator, TaskStatus


def _kernel() -> TaskGraphKernelOrchestrator:
    kernel = TaskGraphKernelOrchestrator("change-retrieval", "test-project")
    kernel.add_task("task", "retrieve evidence", Phase.APPLY.value)
    assert kernel.start_task("task") is True
    return kernel


def _evidence() -> Evidence:
    return Evidence(
        type=EvidenceType.COMMAND,
        claim="retrieval passed",
        command="true",
        exit_code=0,
        stdout="ok",
    )


def test_task_retrieval_retries_and_completes_graph_node():
    kernel = _kernel()
    calls = []

    def retrieve(attempt):
        calls.append(attempt)
        return () if attempt == 1 else (_evidence(),)

    decision = kernel.retrieve_task_evidence("task", retrieve, max_attempts=2)

    assert calls == [1, 2]
    assert decision.assessment.state is EvidenceState.SUFFICIENT
    assert len(decision.attempts) == 2
    assert kernel.task_graph.nodes["task"].status is TaskStatus.COMPLETED
    assert kernel.task_graph.nodes["task"].evidence_refs


def test_task_retrieval_keeps_no_evidence_terminal_after_budget():
    kernel = _kernel()
    calls = []

    def retrieve(attempt):
        calls.append(attempt)
        return ()

    decision = kernel.retrieve_task_evidence("task", retrieve, max_attempts=2)

    assert calls == [1, 2]
    assert decision.assessment.state is EvidenceState.NO_EVIDENCE
    assert decision.exhausted
    assert kernel.task_graph.nodes["task"].status is TaskStatus.IN_PROGRESS


def test_task_retrieval_does_not_retry_low_confidence():
    kernel = _kernel()
    calls = []

    def retrieve(attempt):
        calls.append(attempt)
        return (_evidence(),)

    decision = kernel.retrieve_task_evidence(
        "task", retrieve, max_attempts=3, minimum_confidence=1.1
    )

    assert calls == [1]
    assert decision.assessment.state is EvidenceState.LOW_CONFIDENCE
    assert not decision.should_retrieve
    assert kernel.task_graph.nodes["task"].status is TaskStatus.IN_PROGRESS
