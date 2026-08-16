"""Tests for pre-execution runtime policy enforcement."""

import pytest

from kernel.runtime_guard import RuntimePolicyGuard, RuntimePolicyViolation
from kernel.runtime_policy import RuntimePolicy


def test_guard_allows_explicitly_permitted_actions():
    guard = RuntimePolicyGuard(
        RuntimePolicy.from_mapping({
            "allowed_paths": ["src/**"],
            "allowed_commands": ["pytest*"],
            "tool_permissions": ["run_tests"],
            "network_policy": "allow",
        })
    )

    assert guard.authorize_path("src/kernel.py").allowed
    assert guard.authorize_command("pytest -q").allowed
    assert guard.authorize_tool("run_tests").allowed
    assert guard.authorize_network().allowed


def test_guard_denies_unlisted_actions():
    guard = RuntimePolicyGuard(
        RuntimePolicy.from_mapping({
            "allowed_paths": ["src/**"],
            "allowed_commands": ["pytest*"],
            "tool_permissions": ["run_tests"],
        })
    )

    assert not guard.authorize_path("secrets/key.txt").allowed
    assert not guard.authorize_command("rm -rf /").allowed
    assert not guard.authorize_tool("shell").allowed
    assert not guard.authorize_network().allowed


def test_guard_require_methods_raise_on_policy_violation():
    guard = RuntimePolicyGuard(RuntimePolicy())

    with pytest.raises(RuntimePolicyViolation, match="path denied"):
        guard.require_path("src/kernel.py")
    with pytest.raises(RuntimePolicyViolation, match="command denied"):
        guard.require_command("pytest -q")
    with pytest.raises(RuntimePolicyViolation, match="tool denied"):
        guard.require_tool("shell")
    with pytest.raises(RuntimePolicyViolation, match="network denied"):
        guard.require_network()
