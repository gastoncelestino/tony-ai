"""
Tony Kernel — motor de descomposicion atomica recursiva.

Reemplaza el flujo anterior (pedirle al modelo el TaskSet completo en una
sola llamada, via bootstrapPrompt() delegado a sdd-explore) por N llamadas
chicas: en cada nodo se decide si la tarea es ATOMICA o COMPUESTA, y si es
compuesta se recursa sobre las subtareas hasta TONY_MAX_DECOMPOSITION_DEPTH.

Salida: el mismo shape {"tasks":[...]} que kernel/boundary.py::op_complete_bootstrap
ya valida con _valid_task(). Cero cambios en boundary.py.

Invocacion (mismo patron que boundary.py, un proceso por invocacion):
  echo '{"description": "...", "phase": "explore"}' | python3 -m kernel.atomic_decompose
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

KERNEL_PHASES = ["explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"]

MAX_DEPTH = int(os.environ.get("TONY_MAX_DECOMPOSITION_DEPTH", "3"))
MAX_SUBTASKS_PER_NODE = int(os.environ.get("TONY_MAX_SUBTASKS_PER_NODE", "6"))
LLM_URL = os.environ.get("TONY_LLM_URL", "http://127.0.0.1:8080/v1/chat/completions")
DECOMPOSE_MODEL = os.environ.get("TONY_DECOMPOSE_MODEL", "qwen-3.8-9b")
LLM_TIMEOUT_SECONDS = int(os.environ.get("TONY_DECOMPOSE_TIMEOUT", "60"))

ATOMICITY_PROMPT = (
    "Sos un evaluador de atomicidad de tareas de ingenieria de software. "
    "Te dan una tarea y el contexto de lo que ya se decidio antes en la misma "
    "descomposicion. Decidi si la tarea es ATOMICA (se puede ejecutar en un "
    "solo paso concreto y verificable: un archivo, una funcion, un comando, "
    "una verificacion puntual) o COMPUESTA (mezcla varios pasos distintos o "
    "requiere decisiones intermedias).\n\n"
    "Si es COMPUESTA, dividila en subtareas ejecutables, ordenadas, sin "
    "solapamiento entre ellas, cada una en un dominio del ciclo SDD: "
    f"{', '.join(KERNEL_PHASES)}.\n\n"
    "Respondé SOLO JSON, sin texto adicional, sin markdown, con esta forma "
    'exacta: {"atomic": true} o '
    '{"atomic": false, "subtasks": [{"description": "...", "phase": "..."}]}. '
    f"Maximo {MAX_SUBTASKS_PER_NODE} subtareas por nivel."
)


class DecomposeError(Exception):
    pass


def _call_model(system_prompt: str, user_prompt: str) -> str:
    body = json.dumps(
        {
            "model": DECOMPOSE_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        LLM_URL, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DecomposeError(f"llm call failed: {exc}") from exc

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DecomposeError(f"unexpected llm response shape: {payload}") from exc


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    # tolera fences de markdown si el modelo los agrega pese a la instruccion
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise DecomposeError(f"no JSON object found in model output: {raw!r}")
    return json.loads(text[start : end + 1])


def _valid_phase(phase: object) -> str:
    if phase in KERNEL_PHASES:
        return phase  # type: ignore[return-value]
    return "apply"  # default seguro si el modelo devuelve una fase invalida


def decompose(description: str, phase: str, depth: int = 0, context: str = "") -> list[dict]:
    """Recursion que devuelve hojas atomicas: [{"description", "phase"}, ...]."""
    if depth >= MAX_DEPTH:
        return [{"description": description, "phase": phase}]

    user_prompt = f"Contexto previo en esta descomposicion:\n{context or '(ninguno todavia)'}\n\nTarea a evaluar:\n{description}"

    try:
        raw = _call_model(ATOMICITY_PROMPT, user_prompt)
        decision = _extract_json(raw)
    except DecomposeError:
        # fallback seguro: si el modelo o la llamada fallan, tratamos la tarea
        # como atomica en vez de bloquear toda la descomposicion
        return [{"description": description, "phase": phase}]

    if decision.get("atomic", True):
        return [{"description": description, "phase": phase}]

    subtasks = decision.get("subtasks") or []
    if not isinstance(subtasks, list) or not subtasks:
        return [{"description": description, "phase": phase}]

    leaves: list[dict] = []
    acc_context = context
    for sub in subtasks[:MAX_SUBTASKS_PER_NODE]:
        if isinstance(sub, dict):
            sub_desc = str(sub.get("description", "")).strip()
            sub_phase = _valid_phase(sub.get("phase"))
        else:
            sub_desc = str(sub).strip()
            sub_phase = phase

        if not sub_desc:
            continue

        sub_leaves = decompose(sub_desc, sub_phase, depth + 1, acc_context)
        leaves.extend(sub_leaves)
        # cada hermano ve el resumen acumulado, no el arbol crudo completo
        acc_context += f"\n- {sub_desc}"

    return leaves or [{"description": description, "phase": phase}]


def build_taskset(description: str, phase: str = "explore") -> dict:
    leaves = decompose(description, phase)
    tasks = []
    prev_id: str | None = None
    for i, leaf in enumerate(leaves):
        tid = f"atomic-{i + 1}"
        tasks.append(
            {
                "id": tid,
                "description": leaf["description"],
                "phase": leaf["phase"],
                "dependencies": [prev_id] if prev_id else [],
                "files": [],
            }
        )
        prev_id = tid
    return {"tasks": tasks}


def main() -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON request: {exc}", file=sys.stderr)
        return 1

    description = request.get("description", "")
    if not isinstance(description, str) or not description.strip():
        print("missing or empty 'description'", file=sys.stderr)
        return 1

    phase = request.get("phase", "explore")
    if phase not in KERNEL_PHASES:
        phase = "explore"

    try:
        result = build_taskset(description.strip(), phase)
    except Exception as exc:  # noqa: BLE001 - superficie cualquier fallo al caller TS
        print(f"decomposition failed: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
