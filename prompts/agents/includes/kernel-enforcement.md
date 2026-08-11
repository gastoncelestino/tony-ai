### Kernel Enforcement (HARD GATE)

The Tony Kernel is the authority for phase transitions. Before delegating ANY phase to a sub-agent (sdd-explore, sdd-propose, sdd-spec, sdd-design, sdd-tasks, sdd-apply, sdd-verify, sdd-archive), you MUST call the kernel via the `tony-kernel` MCP server:

1. Call `kernel_can_start_phase(requested_phase)` BEFORE delegating.
2. If the response `allowed` is `false` (decision is one of `block_missing_artifacts`, `block_phase_incomplete`, `block_invalid_transition`, `block_evidence_required`, `block_retry_exhausted`, `block_scope_violation`, `human_required`) — STOP. Do not delegate. Report the block and the `next_action` to the user.
3. Only if `allowed` is `true` — delegate the phase, then call `kernel_record_delegation(phase, sub_agent, task_id?)`.

After a sub-agent completes a phase:

1. Call `kernel_record_phase_completion(phase, artifacts)` with the real artifacts produced (JSON array of `{kind, path, store, hash?}`).
2. Call `kernel_verify_phase_checksum(phase, artifacts)` to ensure artifacts were not tampered with since recording.

For implementation work, register tasks with `kernel_add_task` before delegating sdd-apply, mark them `kernel_start_task`, and close them with `kernel_complete_task(task_id, evidence)` — evidence is mandatory and validated; an empty or failing evidence list is blocked.

You can inspect current state at any time with `kernel_get_status`, and reset it with `kernel_reset` (after explicit user confirmation).

If the `tony-kernel` MCP server is unavailable, fall back to the plugin gate or to `python3 -m kernel.cli` from the repo root (same commands: `can_start_phase`, `record_delegation`, `record_phase_completion`, `verify_phase_checksum`). Never delegate a phase without checking the Kernel first.
