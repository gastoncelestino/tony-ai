"""Pre-execution enforcement for declarative runtime policy."""
from __future__ import annotations

from dataclasses import dataclass

from .runtime_policy import RuntimePolicy


class RuntimePolicyViolation(PermissionError):
    """Raised when a runtime action is outside the configured policy."""


@dataclass(frozen=True, slots=True)
class RuntimeAuthorization:
    """Deterministic authorization result for one runtime action."""

    allowed: bool
    reason: str = ""


class RuntimePolicyGuard:
    """Evaluate runtime actions before they reach an execution backend."""

    def __init__(self, policy: RuntimePolicy):
        self.policy = policy

    def authorize_path(self, path: str) -> RuntimeAuthorization:
        if self.policy.path_allowed(path):
            return RuntimeAuthorization(True, "path allowed")
        return RuntimeAuthorization(False, f"path denied by runtime policy: {path}")

    def authorize_command(self, command: str) -> RuntimeAuthorization:
        if self.policy.command_allowed(command):
            return RuntimeAuthorization(True, "command allowed")
        return RuntimeAuthorization(False, "command denied by runtime policy")

    def authorize_tool(self, tool: str) -> RuntimeAuthorization:
        if self.policy.tool_allowed(tool):
            return RuntimeAuthorization(True, "tool allowed")
        return RuntimeAuthorization(False, f"tool denied by runtime policy: {tool}")

    def authorize_network(self) -> RuntimeAuthorization:
        if self.policy.network_allowed():
            return RuntimeAuthorization(True, "network allowed")
        return RuntimeAuthorization(False, "network denied by runtime policy")

    def require_path(self, path: str) -> None:
        self._require(self.authorize_path(path))

    def require_command(self, command: str) -> None:
        self._require(self.authorize_command(command))

    def require_tool(self, tool: str) -> None:
        self._require(self.authorize_tool(tool))

    def require_network(self) -> None:
        self._require(self.authorize_network())

    @staticmethod
    def _require(result: RuntimeAuthorization) -> None:
        if not result.allowed:
            raise RuntimePolicyViolation(result.reason)


__all__ = ["RuntimeAuthorization", "RuntimePolicyGuard", "RuntimePolicyViolation"]
