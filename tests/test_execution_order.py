"""Tests for the minimal Kernel-owned execution-order contract."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from kernel.execution_order import (
    ExecutionOrder,
    authorize_execution_order,
    authorize_file_access,
    resolve_execution,
)


class FakeKernel:
    def __init__(self, phase: str, status: str, task: dict | None):
        self.change_state = SimpleNamespace(
            current_phase=SimpleNamespace(value=phase),
            get_current_phase_state=lambda: SimpleNamespace(status=SimpleNamespace(value=status)),
        )
        self._task = task

    def get_next_task(self):
        return self._task


class TestExecutionOrder(unittest.TestCase):
    def test_valid_request_produces_v1_order(self):
        result = resolve_execution(FakeKernel("explore", "running", {
            "id": "explore-1", "description": "Inspect the repository", "phase": "explore", "files": ("kernel/",)
        }))
        self.assertTrue(result["allowed"])
        self.assertEqual(result["execution_order"], {
            "phase": "explore", "task_id": "explore-1", "description": "Inspect the repository", "files": ["kernel/"]
        })

    def test_missing_task_id_blocks(self):
        result = resolve_execution(FakeKernel("explore", "running", {"description": "Inspect", "phase": "explore"}))
        self.assertFalse(result["allowed"])

    def test_missing_phase_blocks(self):
        result = resolve_execution(FakeKernel("explore", "running", {"id": "explore-1", "description": "Inspect"}))
        self.assertFalse(result["allowed"])

    def test_missing_description_blocks(self):
        result = resolve_execution(FakeKernel("explore", "running", {"id": "explore-1", "phase": "explore"}))
        self.assertFalse(result["allowed"])

    def test_wrong_phase_blocks(self):
        result = resolve_execution(FakeKernel("explore", "running", {"id": "apply-1", "description": "Modify", "phase": "apply"}))
        self.assertFalse(result["allowed"])

    def test_completed_phase_blocks(self):
        result = resolve_execution(FakeKernel("explore", "completed", {"id": "explore-1", "description": "Inspect", "phase": "explore"}))
        self.assertFalse(result["allowed"])

    def test_order_is_immutable(self):
        order = ExecutionOrder("explore", "explore-1", "Inspect", ("kernel/",))
        with self.assertRaises(FrozenInstanceError):
            order.task_id = "apply-1"

    def test_order_materializes_kernel_state(self):
        task = {"id": "explore-2", "description": "Inspect", "phase": "explore", "files": ("kernel/",)}
        order = resolve_execution(FakeKernel("explore", "running", task))["execution_order"]
        task["id"] = "apply-2"
        task["files"] = ("plugins/",)
        self.assertEqual(order["task_id"], "explore-2")
        self.assertEqual(order["files"], ["kernel/"])

    def test_runtime_accepts_only_authorized_task(self):
        order = ExecutionOrder("explore", "explore-4", "Run", ("kernel/",))
        self.assertTrue(authorize_execution_order(order, "explore-4"))
        self.assertFalse(authorize_execution_order(order, "explore-5"))

    def test_file_inside_order_scope_is_allowed(self):
        order = ExecutionOrder("explore", "explore-5", "Inspect", ("kernel/execution_order.py", "tests/"))
        self.assertTrue(authorize_file_access(order, "kernel/execution_order.py"))

    def test_file_outside_order_scope_is_blocked(self):
        order = ExecutionOrder("explore", "explore-6", "Inspect", ("kernel/execution_order.py",))
        self.assertFalse(authorize_file_access(order, "plugins/opencode.ts"))

    def test_scope_does_not_match_by_prefix(self):
        order = ExecutionOrder("explore", "explore-7", "Inspect", ("kernel/task.py",))
        self.assertFalse(authorize_file_access(order, "kernel/task.py.bak"))


if __name__ == "__main__":
    unittest.main()
