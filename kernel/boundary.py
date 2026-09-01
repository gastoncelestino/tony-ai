"""
Tony Kernel — implementacion minima del lado Python que kernel/transport.ts
invoca como `python3 -m kernel.boundary`.

Protocolo (un JSON por invocacion, via stdin -> stdout, ver kernel/protocol.ts):

  KernelContextRequest   {"operation": "get_context", "project_directory": ..., "session_id": ...}
  KernelCommandRequest   {"operation": "prepare_bootstrap" | "complete_bootstrap" | "complete_task", ...}
  KernelBoundaryRequest  KernelContext + {"requested_description": ...}   (SIN campo "operation")

Cada invocacion es un proceso nuevo (ver transport.ts: spawn + stdin.end(payload)),
asi que el estado se persiste en disco entre llamadas, indexado por
(project_directory, session_id).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

KERNEL_PHASES = ["explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"]
BOOTSTRAP_TASK_ID = "bootstrap"
BOOTSTRAP_DESCRIPTION = "decompose task graph"


def _state_dir() -> Path:
    runtime_dir = os.environ.get("TONY_RUNTIME_DIR")
    base = Path(runtime_dir).expanduser() if runtime_dir else Path.home() / ".tony-ai"
    d = base / "kernel-state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path(project_directory: str, session_id: str) -> Path:
    key = hashlib.sha256(f"{project_directory}\0{session_id}".encode("utf-8")).hexdigest()[:16]
    safe_session = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)[:60]
    return _state_dir() / f"{safe_session}-{key}.json"


def _load_state(project_directory: str, session_id: str) -> dict | None:
    path = _state_path(project_directory, session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_state(project_directory: str, session_id: str, state: dict) -> None:
    path = _state_path(project_directory, session_id)
    path.write_text(json.dumps(state), encoding="utf-8")


def _context_of(state: dict) -> dict:
    return {
        "phase": state["phase"],
        "status": state["status"],
        "tasks": state["tasks"],
        "completed": state["completed"],
    }


# --- operaciones (KernelCommandRequest / KernelContextRequest) -------------

def op_get_context(req: dict) -> dict:
    state = _load_state(req["project_directory"], req["session_id"])
    if state is None:
        return {"available": False, "reason": f"SDD state unavailable: no bootstrap for session {req['session_id']}"}
    return {"available": True, "context": _context_of(state)}


def op_prepare_bootstrap(req: dict) -> dict:
    state = _load_state(req["project_directory"], req["session_id"])
    if state is None:
        state = {
            "phase": "explore",
            "status": "bootstrapping",
            "tasks": [{
                "id": BOOTSTRAP_TASK_ID,
                "description": BOOTSTRAP_DESCRIPTION,
                "phase": "explore",
                "dependencies": [],
                "files": [],
            }],
            "completed": [],
        }
        _save_state(req["project_directory"], req["session_id"], state)
    return {"ok": True}


def _valid_task(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("id"), str) or not isinstance(value.get("description"), str):
        return False
    if value.get("phase") not in KERNEL_PHASES:
        return False
    deps = value.get("dependencies")
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        return False
    files = value.get("files")
    if files is not None and (not isinstance(files, list) or not all(isinstance(f, str) for f in files)):
        return False
    return True


def op_complete_bootstrap(req: dict) -> dict:
    state = _load_state(req["project_directory"], req["session_id"])
    if state is None:
        return {"ok": False, "reason": "complete_bootstrap called before prepare_bootstrap"}
    try:
        decomposition = json.loads(req["decomposition"])
    except json.JSONDecodeError as exc:
        return {"ok": False, "reason": f"decomposition is not valid JSON: {exc}"}
    tasks = decomposition.get("tasks") if isinstance(decomposition, dict) else None
    if not isinstance(tasks, list) or not tasks or not all(_valid_task(t) for t in tasks):
        return {"ok": False, "reason": "decomposition.tasks is missing, empty, or has invalid task entries"}
    for t in tasks:
        t.setdefault("files", [])
    state["tasks"] = tasks
    state["completed"] = [BOOTSTRAP_TASK_ID]
    state["status"] = "ready"
    state["phase"] = tasks[0]["phase"]
    _save_state(req["project_directory"], req["session_id"], state)
    return {"ok": True}


def op_complete_task(req: dict) -> dict:
    state = _load_state(req["project_directory"], req["session_id"])
    if state is None:
        return {"ok": False, "reason": "complete_task called with no active session"}
    task_id = req["task_id"]
    if not any(t["id"] == task_id for t in state["tasks"]):
        return {"ok": False, "reason": f"unknown task_id: {task_id}"}
    if task_id not in state["completed"]:
        state["completed"].append(task_id)
    remaining = [t for t in state["tasks"] if t["id"] not in state["completed"]]
    state["status"] = "ready" if remaining else "done"
    if remaining:
        state["phase"] = remaining[0]["phase"]
    _save_state(req["project_directory"], req["session_id"], state)
    return {"ok": True}


COMMAND_OPS = {
    "get_context": op_get_context,
    "prepare_bootstrap": op_prepare_bootstrap,
    "complete_bootstrap": op_complete_bootstrap,
    "complete_task": op_complete_task,
}


# --- boundary check (KernelBoundaryRequest, sin "operation") ---------------

def _next_eligible_task(request: dict) -> dict | None:
    completed = set(request.get("completed", []))
    tasks = request.get("tasks", [])
    requested_description = request.get("requested_description", "")

    def ready(t: dict) -> bool:
        return t["id"] not in completed and set(t.get("dependencies", [])).issubset(completed)

    # Preferimos matchear por descripcion exacta (asi el orquestador elige la
    # tarea), y si no matchea nada, caemos a la primera tarea lista.
    for t in tasks:
        if ready(t) and t["description"] == requested_description:
            return t
    for t in tasks:
        if ready(t):
            return t
    return None


def op_boundary(request: dict) -> dict:
    task = _next_eligible_task(request)
    if task is None:
        return {"allowed": False, "decision": "blocked", "reason": "no eligible tasks (all completed or blocked by dependencies)", "execution_order": None}
    return {
        "allowed": True,
        "decision": "proceed",
        "reason": f"authorized task {task['id']}",
        "execution_order": {
            "task_id": task["id"],
            "description": task["description"],
            "phase": task["phase"],
            "files": task.get("files", []),
        },
    }


def main() -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON request: {exc}", file=sys.stderr)
        return 1

    try:
        if isinstance(request, dict) and "operation" in request:
            handler = COMMAND_OPS.get(request["operation"])
            if handler is None:
                print(f"unknown operation: {request['operation']}", file=sys.stderr)
                return 1
            response = handler(request)
        else:
            response = op_boundary(request)
    except (KeyError, TypeError) as exc:
        print(f"malformed request: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
