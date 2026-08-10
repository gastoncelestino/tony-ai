#!/usr/bin/env python3
"""
Tony Kernel CLI — Command-line interface for the Kernel Orchestrator
Used by the TypeScript plugin to communicate with the kernel.
"""
from __future__ import annotations
import json
import sys
from typing import Any

# Add kernel to path
import sys
sys.path.insert(0, '/workspace/7cf8dcfc-72e2-49b9-9795-75440ba1be96/sessions/agent_0a609c26-9e31-4ad3-abf7-5af14c9f5367')

from kernel.orchestrator_integration import create_kernel_orchestrator
from kernel.schemas import ArtifactRef, Phase


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No command provided"}), file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    kernel = create_kernel_orchestrator("default", "default")

    try:
        if command == "can_start_phase":
            if len(args) < 1:
                print(json.dumps({"error": "phase required"}), file=sys.stderr)
                sys.exit(1)
            phase = args[0]
            result = kernel.can_start_phase(args[0])
            output = {
                "decision": result.decision.value,
                "reason": result.reason,
                "current_phase": result.current_phase,
                "requested_phase": result.requested_phase,
                "missing_artifacts": list(result.missing_artifacts),
                "missing_evidence": list(result.missing_evidence),
                "scope_violations": list(result.scope_violations),
                "retry_status": result.retry_status,
                "next_action": result.next_action,
            }
            print(json.dumps(output))

        elif command == "record_delegation":
            if len(args) < 2:
                print(json.dumps({"error": "phase and sub_agent required"}), file=sys.stderr)
                sys.exit(1)
            phase, sub_agent = args[0], args[1]
            task_id = args[2] if len(args) > 2 else None
            kernel.record_delegation(phase, sub_agent, task_id)
            print(json.dumps({"ok": True}))

        elif command == "record_phase_completion":
            if len(args) < 2:
                print(json.dumps({"error": "phase and artifacts required"}), file=sys.stderr)
                sys.exit(1)
            phase = args[0]
            artifacts_json = args[1]
            artifacts = json.loads(artifacts_json)
            artifact_refs = []
            for art in artifacts:
                if isinstance(art, dict):
                    artifact_refs.append(ArtifactRef(
                        kind=art.get("kind", ""),
                        path=art.get("path", ""),
                        store=art.get("store", "tonymem"),
                        hash=art.get("hash"),
                        validated=art.get("validated", False),
                    ))
                else:
                    artifact_refs.append(art)
            result = kernel.record_phase_completion(phase, tuple(artifact_refs))
            print(json.dumps({
                "decision": result.decision.value,
                "reason": result.reason,
                "current_phase": result.current_phase,
                "requested_phase": result.requested_phase,
            }))

        elif command == "check_scope":
            if len(args) < 2:
                print(json.dumps({"error": "git_diff and allowed_files required"}), file=sys.stderr)
                sys.exit(1)
            git_diff = args[0]
            allowed_files = json.loads(args[1])
            result = kernel.check_scope(args[0], tuple(json.loads(args[1])))
            print(json.dumps({
                "decision": result.decision.value,
                "reason": result.reason,
                "current_phase": result.current_phase,
                "scope_violations": list(result.scope_violations),
            })

        elif command == "record_delegation":
            if len(args) < 2:
                print(json.dumps({"error": "phase and sub_agent required"}), file=sys.stderr)
                sys.exit(1)
            phase, sub_agent = args[0], args[1]
            task_id = args[2] if len(args) > 2 else None
            kernel.record_delegation(phase, sub_agent, task_id)
            print(json.dumps({"ok": True}))

        elif command == "get_status":
            print(json.dumps(kernel.get_status()))

        elif command == "health":
            print(json.dumps({"status": "ok"}))

        else:
            print(json.dumps({"error": f"Unknown command: {command}"}), file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import json
    main()