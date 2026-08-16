"""Tests for policy-controlled runtime command execution."""

import sys

import pytest

from kernel.runtime_guard import RuntimePolicyViolation
from kernel.runtime_executor import RuntimeExecutor
from kernel.runtime_policy import RuntimePolicy


def _policy(timeout=1.0, cpu_seconds=None):
    data = {
        "allowed_commands": ["*"],
        "timeout_seconds": timeout,
    }
    if cpu_seconds is not None:
        data["cpu_seconds"] = cpu_seconds
    return RuntimePolicy.from_mapping(data)


def test_runtime_executor_runs_authorized_command():
    result = RuntimeExecutor(_policy()).run((sys.executable, "-c", "print('ok')"))

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert not result.timed_out
    assert not result.cpu_limited


def test_runtime_executor_blocks_unauthorized_command():
    executor = RuntimeExecutor(
        RuntimePolicy.from_mapping({"allowed_commands": ["pytest*"]})
    )

    with pytest.raises(RuntimePolicyViolation, match="command denied"):
        executor.run((sys.executable, "-c", "print('blocked')"))


def test_runtime_executor_enforces_timeout():
    result = RuntimeExecutor(_policy(timeout=0.05)).run(
        (sys.executable, "-c", "import time; time.sleep(1)")
    )

    assert result.timed_out
    assert result.exit_code is None


def test_runtime_executor_enforces_cpu_limit():
    result = RuntimeExecutor(_policy(timeout=5.0, cpu_seconds=1)).run(
        (sys.executable, "-c", "while True: pass")
    )

    assert result.cpu_limited
    assert result.exit_code is not None
    assert not result.timed_out


def test_runtime_executor_authorizes_working_directory():
    executor = RuntimeExecutor(
        RuntimePolicy.from_mapping({
            "allowed_commands": ["*"],
            "allowed_paths": ["tests/**"],
        })
    )

    with pytest.raises(RuntimePolicyViolation, match="path denied"):
        executor.run((sys.executable, "-c", "print('blocked')"), cwd="src")
