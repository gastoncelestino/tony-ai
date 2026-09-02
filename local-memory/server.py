#!/usr/bin/env python3
"""TonyMem — local durable project memory for OpenCode 1.18.22.

TonyMem is deliberately narrower than the Tony Kernel:
- Tony Kernel owns workflow state, authorization, execution and evidence.
- TonyMem owns durable project knowledge that is useful across sessions.

The server is a stdlib-only MCP JSON-RPC process backed by SQLite/WAL/FTS5.
It does not capture prompts, tool calls or execution traces automatically.
Those belong to the Execution Graph and Kernel layers.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = os.environ.get("LOCAL_MEMORY_DB") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "memory.db"
)

LIFECYCLE_STATUSES = {"active", "proven", "needs_review"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'project',
                title TEXT NOT NULL,
                topic_key TEXT,
                type TEXT NOT NULL DEFAULT 'fact',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                lifecycle_status TEXT NOT NULL DEFAULT 'active'
            );

            CREATE UNIQUE INDEX IF NOT EXISTS observations_project_topic
                ON observations(project, topic_key)
                WHERE topic_key IS NOT NULL;

            CREATE INDEX IF NOT EXISTS observations_project_updated
                ON observations(project, updated_at DESC);

            CREATE INDEX IF NOT EXISTS observations_project_status
                ON observations(project, lifecycle_status);

            CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
                title, content, topic_key,
                content='observations', content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
                INSERT INTO observations_fts(rowid, title, content, topic_key)
                VALUES (new.id, new.title, new.content, new.topic_key);
            END;

            CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts, rowid, title, content, topic_key)
                VALUES ('delete', old.id, old.title, old.content, old.topic_key);
            END;

            CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts, rowid, title, content, topic_key)
                VALUES ('delete', old.id, old.title, old.content, old.topic_key);
                INSERT INTO observations_fts(rowid, title, content, topic_key)
                VALUES (new.id, new.title, new.content, new.topic_key);
            END;
            """
        )
        conn.commit()
    finally:
        conn.close()


def require(args: dict, names: list[str]) -> None:
    missing = [name for name in names if not args.get(name)]
    if missing:
        raise ValueError("Missing required arguments: " + ", ".join(missing))


def lifecycle(value: str) -> str:
    if value not in LIFECYCLE_STATUSES:
        raise ValueError(
            "Invalid lifecycle_status; expected one of: "
            + ", ".join(sorted(LIFECYCLE_STATUSES))
        )
    return value


def save(args: dict) -> dict:
    require(args, ["project", "title", "content"])
    project = args["project"]
    topic_key = args.get("topic_key") or None
    status = lifecycle(args.get("lifecycle_status", "active"))
    ts = now()

    conn = connect()
    try:
        if topic_key:
            existing = conn.execute(
                "SELECT id FROM observations WHERE project=? AND topic_key=?",
                (project, topic_key),
            ).fetchone()
            action = "updated" if existing else "created"
        else:
            existing = None
            action = "created"

        if topic_key:
            row = conn.execute(
                """
                INSERT INTO observations
                    (project, scope, title, topic_key, type, content,
                     created_at, updated_at, lifecycle_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project, topic_key) WHERE topic_key IS NOT NULL
                DO UPDATE SET
                    scope=excluded.scope,
                    title=excluded.title,
                    type=excluded.type,
                    content=excluded.content,
                    updated_at=excluded.updated_at,
                    lifecycle_status=excluded.lifecycle_status
                RETURNING id
                """,
                (
                    project,
                    args.get("scope", "project"),
                    args["title"],
                    topic_key,
                    args.get("type", "fact"),
                    args["content"],
                    ts,
                    ts,
                    status,
                ),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO observations
                    (project, scope, title, topic_key, type, content,
                     created_at, updated_at, lifecycle_status)
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    project,
                    args.get("scope", "project"),
                    args["title"],
                    args.get("type", "fact"),
                    args["content"],
                    ts,
                    ts,
                    status,
                ),
            ).fetchone()

        conn.commit()
        return {"id": int(row["id"]), "action": action, "topic_key": topic_key}
    finally:
        conn.close()


