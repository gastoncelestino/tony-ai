"""Transport-neutral boundary between callers and the Tony Kernel."""
from __future__ import annotations

import json
import sys
import re
from typing import Mapping, Sequence

from kernel.execution_order import resolve_execution
from kernel.state import KernelState
from kernel.task_set import TaskSet


def _reference_tokens(value: object) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[^a-z0-9]+", str(value).lower()) if token)


def _matches_requested_task(task: Mapping[str, object], requested: str) -> bool:
    if str(task.get("id", "")) == requested or str(task.get("description", "")) == requested:
        return True
    task_tokens = _reference_tokens(task.get("id", ""))
    requested_tokens = _reference_tokens(requested)
    if not task_tokens or len(task_tokens) > len(requested_tokens):
        return False
    position = 0
    for token in requested_tokens:
        if token == task_tokens[position]:
            position += 1
            if position == len(task_tokens):
                return True
    return False


def resolve_boundary(request: Mapping[str, object]) -> dict:
    """Resolve an execution decision from a complete, caller-supplied task snapshot."""
    phase = str(request.get("phase", ""))
    status = str(request.get("status", ""))
    tasks = request.get("tasks", ())
    completed = request.get("completed", ())
    requested_description = str(request.get("requested_description", "")).strip()

    if not phase:
        return _blocked("Missing required phase")
    if status == "failed":
        return _blocked("Kernel execution is halted because the current TaskSet is failed; start a new execution session")
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)):
        return _blocked("tasks must be a sequence")
    if not isinstance(completed, Sequence) or isinstance(completed, (str, bytes)):
        return _blocked("completed must be a sequence")

    try:
        task_set = TaskSet(tuple(tasks), tuple(str(task_id) for task_id in completed))
        if requested_description:
            matches = [
                task
                for task in task_set.ready_tasks()
                if task.get("phase") == phase
                and _matches_requested_task(task, requested_description)
            ]
            if not matches:
                return _blocked(
                    f"Requested task is not ready in phase {phase}: {requested_description}"
                )
            if len(matches) > 1:
                return _blocked(f"Multiple ready tasks match ID or description: {requested_description}")
            state = KernelState(phase, status, matches[0])
        else:
            state = KernelState(phase, status).select_next_task(task_set)
        if state.get_next_task() is not None and state.current_status == "pending":
            state = state.start_task()
        return resolve_execution(state)
    except (TypeError, ValueError) as exc:
        return _blocked(str(exc))


def _blocked(reason: str) -> dict:
    return {
        "decision": "blocked",
        "allowed": False,
        "reason": reason,
        "current_phase": None,
        "execution_order": None,
    }


def main() -> int:
    """Read one JSON request from stdin and write one JSON response to stdout."""
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, Mapping):
            raise TypeError("request must be an object")
        response = resolve_boundary(request)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        response = _blocked(str(exc))

    sys.stdout.write(json.dumps(response, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
