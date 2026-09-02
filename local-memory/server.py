#!/usr/bin/env python3
"""TonyMem: local persistent memory MCP server for OpenCode 1.18.22.

Stdlib-only JSON-RPC/MCP server. Storage is project-scoped SQLite with WAL and
FTS5. The database lives in Tony-AI's existing local-memory directory.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = os.environ.get("LOCAL_MEMORY_DB") or os.path.join(
os.path.dirname(os.path.abspath(__file__)), "memory.db"
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    conn = connect()
    try:
        conn.executescript("""
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
            title, content, topic_key, content='observations', content_rowid='id'
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
        """)
        conn.commit()
    finally:
        conn.close()


def result(value):
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def error(message):
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def args_required(args, names):
    missing = [name for name in names if not args.get(name)]
    if missing:
        raise ValueError("Missing required arguments: " + ", ".join(missing))


def save(args):
    args_required(args, ["project", "title", "content"])
    ts = now()
    project = args["project"]
    topic_key = args.get("topic_key")
    conn = connect()
    try:
        if topic_key:
            row = conn.execute(
                "SELECT id FROM observations WHERE project=? AND topic_key=?",
                (project, topic_key),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE observations SET scope=?, title=?, type=?, content=?, updated_at=?, lifecycle_status=? WHERE id=?",
                    (args.get("scope", "project"), args["title"], args.get("type", "fact"), args["content"], ts, args.get("lifecycle_status", "active"), row["id"]),
                )
                conn.commit()
                return {"id": row["id"], "updated": True}
        cur = conn.execute(
            "INSERT INTO observations(project, scope, title, topic_key, type, content, created_at, updated_at, lifecycle_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project, args.get("scope", "project"), args["title"], topic_key, args.get("type", "fact"), args["content"], ts, ts, args.get("lifecycle_status", "active")),
        )
        conn.commit()
        return {"id": cur.lastrowid, "created": True}
    finally:
        conn.close()


def search(args):
    args_required(args, ["project", "query"])
    limit = min(max(int(args.get("limit", 10)), 1), 50)
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT o.* FROM observations o
               JOIN observations_fts f ON f.rowid=o.id
               WHERE o.project=? AND o.lifecycle_status='active'
                 AND observations_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (args["project"], args["query"], limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_observation(args):
    args_required(args, ["project", "id"])
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


def update(args):
    args_required(args, ["project", "id"])
    allowed = {"scope", "title", "topic_key", "type", "content", "lifecycle_status"}
    changes = {k: args[k] for k in allowed if k in args}
    if not changes:
        raise ValueError("No fields to update")
    changes["updated_at"] = now()
    conn = connect()
    try:
        assignments = ", ".join(f"{key}=?" for key in changes)
        values = list(changes.values()) + [int(args["id"]), args["project"]]
        cur = conn.execute(
            f"UPDATE observations SET {assignments} WHERE id=? AND project=?",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("Observation not found")
        return {"updated": True, "id": int(args["id"])}
    finally:
        conn.close()


def context(args):
    args_required(args, ["project"])
    limit = min(max(int(args.get("limit", 20)), 1), 100)
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM observations WHERE project=? AND lifecycle_status='active' ORDER BY updated_at DESC LIMIT ?",
            (args["project"], limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def session_summary(args):
    args_required(args, ["project", "session_id", "summary"])
    return save({
        "project": args["project"],
        "scope": "session",
        "title": args.get("title") or f"Session {args['session_id']}",
        "topic_key": f"session:{args['session_id']}",
        "type": "session_summary",
        "content": args["summary"],
    })


def suggest_topic_key(args):
    args_required(args, ["title"])
    value = re.sub(r"[^a-z0-9]+", "-", args["title"].lower()).strip("-")
    return {"topic_key": value[:120]}


def save_prompt(args):
    args_required(args, ["project", "prompt"])
    return save({
        "project": args["project"],
        "scope": "prompt",
        "title": args.get("title") or "Prompt capture",
        "topic_key": args.get("topic_key"),
        "type": "prompt_capture",
        "content": args["prompt"],
    })


def review(args):
    args_required(args, ["project", "id", "lifecycle_status"])
    return update({
        "project": args["project"],
        "id": args["id"],
        "lifecycle_status": args["lifecycle_status"],
    })

TOOLS = [
    {"name": "mem_save", "description": "Save or update durable project memory.", "inputSchema": {"type": "object", "required": ["project", "title", "content"], "properties": {"project": {"type": "string"}, "scope": {"type": "string"}, "title": {"type": "string"}, "topic_key": {"type": "string"}, "type": {"type": "string"}, "content": {"type": "string"}, "lifecycle_status": {"type": "string"}}}},
    {"name": "mem_search", "description": "Search active project memory with FTS5.", "inputSchema": {"type": "object", "required": ["project", "query"], "properties": {"project": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "mem_get_observation", "description": "Get one memory observation by id.", "inputSchema": {"type": "object", "required": ["project", "id"], "properties": {"project": {"type": "string"}, "id": {"type": "integer"}}}},
    {"name": "mem_update", "description": "Update one project memory observation.", "inputSchema": {"type": "object", "required": ["project", "id"], "properties": {"project": {"type": "string"}, "id": {"type": "integer"}, "scope": {"type": "string"}, "title": {"type": "string"}, "topic_key": {"type": "string"}, "type": {"type": "string"}, "content": {"type": "string"}, "lifecycle_status": {"type": "string"}}}},
    {"name": "mem_context", "description": "Return the most recently updated active project memories.", "inputSchema": {"type": "object", "required": ["project"], "properties": {"project": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "mem_session_summary", "description": "Persist a compact session summary.", "inputSchema": {"type": "object", "required": ["project", "session_id", "summary"], "properties": {"project": {"type": "string"}, "session_id": {"type": "string"}, "summary": {"type": "string"}, "title": {"type": "string"}}}},
    {"name": "mem_suggest_topic_key", "description": "Suggest a stable topic key for durable memory.", "inputSchema": {"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}}},
    {"name": "mem_save_prompt", "description": "Explicitly persist a prompt capture.", "inputSchema": {"type": "object", "required": ["project", "prompt"], "properties": {"project": {"type": "string"}, "prompt": {"type": "string"}, "title": {"type": "string"}, "topic_key": {"type": "string"}}}},
    {"name": "mem_review", "description": "Change the lifecycle status of a memory observation.", "inputSchema": {"type": "object", "required": ["project", "id", "lifecycle_status"], "properties": {"project": {"type": "string"}, "id": {"type": "integer"}, "lifecycle_status": {"type": "string"}}}},
]

DISPATCH = {
    "mem_save": save,
    "mem_search": search,
    "mem_get_observation": get_observation,
    "mem_update": update,
    "mem_context": context,
    "mem_session_summary": session_summary,
    "mem_suggest_topic_key": suggest_topic_key,
    "mem_save_prompt": save_prompt,
    "mem_review": review,
}


def handle(request):
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "tonymem", "version": "1.0.0"}}}
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
            return {"jsonrpc": "2.0", "id": request_id, "result": error(f"Unknown tool: {name}")}
        try:
            return {"jsonrpc": "2.0", "id": request_id, "result": result(fn(args))}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": error(str(exc))}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    init_db()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            response = handle(json.loads(line))
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
