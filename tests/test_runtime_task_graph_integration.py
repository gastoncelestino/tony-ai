"""Integration tests for runtime execution and task-graph transitions."""

import sys

from kernel import Phase, RuntimeExecutor, RuntimePolicy, TaskGraphKernelOrchestrator, TaskStatus


def _kernel():
    kernel = TaskGraphKernelOrchestrator("runtime-change", "test-project")
    kernel.add_task("task", "execute runtime command", Phase.APPLY)
    assert kernel.start_task("task")
    return kernel


def _executor():
    return RuntimeExecutor(RuntimePolicy.from_mapping({"allowed_commands": ["*"], "timeout_seconds": 2.0}))


def test_runtime_execution_produces_evidence_and_completes_task():
    kernel = _kernel()
    result = kernel.execute_task("task", (sys.executable, "-c", "print('ok')"), executor=_executor(), claim="runtime command succeeded")
    assert result.decision.value == "proceed"
    assert kernel.task_graph.get("task").status is TaskStatus.COMPLETED
    assert kernel.task_graph.get("task").evidence_refs
    assert kernel.task_ledger.tasks["task"].evidence[0].stdout.strip() == "ok"


def test_runtime_execution_without_valid_evidence_does_not_complete_task():
    kernel = _kernel()
    result = kernel.execute_task("task", (sys.executable, "-c", "import sys; sys.exit(3)"), executor=_executor(), claim="runtime command failed")
    assert result.decision.value == "block_evidence_required"
    assert kernel.task_graph.get("task").status is TaskStatus.IN_PROGRESS
    assert kernel.task_graph.get("task").evidence_refs == ()
