#!/usr/bin/env python3
"""TonyMem: local persistent memory MCP server for OpenCode 1.18.22.

Stdlib-only JSON-RPC/MCP server. Storage is project-scoped SQLite with WAL and
FTS5. OpenCode starts local MCP servers with the workspace as cwd, so the
unconfigured database is stored in <workspace>/.tonymem/memory.db.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = os.environ.get("LOCAL_MEMORY_DB") or os.path.join(os.getcwd(), ".tonymem", "memory.db")


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
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'default',
                scope TEXT NOT NULL DEFAULT 'project',
                title TEXT NOT NULL,
                topic_key TEXT,
                type TEXT NOT NULL DEFAULT 'manual',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                lifecycle_status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_topic
                ON observations(project, topic_key)
                WHERE topic_key IS NOT NULL;
            CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
                USING fts5(title, content, content='observations', content_rowid='id');
            CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
                INSERT INTO observations_fts(rowid,title,content) VALUES(new.id,new.title,new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts,rowid,title,content)
                VALUES('delete',old.id,old.title,old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts,rowid,title,content)
                VALUES('delete',old.id,old.title,old.content);
                INSERT INTO observations_fts(rowid,title,content)
                VALUES(new.id,new.title,new.content);
            END;
            """
        )
        conn.commit()
        try:
            conn.execute("ALTER TABLE observations ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'active'")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()


def fts_query(query, mode="all"):
    tokens = [x.replace('"', '""') for x in query.split() if x.strip()]
    if not tokens:
        return '""'
    joiner = " OR " if mode == "any" else " AND "
    return joiner.join(f'"{x}"' for x in tokens)


def mem_save(a):
    title, content = a["title"], a["content"]
    topic = a.get("topic_key")
    project = a.get("project", "default")
    conn = connect()
    try:
        ts = now()
        existed = bool(topic and conn.execute(
            "SELECT 1 FROM observations WHERE project=? AND topic_key=?", (project, topic)
        ).fetchone())
        row = conn.execute(
            """INSERT INTO observations
               (project,scope,title,topic_key,type,content,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(project,topic_key) WHERE topic_key IS NOT NULL
               DO UPDATE SET title=excluded.title, content=excluded.content,
                 type=excluded.type, scope=excluded.scope, updated_at=excluded.updated_at
               RETURNING id""",
            (project, a.get("scope", "project"), title, topic,
             a.get("type", "manual"), content, ts, ts),
        ).fetchone()
        conn.commit()
        return {"id": row["id"], "action": "updated" if existed else "created", "topic_key": topic}
    finally:
        conn.close()


