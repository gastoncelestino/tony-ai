"""Tests for the atomic Kernel execution-service boundary."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from kernel.execution_service import authorize_runtime_execution, resolve_runtime_execution


class FakeKernel:
    def __init__(self, phase: str, status: str, task: dict | None):
        self.change_state = SimpleNamespace(
            current_phase=SimpleNamespace(value=phase),
            get_current_phase_state=lambda: SimpleNamespace(
                status=SimpleNamespace(value=status)
            ),
        )
        self._task = task

    def get_next_task(self):
        return self._task


class TestExecutionService(unittest.TestCase):
    def test_resolve_runtime_execution_returns_v1_order(self):
        kernel = FakeKernel(
            "explore",
            "running",
            {
                "id": "explore-1",
                "description": "Inspect the repository",
                "phase": "explore",
                "files": ("kernel/",),
            },
        )

        result = resolve_runtime_execution(kernel)

        self.assertTrue(result["allowed"])
        self.assertEqual(result["decision"], "proceed")
        self.assertEqual(
            result["execution_order"],
            {
                "phase": "explore",
                "task_id": "explore-1",
                "description": "Inspect the repository",
                "files": ["kernel/"],
            },
        )

    def test_resolve_runtime_execution_blocks_without_order(self):
        kernel = FakeKernel("explore", "completed", None)

        result = resolve_runtime_execution(kernel)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "blocked")
        self.assertIsNone(result["execution_order"])

    def test_authorize_runtime_execution_accepts_kernel_task(self):
        order = {
            "phase": "explore",
            "task_id": "explore-2",
            "description": "Inspect the repository",
            "files": ["kernel/"],
        }

        self.assertTrue(authorize_runtime_execution(order, "explore-2"))

    def test_authorize_runtime_execution_rejects_different_task(self):
        order = {
            "phase": "explore",
            "task_id": "explore-3",
            "description": "Inspect the repository",
            "files": ["kernel/"],
        }

        self.assertFalse(authorize_runtime_execution(order, "apply-3"))


if __name__ == "__main__":
    unittest.main()
