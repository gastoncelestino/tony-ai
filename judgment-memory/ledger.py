#!/usr/bin/env python3
"""
judgment-memory/ledger.py — persistent memory for Judgment Day outcomes.

Implements the pipeline requested for TonyMem's Judgment Day bridge:

    Decision -> Normalize -> Embedding -> Qdrant -> Future Recall

A judgment record (see schema.json) is:
  1. Written to a local SQLite ledger (`judgment-memory.db`, WAL mode) —
     the durable, queryable source of truth. Same "just a file on disk"
     philosophy as `local-memory/server.py`'s `observations` table.
  2. Normalized into one plain-text passage (normalize()) suitable for
     embedding — task + judges' decisions + the lesson, since the lesson
     is what future recall actually needs to match against.
  3. Embedded via Ollama (same /api/embed contract `code-index/core.py`
     already uses) and upserted into Qdrant as a `jdmem_{project}`
     collection, point payload = the full record.
  4. Recalled later (recall()) by embedding a new task description and
     searching that collection — "we saw a similar problem before" —
     which is what `jd_recall` (server.py) and the judgment-day skill's
     pre-flight recall step call before judges run.

Zero third-party dependencies: SQLite via stdlib `sqlite3`, HTTP via
stdlib `urllib.request` — same constraint as every other Tony-AI local
tool (`local-memory/server.py`, `code-index/core.py`).

Requires Ollama (embeddings) and Qdrant (vector store) running locally,
same as code-index — see judgment-memory/README.md. Both are optional at
import time: write/read to the SQLite ledger always works even if
Ollama/Qdrant are down; only embed()/index()/recall() need them.

CLI:
    python3 ledger.py record --file record.json
    python3 ledger.py recall --task "optimize query" --project default
    python3 ledger.py history --project default --limit 10
    python3 ledger.py stats --project default
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "JUDGMENT_MEMORY_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "judgment-memory.db"),
)
OLLAMA_URL = os.environ.get("TONY_OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("TONY_EMBED_MODEL", "nomic-embed-text")
QDRANT_URL = os.environ.get("TONY_QDRANT_URL", "http://localhost:6333")
FINAL_VALUES = {"approve", "reject", "escalated"}
AGREEMENT_VALUES = {"confirmed", "suspect", "contradiction"}
RECALL_SCORE_THRESHOLD = float(os.environ.get("TONY_RECALL_SCORE_THRESHOLD", "0.5"))


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
        CREATE TABLE IF NOT EXISTS judgments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT 'default',
            task TEXT NOT NULL,
            judge_a_model TEXT,
            judge_a_decision TEXT,
            judge_b_model TEXT,
            judge_b_decision TEXT,
            agreement TEXT,
            winner TEXT,
            confidence REAL,
            final TEXT NOT NULL,
            fix TEXT,
            lesson TEXT,
            source_lineage_id TEXT,
            point_id TEXT,
            evidence_refs TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_execution
            ON judgments(project, execution_id);
        CREATE INDEX IF NOT EXISTS idx_judgments_project
            ON judgments(project, created_at DESC);
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(judgments)")}
    if "evidence_refs" not in columns:
        conn.execute("ALTER TABLE judgments ADD COLUMN evidence_refs TEXT NOT NULL DEFAULT '[]'")
    conn.commit()
    conn.close()


def _record_to_row(record: dict) -> tuple:
    judge_a = record.get("judge_a") or {}
    judge_b = record.get("judge_b") or {}
    evidence_refs = record.get("evidence_refs") or []
    return (
        record["execution_id"], record.get("project", "default"), record["task"],
        judge_a.get("model"), judge_a.get("decision"), judge_b.get("model"), judge_b.get("decision"),
        record.get("agreement"), record.get("winner"), record.get("confidence"), record["final"],
        record.get("fix"), record.get("lesson"), record.get("source_lineage_id"),
        json.dumps(list(dict.fromkeys(evidence_refs)), separators=(",", ":")),
    )


def _decode_row(row: sqlite3.Row) -> dict:
    result = dict(row)
    try:
        result["evidence_refs"] = json.loads(result.get("evidence_refs") or "[]")
    except json.JSONDecodeError:
        result["evidence_refs"] = []
    return result


def save_judgment(record: dict, point_id: str = None) -> dict:
    if "execution_id" not in record or not record["execution_id"]:
        raise ValueError("record.execution_id is required")
    if "task" not in record or not record["task"]:
        raise ValueError("record.task is required")
    final = record.get("final")
    if final not in FINAL_VALUES:
        raise ValueError(f"record.final must be one of {sorted(FINAL_VALUES)}, got {final!r}")
    agreement = record.get("agreement")
    if agreement is not None and agreement not in AGREEMENT_VALUES:
        raise ValueError(f"record.agreement must be one of {sorted(AGREEMENT_VALUES)} or omitted, got {agreement!r}")
    ts = now()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, point_id FROM judgments WHERE project=? AND execution_id=?",
            (record.get("project", "default"), record["execution_id"]),
        ).fetchone()
        values = _record_to_row(record)
        if row:
            conn.execute(
                """UPDATE judgments SET
                    task=?, judge_a_model=?, judge_a_decision=?, judge_b_model=?, judge_b_decision=?,
                    agreement=?, winner=?, confidence=?, final=?, fix=?, lesson=?, source_lineage_id=?,
                    point_id=?, evidence_refs=?, created_at=?
                   WHERE id=?""",
                (*values[2:], point_id or row["point_id"], values[-1], ts, row["id"]),
            )
            conn.commit()
            return {"id": row["id"], "action": "updated", "execution_id": record["execution_id"]}
        cur = conn.execute(
            """INSERT INTO judgments
               (execution_id, project, task, judge_a_model, judge_a_decision, judge_b_model, judge_b_decision,
                agreement, winner, confidence, final, fix, lesson, source_lineage_id, point_id, evidence_refs, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (*values, point_id, ts),
        )
        conn.commit()
        return {"id": cur.lastrowid, "action": "created", "execution_id": record["execution_id"]}
    finally:
        conn.close()


