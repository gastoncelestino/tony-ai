from kernel import Evidence, EvidenceState, EvidenceType, Phase, TaskGraphKernelOrchestrator, TaskStatus
from kernel.retrieval_decision import RetrievalAction


def _kernel():
    kernel = TaskGraphKernelOrchestrator("change-retrieval", "test-project")
    kernel.add_task("task", "retrieve evidence", Phase.APPLY.value)
    assert kernel.start_task("task") is True
    return kernel


def _evidence():
    return Evidence(
        type=EvidenceType.COMMAND,
        claim="retrieval result",
        command="true",
        exit_code=0,
        stdout="ok",
    )


def test_retrieval_arbitration_exposes_transition():
    kernel = _kernel()
    decision = kernel.arbitrate_retrieval(
        kernel.assess_task_evidence("task", [_evidence()])
    )
    assert decision.action is RetrievalAction.TRANSITION


def test_retrieval_task_completes_only_after_sufficient_evidence():
    kernel = _kernel()
    calls = []

    def retrieve(attempt):
        calls.append(attempt)
        return () if attempt == 1 else (_evidence(),)

    result = kernel.retrieve_task_evidence("task", retrieve, max_attempts=2)

    assert calls == [1, 2]
    assert result.assessment.state is EvidenceState.SUFFICIENT
    assert kernel.task_graph.nodes["task"].status is TaskStatus.COMPLETED


def test_low_confidence_never_completes_task():
    kernel = _kernel()

    def retrieve(_attempt):
        return (_evidence(),)

    result = kernel.retrieve_task_evidence(
        "task", retrieve, max_attempts=3, minimum_confidence=1.1
    )

    assert result.assessment.state is EvidenceState.LOW_CONFIDENCE
    assert kernel.task_graph.nodes["task"].status is TaskStatus.IN_PROGRESS
