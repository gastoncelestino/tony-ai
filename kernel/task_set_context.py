"""CLI bridge for loading canonical TaskSet-backed Kernel context."""

from __future__ import annotations

import argparse
import json
import sys

from .task_set_persistence import TaskSetPersistence, TaskSetPersistenceError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--get", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--db-path")
    args = parser.parse_args()

    if not args.get:
        parser.error("only --get is available")

    try:
        loaded = TaskSetPersistence(args.db_path).load(
            project_id=args.project,
            session_id=args.session_id,
        )
        if loaded is None:
            print(json.dumps({"available": False, "reason": "SDD state unavailable"}))
            return 0

        task_set, state = loaded
        context = {
            "phase": state["phase"],
            "status": state["status"],
            "tasks": [
                {
                    "id": task["id"],
                    "description": task["description"],
                    "phase": task["phase"],
                    "dependencies": list(task["dependencies"]),
                }
                for task in task_set.tasks
            ],
            "completed": list(task_set.completed),
        }
        print(json.dumps({"available": True, "state": context}, ensure_ascii=False))
        return 0
    except (TaskSetPersistenceError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"available": False, "reason": f"Canonical TaskSet unavailable: {exc}"}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
