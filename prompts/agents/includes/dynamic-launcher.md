# Dynamic Sub-Agent Launcher — Materialized Prompt Resolution

The orchestrator selects a phase, while the repository build step materializes the exact sub-agent prompt for that phase. The model must not concatenate files or invent paths at runtime.

## Source of truth

The manifest at `prompts/agents/includes/phase-manifest.json` declares the includes and shared skills for each SDD or review phase. Run:

```bash
bun run tools/build-prompts.ts
bun run tools/build-prompts.ts --check
```

The generated artifacts are:

```text
prompts/generated/tony-orchestrator.md
prompts/generated/phases/<phase>.md
prompts/generated/prompt-manifest.json
```

`prompt-manifest.json` records the SHA-256 hash of every generated bundle and dependency. A stale bundle is a build failure.

## Launch procedure

When launching a sub-agent for phase `X`:

1. Select `prompts/generated/phases/X.md`.
2. Pass that materialized prompt as the task context.
3. Preserve the phase name and bundle hash in the delegation evidence.
4. Do not ask the sub-agent to resolve includes, load a manifest, or construct a prompt from filenames.

The phase bundle already contains the common context, phase-specific includes, shared skills, and phase instructions in deterministic order. Review phases include the review contract only when the selected phase requires it.

## Runtime invariants

- No unresolved repository include directives or native config file tokens may remain in generated bundles.
- Includes are resolved relative to the file that contains them.
- Includes cannot escape the repository prompt root.
- Cycles and dynamic filenames are rejected.
- A dependency is materialized at most once per bundle.
- The same source tree produces byte-identical output.
- The orchestrator decides *which* phase to launch; the bundler decides *what prompt* that phase receives.

## Failure handling

If a bundle is missing or stale, stop before delegation and run the build command. If resolution fails, report the complete include chain, the source file, and the requested path. Never silently fall back to a partial prompt.
