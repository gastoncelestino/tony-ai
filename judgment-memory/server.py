#!/usr/bin/env python3
"""
judgment-memory/server.py — MCP tool server exposing ledger.py's pipeline.

Same minimal MCP-over-stdio contract as `local-memory/server.py` (no
external deps, newline-delimited JSON-RPC), just wrapping a different
table. Point OpenCode at this file as a second local MCP server — it does
not replace tonymem/local-memory, it sits next to it (see opencode.json's
`mcp.judgment-memory` block and TONY-AI-INSTALL.md).

Tools:
  jd_recall  — semantic search over past judgments for a task description.
               Call this BEFORE launching Judgment Day (see
               skills/judgment-day/SKILL.md step 1).
  jd_record  — persist a finished judgment (ledger write + embed + Qdrant
               upsert). Call this AFTER a lineage reaches a terminal state
               (approved/escalated), from the parent orchestrator only —
               same "only the parent writes the ledger" rule as
               review-ledger-contract.md.
  jd_history — recent judgments for a project, SQLite-only (no embedding
               dependency, always available even if Qdrant/Ollama are down).
  jd_stats   — aggregate counts (by outcome, by agreement, contradiction
               rate) for a project.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402

TOOLS = {
    "jd_recall": {
        "description": (
            "Semantic recall of past Judgment Day outcomes similar to a new task. "
            "Call before launching judges — if a close match exists, use its 'lesson' "
            "and 'fix' as context for the judges instead of relitigating from scratch. "
            "Degrades gracefully (available=false) if Ollama/Qdrant aren't running."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "project": {"type": "string", "description": "default 'default'"},
                "limit": {"type": "number", "description": "default 5"},
            },
            "required": ["task"],
        },
        "handler": lambda args: ledger.recall(
            args["task"], project=args.get("project", "default"), limit=int(args.get("limit", 5))
        ),
    },
    "jd_record": {
        "description": (
            "Persist a completed judgment record: ledger write (SQLite) + normalize + "
            "embed + Qdrant upsert, so future jd_recall calls can find it. Only call "
            "this from the parent orchestrator once a lineage reaches a terminal state "
            "(final: approve | reject | escalated). Pass the full record per schema.json."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "execution_id": {"type": "string"},
                "project": {"type": "string"},
                "task": {"type": "string"},
                "judge_a": {"type": "object", "properties": {"model": {"type": "string"}, "decision": {"type": "string"}}},
                "judge_b": {"type": "object", "properties": {"model": {"type": "string"}, "decision": {"type": "string"}}},
                "agreement": {"type": "string", "description": "confirmed | suspect | contradiction"},
                "winner": {"type": "string"},
                "confidence": {"type": "number"},
                "final": {"type": "string", "description": "approve | reject | escalated"},
                "fix": {"type": "string"},
                "lesson": {"type": "string"},
                "source_lineage_id": {"type": "string"},
            },
            "required": ["execution_id", "task", "final"],
        },
        "handler": lambda args: ledger.record_judgment(args),
    },
    "jd_history": {
        "description": "Recent judgment records for a project, most recent first. SQLite-only, no embedding dependency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "limit": {"type": "number", "description": "default 10"},
                "all_projects": {"type": "boolean"},
            },
            "required": [],
        },
        "handler": lambda args: {
            "results": ledger.history(
                project=args.get("project", "default"),
                limit=int(args.get("limit", 10)),
                all_projects=bool(args.get("all_projects", False)),
            )
        },
    },
    "jd_stats": {
        "description": "Aggregate stats for a project: total judgments, breakdown by outcome and agreement, contradiction rate.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
            "required": [],
        },
        "handler": lambda args: ledger.stats(project=args.get("project", "default")),
    },
}


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "judgment-memory", "version": "1.0.0"},
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
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"unknown tool: {tool_name}"}}
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
                "result": {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True},
            }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"unknown method: {method}"}}
    return None


def main() -> None:
    ledger.init_db()
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
