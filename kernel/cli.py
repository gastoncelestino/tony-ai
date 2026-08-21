#!/usr/bin/env python3
"""
Tony Kernel CLI — command-line interface for the Kernel Orchestrator.

Used by the tony-kernel plugin (and by hand, for debugging) to talk to the
kernel. State is persisted across invocations via kernel/persistence.py, so a
phase completed in one call is visible to the next (this is what makes the
gate deterministic instead of stateless).

Run from the repository root:  python3 -m kernel.cli <command> [args...]
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional


def _runtime_dir() -> str:
    configured = os.environ.get("TONY_RUNTIME_DIR")
    if not configured:
        raise RuntimeError("TONY_RUNTIME_DIR must be configured")
    return os.path.abspath(os.path.expanduser(configured))


def _ensure_runtime() -> str:
    runtime_dir = _runtime_dir()
    os.environ.setdefault("TONY_KERNEL_STATE_DIR", os.path.join(runtime_dir, "kernel"))
    return runtime_dir


from .persistence import load_orchestrator, update_orchestrator, reset_state
from .artifact_store import disk_artifact_store, disk_artifact_hasher
from .execution_order import resolve_execution
from .schemas import ArtifactRef, Evidence, EvidenceType


def _build_store():
    _ensure_runtime()
    base = os.environ.get("TONY_REPO_ROOT") or os.getcwd()
    return disk_artifact_store(base)


def _build_hasher():
    _ensure_runtime()
    base = os.environ.get("TONY_REPO_ROOT") or os.getcwd()
    return disk_artifact_hasher(base)


def _load():
    _ensure_runtime()
    return load_orchestrator(artifact_store=_build_store(), artifact_hasher=_build_hasher())


def _result_to_dict(r) -> dict:
    """Normalize an OrchestrationResult into the JSON shape the plugin reads."""
    decision = r.decision.value
    return {
        "decision": decision,
        "allowed": decision in ("proceed", "phase_complete"),
        "reason": r.reason,
        "current_phase": r.current_phase,
        "requested_phase": r.requested_phase,
        "missing_artifacts": list(r.missing_artifacts),
        "missing_evidence": list(r.missing_evidence),
        "scope_violations": list(r.scope_violations),
        "retry_status": r.retry_status,
        "next_action": r.next_action,
    }


def _parse_artifact_refs(raw: list) -> tuple:
    refs = []
    for art in raw:
        if isinstance(art, dict):
            refs.append(ArtifactRef(
                kind=art.get("kind", ""),
                path=art.get("path", ""),
                store=art.get("store", "tonymem"),
                hash=art.get("hash"),
                validated=art.get("validated", False),
            ))
        else:
            refs.append(art)
    return tuple(refs)


def _parse_evidence(raw: list) -> list:
    evidence = []
    for ev in raw:
        if isinstance(ev, dict):
            evidence.append(Evidence(
                type=EvidenceType(ev.get("type", "manual")),
                claim=ev.get("claim", ""),
                command=ev.get("command"),
                exit_code=ev.get("exit_code"),
                stdout=ev.get("stdout"),
                stderr=ev.get("stderr"),
                file_path=ev.get("file_path"),
                file_hash=ev.get("file_hash"),
            ))
        elif isinstance(ev, Evidence):
            evidence.append(ev)
    return evidence


def _cmd_arg(args: list, index: int, name: str) -> str:
    if index >= len(args):
        print(json.dumps({"error": f"missing argument: {name}"}), file=sys.stderr)
        sys.exit(1)
    return args[index]


def _main(argv: list) -> None:
    if len(argv) < 1:
        print(json.dumps({"error": "No command provided"}), file=sys.stderr)
        sys.exit(1)

    command = argv[0]
    args = argv[1:]

    _ensure_runtime()

    if command in ("status", "get_status"):
        orch = _load()
        print(json.dumps(orch.get_status()))
        return

    if command == "health":
        print(json.dumps({"status": "ok"}))
        return

    if command == "reset":
        reset_state()
        print(json.dumps({"ok": True}))
        return

    if command == "resolve_execution":
        orch = _load()
        result = resolve_execution(orch)
        print(json.dumps(result))
        return

    if command == "can_start_phase":
        phase = _cmd_arg(args, 0, "phase")
        orch = _load()
        result = orch.can_start_phase(phase)
        print(json.dumps(_result_to_dict(result)))
        return

    if command == "record_delegation":
        phase = _cmd_arg(args, 0, "phase")
        sub_agent = _cmd_arg(args, 1, "sub_agent")
        task_id = args[2] if len(args) > 2 else None
        update_orchestrator(
            lambda orch: orch.record_delegation(phase, sub_agent, task_id),
            artifact_store=_build_store(),
            artifact_hasher=_build_hasher(),
        )
        print(json.dumps({"ok": True}))
        return

    if command == "record_phase_completion":
        phase = _cmd_arg(args, 0, "phase")
        artifacts_json = _cmd_arg(args, 1, "artifacts")
        try:
            raw = json.loads(artifacts_json)
        except json.JSONDecodeError:
            print(json.dumps({"error": "artifacts must be a JSON array"}), file=sys.stderr)
            sys.exit(1)
        evidence_raw = []
        if len(args) > 2:
            try:
                evidence_raw = json.loads(args[2])
            except json.JSONDecodeError:
                print(json.dumps({"error": "evidence must be a JSON array"}), file=sys.stderr)
                sys.exit(1)
        result = update_orchestrator(
            lambda orch: orch.record_phase_completion(
                phase, _parse_artifact_refs(raw), _parse_evidence(evidence_raw)
            ),
            artifact_store=_build_store(),
            artifact_hasher=_build_hasher(),
        )
        print(json.dumps(_result_to_dict(result)))
        return

    if command == "verify_phase_checksum":
        phase = _cmd_arg(args, 0, "phase")
        artifacts_json = _cmd_arg(args, 1, "artifacts")
        try:
            raw = json.loads(artifacts_json)
        except json.JSONDecodeError:
            print(json.dumps({"error": "artifacts must be a JSON array"}), file=sys.stderr)
            sys.exit(1)
        orch = _load()
        result = orch.verify_phase_checksum(phase, _parse_artifact_refs(raw))
        print(json.dumps(result))
        return

    if command == "add_task":
        task_id = _cmd_arg(args, 0, "task_id")
        description = _cmd_arg(args, 1, "description")
        phase = _cmd_arg(args, 2, "phase")
        update_orchestrator(
            lambda orch: orch.add_task(task_id, description, phase),
            artifact_store=_build_store(),
            artifact_hasher=_build_hasher(),
        )
        print(json.dumps({"ok": True}))
        return

    if command == "start_task":
        task_id = _cmd_arg(args, 0, "task_id")
        ok = update_orchestrator(
            lambda orch: orch.start_task(task_id),
            artifact_store=_build_store(),
            artifact_hasher=_build_hasher(),
        )
        print(json.dumps({"ok": ok}))
        return

    if command == "complete_task":
        task_id = _cmd_arg(args, 0, "task_id")
        evidence_json = _cmd_arg(args, 1, "evidence")
        try:
            raw = json.loads(evidence_json)
        except json.JSONDecodeError:
            print(json.dumps({"error": "evidence must be a JSON array"}), file=sys.stderr)
            sys.exit(1)
        result = update_orchestrator(
            lambda orch: orch.complete_task(task_id, _parse_evidence(raw)),
            artifact_store=_build_store(),
            artifact_hasher=_build_hasher(),
        )
        print(json.dumps(_result_to_dict(result)))
        return

    if command == "check_scope":
        git_diff = _cmd_arg(args, 0, "git_diff")
        allowed_json = _cmd_arg(args, 1, "allowed_files")
        try:
            allowed = json.loads(allowed_json)
        except json.JSONDecodeError:
            print(json.dumps({"error": "allowed_files must be a JSON array"}), file=sys.stderr)
            sys.exit(1)
        orch = _load()
        result = orch.check_scope(git_diff, tuple(allowed))
        print(json.dumps({
            "decision": result.decision.value,
            "allowed": result.decision.value in ("proceed", "phase_complete"),
            "reason": result.reason,
            "current_phase": result.current_phase,
            "scope_violations": list(result.scope_violations),
        }))
        return

    print(json.dumps({"error": f"Unknown command: {command}"}), file=sys.stderr)
    sys.exit(1)


def main() -> None:
    _main(sys.argv[1:])


if __name__ == "__main__":
    main()
