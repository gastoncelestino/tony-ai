"""Integration tests for runtime policy arbitration in the task-graph Kernel."""

from kernel import Phase, TaskGraphKernelOrchestrator
from kernel.runtime_policy import RuntimePolicy


def test_task_graph_orchestrator_uses_runtime_policy_when_configured():
    kernel = TaskGraphKernelOrchestrator(
        "runtime-policy-change",
        "test-project",
        runtime_policy=RuntimePolicy.from_mapping({
            "allowed_paths": ["src/**"],
            "allowed_commands": ["pytest*"],
            "tool_permissions": ["run_tests"],
            "network_policy": "deny",
        }),
    )

    assert kernel.authorize_path("src/kernel.py").allowed
    assert not kernel.authorize_path("secrets/key.txt").allowed
    assert kernel.authorize_command("pytest -q").allowed
    assert not kernel.authorize_command("rm -rf /").allowed
    assert kernel.authorize_tool("run_tests").allowed
    assert not kernel.authorize_tool("shell").allowed
    assert not kernel.authorize_network().allowed


def test_task_graph_orchestrator_preserves_legacy_runtime_behavior_without_policy():
    kernel = TaskGraphKernelOrchestrator("legacy-change", "test-project")

    assert kernel.authorize_path("anything").allowed
    assert kernel.authorize_command("anything").allowed
    assert kernel.authorize_tool("anything").allowed
    assert kernel.authorize_network().allowed


def test_runtime_policy_does_not_change_task_graph_transitions():
    kernel = TaskGraphKernelOrchestrator(
        "graph-change",
        "test-project",
        runtime_policy=RuntimePolicy.from_mapping({
            "allowed_paths": ["src/**"],
            "allowed_commands": ["pytest*"],
            "tool_permissions": ["run_tests"],
        }),
    )
    kernel.add_task("task", "run task", Phase.APPLY)

    assert kernel.start_task("task")
    assert kernel.get_task_graph().get("task").status.value == "in_progress"
