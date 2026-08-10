### SDD Session Preflight (HARD GATE)

Before executing ANY SDD command or natural-language SDD request, ensure this session has an explicit `SDD Session Preflight` decision block.

This applies to `/sdd-new`, `/sdd-ff`, `/sdd-continue`, `/sdd-explore`, `/sdd-status`, `/sdd-apply`, `/sdd-verify`, `/sdd-archive`, and natural-language equivalents such as "use SDD to add dark mode" / "do it with SDD".

Required preflight choices:

1. **Execution mode**: `interactive` or `auto`.
2. **Artifact store**: `openspec`, `tonymem`, or `both` when tonymem is callable. If tonymem is unavailable, offer only file/inline-safe choices.
3. **Chained PR strategy**: `auto-forecast`, `ask-always`, `single-pr-default`, or `force-chained`.
4. **Review budget**: maximum changed lines before stopping for reviewer-burden approval.

User-facing preflight question format:

Use the `question` tool for SDD Session Preflight. Do NOT render the full preflight menu as plain chat text.

Ask all four preflight groups in one single `question` tool call so OpenCode can render the groups as tabs. Do NOT run this as a sequential wizard. Do NOT issue four separate `question` tool calls.

The single `question` tool call must contain these four localized groups in this order:

1. Pace: Interactive, Automatic.
2. Artifacts: OpenSpec, tonymem, Both.
3. PRs: Ask me, Single PR, Chained, Auto.
4. Review: 400 lines, 800 lines, Other.

Match the user's current language and active persona for question labels and descriptions. Treat the preflight UI as direct orchestrator conversation, not as a generated technical artifact. Technical artifacts still default to English, but this UI follows the user's conversation language/persona. Do NOT mix languages inside one grouped question.

Do NOT show option codes in the interactive UI. Do NOT show canonical values or other internal values in the interactive UI labels or descriptions.

After the single grouped `question` tool call returns, map the selected human labels to canonical values internally. Do not reveal the canonical values in the UI.

If Other is selected for review budget, ask one follow-up question for the numeric budget.

Only after all four preflight choices are collected, summarize them as the `SDD Session Preflight` decision block and continue with the SDD init guard/requested phase.

Map answers to canonical values:

- Pace: Interactive -> `interactive`; Automatic -> `auto`.
- Artifacts: OpenSpec -> `openspec`; tonymem -> `tonymem`; Both -> `both`.
- PRs: Ask me -> `ask-always`; Single PR -> `single-pr-default`; Chained -> `force-chained`; Auto -> `auto-forecast`.
- Review: 400 lines -> `review_budget_lines: 400`; 800 lines -> `review_budget_lines: 800`; Other -> ask one follow-up for the number.

Hard gate rules:

- `openspec/config.yaml`, existing SDD artifacts, previous `sdd-init` results, or installed SDD assets do NOT satisfy session preflight.
- If the session has no preflight block, ask the single grouped `question` tool preflight above. Do not run init, delegate phases, edit files, or apply tasks until all four choices are collected.
- Cache the choices for this session and include them in later phase prompts.
- If the user explicitly provided all four choices in the current conversation, summarize them as the session preflight block and continue.