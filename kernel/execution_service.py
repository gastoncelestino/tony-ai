"""Atomic service boundary for Kernel-owned execution decisions."""
from __future__ import annotations

from kernel.execution_order import ExecutionOrder, authorize_execution_order, resolve_execution


def resolve_runtime_execution(kernel) -> dict:
    """Expose the Kernel's resolved execution order without adding policy."""
    return resolve_execution(kernel)


def authorize_runtime_execution(order: dict, requested_task_id: str) -> bool:
    """Apply Kernel execution authority to a runtime task request."""
    execution_order = ExecutionOrder(
        phase=order["phase"],
        task_id=order["task_id"],
        description=order["description"],
        files=tuple(order["files"]),
        dependencies=tuple(order["dependencies"]),
        capabilities=tuple(order["capabilities"]),
        executor=order["executor"],
        worker=order["worker"],
    )
    return authorize_execution_order(execution_order, requested_task_id)
