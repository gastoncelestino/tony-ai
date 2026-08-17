"""Tests for KernelOrchestrator scope enforcement."""
from __future__ import annotations
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from kernel.orchestrator_integration import KernelOrchestrator, OrchestrationDecision


class TestOrchestratorScope(unittest.TestCase):
    def setUp(self):
        self.orch = KernelOrchestrator("scope-test", "test-project")

    def test_empty_diff_proceeds(self):
        result = self.orch.check_scope("", ("src/*.py",))
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)

    def test_allowed_file_proceeds(self):
        diff = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new\n"
        result = self.orch.check_scope(diff, ("src/*.py",))
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)
        self.assertEqual(result.scope_violations, ())

    def test_disallowed_file_blocks(self):
        diff = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new\n"
        result = self.orch.check_scope(diff, ("tests/*.py",))
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_SCOPE_VIOLATION)
        self.assertEqual(result.scope_violations, ("src/main.py",))

    def test_glob_pattern_allows_nested_file(self):
        diff = "--- a/src/kernel/main.py\n+++ b/src/kernel/main.py\n@@ -1 +1 @@\n-old\n+new\n"
        result = self.orch.check_scope(diff, ("src/**/*.py",))
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)

    def test_any_violation_blocks_multiple_files(self):
        diff = (
            "--- a/src/main.py\n+++ b/src/main.py\n"
            "--- a/tests/test_main.py\n+++ b/tests/test_main.py\n"
        )
        result = self.orch.check_scope(diff, ("src/*.py",))
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_SCOPE_VIOLATION)
        self.assertEqual(result.scope_violations, ("tests/test_main.py",))


if __name__ == "__main__":
    unittest.main()
