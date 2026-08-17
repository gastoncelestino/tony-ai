"""Tests for the existing Kernel task dependency behavior.

These tests intentionally cover the smallest Task State Graph capability:
A task cannot start until every declared dependency is completed.
"""
from __future__ import annotations

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from kernel.orchestrator_integration import create_kernel_orchestrator
from kernel.schemas import Evidence, EvidenceType


class TestTaskDependencies(unittest.TestCase):
    def test_dependent_task_cannot_start_before_dependency(self):
        orch = create_kernel_orchestrator("task-deps", "test-project")
        orch.add_task("implementation", "Implement change", "apply")
        orch.add_task("tests", "Run tests", "verify", dependencies=("implementation",))

        self.assertTrue(orch.start_task("implementation"))
        self.assertFalse(orch.start_task("tests"))
        self.assertEqual(orch.task_ledger.tasks["tests"].status.value, "pending")

    def test_dependent_task_starts_after_dependency_is_completed(self):
        orch = create_kernel_orchestrator("task-deps", "test-project")
        orch.add_task("implementation", "Implement change", "apply")
        orch.add_task("tests", "Run tests", "verify", dependencies=("implementation",))

        self.assertTrue(orch.start_task("implementation"))
        evidence = Evidence(
            type=EvidenceType.COMMAND,
            claim="Implementation completed",
            command="test-command",
            exit_code=0,
            stdout="ok",
        )
        result = orch.complete_task("implementation", [evidence])
        self.assertEqual(result.decision.value, "proceed")

        self.assertTrue(orch.start_task("tests"))
        self.assertEqual(orch.task_ledger.tasks["tests"].status.value, "in_progress")

    def test_next_task_returns_only_ready_task(self):
        orch = create_kernel_orchestrator("task-deps", "test-project")
        orch.add_task("implementation", "Implement change", "apply")
        orch.add_task("tests", "Run tests", "verify", dependencies=("implementation",))

        next_task = orch.get_next_task()
        self.assertEqual(next_task["id"], "implementation")

        self.assertTrue(orch.start_task("implementation"))
        self.assertIsNone(orch.get_next_task())


if __name__ == "__main__":
    unittest.main()
