"""Bootstrap and finalize the first TaskSet for an OpenCode session."""

from __future__ import annotations

import argparse
import json
import sys

if __package__ in (None, ""):
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.task_set import TaskSet
from kernel.task_set_persistence import TaskSetPersistence, TaskSetPersistenceError

BOOTSTRAP_TASK_ID = "__tony_bootstrap_decompose__"
BOOTSTRAP_DESCRIPTION = "decompose task graph"
BOOTSTRAP_PHASE = "bootstrap"


def prepare(*, project_id: str, session_id: str, db_path: str | None = None) -> dict:
    persistence = TaskSetPersistence(db_path)
    if persistence.load(project_id=project_id, session_id=session_id) is not None:
        raise TaskSetPersistenceError("SDD state already exists")
    task_set = TaskSet(
        (
            {
                "id": BOOTSTRAP_TASK_ID,
                "description": BOOTSTRAP_DESCRIPTION,
                "phase": BOOTSTRAP_PHASE,
                "dependencies": (),
                "files": (),
            },
        )
    )
    return persistence.save(
        project_id=project_id,
        session_id=session_id,
        change_id=session_id,
        phase=BOOTSTRAP_PHASE,
        status="pending",
        task_set=task_set,
        expected_version=0,
    )


def _parse_tasks(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TaskSetPersistenceError("Decomposition result is not valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
        raise TaskSetPersistenceError("Decomposition result must contain a tasks array")

    tasks: list[dict] = []
    descriptions: set[str] = set()
    for item in payload["tasks"]:
        if not isinstance(item, dict):
            raise TaskSetPersistenceError("Every decomposed task must be an object")
        required = ("id", "description", "phase", "dependencies")
        if any(not isinstance(item.get(field), str) for field in required[:3]):
            raise TaskSetPersistenceError("Every decomposed task needs id, description, and phase")
        description = item["description"].strip()
        if not description:
            raise TaskSetPersistenceError("Every decomposed task needs a non-empty description")
        if description in descriptions:
            raise TaskSetPersistenceError(f"Task descriptions must be unique: {description}")
        descriptions.add(description)
        dependencies = item.get("dependencies")
        if not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies):
            raise TaskSetPersistenceError("Every decomposed task needs a string dependencies array")
        files = item.get("files", ())
        if not isinstance(files, list) or not all(isinstance(path, str) for path in files):
            raise TaskSetPersistenceError("Task files must be a string array")
        task = {
            "id": item["id"].strip(),
            "description": description,
            "phase": item["phase"].strip(),
            "dependencies": tuple(dependencies),
            "files": tuple(files),
        }
        tasks.append(task)
    if not tasks:
        raise TaskSetPersistenceError("Decomposition produced no tasks")
    return tasks


def complete(
    *,
    project_id: str,
    session_id: str,
    decomposition: str,
    db_path: str | None = None,
) -> dict:
    persistence = TaskSetPersistence(db_path)
    loaded = persistence.load(project_id=project_id, session_id=session_id)
    if loaded is None:
        raise TaskSetPersistenceError("Bootstrap SDD state unavailable")
    current, persisted = loaded
    if current.get(BOOTSTRAP_TASK_ID) is None:
        raise TaskSetPersistenceError("Bootstrap task is not present")
    tasks = _parse_tasks(decomposition)
    if any(task["id"] == BOOTSTRAP_TASK_ID for task in tasks):
        raise TaskSetPersistenceError("Decomposition task ID is reserved")
    task_set = TaskSet(tuple(tasks))
    first_phase = str(task_set.tasks[0].get("phase", ""))
    if not first_phase:
        raise TaskSetPersistenceError("First decomposed task has no phase")
    saved = persistence.save(
        project_id=project_id,
        session_id=session_id,
        change_id=persisted["change_id"],
        phase=first_phase,
        status="pending",
        task_set=task_set,
        expected_version=persisted["version"],
    )
    return {
        "version": saved["version"],
        "phase": saved["phase"],
        "tasks": [task["id"] for task in task_set.tasks],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--decomposition")
    parser.add_argument("--db-path")
    args = parser.parse_args()
    try:
        if args.prepare == args.complete:
            parser.error("choose exactly one of --prepare or --complete")
        if args.prepare:
            result = prepare(project_id=args.project, session_id=args.session_id, db_path=args.db_path)
        else:
            if args.decomposition is None:
                parser.error("--decomposition is required with --complete")
            result = complete(
                project_id=args.project,
                session_id=args.session_id,
                decomposition=args.decomposition,
                db_path=args.db_path,
            )
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except (TaskSetPersistenceError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
