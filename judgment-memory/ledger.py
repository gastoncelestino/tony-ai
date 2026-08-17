"""Persistent Judgment Memory ledger with evidence lineage support."""
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get("JUDGMENT_MEMORY_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "judgment-memory.db"))
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
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_execution ON judgments(project, execution_id);
        CREATE INDEX IF NOT EXISTS idx_judgments_project ON judgments(project, created_at DESC);
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
    refs = record.get("evidence_refs") or []
    return (
        record["execution_id"], record.get("project", "default"), record["task"],
        judge_a.get("model"), judge_a.get("decision"), judge_b.get("model"), judge_b.get("decision"),
        record.get("agreement"), record.get("winner"), record.get("confidence"), record["final"],
        record.get("fix"), record.get("lesson"), record.get("source_lineage_id"),
        json.dumps(list(dict.fromkeys(refs)), separators=(",", ":")),
    )


def save_judgment(record: dict, point_id: str = None) -> dict:
    if not record.get("execution_id"):
        raise ValueError("record.execution_id is required")
    if not record.get("task"):
        raise ValueError("record.task is required")
    if record.get("final") not in FINAL_VALUES:
        raise ValueError(f"record.final must be one of {sorted(FINAL_VALUES)}, got {record.get('final')!r}")
    if record.get("agreement") is not None and record["agreement"] not in AGREEMENT_VALUES:
        raise ValueError(f"record.agreement must be one of {sorted(AGREEMENT_VALUES)} or omitted, got {record['agreement']!r}")
    ts = now()
    conn = connect()
    try:
        row = conn.execute("SELECT id, point_id FROM judgments WHERE project=? AND execution_id=?", (record.get("project", "default"), record["execution_id"])).fetchone()
        values = _record_to_row(record)
        if row:
            conn.execute(
                """UPDATE judgments SET task=?, judge_a_model=?, judge_a_decision=?, judge_b_model=?, judge_b_decision=?,
                agreement=?, winner=?, confidence=?, final=?, fix=?, lesson=?, source_lineage_id=?, point_id=?, evidence_refs=?, created_at=? WHERE id=?""",
                (*values[2:], point_id or row["point_id"], values[-1], ts, row["id"]),
            )
            conn.commit()
            return {"id": row["id"], "action": "updated", "execution_id": record["execution_id"]}
        cur = conn.execute(
            """INSERT INTO judgments
            (execution_id, project, task, judge_a_model, judge_a_decision, judge_b_model, judge_b_decision,
             agreement, winner, confidence, final, fix, lesson, source_lineage_id, point_id, evidence_refs, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (*values[:14], point_id, values[14], ts),
        )
        conn.commit()
        return {"id": cur.lastrowid, "action": "created", "execution_id": record["execution_id"]}
    finally:
        conn.close()


def get_judgment(project: str, execution_id: str) -> dict | None:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM judgments WHERE project=? AND execution_id=?", (project, execution_id)).fetchone()
        if row is None:
            return None
        result = dict(row)
        try:
            result["evidence_refs"] = json.loads(result.get("evidence_refs") or "[]")
        except json.JSONDecodeError:
            result["evidence_refs"] = []
        return result
    finally:
        conn.close()

__all__ = ["connect", "init_db", "save_judgment", "get_judgment"]
