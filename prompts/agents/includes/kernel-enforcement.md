### Kernel Enforcement (HARD GATE)

Before delegating ANY phase to a sub-agent (sdd-explore, sdd-propose, sdd-spec, sdd-design, sdd-tasks, sdd-apply, sdd-verify, sdd-archive), you MUST:

1. Call `kernel.can_start_phase(requested_phase)` via the Kernel HTTP API or the `tony-kernel` plugin.
2. If the response is `BLOCK_MISSING_ARTIFACTS`, `BLOCK_PHASE_INCOMPLETE`, `BLOCK_INVALID_TRANSITION`, `BLOCK_EVIDENCE_REQUIRED`, `BLOCK_RETRY_EXHAUSTED`, or `BLOCK_SCOPE_VIOLATION` — STOP. Do not delegate. Report the block to the user.
3. If the response is `HUMAN_REQUIRED` — STOP. Escalate to human.
4. Only if the response is `PROCEED` — delegate the phase.

After a sub-agent completes a phase:
1. Call `kernel.record_phase_completion(phase, artifacts, evidence)` with the real artifacts and evidence produced.
2. Call `kernel.verify_phase_checksum(phase, artifacts)` to ensure artifacts were not tampered with.

Never delegate a phase without first checking the Kernel. The Kernel is the authority for phase transitions. If the plugin is unavailable, fall back to calling the Python `KernelOrchestrator` directly via HTTP at `http://127.0.0.1:7438`.
