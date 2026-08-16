"""Policy-controlled subprocess execution with bounded wall-clock time."""
from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Sequence

from .runtime_guard import RuntimePolicyGuard
from .runtime_policy import RuntimePolicy


@dataclass(frozen=True, slots=True)
class RuntimeExecutionResult:
    """Result of one policy-authorized command execution."""

    command: tuple[str, ...]
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class RuntimeExecutor:
    """Execute commands only after runtime-policy authorization."""

    def __init__(self, policy: RuntimePolicy):
        self.policy = policy
        self.guard = RuntimePolicyGuard(policy)

    def run(self, command: Sequence[str], *, cwd: str | None = None) -> RuntimeExecutionResult:
        """Run a command with the policy timeout and optional authorized cwd."""
        argv = tuple(command)
        if not argv or not all(isinstance(part, str) and part for part in argv):
            raise ValueError("command must contain at least one non-empty string")
        self.guard.require_command(" ".join(argv))
        if cwd is not None:
            self.guard.require_path(cwd)
        try:
            completed = subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True,
                timeout=self.policy.timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            return RuntimeExecutionResult(argv, None, stdout, stderr, True)
        return RuntimeExecutionResult(argv, completed.returncode, completed.stdout, completed.stderr)


__all__ = ["RuntimeExecutionResult", "RuntimeExecutor"]
