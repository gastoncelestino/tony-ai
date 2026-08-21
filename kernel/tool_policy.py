"""Tony Kernel phase capability policy.

The Kernel owns which runtime tools a phase may use. OpenCode is only the
execution bridge: it asks this policy before executing a tool.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDecision:
    allowed: bool
    reason: str


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


def main() -> None:
    """CLI bridge used by the OpenCode Kernel capability hook."""
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 -m kernel.tool_policy <tool-name>")

    if not os.environ.get("TONY_RUNTIME_DIR"):
        raise RuntimeError("TONY_RUNTIME_DIR must be configured")

    from .persistence import load_orchestrator
    from .artifact_store import disk_artifact_store, disk_artifact_hasher

    base = os.environ.get("TONY_REPO_ROOT") or os.getcwd()
    orchestrator = load_orchestrator(
        artifact_store=disk_artifact_store(base),
        artifact_hasher=disk_artifact_hasher(base),
    )
    phase = orchestrator.get_status()["current_phase"]
    decision = check_tool_capability(phase, sys.argv[1])
    print(json.dumps({
        "allowed": decision.allowed,
        "reason": decision.reason,
        "phase": phase,
        "tool": sys.argv[1],
    }))


if __name__ == "__main__":
    main()
