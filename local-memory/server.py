#!/usr/bin/env python3
"""
tonymem — a minimal, local-only MCP memory server.

Topic_key-based upserts, per-project scoping, full-text search over saved
observations, exposed as MCP tools so an SDD orchestrator can read/write
persistent context — written from scratch, in ~300 lines of stdlib-only
Python. No build step, no external dependencies, no telemetry, no cloud
sync. Everything lives in one SQLite file on your disk.

Usage: point OpenCode (or any MCP-capable client) at this file with
`python3 server.py` as the local MCP server command. See README.md.

---
Tony-AI fork note: this file adds four tools (mem_context,
mem_session_summary, mem_suggest_topic_key, mem_save_prompt) on top of the
original 4-tool contract (mem_save, mem_search, mem_get_observation,
mem_update). They exist because Tony-AI's AGENTS.md and shared skills
call them by name — everything here is a real implementation over the same
`observations` table, nothing is stubbed. No prompt/skill/command file had
to change: the tool names match exactly what those files already call.
"""

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get(
    "LOCAL_MEMORY_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db"),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project    TEXT NOT NULL DEFAULT 'default',
            scope      TEXT NOT NULL DEFAULT 'project',
            title      TEXT NOT NULL,
            topic_key  TEXT,
            type       TEXT NOT NULL DEFAULT 'manual',
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_topic
            ON observations(project, topic_key)
            WHERE topic_key IS NOT NULL;

        CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
            USING fts5(title, content, content='observations', content_rowid='id');

        CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
            INSERT INTO observations_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
            INSERT INTO observations_fts(observations_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
            INSERT INTO observations_fts(observations_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO observations_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        """
    )
    conn.commit()
    conn.close()


def fts_query(query: str, match_mode: str = "all") -> str:
    tokens = [t.replace('"', '""') for t in query.split() if t.strip()]
    if not tokens:
        return '""'
    joiner = " AND " if match_mode != "any" else " OR "
    return joiner.join(f'"{t}"' for t in tokens)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def mem_save(args: dict) -> dict:
    title = args["title"]
    content = args["content"]
    topic_key = args.get("topic_key")
    project = args.get("project", "default")
    type_ = args.get("type", "manual")
    scope = args.get("scope", "project")
    ts = now()

    conn = connect()
    try:
        if topic_key:
            row = conn.execute(
                "SELECT id FROM observations WHERE project=? AND topic_key=?",
                (project, topic_key),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE observations SET title=?, content=?, type=?, scope=?, updated_at=? WHERE id=?",
                    (title, content, type_, scope, ts, row["id"]),
                )
                conn.commit()
                return {"id": row["id"], "action": "updated", "topic_key": topic_key}

        cur = conn.execute(
            "INSERT INTO observations (project, scope, title, topic_key, type, content, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (project, scope, title, topic_key, type_, content, ts, ts),
        )
        conn.commit()
        return {"id": cur.lastrowid, "action": "created", "topic_key": topic_key}
    finally:
        conn.close()


def mem_search(args: dict) -> dict:
    query = args["query"]
    limit = min(int(args.get("limit", 10)), 20)
    project = args.get("project")
    all_projects = args.get("all_projects", False)
    type_ = args.get("type")
    scope = args.get("scope")
    match_mode = args.get("match_mode", "all")

    conn = connect()
    try:
        sql = (
            "SELECT o.id, o.project, o.title, o.topic_key, o.type, o.scope, "
            "       snippet(observations_fts, 1, '[', ']', '...', 12) AS snippet, "
            "       o.created_at, o.updated_at "
            "FROM observations_fts f "
            "JOIN observations o ON o.id = f.rowid "
            "WHERE observations_fts MATCH ?"
        )
        params = [fts_query(query, match_mode)]

        if not all_projects and project:
            sql += " AND o.project = ?"
            params.append(project)
        if type_:
            sql += " AND o.type = ?"
            params.append(type_)
        else:
            # prompt-capture entries are internal (mem_save_prompt bookkeeping),
            # not decisions/discoveries — keep them out of default search noise
            # unless the caller explicitly asks for that type.
            sql += " AND o.type != 'prompt-capture'"
        if scope:
            sql += " AND o.scope = ?"
            params.append(scope)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return {"results": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


def mem_get_observation(args: dict) -> dict:
    obs_id = int(args["id"])
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM observations WHERE id=?", (obs_id,)).fetchone()
        if not row:
            return {"error": f"observation {obs_id} not found"}
        return dict(row)
    finally:
        conn.close()


def mem_update(args: dict) -> dict:
    obs_id = int(args["id"])
    ts = now()
    fields, params = [], []
    for key in ("title", "content", "type"):
        if key in args and args[key] is not None:
            fields.append(f"{key}=?")
            params.append(args[key])
    if not fields:
        return {"error": "nothing to update"}
    fields.append("updated_at=?")
    params.append(ts)
    params.append(obs_id)

    conn = connect()
    try:
        cur = conn.execute(f"UPDATE observations SET {', '.join(fields)} WHERE id=?", params)
        conn.commit()
        if cur.rowcount == 0:
            return {"error": f"observation {obs_id} not found"}
        return {"id": obs_id, "action": "updated"}
    finally:
        conn.close()


def mem_context(args: dict) -> dict:
    """Recent session history for a project — cheap, no query needed.

    Mirrors what the AGENTS.md protocol expects from `mem_context`: a fast
    look at what happened recently (session summaries first, then other
    recent observations) before falling back to a full mem_search.
    """
    project = args.get("project", "default")
    limit = min(int(args.get("limit", 5)), 20)

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, project, title, topic_key, type, scope, content, created_at, updated_at "
            "FROM observations WHERE project=? AND type='session-summary' "
            "ORDER BY updated_at DESC LIMIT 1",
            (project,),
        ).fetchall()

        remaining = limit - len(rows)
        if remaining > 0:
            exclude_ids = tuple(r["id"] for r in rows) or (-1,)
            placeholders = ",".join("?" * len(exclude_ids))
            rows += conn.execute(
                f"SELECT id, project, title, topic_key, type, scope, content, created_at, updated_at "
                f"FROM observations WHERE project=? AND type != 'prompt-capture' AND id NOT IN ({placeholders}) "
                f"ORDER BY updated_at DESC LIMIT ?",
                (project, *exclude_ids, remaining),
            ).fetchall()

        return {"context": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


def mem_session_summary(args: dict) -> dict:
    """Save an end-of-session summary. Upserts per (project, session_id) so
    re-summarizing the same session updates instead of piling up duplicates;
    a new session_id (or none) starts a fresh entry.
    """
    content = args["content"]
    project = args.get("project", "default")
    session_id = args.get("session_id")
    topic_key = f"session/{project}/{session_id}" if session_id else f"session/{project}/{now()}"

    return mem_save(
        {
            "title": f"Session summary — {project}",
            "content": content,
            "topic_key": topic_key,
            "project": project,
            "type": "session-summary",
            "scope": "project",
        }
    )


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    return slug.strip("-") or "topic"


def mem_suggest_topic_key(args: dict) -> dict:
    """Suggest a stable topic_key for a title, avoiding collisions with
    existing keys for the same project. Pure heuristic, no content saved.
    """
    title = args["title"]
    project = args.get("project", "default")
    base = slugify(title)

    conn = connect()
    try:
        existing = {
            row["topic_key"]
            for row in conn.execute(
                "SELECT topic_key FROM observations WHERE project=? AND topic_key LIKE ?",
                (project, f"{base}%"),
            ).fetchall()
        }
    finally:
        conn.close()

    if base not in existing:
        return {"topic_key": base, "collision": False}

    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return {"topic_key": f"{base}-{n}", "collision": True}


def mem_save_prompt(args: dict) -> dict:
    """Record the raw user prompt for a session, best-effort. Kept separate
    from `observations` full-text noise (type='prompt-capture') so it never
    surfaces in normal mem_search results unless explicitly requested via
    type filter. Upserts per (project, session_id) — only the latest prompt
    for a session is kept, matching what mem_context needs.
    """
    content = args["content"]
    project = args.get("project", "default")
    session_id = args.get("session_id", "unknown")

    return mem_save(
        {
            "title": f"Prompt capture — {project}/{session_id}",
            "content": content,
            "topic_key": f"prompt/{project}/{session_id}",
            "project": project,
            "type": "prompt-capture",
            "scope": "project",
        }
    )


TOOLS = {
    "mem_save": {
        "description": "Save or upsert a piece of persistent memory. Pass topic_key to upsert (saving again with the same project+topic_key updates instead of duplicating).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "topic_key": {"type": "string", "description": "Stable key for upserts, e.g. sdd/{change}/proposal"},
                "project": {"type": "string", "description": "Project name, default 'default'"},
                "type": {"type": "string", "description": "decision | architecture | bugfix | pattern | manual, etc."},
                "scope": {"type": "string", "description": "project | personal"},
            },
            "required": ["title", "content"],
        },
        "handler": mem_save,
    },
    "mem_search": {
        "description": "Full-text search over saved memories. Returns truncated snippets — use mem_get_observation for full content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "type": {"type": "string"},
                "project": {"type": "string"},
                "all_projects": {"type": "boolean"},
                "scope": {"type": "string"},
                "match_mode": {"type": "string", "description": "'all' (default) or 'any'"},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
        "handler": mem_search,
    },
    "mem_get_observation": {
        "description": "Retrieve the full content of a saved observation by id (search results are truncated).",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": ["number", "string"]}},
            "required": ["id"],
        },
        "handler": mem_get_observation,
    },
    "mem_update": {
        "description": "Update an existing observation by id (title/content/type).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": ["number", "string"]},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "type": {"type": "string"},
            },
            "required": ["id"],
        },
        "handler": mem_update,
    },
    "mem_context": {
        "description": "Fast recent-session lookup for a project (latest session summary + most recent observations). Cheaper than mem_search — call this first when the user references past work.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name, default 'default'"},
                "limit": {"type": "number", "description": "Max items to return, default 5"},
            },
            "required": [],
        },
        "handler": mem_context,
    },
    "mem_session_summary": {
        "description": "Save an end-of-session summary (Goal/Instructions/Discoveries/Accomplished/Next Steps/Relevant Files). Upserts per (project, session_id).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "project": {"type": "string"},
                "session_id": {"type": "string", "description": "Stable per-session id for upserting; omit to always create a new entry"},
            },
            "required": ["content"],
        },
        "handler": mem_session_summary,
    },
    "mem_suggest_topic_key": {
        "description": "Suggest a stable, collision-free topic_key slug for a title, scoped to a project. Does not save anything.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "project": {"type": "string"},
            },
            "required": ["title"],
        },
        "handler": mem_suggest_topic_key,
    },
    "mem_save_prompt": {
        "description": "Record the raw user prompt for a session, best-effort, so later mem_context calls have prompt context. Upserts per (project, session_id) — only the latest prompt is kept.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "project": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["content"],
        },
        "handler": mem_save_prompt,
    },
}

# ---------------------------------------------------------------------------
# MCP JSON-RPC over stdio (newline-delimited JSON, no external deps)
# ---------------------------------------------------------------------------

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
                "serverInfo": {"name": "tonymem", "version": "1.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None  # notification, no response

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
    init_db()
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