def history(project: str = "default", limit: int = 10, all_projects: bool = False) -> list:
    conn = connect()
    try:
        if all_projects:
            rows = conn.execute("SELECT * FROM judgments ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM judgments WHERE project=? ORDER BY created_at DESC LIMIT ?",
                (project, limit),
            ).fetchall()
        return [_decode_row(r) for r in rows]
    finally:
        conn.close()


def stats(project: str = "default") -> dict:
    conn = connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM judgments WHERE project=?", (project,)).fetchone()["n"]
        by_final = {r["final"]: r["n"] for r in conn.execute(
            "SELECT final, COUNT(*) AS n FROM judgments WHERE project=? GROUP BY final", (project,)
        ).fetchall()}
        by_agreement = {r["agreement"]: r["n"] for r in conn.execute(
            "SELECT agreement, COUNT(*) AS n FROM judgments WHERE project=? AND agreement IS NOT NULL GROUP BY agreement",
            (project,),
        ).fetchall()}
        contradictions = by_agreement.get("contradiction", 0)
        return {
            "project": project,
            "total_judgments": total,
            "by_final": by_final,
            "by_agreement": by_agreement,
            "contradiction_rate": round(contradictions / total, 3) if total else 0.0,
        }
    finally:
        conn.close()


def normalize(record: dict) -> str:
    judge_a = record.get("judge_a") or {}
    judge_b = record.get("judge_b") or {}
    parts = [f"task: {record.get('task', '')}", f"outcome: {record.get('final', '')}"]
    if record.get("agreement"):
        parts.append(f"agreement: {record['agreement']}")
    if judge_a.get("decision"):
        parts.append(f"judge_a ({judge_a.get('model', '?')}): {judge_a['decision']}")
    if judge_b.get("decision"):
        parts.append(f"judge_b ({judge_b.get('model', '?')}): {judge_b['decision']}")
    if record.get("fix"):
        parts.append(f"fix: {record['fix']}")
    if record.get("lesson"):
        parts.append(f"lesson: {record['lesson']}")
        parts.append(record["lesson"])
    return "\n".join(parts)


def embed_texts(texts: list, model: str = EMBED_MODEL, base_url: str = OLLAMA_URL) -> list:
    if not texts:
        return []
    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/embed", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {base_url} for embeddings (model={model}): {exc}. "
            f"Is `ollama serve` running and has `ollama pull {model}` been run?"
        ) from exc
    embeddings = body.get("embeddings")
    if not embeddings:
        raise RuntimeError(f"Ollama returned no embeddings for model={model}: {body}")
    return embeddings


def embedding_dim(model: str = EMBED_MODEL, base_url: str = OLLAMA_URL) -> int:
    return len(embed_texts(["dimension probe"], model=model, base_url=base_url)[0])


def _qdrant_request(method: str, path: str, body: dict = None, base_url: str = QDRANT_URL) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{base_url}{path}", data=data, headers={"Content-Type": "application/json"}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Qdrant {method} {path} failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Qdrant at {base_url}{path}: {exc}. Is Qdrant running? "
            f"(docker run -p 6333:6333 qdrant/qdrant)"
        ) from exc


