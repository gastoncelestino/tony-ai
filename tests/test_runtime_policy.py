"""Tests for declarative runtime policy boundaries."""

import pytest

from kernel.runtime_policy import RuntimePolicy, RuntimePolicyError


def test_runtime_policy_defaults_to_deny_network():
    policy = RuntimePolicy()
    assert not policy.network_allowed()
    assert policy.timeout_seconds == 300.0


def test_runtime_policy_matches_paths_commands_and_tools():
    policy = RuntimePolicy.from_mapping({
        "allowed_paths": ["src/**", "tests/**"],
        "allowed_commands": ["pytest*", "git diff*"],
        "tool_permissions": ["read_file", "run_tests"],
    })
    assert policy.path_allowed("src/kernel.py")
    assert not policy.path_allowed("secrets/key.txt")
    assert policy.command_allowed("pytest -q")
    assert not policy.command_allowed("rm -rf /")
    assert policy.tool_allowed("run_tests")
    assert not policy.tool_allowed("shell")


def test_runtime_policy_accepts_explicit_resource_limits():
    policy = RuntimePolicy.from_mapping({
        "network_policy": "allow",
        "timeout_seconds": 30,
        "cpu_seconds": 10,
        "memory_mb": 512,
    })
    assert policy.network_allowed()
    assert policy.timeout_seconds == 30.0
    assert policy.cpu_seconds == 10.0
    assert policy.memory_mb == 512


@pytest.mark.parametrize(
    "data",
    [
        {"network_policy": "maybe"},
        {"timeout_seconds": 0},
        {"cpu_seconds": -1},
        {"memory_mb": 0},
        {"memory_mb": 1.5},
    ],
)
def test_runtime_policy_rejects_invalid_limits(data):
    with pytest.raises(RuntimePolicyError):
        RuntimePolicy.from_mapping(data)
