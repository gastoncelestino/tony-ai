"""
Tony Kernel — State Persistence

Serializes/deserializes KernelOrchestrator state to/from JSON so phase
progress survives across CLI/MCP invocations. Without this, every
`can_start_phase` call starts from a fresh EXPLORE state and the gate
never sees earlier completions.

Stdlib-only. State file is a JSON document keyed by a single active change
per project (mirrors how the orchestrator runs one SDD change at a time).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Callable, Optional

from .schemas import (
    Phase,
    PhaseStatus,
    PhaseState,
    ChangeState,
    ArtifactRef,
    Evidence,
    EvidenceType,
    EvidenceStatus,
    Claim,
    ClaimStatus,
    Task,
    TaskStatus,
    TaskLedger,
)
from .state_machine import PhaseController, create_initial_state
from .phase_gate import PhaseGate, PhaseGateConfig
from .orchestrator_integration import KernelOrchestrator, create_kernel_orchestrator
from .phase_checksum import PhaseChecksum, PhaseChecksumRegistry


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _from_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# ─── ArtifactRef ─────────────────────────────────────────────────────────────

def artifact_to_dict(a: ArtifactRef) -> dict:
    return {
        "kind": a.kind,
        "path": a.path,
        "store": a.store,
        "hash": a.hash,
        "validated": a.validated,
    }


def artifact_from_dict(d: dict) -> ArtifactRef:
    return ArtifactRef(
        kind=d.get("kind", ""),
        path=d.get("path", ""),
        store=d.get("store", "tonymem"),
        hash=d.get("hash"),
        validated=d.get("validated", False),
    )


# ─── PhaseState / ChangeState ────────────────────────────────────────────────

def phase_state_to_dict(ps: PhaseState) -> dict:
    return {
        "phase": ps.phase.value,
        "status": ps.status.value,
        "artifacts": [artifact_to_dict(a) for a in ps.artifacts],
        "started_at": _iso(ps.started_at),
        "completed_at": _iso(ps.completed_at),
        "error": ps.error,
    }


def phase_state_from_dict(d: dict) -> PhaseState:
    return PhaseState(
        phase=Phase(d["phase"]),
        status=PhaseStatus(d.get("status", "not_started")),
        artifacts=tuple(artifact_from_dict(a) for a in d.get("artifacts", [])),
        started_at=_from_iso(d.get("started_at")),
        completed_at=_from_iso(d.get("completed_at")),
        error=d.get("error"),
    )


def change_state_to_dict(cs: ChangeState) -> dict:
    return {
        "change_id": cs.change_id,
        "project": cs.project,
        "current_phase": cs.current_phase.value,
        "phases": {p.value: phase_state_to_dict(s) for p, s in cs.phases.items()},
        "created_at": _iso(cs.created_at),
        "updated_at": _iso(cs.updated_at),
        "metadata": cs.metadata,
    }


def change_state_from_dict(d: dict) -> ChangeState:
    return ChangeState(
        change_id=d["change_id"],
        project=d["project"],
        current_phase=Phase(d["current_phase"]),
        phases={Phase(p): phase_state_from_dict(s) for p, s in d.get("phases", {}).items()},
        created_at=_from_iso(d.get("created_at")),
        updated_at=_from_iso(d.get("updated_at")),
        metadata=d.get("metadata", {}),
    )


# ─── Evidence / Claim ────────────────────────────────────────────────────────

def evidence_to_dict(e: Evidence) -> dict:
    return {
        "type": e.type.value,
        "claim": e.claim,
        "command": e.command,
        "exit_code": e.exit_code,
        "stdout": e.stdout,
        "stderr": e.stderr,
        "stdout_hash": e.stdout_hash,
        "stdout_path": e.stdout_path,
        "file_path": e.file_path,
        "file_hash": e.file_hash,
        "metadata": e.metadata,
        "timestamp": _iso(e.timestamp),
        "status": e.status.value,
    }


def evidence_from_dict(d: dict) -> Evidence:
    return Evidence(
        type=EvidenceType(d.get("type", "manual")),
        claim=d.get("claim", ""),
        command=d.get("command"),
        exit_code=d.get("exit_code"),
        stdout=d.get("stdout"),
        stderr=d.get("stderr"),
        stdout_hash=d.get("stdout_hash"),
        stdout_path=d.get("stdout_path"),
        file_path=d.get("file_path"),
        file_hash=d.get("file_hash"),
        metadata=d.get("metadata", {}),
        timestamp=_from_iso(d.get("timestamp")) or datetime.now(),
        status=EvidenceStatus(d.get("status", "pending")),
    )


def claim_to_dict(c: Claim) -> dict:
    return {
        "id": c.id,
        "description": c.description,
        "evidence": [evidence_to_dict(e) for e in c.evidence],
        "status": c.status.value,
        "required": c.required,
        "metadata": c.metadata,
    }


def claim_from_dict(d: dict) -> Claim:
    return Claim(
        id=d["id"],
        description=d.get("description", ""),
        evidence=tuple(evidence_from_dict(e) for e in d.get("evidence", [])),
        status=ClaimStatus(d.get("status", "insufficient")),
        required=d.get("required", True),
        metadata=d.get("metadata", {}),
    )


# ─── Task / TaskLedger ───────────────────────────────────────────────────────

def task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "description": t.description,
        "phase": t.phase.value,
        "status": t.status.value,
        "dependencies": list(t.dependencies),
        "files": list(t.files),
        "evidence": [evidence_to_dict(e) for e in t.evidence],
        "started_at": _iso(t.started_at),
        "completed_at": _iso(t.completed_at),
        "assigned_agent": t.assigned_agent,
        "metadata": t.metadata,
    }


def task_from_dict(d: dict) -> Task:
    return Task(
        id=d["id"],
        description=d.get("description", ""),
        phase=Phase(d.get("phase", "tasks")),
        status=TaskStatus(d.get("status", "pending")),
        dependencies=tuple(d.get("dependencies", [])),
        files=tuple(d.get("files", [])),
        evidence=tuple(evidence_from_dict(e) for e in d.get("evidence", [])),
        started_at=_from_iso(d.get("started_at")),
        completed_at=_from_iso(d.get("completed_at")),
        assigned_agent=d.get("assigned_agent"),
        metadata=d.get("metadata", {}),
    )


# ─── PhaseChecksumRegistry ───────────────────────────────────────────────────

def registry_to_dict(r: PhaseChecksumRegistry) -> dict:
    checksums = {}
    for phase, cs in r.checksums.items():
        checksums[phase] = {
            "phase": cs.phase,
            "artifacts_hash": cs.artifacts_hash,
            "individual_hashes": dict(cs.individual_hashes),
            "recorded_at": _iso(cs.recorded_at),
            "recorded_by": cs.recorded_by,
        }
    return {
        "checksums": checksums,
        "history": r.history,
    }


def registry_from_dict(d: dict) -> PhaseChecksumRegistry:
    reg = PhaseChecksumRegistry()
    for phase, cs in d.get("checksums", {}).items():
        reg.checksums[phase] = PhaseChecksum(
            phase=cs.get("phase", phase),
            artifacts_hash=cs.get("artifacts_hash", ""),
            individual_hashes=cs.get("individual_hashes", {}),
            recorded_at=_from_iso(cs.get("recorded_at")) or datetime.now(),
            recorded_by=cs.get("recorded_by", "system"),
        )
    reg.history = list(d.get("history", []))
    return reg


# ─── Orchestrator ────────────────────────────────────────────────────────────

def orchestrator_to_dict(o: KernelOrchestrator) -> dict:
    return {
        "change_id": o.change_state.change_id,
        "project": o.change_state.project,
        "change_state": change_state_to_dict(o.change_state),
        "delegation_log": list(o.delegation_log),
        "retry_attempts": o.retry_budget.attempts,
        "task_ledger": {tid: task_to_dict(t) for tid, t in o.task_ledger.tasks.items()},
        "evidence_claims": {cid: claim_to_dict(c) for cid, c in o.evidence_ledger.claims.items()},
        "checksum_registry": registry_to_dict(o.checksum_registry),
    }


def orchestrator_from_dict(d: dict, artifact_store: Optional[Callable[[ArtifactRef], bool]] = None) -> KernelOrchestrator:
    change_id = d.get("change_id", "default")
    project = d.get("project", "default")
    o = create_kernel_orchestrator(change_id, project, artifact_store=artifact_store)
    o.change_state = change_state_from_dict(d["change_state"])
    o.controller = PhaseController(o.change_state)
    o.gate = PhaseGate(o.controller, config=PhaseGateConfig(), artifact_store=artifact_store)
    o.delegation_log = list(d.get("delegation_log", []))
    o.retry_budget.attempts = dict(d.get("retry_attempts", {}))
    o.task_ledger = TaskLedger(tasks={tid: task_from_dict(t) for tid, t in d.get("task_ledger", {}).items()})
    o.evidence_ledger.claims = {cid: claim_from_dict(c) for cid, c in d.get("evidence_claims", {}).items()}
    o.checksum_registry = registry_from_dict(d.get("checksum_registry", {}))
    return o


# ─── File helpers ────────────────────────────────────────────────────────────

def default_state_dir() -> str:
    """Directory for the kernel state file, honoring env override."""
    override = os.environ.get("TONY_KERNEL_STATE_DIR")
    if override:
        return override
    return os.path.join(os.getcwd(), ".tony-kernel")


def state_file_path() -> str:
    d = default_state_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "kernel-state.json")


def save_orchestrator(o: KernelOrchestrator, path: Optional[str] = None) -> str:
    path = path or state_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(orchestrator_to_dict(o), f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def load_orchestrator(path: Optional[str] = None,
                      artifact_store: Optional[Callable[[ArtifactRef], bool]] = None) -> KernelOrchestrator:
    """Load the current orchestrator state, or a fresh one if none exists."""
    path = path or state_file_path()
    if not os.path.exists(path):
        return create_kernel_orchestrator("default", "default", artifact_store=artifact_store)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return orchestrator_from_dict(data, artifact_store=artifact_store)
    except (ValueError, KeyError, json.JSONDecodeError, OSError):
        # Corrupt/partial state file — start clean rather than crash the gate.
        return create_kernel_orchestrator("default", "default", artifact_store=artifact_store)


def reset_state(path: Optional[str] = None) -> None:
    path = path or state_file_path()
    if os.path.exists(path):
        os.remove(path)
