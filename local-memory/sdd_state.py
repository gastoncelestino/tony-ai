#!/usr/bin/env python3
"""Structured SDD state persistence for TonyMem.

SDD workflow state is kept separate from free-form memory observations while
using the same SQLite database. State writes are an internal Python API; the
command line exposes read-only access for the Kernel context provider.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.environ.get(
    "LOCAL_MEMORY_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db"),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_sdd_state(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sdd_state (
            project_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            change_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            status TEXT NOT NULL,
            tasks_json TEXT NOT NULL,
            completed_json TEXT NOT NULL,
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project_id, session_id)
        );

        CREATE TABLE IF NOT EXISTS sdd_state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            change_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            phase TEXT NOT NULL,
            status TEXT NOT NULL,
            tasks_json TEXT NOT NULL,
            completed_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            UNIQUE (project_id, session_id, version)
        );
        """
    )


def _decode_json(value: str, field: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {field} JSON in SDD state") from exc


def _row_to_state(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "project_id": row["project_id"],
        "session_id": row["session_id"],
        "change_id": row["change_id"],
        "phase": row["phase"],
        "status": row["status"],
        "tasks": _decode_json(row["tasks_json"], "tasks"),
        "completed": _decode_json(row["completed_json"], "completed"),
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def get_sdd_state(project_id: str, session_id: str, db_path: str | None = None) -> dict[str, Any] | None:
    conn = connect(db_path)
    try:
        init_sdd_state(conn)
        row = conn.execute(
            "SELECT project_id, session_id, change_id, phase, status, tasks_json, "
            "completed_json, version, updated_at FROM sdd_state "
            "WHERE project_id=? AND session_id=?",
            (project_id, session_id),
        ).fetchone()
        return _row_to_state(row) if row else None
    finally:
        conn.close()


def record_sdd_state(
    *,
    project_id: str,
    session_id: str,
    change_id: str,
    phase: str,
    status: str,
    tasks: list[dict[str, Any]],
    completed: list[str],
    expected_version: int | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Persist a state snapshot and append history atomically.

    expected_version provides optimistic concurrency control. This function
    is intentionally not exposed as an MCP tool; the authoritative workflow
    transition layer decides when to invoke it.
    """
    conn = connect(db_path)
    try:
        init_sdd_state(conn)
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT version FROM sdd_state WHERE project_id=? AND session_id=?",
            (project_id, session_id),
        ).fetchone()
        current_version = current["version"] if current else 0

        if expected_version is not None and current_version != expected_version:
            raise ValueError(
                f"SDD state version conflict: expected {expected_version}, got {current_version}"
            )

        version = current_version + 1
        ts = now()
        tasks_json = json.dumps(tasks, ensure_ascii=False, separators=(",", ":"))
        completed_json = json.dumps(completed, ensure_ascii=False, separators=(",", ":"))

        conn.execute(
            "INSERT INTO sdd_state (project_id, session_id, change_id, phase, status, "
            "tasks_json, completed_json, version, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(project_id, session_id) DO UPDATE SET "
            "change_id=excluded.change_id, phase=excluded.phase, status=excluded.status, "
            "tasks_json=excluded.tasks_json, completed_json=excluded.completed_json, "
            "version=excluded.version, updated_at=excluded.updated_at",
            (project_id, session_id, change_id, phase, status, tasks_json, completed_json, version, ts),
        )
        conn.execute(
            "INSERT INTO sdd_state_history (project_id, session_id, change_id, version, phase, "
            "status, tasks_json, completed_json, recorded_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (project_id, session_id, change_id, version, phase, status, tasks_json, completed_json, ts),
        )
        conn.commit()
        return get_sdd_state(project_id, session_id, db_path) or {}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--get", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    if not args.get:
        parser.error("only --get is available from the command line")

    try:
        state = get_sdd_state(args.project, args.session_id)
        if state is None:
            print(json.dumps({"available": False, "reason": "SDD state unavailable"}))
        else:
            print(json.dumps({"available": True, "state": state}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"available": False, "reason": f"SDD state read failed: {exc}"}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
