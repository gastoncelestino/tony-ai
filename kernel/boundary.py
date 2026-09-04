"""
Tony Kernel — implementacion minima del lado Python que kernel/transport.ts
invoca como `python3 -m kernel.boundary`.

El Kernel es la fuente de verdad de las decisiones de orquestacion. OpenCode
solo consume el Action Plan y ejecuta el trabajo.
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
PHASE_AGENTS = {
    "explore": "sdd-explore",
    "propose": "sdd-propose",
    "spec": "sdd-spec",
    "design": "sdd-design",
    "tasks": "sdd-tasks",
    "apply": "sdd-apply",
    "verify": "sdd-verify",
    "archive": "sdd-archive",
}
PHASE_TOOLS = {
    "explore": ["read", "glob", "grep", "batch_read"],
    "propose": ["read", "glob", "grep", "batch_read"],
    "spec": ["read", "glob", "grep", "batch_read"],
    "design": ["read", "glob", "grep", "batch_read"],
    "tasks": ["read", "glob", "grep", "batch_read"],
    "apply": ["read", "glob", "grep", "batch_read", "edit", "write"],
    "verify": ["read", "glob", "grep", "batch_read", "bash"],
    "archive": ["read", "glob", "grep", "batch_read"],
}
MAX_ITERATIONS = 8


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
    _state_path(project_directory, session_id).write_text(json.dumps(state), encoding="utf-8")


def _context_of(state: dict) -> dict:
    return {"phase": state["phase"], "status": state["status"], "tasks": state["tasks"], "completed": state["completed"]}


def op_get_context(req: dict) -> dict:
    state = _load_state(req["project_directory"], req["session_id"])
    if state is None:
        return {"available": False, "reason": f"SDD state unavailable: no bootstrap for session {req['session_id']}"}
    return {"available": True, "context": _context_of(state)}


def _bootstrap_objective(user_prompt: str) -> str:
    return "\n\n".join(
        [
            "Decompose the user's task into an executable TaskSet covering the complete SDD workflow.",
            f"User objective:\n{user_prompt or '(not provided)'}",
            "The TaskSet MUST contain at least one task in EVERY phase, in this exact order: explore, propose, spec, design, tasks, apply, verify, archive.",
            "Tasks must form a dependency chain across phases: every task in a phase after explore MUST depend (directly or through same-phase tasks) on work from the immediately preceding phase. Do not create a task in a later phase that can execute before the previous phase has produced its result.",
            "Return a TaskSet using this schema:\n<task_result>{\"tasks\":[{\"id\":\"unique-id\",\"description\":\"unique executable task description\",\"phase\":\"phase-name\",\"dependencies\":[\"other-task-id\"],\"files\":[\"optional/path\"]}]}</task_result>",
            "phase must be one of: explore, propose, spec, design, tasks, apply, verify, archive.",
            "The workflow is not complete until the archive phase task(s) are completed.",
        ]
    )


def _bootstrap_state() -> dict:
    return {
        "phase": "explore",
        "status": "bootstrapping",
        "tasks": [{"id": BOOTSTRAP_TASK_ID, "description": BOOTSTRAP_DESCRIPTION, "phase": "explore", "dependencies": [], "files": []}],
        "completed": [],
    }


def _bootstrap_plan(user_prompt: str) -> dict:
    return {
        "action": "delegate",
        "phase": "explore",
        "task_id": BOOTSTRAP_TASK_ID,
        "agent": PHASE_AGENTS["explore"],
        "objective": _bootstrap_objective(user_prompt),
        "files": [],
        "allowed_tools": list(PHASE_TOOLS["explore"]),
        "max_iterations": MAX_ITERATIONS,
    }


def op_next_action(req: dict) -> dict:
    project_directory = req["project_directory"]
    session_id = req["session_id"]
    state = _load_state(project_directory, session_id)
    if state is None:
        state = _bootstrap_state()
        _save_state(project_directory, session_id, state)
        return {"available": True, "plan": _bootstrap_plan(str(req.get("prompt", "")))}

    completed = set(state.get("completed", []))
    tasks = state.get("tasks", [])
    if tasks and all(task["id"] in completed for task in tasks):
        return {"available": True, "plan": {"action": "done", "reason": "all workflow tasks completed through archive"}}

    for task in tasks:
        if task["id"] in completed:
            continue
        if not all(dependency in completed for dependency in task.get("dependencies", [])):
            continue
        phase = task["phase"]
        return {
            "available": True,
            "plan": {
                "action": "delegate",
                "phase": phase,
                "task_id": task["id"],
                "agent": PHASE_AGENTS[phase],
                "objective": task["description"],
                "files": task.get("files", []),
                "allowed_tools": list(PHASE_TOOLS[phase]),
                "max_iterations": MAX_ITERATIONS,
            },
        }

    return {"available": False, "reason": "no eligible task is available"}


def op_prepare_bootstrap(req: dict) -> dict:
    state = _load_state(req["project_directory"], req["session_id"])
    if state is None:
        _save_state(req["project_directory"], req["session_id"], _bootstrap_state())
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
    return files is None or (isinstance(files, list) and all(isinstance(f, str) for f in files))


def _parse_decomposition(value: str) -> object:
    text = value.strip()
    match = re.search(r"<task_result>\s*(.*?)\s*</task_result>", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _validate_workflow(tasks: list[dict]) -> str | None:
    required = set(KERNEL_PHASES)
    phases_present = {task["phase"] for task in tasks}
    missing = required - phases_present
    if missing:
        return f"decomposition missing phases: {sorted(missing)}"

    phase_index = {phase: index for index, phase in enumerate(KERNEL_PHASES)}
    by_id = {task["id"]: task for task in tasks}

    for task in tasks:
        phase = task["phase"]
        index = phase_index[phase]
        dependencies = task.get("dependencies", [])
        if index == 0:
            if dependencies:
                return f"explore task {task['id']} cannot depend on a later or unknown phase task"
            continue
        previous_phase = KERNEL_PHASES[index - 1]
        if not any(by_id[dependency]["phase"] == previous_phase for dependency in dependencies):
            return f"task {task['id']} in phase {phase} must depend on at least one task from phase {previous_phase}"
        for dependency in dependencies:
            dependency_phase = by_id[dependency]["phase"]
            if phase_index[dependency_phase] > index:
                return f"task {task['id']} depends on later phase {dependency_phase}"

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> bool:
        if task_id in visiting:
            return False
        if task_id in visited:
            return True
        visiting.add(task_id)
        for dependency in by_id[task_id].get("dependencies", []):
            if not visit(dependency):
                return False
        visiting.remove(task_id)
        visited.add(task_id)
        return True

    if not all(visit(task["id"]) for task in tasks):
        return "decomposition contains a dependency cycle"
    return None


def op_complete_bootstrap(req: dict) -> dict:
    state = _load_state(req["project_directory"], req["session_id"])
    if state is None:
        return {"ok": False, "reason": "complete_bootstrap called before prepare_bootstrap"}
    try:
        decomposition = _parse_decomposition(req["decomposition"])
    except (json.JSONDecodeError, TypeError) as exc:
        return {"ok": False, "reason": f"decomposition is not valid JSON: {exc}"}
    tasks = decomposition.get("tasks") if isinstance(decomposition, dict) else None
    if not isinstance(tasks, list) or not tasks or not all(_valid_task(t) for t in tasks):
        return {"ok": False, "reason": "decomposition.tasks is missing, empty, or has invalid task entries"}
    ids = [task["id"] for task in tasks]
    if len(ids) != len(set(ids)) or BOOTSTRAP_TASK_ID in ids:
        return {"ok": False, "reason": "decomposition contains duplicate task ids or reserved bootstrap id"}
    known = set(ids)
    for task in tasks:
        if any(dependency not in known for dependency in task.get("dependencies", [])):
            return {"ok": False, "reason": f"task {task['id']} has an unknown dependency"}
        task.setdefault("files", [])

    workflow_error = _validate_workflow(tasks)
    if workflow_error:
        return {"ok": False, "reason": workflow_error}

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
    if not any(task["id"] == task_id for task in state["tasks"]):
        return {"ok": False, "reason": f"unknown task_id: {task_id}"}
    if task_id not in state["completed"]:
        state["completed"].append(task_id)
    remaining = [task for task in state["tasks"] if task["id"] not in state["completed"]]
    state["status"] = "ready" if remaining else "done"
    if remaining:
        state["phase"] = remaining[0]["phase"]
    _save_state(req["project_directory"], req["session_id"], state)
    return {"ok": True}


COMMAND_OPS = {
    "get_context": op_get_context,
    "next_action": op_next_action,
    "prepare_bootstrap": op_prepare_bootstrap,
    "complete_bootstrap": op_complete_bootstrap,
    "complete_task": op_complete_task,
}


def _next_eligible_task(request: dict) -> dict | None:
    completed = set(request.get("completed", []))
    for task in request.get("tasks", []):
        if task["id"] not in completed and all(dependency in completed for dependency in task.get("dependencies", [])) and task["description"] == request.get("requested_description", ""):
            return task
    return None


def op_boundary(request: dict) -> dict:
    completed = set(request.get("completed", []))
    tasks = request.get("tasks", [])
    if tasks and all(task["id"] in completed for task in tasks):
        return {"allowed": False, "decision": "done", "reason": "all workflow tasks completed through archive — respond to the user directly, do not call task() again", "execution_order": None}
    task = _next_eligible_task(request)
    if task is None:
        return {"allowed": False, "decision": "blocked", "reason": "requested task is not the next eligible task", "execution_order": None}
    return {"allowed": True, "decision": "proceed", "reason": f"authorized task {task['id']}", "execution_order": {"task_id": task["id"], "description": task["description"], "phase": task["phase"], "files": task.get("files", [])}}


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
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
