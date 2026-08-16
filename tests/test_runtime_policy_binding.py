"""Tests for optional runtime policy binding."""

from kernel.runtime_policy import RuntimePolicy
from kernel.runtime_policy_binding import RuntimePolicyBinding


def test_unconfigured_binding_preserves_legacy_allow_behavior():
    binding = RuntimePolicyBinding()
    assert not binding.enabled
    assert binding.authorize_tool("shell").allowed
    assert binding.authorize_path("anything").allowed


def test_configured_binding_delegates_to_runtime_guard():
    binding = RuntimePolicyBinding(
        RuntimePolicy.from_mapping({
            "allowed_paths": ["src/**"],
            "allowed_commands": ["pytest*"],
            "tool_permissions": ["run_tests"],
            "network_policy": "allow",
        })
    )
    assert binding.enabled
    assert binding.authorize_path("src/kernel.py").allowed
    assert not binding.authorize_path("secrets/key.txt").allowed
    assert binding.authorize_command("pytest -q").allowed
    assert not binding.authorize_command("rm -rf /").allowed
    assert binding.authorize_tool("run_tests").allowed
    assert not binding.authorize_tool("shell").allowed
    assert binding.authorize_network().allowed
