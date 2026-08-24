---
name: judgment-day
description: "Trigger: judgment day, dual review, adversarial review, juzgar. Run explicit blind dual review with at most two scoped fix/re-judgment rounds."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.6"
---

## Activation Contract

Load only when the user explicitly requests Judgment Day or equivalent dual/adversarial review for a concrete target. Judgment Day replaces ordinary 4R for that target; never run both.

## Hard Rules

- Before building the target, call `jd_recall` (judgment-memory MCP server — see `../../plugins/judgment-memory.ts`) with a short task description. A returned match is prior context for the judges, never a substitute for their independent read, and never skips a round or changes the Decision Gates below.
- Resolve matching project skills before starting and pass the same paths to both judges and any fix actor.
- Build one complete immutable target, then launch two blind read-only judges in parallel with identical scope and criteria.
- Each judge returns one neutral findings result and terminates. Wait for both; never accept a partial judgment.
- Never launch `review-refuter`; two-judge agreement is the corroboration mechanism.
- Only the parent orchestrator merges/persists findings, launches the fix actor, launches scoped re-judgment, and updates native counters.
- Fix only severe findings confirmed by both judges. WARNING/SUGGESTION rows remain `info`.
- Permit at most two fix rounds and two scoped re-judgments. Re-judgment sees only the frozen ledger plus fix delta and may record fix-caused defects.
- Terminal transaction states are only `approved | escalated`; never reset or extend an exhausted lineage.

## Decision Gates

| Condition | Action |
|---|---|
| Target unclear | Ask one scope question and stop. |
| Both judges confirm severe finding | Ask before round-one correction; then use the bounded fix actor. |
| One judge reports it | Record suspect; do not auto-fix. |
| Judges contradict | Escalate for explicit human decision. |
| Scoped re-judgment fails before round two | Parent may launch the final bounded fix round. |
| Any issue remains after round two | Escalate and stop. |

## Execution Steps

1. Call `jd_recall(task=<short target description>)`. If it returns a close match, note its `lesson`/`fix` for the judge prompts in step 3.
2. Start `review/start(target, mode=judgment_day)` and persist the transaction.
3. Launch both read-only judges against the same immutable target.
4. Merge findings into the frozen ledger and persist it through the selected artifact store.
5. Ask before round-one correction; run the fix actor only for confirmed severe IDs.
6. Run both judges again only over the frozen ledger plus immutable fix delta.
7. Repeat once at most, then run independent final verification and emit the terminal receipt.
8. Once the terminal `JUDGMENT: APPROVED ✅` / `JUDGMENT: ESCALATED ⚠️` is emitted, call `jd_record` with the full outcome (see `../../judgment-memory/schema.json`) so future step-1 recalls can find it. Only the parent orchestrator calls this — same authority rule as everything else in this file.

## Output Contract

Return target identity, round, confirmed/suspect/contradiction/INFO counts, correction work units, scoped re-judgment result, artifact references, skill resolution, and exactly one final `JUDGMENT: APPROVED ✅` or `JUDGMENT: ESCALATED ⚠️`.

## References

- [../_shared/review-ledger-contract.md](../_shared/review-ledger-contract.md) — canonical transaction, ledger, persistence, and lifecycle contract.
- [references/prompts-and-formats.md](references/prompts-and-formats.md) — compact judge/fix prompts and verdict shape.