def mem_search(a):
    project, all_projects = a.get("project"), a.get("all_projects", False)
    typ, scope = a.get("type"), a.get("scope")
    conn = connect()
    try:
        sql = """SELECT o.id,o.project,o.title,o.topic_key,o.type,o.scope,
                 o.lifecycle_status,
                 snippet(observations_fts,1,'[',']','...',12) snippet,
                 o.created_at,o.updated_at
                 FROM observations_fts f JOIN observations o ON o.id=f.rowid
                 WHERE observations_fts MATCH ?"""
        params = [fts_query(a["query"], a.get("match_mode", "all"))]
        if project and not all_projects:
            sql += " AND o.project=?"; params.append(project)
        if typ:
            sql += " AND o.type=?"; params.append(typ)
        else:
            sql += " AND o.type != 'prompt-capture'"
        if scope:
            sql += " AND o.scope=?"; params.append(scope)
        sql += " ORDER BY CASE o.lifecycle_status WHEN 'proven' THEN 0 ELSE 1 END, rank LIMIT ?"
        params.append(min(int(a.get("limit", 10)), 20))
        rows = conn.execute(sql, params).fetchall()
        return {"results": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


def mem_get_observation(a):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM observations WHERE id=?", (int(a["id"]),)).fetchone()
        return dict(row) if row else {"error": f"observation {a['id']} not found"}
    finally:
        conn.close()


def mem_update(a):
    fields, params = [], []
    for key in ("title", "content", "type"):
        if a.get(key) is not None:
            fields.append(key + "=?"); params.append(a[key])
    if not fields:
        return {"error": "nothing to update"}
    fields.append("updated_at=?"); params.append(now()); params.append(int(a["id"]))
    conn = connect()
    try:
        cur = conn.execute(f"UPDATE observations SET {','.join(fields)} WHERE id=?", params)
        conn.commit()
        return {"id": int(a["id"]), "action": "updated"} if cur.rowcount else {"error": f"observation {a['id']} not found"}
    finally:
        conn.close()


def mem_context(a):
    project = a.get("project", "default")
    limit, offset = min(int(a.get("limit", 5)), 20), max(int(a.get("offset", 0)), 0)
    conn = connect()
    try:
        if offset:
            rows = conn.execute(
                "SELECT id,project,title,topic_key,type,scope,content,created_at,updated_at "
                "FROM observations WHERE project=? AND type!='prompt-capture' "
                "ORDER BY updated_at DESC LIMIT ? OFFSET ?", (project, limit, offset)
            ).fetchall()
            return {"context": [dict(r) for r in rows], "count": len(rows)}
        rows = conn.execute(
            "SELECT id,project,title,topic_key,type,scope,content,created_at,updated_at "
            "FROM observations WHERE project=? AND type='session-summary' "
            "ORDER BY updated_at DESC LIMIT 1", (project,)
        ).fetchall()
        remaining = limit - len(rows)
        if remaining > 0:
            ids = tuple(r["id"] for r in rows) or (-1,)
            marks = ",".join("?" * len(ids))
            rows += conn.execute(
                f"SELECT id,project,title,topic_key,type,scope,content,created_at,updated_at "
                f"FROM observations WHERE project=? AND type!='prompt-capture' AND id NOT IN ({marks}) "
                f"ORDER BY updated_at DESC LIMIT ?", (project, *ids, remaining)
            ).fetchall()
        return {"context": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


def mem_session_summary(a):
    project, sid = a.get("project", "default"), a.get("session_id")
    topic = f"session/{project}/{sid}" if sid else f"session/{project}/{now()}"
    return mem_save({"title": f"Session summary — {project}", "content": a["content"],
                     "topic_key": topic, "project": project, "type": "session-summary"})


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-") or "topic"


def mem_suggest_topic_key(a):
    base, project = slugify(a["title"]), a.get("project", "default")
    conn = connect()
    try:
        existing = {r[0] for r in conn.execute(
            "SELECT topic_key FROM observations WHERE project=? AND topic_key LIKE ?", (project, base + "%")
        )}
    finally:
        conn.close()
    if base not in existing:
        return {"topic_key": base, "collision": False}
    n = 2
    while f"{base}-{n}" in existing: n += 1
    return {"topic_key": f"{base}-{n}", "collision": True}


def mem_save_prompt(a):
    project, sid = a.get("project", "default"), a.get("session_id", "unknown")
    return mem_save({"title": f"Prompt capture — {project}/{sid}", "content": a["content"],
                     "topic_key": f"prompt/{project}/{sid}", "project": project,
                     "type": "prompt-capture"})


def mem_review(a):
    action, project = a.get("action", "list"), a.get("project", "default")
    conn = connect()
    try:
        if action == "list":
            status = a.get("status")
            if status:
                rows = conn.execute(
                    "SELECT id,project,title,topic_key,type,scope,lifecycle_status,created_at,updated_at "
                    "FROM observations WHERE project=? AND lifecycle_status=? ORDER BY updated_at DESC", (project, status)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id,project,title,topic_key,type,scope,lifecycle_status,created_at,updated_at "
                    "FROM observations WHERE project=? AND lifecycle_status='needs_review' ORDER BY updated_at DESC", (project,)
                ).fetchall()
            return {"results": [dict(r) for r in rows], "count": len(rows)}
        ids = a.get("ids")
        if isinstance(ids, int): ids = [ids]
        if not ids: return {"error": "ids required for update actions"}
        status = {"mark_reviewed": "active", "mark_proven": "proven", "mark_stale": "needs_review"}.get(action)
        if not status: return {"error": f"unknown action: {action}"}
        marks = ",".join("?" * len(ids))
        cur = conn.execute(f"UPDATE observations SET lifecycle_status=?,updated_at=? WHERE id IN ({marks})",
                           [status, now(), *ids])
        conn.commit()
        return {"updated": cur.rowcount}
    finally:
        conn.close()


TOOLS = {
    "mem_save": ("Save or upsert persistent memory; topic_key enables stable project-scoped upserts.", mem_save,
        {"type":"object","properties":{"title":{"type":"string"},"content":{"type":"string"},"topic_key":{"type":"string"},"project":{"type":"string"},"type":{"type":"string"},"scope":{"type":"string"}},"required":["title","content"]}),
    "mem_search": ("Full-text search over memories; returns snippets.", mem_search,
        {"type":"object","properties":{"query":{"type":"string"},"type":{"type":"string"},"project":{"type":"string"},"all_projects":{"type":"boolean"},"scope":{"type":"string"},"match_mode":{"type":"string"},"limit":{"type":"number"}},"required":["query"]}),
    "mem_get_observation": ("Retrieve full memory by id.", mem_get_observation,
        {"type":"object","properties":{"id":{"type":["number","string"]}},"required":["id"]}),
    "mem_update": ("Update title, content or type of an observation.", mem_update,
        {"type":"object","properties":{"id":{"type":["number","string"]},"title":{"type":"string"},"content":{"type":"string"},"type":{"type":"string"}},"required":["id"]}),
    "mem_context": ("Fast recent project context; offset supports pagination.", mem_context,
        {"type":"object","properties":{"project":{"type":"string"},"limit":{"type":"number"},"offset":{"type":"number"}}}),
    "mem_session_summary": ("Save an end-of-session summary, upserted by project/session_id.", mem_session_summary,
        {"type":"object","properties":{"content":{"type":"string"},"project":{"type":"string"},"session_id":{"type":"string"}},"required":["content"]}),
    "mem_suggest_topic_key": ("Suggest a stable collision-free topic key without saving.", mem_suggest_topic_key,
        {"type":"object","properties":{"title":{"type":"string"},"project":{"type":"string"}},"required":["title"]}),
    "mem_save_prompt": ("Capture the latest user prompt for a session.", mem_save_prompt,
        {"type":"object","properties":{"content":{"type":"string"},"project":{"type":"string"},"session_id":{"type":"string"}},"required":["content"]}),
    "mem_review": ("Manage memory lifecycle: list, mark_reviewed, mark_proven, mark_stale.", mem_review,
        {"type":"object","properties":{"action":{"type":"string","enum":["list","mark_reviewed","mark_proven","mark_stale"]},"project":{"type":"string"},"status":{"type":"string","enum":["active","proven","needs_review"]},"ids":{"type":"array","items":{"type":"number"}}},"required":["action"]}),
}


def reply(mid, result=None, error=None):
    out = {"jsonrpc":"2.0", "id":mid}
    if error is not None: out["error"] = error
    else: out["result"] = result
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        reply(mid, {"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"tonymem","version":"1.0.0"}})
    elif method == "notifications/initialized":
        return
    elif method == "ping":
        reply(mid, {})
    elif method == "tools/list":
        reply(mid, {"tools":[{"name":n,"description":d,"inputSchema":s} for n,(d,_,s) in TOOLS.items()]})
    elif method == "tools/call":
        p = msg.get("params", {}); name = p.get("name"); item = TOOLS.get(name)
        if not item:
            return reply(mid, error={"code":-32601,"message":f"unknown tool: {name}"})
        try:
            value = item[1](p.get("arguments") or {})
            reply(mid, {"content":[{"type":"text","text":json.dumps(value,ensure_ascii=False)}]})
        except Exception as exc:
            reply(mid, {"content":[{"type":"text","text":f"error: {exc}"}],"isError":True})
    elif mid is not None:
        reply(mid, error={"code":-32601,"message":f"unknown method: {method}"})


def main():
    init_db()
    for line in sys.stdin:
        if not line.strip(): continue
        try: handle(json.loads(line))
        except json.JSONDecodeError: continue


if __name__ == "__main__": main()
