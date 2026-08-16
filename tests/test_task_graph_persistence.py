from kernel.orchestrator_integration import KernelOrchestrator
from kernel.schemas import Evidence, EvidenceType, Phase, TaskStatus
from kernel.task_graph_persistence import mutate_with_task_graph


def test_mutation_uses_graph_and_projects_back_to_ledger():
    orchestrator = KernelOrchestrator("change", "project")
    orchestrator.add_task("task-1", "run command", Phase.APPLY)
    assert orchestrator.start_task("task-1")

    evidence = Evidence(
        type=EvidenceType.COMMAND,
        claim="command succeeded",
        command="echo ok",
        exit_code=0,
        stdout="ok\n",
    )

    result = mutate_with_task_graph(
        orchestrator,
        lambda graph: graph.complete_task("task-1", [evidence]),
    )

    assert result.decision.value == "proceed"
    assert orchestrator.task_ledger.tasks["task-1"].status is TaskStatus.COMPLETED
    assert orchestrator.task_ledger.tasks["task-1"].metadata["evidence_refs"]
    assert orchestrator.task_ledger.tasks["task-1"].metadata["graph_attempts"]


def test_failed_evidence_does_not_complete_graph_task():
    orchestrator = KernelOrchestrator("change", "project")
    orchestrator.add_task("task-1", "run command", Phase.APPLY)
    assert orchestrator.start_task("task-1")

    evidence = Evidence(
        type=EvidenceType.COMMAND,
        claim="command failed",
        command="false",
        exit_code=1,
        stderr="failed",
    )

    result = mutate_with_task_graph(
        orchestrator,
        lambda graph: graph.complete_task("task-1", [evidence]),
    )

    assert result.decision.value == "block_evidence_required"
    assert orchestrator.task_ledger.tasks["task-1"].status is TaskStatus.IN_PROGRESS
