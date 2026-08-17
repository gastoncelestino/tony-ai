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
        project = record.get("project", "default")
        row = conn.execute(
            "SELECT id, point_id FROM judgments WHERE project=? AND execution_id=?",
            (project, record["execution_id"]),
        ).fetchone()
        values = _record_to_row(record)
        if row:
            conn.execute(
                """UPDATE judgments SET
                    task=?, judge_a_model=?, judge_a_decision=?, judge_b_model=?, judge_b_decision=?,
                    agreement=?, winner=?, confidence=?, final=?, fix=?, lesson=?, source_lineage_id=?,
                    point_id=?, evidence_refs=?, created_at=?
                   WHERE id=?""",
                (*values[2:14], point_id or row["point_id"], values[14], ts, row["id"]),
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
    rows = history(project=project, limit=100000)
    by_final = {value: 0 for value in FINAL_VALUES}
    by_agreement = {value: 0 for value in AGREEMENT_VALUES}
    for row in rows:
        if row.get("final") in by_final:
            by_final[row["final"]] += 1
        if row.get("agreement") in by_agreement:
            by_agreement[row["agreement"]] += 1
    total = len(rows)
    return {
        "total_judgments": total,
        "by_final": by_final,
        "by_agreement": by_agreement,
        "contradiction_rate": by_agreement["contradiction"] / total if total else 0.0,
    }


__all__ = ["connect", "init_db", "save_judgment", "history", "stats"]
