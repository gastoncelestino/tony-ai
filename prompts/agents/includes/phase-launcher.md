# Phase Launcher — Materialized Prompt Bundles

The phase manifest is the source of truth for sub-agent prompt composition. The bundler resolves it before runtime and writes one immutable prompt per phase.

## Generated artifacts

```text
prompts/generated/phases/<phase>.md
prompts/generated/prompt-manifest.json
```

Each phase bundle contains the base context, phase-specific includes, shared skills, and the phase prompt in deterministic order. Review bundles contain the review contract only when declared by `review_phases`.

## Runtime procedure

When launching phase `X`:

1. Confirm that `prompts/generated/phases/X.md` exists.
2. Confirm that `prompt-manifest.json` contains its SHA-256.
3. Pass the generated file contents as the sub-agent prompt.
4. Include the phase name and bundle hash in the delegation evidence.

The orchestrator chooses the phase; it does not resolve filenames, concatenate Markdown, or ask the model to interpret a manifest. If the bundle is missing or stale, delegation must stop and the repository build command must be run.

## Build and verification

```bash
bun run tools/build-prompts.ts
bun run tools/build-prompts.ts --check
```

The resolver rejects missing files, dynamic filenames, path traversal, cycles, excessive include depth, and unresolved include tokens. The generated output must not contain native config references or bundler directives.

## Phase inventory

The complete SDD, review, and Judgment Day phase inventory is stored in `prompts/agents/includes/phase-manifest.json`. Do not duplicate phase mappings in this document; duplicate mappings drift and are not authoritative.
