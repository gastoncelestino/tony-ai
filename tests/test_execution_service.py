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
    def test_resolve_runtime_execution_returns_kernel_execution_order(self):
        kernel = FakeKernel(
            "explore",
            "running",
            {
                "id": "explore-1",
                "description": "Inspect the repository",
                "phase": "explore",
                "files": ("kernel/",),
                "dependencies": (),
                "capabilities": ("read",),
            },
        )

        result = resolve_runtime_execution(kernel)

        self.assertTrue(result["allowed"])
        self.assertEqual(result["decision"], "proceed")
        self.assertEqual(result["execution_order"]["task_id"], "explore-1")

    def test_resolve_runtime_execution_blocks_without_order(self):
        kernel = FakeKernel("explore", "completed", None)

        result = resolve_runtime_execution(kernel)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "blocked")
        self.assertIsNone(result["execution_order"])

    def test_authorize_runtime_execution_accepts_kernel_task(self):
        kernel = FakeKernel(
            "explore",
            "running",
            {
                "id": "explore-2",
                "description": "Inspect the repository",
                "phase": "explore",
            },
        )

        result = resolve_runtime_execution(kernel)

        self.assertTrue(
            authorize_runtime_execution(result["execution_order"], "explore-2")
        )

    def test_authorize_runtime_execution_rejects_different_task(self):
        kernel = FakeKernel(
            "explore",
            "running",
            {
                "id": "explore-3",
                "description": "Inspect the repository",
                "phase": "explore",
            },
        )

        result = resolve_runtime_execution(kernel)

        self.assertFalse(
            authorize_runtime_execution(result["execution_order"], "apply-3")
        )


if __name__ == "__main__":
    unittest.main()
