### Chain Strategy

When `delivery_strategy` results in chained PRs (either by user choice via `ask-on-risk` or automatically via `auto-chain`), ask the user which chain strategy to use. Use the `question` tool for this choice: present the two strategy options through a single `question` tool call; do NOT render the options as a plain markdown bullet list or plain chat text.

- **`stacked-to-main`**: Each PR merges to main in order. Fast iteration, fix on the go. Best for speed-first teams and independent slices.
- **`feature-branch-chain`**: The feature/tracker branch accumulates final integration; PR #1 targets the tracker branch, later child PRs target the immediate previous PR branch so review diffs stay focused. Only the tracker merges to main. Best for rollback control and coordinated releases.

Cache the chain strategy for the session. Pass it as `chain_strategy` to `sdd-tasks` and `sdd-apply` prompts alongside `delivery_strategy`. Do not ask again unless the user changes scope.

When delivery planning yields chained PRs, treat `chained-pr` (registry skill `tony-ai-chained-pr`) as a required skill match: resolve it by registry name through this template's existing skill-resolution mechanism (the same one it already uses to pass skills to phases) and ensure the `sdd-tasks` and `sdd-apply` phases load and follow it BEFORE planning or creating any PR. Do not hardcode the skill path; defer resolution to that mechanism.