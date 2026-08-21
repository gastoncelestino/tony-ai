"""Tony Kernel phase capability policy.

The Kernel owns which runtime tools a phase may use. OpenCode is only the
execution bridge: it asks this policy before executing a tool.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDecision:
    allowed: bool
    reason: str


# Tool names are matched by exact name or prefix. Native read-only inspection
# tools are allowed during planning phases; mutation/delegation/web tools are
# explicitly denied until the implementation/verification phases permit them.
PHASE_ALLOWED_PREFIXES = {
    "explore": ("code-index_", "read", "glob", "grep", "tonymem_mem_save"),
    "propose": ("code-index_", "read", "glob", "grep", "tonymem_"),
    "spec": ("code-index_", "read", "glob", "grep", "tonymem_"),
    "design": ("code-index_", "read", "glob", "grep", "tonymem_"),
    "tasks": ("code-index_", "read", "glob", "grep", "tonymem_"),
    "apply": ("code-index_", "read", "glob", "grep", "tonymem_", "edit", "write", "bash"),
    "verify": ("code-index_", "read", "glob", "grep", "tonymem_", "bash"),
    "archive": ("read", "glob", "grep", "tonymem_", "bash"),
}

ALWAYS_ALLOWED_PREFIXES = ("tony-kernel_",)
ALWAYS_DENIED_PREFIXES = ("task", "webfetch", "websearch")


def check_tool_capability(phase: str, tool: str) -> ToolDecision:
    """Return the Kernel's authoritative decision for a phase/tool pair."""
    if any(tool == prefix or tool.startswith(prefix) for prefix in ALWAYS_ALLOWED_PREFIXES):
        return ToolDecision(True, "Tony Kernel control-plane tool")

    if any(tool == prefix or tool.startswith(prefix) for prefix in ALWAYS_DENIED_PREFIXES):
        return ToolDecision(False, f"tool '{tool}' is not allowed during phase '{phase}'")

    allowed = PHASE_ALLOWED_PREFIXES.get(phase)
    if allowed is None:
        return ToolDecision(False, f"unknown kernel phase '{phase}'")

    if any(tool == prefix or tool.startswith(prefix) for prefix in allowed):
        return ToolDecision(True, f"tool '{tool}' allowed during phase '{phase}'")

    return ToolDecision(False, f"tool '{tool}' is not allowed during phase '{phase}'")
