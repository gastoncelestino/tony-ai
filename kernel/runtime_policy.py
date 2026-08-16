"""Declarative runtime policy for bounded agent execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Mapping, Sequence


class RuntimePolicyError(ValueError):
    """Raised when a runtime policy is invalid."""


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """Immutable execution limits evaluated before tool execution."""

    allowed_paths: tuple[str, ...] = ()
    allowed_commands: tuple[str, ...] = ()
    network_policy: str = "deny"
    timeout_seconds: float = 300.0
    cpu_seconds: float | None = None
    memory_mb: int | None = None
    tool_permissions: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "RuntimePolicy":
        """Build a policy from a YAML/JSON-compatible mapping."""
        def strings(key: str) -> tuple[str, ...]:
            value = data.get(key, ())
            if isinstance(value, str):
                value = (value,)
            if not isinstance(value, Sequence) or isinstance(value, (bytes, str)):
                raise RuntimePolicyError(f"{key} must be a sequence")
            result = tuple(value)
            if not all(isinstance(item, str) and item for item in result):
                raise RuntimePolicyError(f"{key} must contain non-empty strings")
            return result

        network = data.get("network_policy", "deny")
        if network not in {"deny", "allow"}:
            raise RuntimePolicyError("network_policy must be 'deny' or 'allow'")

        timeout = data.get("timeout_seconds", 300.0)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise RuntimePolicyError("timeout_seconds must be positive")

        cpu = data.get("cpu_seconds")
        if cpu is not None and (not isinstance(cpu, (int, float)) or cpu <= 0):
            raise RuntimePolicyError("cpu_seconds must be positive when set")

        memory = data.get("memory_mb")
        if memory is not None and (not isinstance(memory, int) or memory <= 0):
            raise RuntimePolicyError("memory_mb must be a positive integer when set")

        return cls(
            allowed_paths=strings("allowed_paths"),
            allowed_commands=strings("allowed_commands"),
            network_policy=network,
            timeout_seconds=float(timeout),
            cpu_seconds=float(cpu) if cpu is not None else None,
            memory_mb=memory,
            tool_permissions=strings("tool_permissions"),
        )

    def path_allowed(self, path: str) -> bool:
        return bool(self.allowed_paths) and any(
            fnmatch(path, pattern) for pattern in self.allowed_paths
        )

    def command_allowed(self, command: str) -> bool:
        return bool(self.allowed_commands) and any(
            fnmatch(command, pattern) for pattern in self.allowed_commands
        )

    def tool_allowed(self, tool: str) -> bool:
        return bool(self.tool_permissions) and tool in self.tool_permissions

    def network_allowed(self) -> bool:
        return self.network_policy == "allow"


__all__ = ["RuntimePolicy", "RuntimePolicyError"]
