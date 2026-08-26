"""Minimal Kernel-owned tool capability policy."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolDecision:
    allowed: bool
    reason: str


PHASE_ALLOWED_TOOLS = {
    "explore": ("read", "glob", "grep"),
    "propose": ("read", "glob", "grep"),
    "spec": ("read", "glob", "grep"),
    "design": ("read", "glob", "grep"),
    "tasks": ("read", "glob", "grep"),
    "apply": ("read", "glob", "grep", "edit", "write", "bash"),
    "verify": ("read", "glob", "grep", "bash"),
    "archive": ("read", "glob", "grep", "bash"),
}


def authorize_tool(phase: str, tool: str) -> ToolDecision:
    """Return whether a runtime tool is allowed in the current Kernel phase."""
    allowed = PHASE_ALLOWED_TOOLS.get(phase)
    if allowed is None:
        return ToolDecision(False, "unknown phase")
    if tool not in allowed:
        return ToolDecision(False, "tool not allowed in phase")
    return ToolDecision(True, "tool allowed in phase")
