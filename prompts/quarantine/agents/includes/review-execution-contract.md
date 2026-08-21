### Review Execution Contract

# Native Bounded Review Orchestration

Parent orchestrator and native CLI only. Never pass this contract to a reviewer, refuter, judge, correction actor, or validator. Those roles receive only scope, candidate-causal admission, severity, evidence requirements, and output shape.

## Route

Call `launch review agents (review-readability/review-reliability/review-resilience/review-risk)` once. The native facade discovers the repository root and untracked scope, derives the immutable target, selects zero lenses for low risk, one focus lens for standard risk, or canonical 4R for high risk, and freezes the original line count, tier, and correction budget `min(200, ceil(original_changed_lines / 2))`. Goldens stay in snapshot identity but not that count. Correction and compatible base advance never recalculate risk or open review.

Run each selected lens once and pass its JSON result to `finalize review via review-refuter + native receipt --result <file>`. Native Go assigns missing lens/IDs, validates evidence, derives canonical ledger and hash identities, and performs required transitions; models never construct canonical bytes or hashes, or operation JSON. Freeze merged findings and classify every severe finding. Only `introduced`, `behavior-activated`, or `worsened` with changed-hunk, candidate-created-path, differential-test, or before/after proof may block. Route `pre-existing` and `base-only` to follow-ups; `unknown` escalates. WARNING/SUGGESTION remain `info`. Deterministic blockers need no refuter; all inferential blockers share one read-only refuter batch. Judgment Day uses two independent judges instead.

Ordinary review permits one correction transaction. When finalize reports correction required, rerun it with a positive `--correction-lines` forecast before editing. After the bounded edit, run one read-only scoped fix validator and pass its targeted result with `--validation <file>` plus final test/verification evidence with `--evidence <file>`. The facade maps correction only to corroborated frozen IDs and genesis paths, rejects over-budget repository evidence, and creates or discovers the terminal receipt. Later observations are follow-ups, not another correction. Judgment Day alone keeps its existing two-round rule. SDD then runs one independent requirements/runtime verification. Failure escalates and never starts another reviewer, refuter, correction, or validator.

<!-- authority-first-terminal-procedure:start -->
### Authority-First Terminal Procedure

Use only the compact facade; it appends and reads back native authority before materializing existing compatibility artifacts.

| Order | Operation | Required result | Terminal mirrors |
|---|---|---|---|
| 01 | `launch review agents (review-readability/review-reliability/review-resilience/review-risk)` | target, tier, lenses, and budget bound | blocked |
| 02 | `finalize review via review-refuter + native receipt` | results, evidence, native transitions, and receipt bound | blocked |
| 03 | `validate review receipt via mem_review/mem_search against AGENTS.md <gate> --cwd <repo>` | authority, receipt, and live Git checked | blocked |
| 04 | `reconcile-terminal-mirrors` | existing mirrors reconciled | allowed |

After ambiguous output, rerun the same facade operation; native discovery resumes committed authority without another budget. Malformed or ambiguous lineage remains invalid.