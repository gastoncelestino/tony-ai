### Artifact Store Mode

This is collected by `SDD Session Preflight`. If missing, enforce the hard gate before any phase work. Ask which artifact store they want for this change:

- **`tonymem`**: Fast, no files created. Artifacts live in tonymem only.
- **`openspec`**: File-based. Creates `openspec/` with a shareable artifact trail.
- **`both` / `hybrid`**: Both - files for team sharing + tonymem for cross-session recovery.

If the user doesn't specify, detect: if tonymem is available -> default to `tonymem`. Otherwise -> `none`.

Cache the artifact store choice for the session. Pass it as `artifact_store.mode` to every sub-agent launch.