"""Tests for Kernel-owned execution-order resolution."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from kernel.execution_order import ExecutionOrder, resolve_execution


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


class TestExecutionOrder(unittest.TestCase):
    def test_resolves_ready_task_from_kernel_state(self):
        kernel = FakeKernel(
            "explore",
            "running",
            {
                "id": "explore-1",
                "description": "Inspect the repository",
                "phase": "explore",
                "dependencies": (),
                "files": ("kernel/",),
                "capabilities": ("read", "search"),
            },
        )

        result = resolve_execution(kernel)

        self.assertTrue(result["allowed"])
        self.assertEqual(result["decision"], "proceed")
        self.assertEqual(result["execution_order"]["executor"], "opencode")
        self.assertEqual(result["execution_order"]["worker"], "llm")
        self.assertEqual(result["execution_order"]["task_id"], "explore-1")
        self.assertEqual(
            result["execution_order"]["capabilities"], ["read", "search"]
        )

    def test_blocks_completed_phase(self):
        result = resolve_execution(
            FakeKernel(
                "explore",
                "completed",
                {
                    "id": "explore-1",
                    "description": "Inspect the repository",
                    "phase": "explore",
                },
            )
        )

        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "blocked")
        self.assertIsNone(result["execution_order"])

    def test_blocks_task_from_different_phase(self):
        result = resolve_execution(
            FakeKernel(
                "explore",
                "running",
                {
                    "id": "apply-1",
                    "description": "Modify code",
                    "phase": "apply",
                },
            )
        )

        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "blocked")
        self.assertIsNone(result["execution_order"])

    def test_blocks_when_no_task_is_ready(self):
        result = resolve_execution(FakeKernel("explore", "running", None))

        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "blocked")
        self.assertIsNone(result["execution_order"])

    def test_blocks_incomplete_task_definition(self):
        result = resolve_execution(
            FakeKernel(
                "explore",
                "running",
                {"id": "explore-1", "phase": "explore"},
            )
        )

        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "blocked")

    def test_blocks_unsupported_capability(self):
        result = resolve_execution(
            FakeKernel(
                "explore",
                "running",
                {
                    "id": "explore-1",
                    "description": "Inspect the repository",
                    "phase": "explore",
                    "capabilities": ("write",),
                },
            )
        )

        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "blocked")
        self.assertIsNone(result["execution_order"])

    def test_capabilities_are_kernel_order_fields(self):
        result = resolve_execution(
            FakeKernel(
                "explore",
                "running",
                {
                    "id": "explore-1",
                    "description": "Inspect the repository",
                    "phase": "explore",
                    "capabilities": ("search",),
                },
            )
        )

        self.assertTrue(result["allowed"])
        self.assertEqual(result["execution_order"]["capabilities"], ["search"])

    def test_task_selection_comes_from_kernel_state(self):
        kernel = FakeKernel(
            "explore",
            "running",
            {
                "id": "kernel-selected-task",
                "description": "Task selected by Kernel",
                "phase": "explore",
            },
        )

        result = resolve_execution(kernel)

        self.assertTrue(result["allowed"])
        self.assertEqual(
            result["execution_order"]["task_id"],
            "kernel-selected-task",
        )

    def test_execution_order_is_immutable(self):
        order = ExecutionOrder(
            phase="explore",
            task_id="explore-1",
            description="Inspect the repository",
            files=("kernel/",),
            dependencies=(),
            capabilities=("read", "search"),
        )

        with self.assertRaises(FrozenInstanceError):
            order.task_id = "apply-1"


if __name__ == "__main__":
    unittest.main()