def collection_name(project: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", project)
    return f"jdmem_{safe}"


def qdrant_ensure_collection(collection: str, dim: int, base_url: str = QDRANT_URL) -> None:
    try:
        _qdrant_request("GET", f"/collections/{collection}", base_url=base_url)
        return
    except RuntimeError:
        pass
    _qdrant_request("PUT", f"/collections/{collection}", {"vectors": {"size": dim, "distance": "Cosine"}}, base_url=base_url)


def qdrant_upsert(collection: str, points: list, base_url: str = QDRANT_URL) -> None:
    if points:
        _qdrant_request("PUT", f"/collections/{collection}/points?wait=true", {"points": points}, base_url=base_url)


def qdrant_search(collection: str, vector: list, limit: int = 5, base_url: str = QDRANT_URL) -> list:
    result = _qdrant_request(
        "POST", f"/collections/{collection}/points/search",
        {"vector": vector, "limit": limit, "with_payload": True}, base_url=base_url
    )
    return result.get("result", [])


def point_id_for(project: str, execution_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"jdmem:{project}:{execution_id}"))


def record_judgment(record: dict, embed_model: str = EMBED_MODEL, ollama_url: str = OLLAMA_URL,
                     qdrant_url: str = QDRANT_URL, index: bool = True) -> dict:
    project = record.get("project", "default")
    pid = point_id_for(project, record["execution_id"])
    ledger_result = save_judgment(record, point_id=pid)
    if not index:
        return {**ledger_result, "indexed": False}
    try:
        text = normalize(record)
        vec = embed_texts([text], model=embed_model, base_url=ollama_url)[0]
        coll = collection_name(project)
        qdrant_ensure_collection(coll, len(vec), base_url=qdrant_url)
        qdrant_upsert(coll, [{"id": pid, "vector": vec, "payload": {**record, "project": project}}], base_url=qdrant_url)
        return {**ledger_result, "indexed": True, "point_id": pid, "collection": coll}
    except RuntimeError as exc:
        return {**ledger_result, "indexed": False, "index_error": str(exc)}


def recall(task: str, project: str = "default", limit: int = 5,
           embed_model: str = EMBED_MODEL, ollama_url: str = OLLAMA_URL, qdrant_url: str = QDRANT_URL) -> dict:
    coll = collection_name(project)
    try:
        vec = embed_texts([task], model=embed_model, base_url=ollama_url)[0]
        hits = qdrant_search(coll, vec, limit=limit, base_url=qdrant_url)
    except RuntimeError as exc:
        return {"available": False, "error": str(exc), "results": []}
    return {
        "available": True,
        "results": [
            {
                "score": h["score"],
                "execution_id": h["payload"].get("execution_id"),
                "task": h["payload"].get("task"),
                "final": h["payload"].get("final"),
                "fix": h["payload"].get("fix"),
                "lesson": h["payload"].get("lesson"),
                "evidence_refs": h["payload"].get("evidence_refs", []),
            }
            for h in hits if h["score"] > RECALL_SCORE_THRESHOLD
        ],
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Tony-AI judgment-memory ledger (Judgment Day <-> TonyMem bridge)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_record = sub.add_parser("record", help="Save (and index) a judgment record")
    p_record.add_argument("--file", required=True, help="Path to a JSON file matching schema.json")
    p_record.add_argument("--no-index", action="store_true", help="Ledger-only, skip embedding/Qdrant")
    p_recall = sub.add_parser("recall", help="Semantic recall of past judgments for a new task")
    p_recall.add_argument("--task", required=True)
    p_recall.add_argument("--project", default="default")
    p_recall.add_argument("--limit", type=int, default=5)
    p_history = sub.add_parser("history", help="Recent judgments for a project (SQLite, no embedding needed)")
    p_history.add_argument("--project", default="default")
    p_history.add_argument("--limit", type=int, default=10)
    p_history.add_argument("--all-projects", action="store_true")
    p_stats = sub.add_parser("stats", help="Aggregate stats for a project")
    p_stats.add_argument("--project", default="default")
    args = parser.parse_args()
    init_db()
    if args.cmd == "record":
        with open(args.file, "r", encoding="utf-8") as f:
            record = json.load(f)
        print(json.dumps(record_judgment(record, index=not args.no_index), indent=2, ensure_ascii=False))
    elif args.cmd == "recall":
        print(json.dumps(recall(args.task, project=args.project, limit=args.limit), indent=2, ensure_ascii=False))
    elif args.cmd == "history":
        print(json.dumps(history(project=args.project, limit=args.limit, all_projects=args.all_projects), indent=2, ensure_ascii=False))
    elif args.cmd == "stats":
        print(json.dumps(stats(project=args.project), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
