<!-- tony-ai:sdd-model-assignments -->

## Model Assignments

Read the configured models from `opencode.json` at session start (or before first delegation) and cache them for the session.

- Treat `agent.tony-orchestrator.model` as authoritative when it is set.
- Treat `agent.sdd-<phase>.model` as authoritative when it is set.
- If a phase does not have an explicit model, use the default OpenCode runtime model for that agent and continue.
- For named profiles, apply the same rule to the suffixed agent keys (for example, `sdd-apply-cheap`).

<!-- /tony-ai:sdd-model-assignments -->