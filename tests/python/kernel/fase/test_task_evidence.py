"""Tests for task completion evidence enforcement."""
from __future__ import annotations

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from kernel.orchestrator_integration import create_kernel_orchestrator
from kernel.schemas import Evidence, EvidenceType


class TestTaskEvidence(unittest.TestCase):
    def _orchestrator(self):
        orch = create_kernel_orchestrator("task-evidence", "test-project")
        orch.add_task("implementation", "Implement change", "apply")
        self.assertTrue(orch.start_task("implementation"))
        return orch

    def test_task_cannot_complete_without_evidence(self):
        orch = self._orchestrator()

        result = orch.complete_task("implementation", [])

        self.assertEqual(result.decision.value, "block_evidence_required")
        self.assertEqual(
            orch.task_ledger.tasks["implementation"].status.value,
            "in_progress",
        )

    def test_task_cannot_complete_with_invalid_evidence(self):
        orch = self._orchestrator()
        evidence = Evidence(
            type=EvidenceType.COMMAND,
            claim="Command failed",
            command="test-command",
            exit_code=1,
            stdout="",
        )

        result = orch.complete_task("implementation", [evidence])

        self.assertEqual(result.decision.value, "block_evidence_required")
        self.assertEqual(
            orch.task_ledger.tasks["implementation"].status.value,
            "in_progress",
        )

    def test_task_completes_with_valid_evidence(self):
        orch = self._orchestrator()
        evidence = Evidence(
            type=EvidenceType.COMMAND,
            claim="Implementation completed",
            command="test-command",
            exit_code=0,
            stdout="ok",
        )

        result = orch.complete_task("implementation", [evidence])

        self.assertEqual(result.decision.value, "proceed")
        self.assertEqual(
            orch.task_ledger.tasks["implementation"].status.value,
            "completed",
        )

    def test_command_evidence_requires_successful_exit_code(self):
        valid = Evidence(
            type=EvidenceType.COMMAND,
            claim="Command succeeded",
            command="test-command",
            exit_code=0,
        )
        invalid = Evidence(
            type=EvidenceType.COMMAND,
            claim="Command failed",
            command="test-command",
            exit_code=1,
        )

        self.assertEqual(valid.validate().value, "valid")
        self.assertEqual(invalid.validate().value, "invalid")


if __name__ == "__main__":
    unittest.main()
