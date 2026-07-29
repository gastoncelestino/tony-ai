# Review Ledger, Transaction, and Persistence Contract

Shared contract for both review lineages this project runs: ordinary 4R
(`review-risk`, `review-readability`, `review-reliability`, `review-resilience`,
corroborated by `review-refuter`, orchestrated through the native `gentle-ai
review start/finalize/validate` facade) and Judgment Day (`jd-judge-a` +
`jd-judge-b` blind dual review, orchestrated entirely by the parent — see
`../judgment-day/SKILL.md`). Both lineages read and write the same five
artifacts in the same shape, so `sdd-status`, `sdd-verify`, and `sdd-archive`
can consume either without caring which one produced them. This file exists
because `judgment-day/SKILL.md` references it as canonical; nothing here
invents new mechanics — it consolidates field names and rules already
asserted across `sdd-status-contract.md`, `sdd-archive/SKILL.md`,
`sdd-verify/SKILL.md`, and `judgment-day/references/prompts-and-formats.md`
into one place so orchestration stops re-deriving them per session.

## The Five Artifacts

Every review lineage produces exactly these, never more, never fewer:

| Artifact | Written by | Authoritative for |
|---|---|---|
| `transaction` | Both lineages | Current round, mode, lineage/generation counters, state |
| `ledger` | Both lineages | Frozen findings — the corroborated record |
| `receipt` | Terminal step only | Signed-off approval bound to an exact candidate tree |
| `chain-bundle` | Both lineages | Portable recovery snapshot — non-authoritative |
| `gate-context` | Post-apply gate only | Why `reviewGate.result` is what it is |

### Persistence paths (exact, per artifact store — do not vary)

- **openspec / hybrid**: `openspec/changes/{change-name}/reviews/{transaction,ledger,receipt,chain-bundle,gate-context}.json`
- **engram** (TonyMem, same tool names): exact topic keys `sdd/{change-name}/review/{transaction,ledger,receipt,chain-bundle,gate-context}`, written with `mem_save`/`mem_update` and read with `mem_search` + `mem_get_observation`, same convention every other SDD artifact already uses.

The chain bundle is a portable, non-authoritative recovery source. It requires
explicit validated import into the repository-derived store before anything
treats it as truth — never substitute it for the live transaction/ledger when
those are readable.

## `transaction` schema

```yaml
schemaName: gentle-ai.review-transaction
schemaVersion: 1
targetIdentity: <sha256 of the immutable candidate target>
mode: ordinary_4r | judgment_day
state: open | judging | correcting | rejudging | approved | escalated
round: 1 | 2
lineageId: <stable id for this review lineage>
generation: 0
correctionBudget:
  fixRoundsUsed: 0
  fixRoundsMax: 2
  scopedRejudgmentsUsed: 0
  scopedRejudgmentsMax: 2
baseRelationship: <base SHA or ref this target was built against>
```

- `state` values are the only legal values; there is no third round for
  either lineage. `fixRoundsMax`/`scopedRejudgmentsMax` are hard-capped at 2
  each per `judgment-day/SKILL.md`'s hard rules — an orchestrator must never
  raise them for a given lineage, even under user pressure. A lineage that
  exhausts its budget with unresolved severe findings moves straight to
  `escalated`; it is never reset or extended (open a new lineage instead).
- `mode` is set once at `review/start` and never changes for that lineage.
  Ordinary 4R and Judgment Day never share a lineage — `judgment-day/SKILL.md`
  is explicit that Judgment Day *replaces* ordinary 4R for a target, it does
  not run alongside it.

## `ledger` schema

```yaml
schemaName: gentle-ai.review-ledger
schemaVersion: 1
targetIdentity: <matches transaction.targetIdentity>
findings:
  - id: <stable finding id within this lineage>
    location: <path:line>
    severity: CRITICAL | WARNING | SUGGESTION
    claim: <observable incorrect behavior, not a style opinion>
    evidenceClass: deterministic | inferential
    causalDisposition: introduced | behavior-activated | worsened | pre-existing | base-only | unknown
    proofRefs: [<concrete proof: changed-hunk, differential-test, candidate-created-path, or before/after>]
    corroboration: confirmed | suspect | contradiction | info
    reportedBy: [jd-judge-a, jd-judge-b] | [review-risk, review-readability, review-reliability, review-resilience] | [review-refuter]
    fixCaused: false
```

