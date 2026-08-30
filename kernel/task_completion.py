"""Complete one authorized TaskSet task and persist the resulting state."""

from __future__ import annotations

import argparse
import json
import sys

if __package__ in (None, ""):
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.state import KernelState
from kernel.task_execution_lifecycle import TaskExecutionContext, complete_successful_task
from kernel.task_set_persistence import TaskSetPersistence, TaskSetPersistenceError


def complete_task(
    *,
    project_id: str,
    session_id: str,
    task_id: str,
    evidence: object,
    db_path: str | None = None,
) -> dict:
    persistence = TaskSetPersistence(db_path)
    loaded = persistence.load_for_context(project_id=project_id, session_id=session_id)
    if loaded is None:
        raise TaskSetPersistenceError("SDD state unavailable")

    task_set, persisted = loaded
    pending_state = KernelState(persisted["phase"], "pending").select_next_task(task_set)
    selected = pending_state.get_next_task()
    if selected is None or selected.get("id") != task_id:
        raise TaskSetPersistenceError(
            f"Authorized task does not match current ready task: {task_id}"
        )

    context = TaskExecutionContext(
        project_id=project_id,
        session_id=persisted["session_id"],
        change_id=persisted["change_id"],
        phase=persisted["phase"],
        status=persisted["status"],
        version=persisted["version"],
        task_set=task_set,
    )
    completed = complete_successful_task(
        persistence,
        context,
        pending_state.start_task(),
        evidence,
    )
    return {
        "completed_task_id": task_id,
        "phase": completed.phase,
        "status": completed.status,
        "completed": list(completed.task_set.completed),
        "version": completed.version,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--db-path")
    args = parser.parse_args()

    if not args.complete:
        parser.error("only --complete is available")

    try:
        evidence = json.loads(args.evidence)
        result = complete_task(
            project_id=args.project,
            session_id=args.session_id,
            task_id=args.task_id,
            evidence=evidence,
            db_path=args.db_path,
        )
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except (TaskSetPersistenceError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