def search(args: dict) -> dict:
    require(args, ["project", "query"])
    limit = min(max(int(args.get("limit", 10)), 1), 50)
    query = args["query"].strip()
    if not query:
        return {"results": [], "count": 0}

    # Quote tokens so user text is treated as terms, not raw FTS5 syntax.
    tokens = [token.replace('"', '""') for token in query.split() if token]
    fts = " AND ".join(f'"{token}"' for token in tokens)

    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT o.id, o.project, o.scope, o.title, o.topic_key, o.type,
                   o.content, o.lifecycle_status, o.created_at, o.updated_at,
                   snippet(observations_fts, 1, '[', ']', '…', 12) AS snippet
            FROM observations_fts
            JOIN observations o ON o.id = observations_fts.rowid
            WHERE o.project=?
              AND o.lifecycle_status != 'needs_review'
              AND observations_fts MATCH ?
            ORDER BY
                CASE o.lifecycle_status WHEN 'proven' THEN 0 ELSE 1 END,
                rank,
                o.updated_at DESC
            LIMIT ?
            """,
            (args["project"], fts, limit),
        ).fetchall()
        return {"results": [dict(row) for row in rows], "count": len(rows)}
    finally:
        conn.close()


def get_observation(args: dict) -> dict:
    require(args, ["project", "id"])
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM observations WHERE project=? AND id=?",
            (args["project"], int(args["id"])),
        ).fetchone()
        if not row:
            raise ValueError("Observation not found")
        return dict(row)
    finally:
        conn.close()


def update(args: dict) -> dict:
    require(args, ["project", "id"])
    allowed = {"scope", "title", "topic_key", "type", "content", "lifecycle_status"}
    changes = {key: args[key] for key in allowed if key in args}
    if "lifecycle_status" in changes:
        changes["lifecycle_status"] = lifecycle(changes["lifecycle_status"])
    if "topic_key" in changes and not changes["topic_key"]:
        changes["topic_key"] = None
    if not changes:
        raise ValueError("No fields to update")

    changes["updated_at"] = now()
    assignments = ", ".join(f"{key}=?" for key in changes)
    values = list(changes.values()) + [int(args["id"]), args["project"]]

    conn = connect()
    try:
        cur = conn.execute(
            f"UPDATE observations SET {assignments} WHERE id=? AND project=?",
            values,
        )
        if cur.rowcount == 0:
            raise ValueError("Observation not found")
        conn.commit()
        return {"updated": True, "id": int(args["id"])}
    finally:
        conn.close()


def context(args: dict) -> dict:
    require(args, ["project"])
    limit = min(max(int(args.get("limit", 20)), 1), 100)
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM observations
            WHERE project=? AND lifecycle_status='active'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args["project"], limit),
        ).fetchall()
        return {"observations": [dict(row) for row in rows], "count": len(rows)}
    finally:
        conn.close()


def suggest_topic_key(args: dict) -> dict:
    require(args, ["title"])
    value = re.sub(r"[^a-z0-9]+", "-", args["title"].lower()).strip("-")
    return {"topic_key": value[:120]}


def review(args: dict) -> dict:
    require(args, ["project", "id", "lifecycle_status"])
    return update({
        "project": args["project"],
        "id": args["id"],
        "lifecycle_status": args["lifecycle_status"],
    })


TOOLS = [
    {
        "name": "mem_save",
        "description": "Save or update durable project knowledge. Use topic_key for stable facts or decisions.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "title", "content"],
            "properties": {
                "project": {"type": "string"},
                "scope": {"type": "string", "default": "project"},
                "title": {"type": "string"},
                "topic_key": {"type": "string"},
                "type": {"type": "string", "default": "fact"},
                "content": {"type": "string"},
                "lifecycle_status": {"type": "string", "enum": sorted(LIFECYCLE_STATUSES), "default": "active"},
            },
        },
    },
    {
        "name": "mem_search",
        "description": "Search durable project knowledge with FTS5.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "query"],
            "properties": {
                "project": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
        },
    },
    {
        "name": "mem_get_observation",
        "description": "Get one durable memory observation by id.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "id"],
            "properties": {"project": {"type": "string"}, "id": {"type": "integer"}},
        },
    },
    {
        "name": "mem_update",
        "description": "Update one durable project memory observation.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "id"],
            "properties": {
                "project": {"type": "string"},
                "id": {"type": "integer"},
                "scope": {"type": "string"},
                "title": {"type": "string"},
                "topic_key": {"type": "string"},
                "type": {"type": "string"},
                "content": {"type": "string"},
                "lifecycle_status": {"type": "string", "enum": sorted(LIFECYCLE_STATUSES)},
            },
        },
    },
    {
        "name": "mem_context",
        "description": "Return recent active durable project memories. Nothing is injected automatically.",
        "inputSchema": {
            "type": "object",
            "required": ["project"],
            "properties": {"project": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
        },
    },
    {
        "name": "mem_suggest_topic_key",
        "description": "Suggest a stable topic key without saving anything.",
        "inputSchema": {
            "type": "object",
            "required": ["title"],
            "properties": {"title": {"type": "string"}},
        },
    },
    {
        "name": "mem_review",
        "description": "Mark a memory observation active, proven, or needing review.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "id", "lifecycle_status"],
            "properties": {
                "project": {"type": "string"},
                "id": {"type": "integer"},
                "lifecycle_status": {"type": "string", "enum": sorted(LIFECYCLE_STATUSES)},
            },
        },
    },
]

DISPATCH = {
    "mem_save": save,
    "mem_search": search,
    "mem_get_observation": get_observation,
    "mem_update": update,
    "mem_context": context,
    "mem_suggest_topic_key": suggest_topic_key,
    "mem_review": review,
}


def mcp_result(value: object) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def mcp_error(message: str) -> dict:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def handle(request: dict) -> dict:
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tonymem", "version": "2.0.0"},
            },
        }
    if method in {"notifications/initialized", "ping"}:
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = DISPATCH.get(name)
        if not fn:
            return {"jsonrpc": "2.0", "id": request_id, "result": mcp_error(f"Unknown tool: {name}")}
        try:
            return {"jsonrpc": "2.0", "id": request_id, "result": mcp_result(fn(args))}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": mcp_error(str(exc))}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    init_db()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            response = handle(json.loads(line))
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
