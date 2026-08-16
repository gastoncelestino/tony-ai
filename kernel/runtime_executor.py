"""Policy-controlled subprocess execution with bounded resource limits."""
from __future__ import annotations

import math
import signal
import subprocess
from dataclasses import dataclass
from typing import Sequence

from .runtime_guard import RuntimePolicyGuard, RuntimePolicyViolation
from .runtime_policy import RuntimePolicy

try:
    import resource
except ImportError:  # pragma: no cover - exercised only on non-POSIX hosts
    resource = None


@dataclass(frozen=True, slots=True)
class RuntimeExecutionResult:
    """Result of one policy-authorized command execution."""

    command: tuple[str, ...]
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cpu_limited: bool = False
    memory_limited: bool = False


class RuntimeExecutor:
    """Execute commands only after runtime-policy authorization."""

    def __init__(self, policy: RuntimePolicy):
        self.policy = policy
        self.guard = RuntimePolicyGuard(policy)

    def run(self, command: Sequence[str], *, cwd: str | None = None) -> RuntimeExecutionResult:
        """Run a command with policy authorization and resource limits."""
        argv = tuple(command)
        if not argv or not all(isinstance(part, str) and part for part in argv):
            raise ValueError("command must contain at least one non-empty string")
        self.guard.require_command(" ".join(argv))
        if cwd is not None:
            self.guard.require_path(cwd)
        if (self.policy.cpu_seconds is not None or self.policy.memory_mb is not None) and resource is None:
            raise RuntimePolicyViolation("CPU/memory limits are unsupported on this platform")

        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.policy.timeout_seconds,
                check=False,
                preexec_fn=self._resource_limits() if resource is not None else None,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            return RuntimeExecutionResult(argv, None, stdout, stderr, timed_out=True)

        cpu_limited = (
            self.policy.cpu_seconds is not None
            and completed.returncode in {
                -getattr(signal, "SIGXCPU", 24),
                -getattr(signal, "SIGKILL", 9),
            }
        )
        memory_limited = (
            self.policy.memory_mb is not None
            and completed.returncode in {
                -getattr(signal, "SIGSEGV", 11),
                -getattr(signal, "SIGKILL", 9),
            }
        )
        return RuntimeExecutionResult(
            argv,
            completed.returncode,
            completed.stdout,
            completed.stderr,
            cpu_limited=cpu_limited,
            memory_limited=memory_limited,
        )

    def _resource_limits(self):
        if resource is None:
            return None

        cpu_limit = None
        if self.policy.cpu_seconds is not None:
            cpu_limit = max(1, math.ceil(self.policy.cpu_seconds))

        memory_limit = None
        if self.policy.memory_mb is not None:
            memory_limit = self.policy.memory_mb * 1024 * 1024

        if cpu_limit is None and memory_limit is None:
            return None

        def apply_limits() -> None:
            if cpu_limit is not None:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
            if memory_limit is not None:
                resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))

        return apply_limits


__all__ = ["RuntimeExecutionResult", "RuntimeExecutor"]
