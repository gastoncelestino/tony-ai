import unittest

from kernel.orchestrator_integration import KernelOrchestrator, OrchestrationDecision
from kernel.schemas import Phase, TaskStatus
from kernel.task_graph_persistence import mutate_with_task_graph


class TaskGraphPersistenceTests(unittest.TestCase):
    def test_complete_task_mutates_authoritative_graph_and_ledger(self):
        orchestrator = KernelOrchestrator("change", "project")
        orchestrator.add_task("task", "complete me", Phase.APPLY)
        self.assertTrue(orchestrator.start_task("task"))

        evidence = {
            "type": "command",
            "claim": "command succeeded",
            "command": "echo ok",
            "exit_code": 0,
        }
        result = mutate_with_task_graph(
            orchestrator,
            lambda graph: graph.complete_task("task", [evidence]),
        )

        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)
        self.assertEqual(orchestrator.task_ledger.tasks["task"].status, TaskStatus.COMPLETED)

    def test_failed_evidence_does_not_complete_task(self):
        orchestrator = KernelOrchestrator("change", "project")
        orchestrator.add_task("task", "complete me", Phase.APPLY)
        self.assertTrue(orchestrator.start_task("task"))

        evidence = {
            "type": "command",
            "claim": "command failed",
            "command": "false",
            "exit_code": 1,
        }
        result = mutate_with_task_graph(
            orchestrator,
            lambda graph: graph.complete_task("task", [evidence]),
        )

        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED)
        self.assertEqual(orchestrator.task_ledger.tasks["task"].status, TaskStatus.IN_PROGRESS)


if __name__ == "__main__":
    unittest.main()
