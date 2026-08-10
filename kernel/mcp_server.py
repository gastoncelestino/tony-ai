#!/usr/bin/env python3
"""
Tony Kernel — MCP server (stdio)

Exposes the Kernel Orchestrator to the tony-orchestrator as MCP tools, so the
LLM can call the gate deterministically:

- kernel_can_start_phase      check before delegating a phase
- kernel_record_delegation    log a delegation
- kernel_record_phase_completion  record artifacts + advance state
- kernel_verify_phase_checksum    verify a phase's artifacts weren't tampered
- kernel_add_task / kernel_complete_task / kernel_start_task   task lifecycle
- kernel_check_scope          scope-guard a git diff
- kernel_get_status / kernel_reset

Same protocol as local-memory/server.py: newline-delimited JSON-RPC over
stdio, stdlib-only, no external deps. State persists across calls via
kernel/persistence.py (default: `<cwd>/.tony-kernel/kernel-state.json`).

Point OpenCode at it: python3 kernel/mcp_server.py
"""
from __future__ import annotations

import json
import os
import sys

# Make `kernel` importable when running as a plain script (python3 kernel/mcp_server.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.cli import _build_store, _load, _result_to_dict, _parse_artifact_refs, _parse_evidence
from kernel.persistence import save_orchestrator, reset_state


def _json_arg(arg):
    if isinstance(arg, str):
        return json.loads(arg)
    return arg


def _can_start_phase(args: dict) -> dict:
    orch = _load()
    result = orch.can_start_phase(args["phase"])
    save_orchestrator(orch)
    return _result_to_dict(result)


def _record_delegation(args: dict) -> dict:
    orch = _load()
    orch.record_delegation(args["phase"], args.get("sub_agent", "sub-agent"),
                           args.get("task_id"))
    save_orchestrator(orch)
    return {"ok": True}


def _record_phase_completion(args: dict) -> dict:
    raw = _json_arg(args.get("artifacts", []))
    orch = _load()
    result = orch.record_phase_completion(args["phase"], _parse_artifact_refs(raw))
    save_orchestrator(orch)
    return _result_to_dict(result)


def _verify_phase_checksum(args: dict) -> dict:
    raw = _json_arg(args.get("artifacts", []))
    orch = _load()
    return orch.verify_phase_checksum(args["phase"], _parse_artifact_refs(raw))


def _add_task(args: dict) -> dict:
    orch = _load()
    orch.add_task(args["task_id"], args["description"], args["phase"])
    save_orchestrator(orch)
    return {"ok": True}


def _start_task(args: dict) -> dict:
    orch = _load()
    ok = orch.start_task(args["task_id"])
    save_orchestrator(orch)
    return {"ok": ok}


def _complete_task(args: dict) -> dict:
    raw = _json_arg(args.get("evidence", []))
    orch = _load()
    result = orch.complete_task(args["task_id"], _parse_evidence(raw))
    save_orchestrator(orch)
    return _result_to_dict(result)


def _check_scope(args: dict) -> dict:
    allowed = _json_arg(args.get("allowed_files", []))
    orch = _load()
    result = orch.check_scope(args.get("git_diff", ""), tuple(allowed))
    return {
        "decision": result.decision.value,
        "allowed": result.decision.value in ("proceed", "phase_complete"),
        "reason": result.reason,
        "current_phase": result.current_phase,
        "scope_violations": list(result.scope_violations),
    }


def _get_status(args: dict) -> dict:
    return _load().get_status()


def _reset(args: dict) -> dict:
    reset_state()
    return {"ok": True}


TOOLS = {
    "kernel_can_start_phase": {
        "description": "Ask the Tony Kernel whether a phase may start before delegating it to a sub-agent. Returns decision (proceed / block_* / human_required) and allowed.",
        "inputSchema": {
            "type": "object",
            "properties": {"phase": {"type": "string", "enum": ["explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"]}},
            "required": ["phase"],
        },
        "handler": _can_start_phase,
    },
    "kernel_record_delegation": {
        "description": "Record that a phase was delegated to a sub-agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phase": {"type": "string"},
                "sub_agent": {"type": "string"},
                "task_id": {"type": "string"},
            },
            "required": ["phase"],
        },
        "handler": _record_delegation,
    },
    "kernel_record_phase_completion": {
        "description": "Record a completed phase with its artifacts (JSON array of {kind, path, store, hash?, validated?}). Advances the state machine and records a checksum.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phase": {"type": "string"},
                "artifacts": {"type": "string", "description": "JSON array of artifact objects"},
            },
            "required": ["phase", "artifacts"],
        },
        "handler": _record_phase_completion,
    },
    "kernel_verify_phase_checksum": {
        "description": "Verify a phase's artifacts weren't modified since completion. Returns status: valid | modified | missing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phase": {"type": "string"},
                "artifacts": {"type": "string", "description": "JSON array of current artifact objects"},
            },
            "required": ["phase"],
        },
        "handler": _verify_phase_checksum,
    },
    "kernel_add_task": {
        "description": "Register an implementation task in the task ledger.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "description": {"type": "string"},
                "phase": {"type": "string"},
            },
            "required": ["task_id", "description", "phase"],
        },
        "handler": _add_task,
    },
    "kernel_start_task": {
        "description": "Mark a task as in progress (only if its dependencies are complete).",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        "handler": _start_task,
    },
    "kernel_complete_task": {
        "description": "Complete a task with evidence (JSON array of {type, claim, command?, exit_code?, stdout?}). Evidence is mandatory and validated — an empty or invalid list is blocked.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "evidence": {"type": "string", "description": "JSON array of evidence objects"},
            },
            "required": ["task_id", "evidence"],
        },
        "handler": _complete_task,
    },
    "kernel_check_scope": {
        "description": "Check a git diff stays within the allowed files (scope guard).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "git_diff": {"type": "string"},
                "allowed_files": {"type": "string", "description": "JSON array of glob patterns"},
            },
            "required": ["git_diff", "allowed_files"],
        },
        "handler": _check_scope,
    },
    "kernel_get_status": {
        "description": "Get the current kernel state (phase, tasks, retry budgets, checksums, delegations).",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": _get_status,
    },
    "kernel_reset": {
        "description": "Reset the kernel state for this project.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": _reset,
    },
}


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg: dict):
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tony-kernel", "version": "1.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {"name": name, "description": t["description"], "inputSchema": t["inputSchema"]}
                    for name, t in TOOLS.items()
                ]
            },
        }

    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {}) or {}
        tool = TOOLS.get(tool_name)
        if not tool:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"unknown tool: {tool_name}"},
            }
        try:
            result = tool["handler"](args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"error: {exc}"}],
                    "isError": True,
                },
            }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"unknown method: {method}"}}
    return None


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(msg)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()