- `corroboration` is derived, not asserted by a single reviewer:
  - **Judgment Day**: `confirmed` requires both `jd-judge-a` and `jd-judge-b`
    to independently report the same finding. `suspect` = exactly one judge.
    `contradiction` = judges disagree about the same location/claim — this
    always routes to human escalation per the Decision Gates table, never to
    an automatic fix.
  - **Ordinary 4R**: `confirmed` requires `review-refuter` to return
    `corroborated` for that finding; `refuted` findings are dropped, not kept
    as `info`; `inconclusive` becomes `suspect`.
- `WARNING`/`SUGGESTION` rows never gate anything and are never auto-fixed —
  they stay `info` regardless of corroboration, per Judgment Day's hard rules.
- Only the parent orchestrator (never a judge, never the fix actor) merges
  findings into this ledger and persists it. Judges and reviewers return
  results; they do not write the ledger themselves.
- `fixCaused: true` marks a defect a scoped re-judgment attributes to the fix
  itself (introduced while fixing something else) — these feed back into
  `findings` as new entries on the next round, capped by the same
  `correctionBudget`.

## `receipt` schema (terminal only — must not exist before `state: approved`)

```yaml
schemaName: gentle-ai.review-receipt
schemaVersion: 1
targetIdentity: <matches transaction.targetIdentity>
finalCandidateTree: <sha256 of the tree the receipt approves>
pathsDigest: <hash of the exact file set covered>
policy: <mode + budget snapshot at approval time>
ledgerRef: <pointer to the frozen ledger this receipt closes over>
fixDelta: <summary of what changed between rounds, if any>
verificationEvidence: <current independent verification results this receipt relies on>
modeCounters: { fixRoundsUsed: 0, scopedRejudgmentsUsed: 0 }
baseRelationship: <base SHA or ref>
approvedAt: <timestamp>
```

A receipt is valid for exactly one `finalCandidateTree`. Any further edit to
the target invalidates it — `sdd-archive` and pre-commit/pre-push/pre-PR
validation must confirm the receipt's tree matches the live tree before
trusting it; a stale receipt blocks archive the same as a missing one.

## `gate-context` schema (post-apply gate only)

```yaml
schemaName: gentle-ai.review-gate-context
schemaVersion: 1
targetIdentity: <matches transaction.targetIdentity>
result: allow | scope-changed | invalidated | escalated
reason: <deterministic explanation, not prose speculation>
receiptRef: <pointer to the receipt this gate decision is bound to, or null>
```

This is what `reviewGate` in the `sdd-status` schema (see
`sdd-status-contract.md`) surfaces to `sdd-archive`. It is written once the
post-apply gate runs and is never present before then — `sdd-verify` must
not require it, since final verification has to complete before it can exist.

## Round and lineage rules (apply to both lineages)

- At most 2 fix rounds and 2 scoped re-judgments per lineage. No third round
  exists under any circumstance, including explicit user request — open a
  new lineage instead, which starts its own budget from zero.
- A lineage in `escalated` is terminal. Nothing reopens it; a new lineage for
  the same target is a new `lineageId`, not a mutation of the old one.
- Scoped re-judgment reads only the frozen ledger plus the immutable fix
  delta — never the original full target again — and may add `fixCaused`
  entries, never remove or soften existing corroborated findings.

## Cross-references

- Ordinary 4R corroboration and native facade calls (`gentle-ai review
  start/finalize/validate`): see `commands/sdd-apply.md`'s Authority-First
  Terminal Procedure table.
- Judgment Day execution order, hard rules, and judge/fix prompts: see
  `../judgment-day/SKILL.md` and `../judgment-day/references/prompts-and-formats.md`.
- Archive-time gating on these artifacts: see `../sdd-archive/SKILL.md`.
- Status surface (`reviewGate`, `artifactPaths.review*`): see
  `sdd-status-contract.md`.
