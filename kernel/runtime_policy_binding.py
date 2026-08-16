"""Runtime policy binding for Kernel orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .runtime_guard import RuntimeAuthorization, RuntimePolicyGuard
from .runtime_policy import RuntimePolicy


@dataclass(frozen=True, slots=True)
class RuntimePolicyBinding:
    """Optional policy binding that keeps legacy callers unrestricted by default."""

    policy: Optional[RuntimePolicy] = None

    @property
    def enabled(self) -> bool:
        return self.policy is not None

    def guard(self) -> Optional[RuntimePolicyGuard]:
        return RuntimePolicyGuard(self.policy) if self.policy is not None else None

    def authorize_tool(self, tool: str) -> RuntimeAuthorization:
        guard = self.guard()
        if guard is None:
            return RuntimeAuthorization(True, "runtime policy not configured")
        return guard.authorize_tool(tool)

    def authorize_path(self, path: str) -> RuntimeAuthorization:
        guard = self.guard()
        if guard is None:
            return RuntimeAuthorization(True, "runtime policy not configured")
        return guard.authorize_path(path)

    def authorize_command(self, command: str) -> RuntimeAuthorization:
        guard = self.guard()
        if guard is None:
            return RuntimeAuthorization(True, "runtime policy not configured")
        return guard.authorize_command(command)

    def authorize_network(self) -> RuntimeAuthorization:
        guard = self.guard()
        if guard is None:
            return RuntimeAuthorization(True, "runtime policy not configured")
        return guard.authorize_network()


__all__ = ["RuntimePolicyBinding"]
