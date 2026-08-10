# Dynamic Sub-Agent Launcher — Smart Include Resolution

When the orchestrator decides to launch a sub-agent for any SDD phase or review, it dynamically resolves includes using the phase manifest.

## Phase Manifest

The manifest at `{file:./includes/phase-manifest.json}` defines exact includes and skills for each phase.

## Launch Procedure

When you need to launch a sub-agent for phase `X`:

1. **Read the manifest**: `{file:./includes/phase-manifest.json}`
2. **Resolve includes** for phase `X`:
   - Base includes (always): `sub-agent-context-protocol.md`
   - Phase-specific includes from `phases["X"].includes` (or `review_phases["X"].includes`)
   - Skills from `phases["X"].skills` (or `review_phases["X"].skills`)
3. **Build sub-agent prompt** by concatenating:
   ```
   {file:./includes/sub-agent-context-protocol.md}
   {file:./includes/{include_1}.md}
   {file:./includes/{include_2}.md}
   ...
   
   ## Skills to load before work
   {file:./../_shared/sdd-phase-common.md}
   {file:./../_shared/{skill_1}.md}
   {file:./../_shared/{skill_2}.md}
   ...
   
   {file:./prompts/sdd/{phase_name}.md}
   ```
3. Launch sub-agent with constructed prompt.

## Conditional Review Contract Injection

**CRITICAL**: The full Review Contract (`review-contract-full.md`) is NOT loaded by default. It is injected ONLY when launching a review agent or when a review trigger fires.

When launching a review agent (`review-readability`, `review-reliability`, `review-resilience`, `review-risk`, `review-refuter`) OR when the orchestrator detects a review trigger (post-apply, pre-commit, pre-push, pre-pr, release), inject:
```
{file:./includes/review-contract-full.md}
```
before the phase-specific prompt.

## Smart Launch Rules

- **Always include** `sub-agent-context-protocol.md` (base)
- **Inject skills** as `## Skills to load before work` section with `{file:./../_shared/{skill}.md}`
- **Append phase-specific prompt** from `prompts/sdd/{phase}.md` (which now contains ONLY phase-specific logic, no common includes)
- **Deduplicate** includes if multiple phases reference the same file
- **Cache manifest** after first read per session

## Launch Pattern (Pseudocode)

```
manifest = read_json("./includes/phase-manifest.json")
phase_config = manifest["phases"][phase_name] || manifest["review_phases"][phase_name]

includes = ["sub-agent-context-protocol.md"] + phase_config["includes"]
skills = ["sdd-phase-common.md"] + phase_config["skills"]

# Conditional: inject Review Contract for review agents
is_review = phase_name in ["review-readability", "review-reliability", "review-resilience", "review-risk", "review-refuter"]
if is_review:
    includes = ["review-contract-full.md"] + includes

prompt_parts = [
  *[f"{{file:./includes/{inc}}}" for inc in includes],
  "## Skills to load before work",
  *[f"{{file:./../_shared/{skill}}}" for skill in skills],
  f"{{file:./prompts/sdd/{phase_name}.md}}"
]

launch_subagent(phase_name, join(prompt_parts, "\n"))
```

This ensures each sub-agent loads ONLY the includes it needs (~70-80% token reduction vs monolithic prompt), and the heavy Review Contract loads ONLY when a review actually fires.