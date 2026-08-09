# TonyMem Artifact Convention (shared across all SDD skills)

## Storage Model

TonyMem persists SDD artifacts as observations in a shared SQLite database
(`memory.db`). Each artifact is one row in the `observations` table, keyed by
`(project, topic_key)` with upsert semantics: saving the same `topic_key` again
updates the existing row instead of creating a duplicate.

## Topic Key Format

Every SDD artifact uses a deterministic topic key so phases can find each
other's output without guessing:

```
sdd/{change-name}/{artifact-type}
```

| Artifact | Topic Key |
|----------|-----------|
| Project context | `sdd-init/{project}` |
| Exploration | `sdd/{change-name}/explore` |
| Proposal | `sdd/{change-name}/proposal` |
| Spec | `sdd/{change-name}/spec` |
| Design | `sdd/{change-name}/design` |
| Tasks | `sdd/{change-name}/tasks` |
| Apply progress | `sdd/{change-name}/apply-progress` |
| Verify report | `sdd/{change-name}/verify-report` |
| Archive report | `sdd/{change-name}/archive-report` |

## mem_save Contract

When persisting an artifact to tonymem, use:

```
mem_save(
  title: "sdd/{change-name}/{artifact-type}",
  topic_key: "sdd/{change-name}/{artifact-type}",
  type: "architecture",
  project: "{project}",
  capture_prompt: false,
  content: "{full artifact markdown}"
)
```

Rules:
- `capture_prompt: false` is mandatory for automated SDD artifacts. They are
  pipeline outputs, not human/proactive memory saves.
- If the tool schema does not expose `capture_prompt`, omit it rather than
  failing the save.
- `type` is advisory metadata; use `architecture` for planning artifacts,
  `decision` for choices, `bugfix` for corrections, or match the artifact kind.

## mem_get_observation Contract

`mem_search` returns 300-character previews. For full artifact content, always
follow up with `mem_get_observation(id)`. Never treat a search preview as
source material.

## mem_search Queries

To find an existing artifact:

```
mem_search(query: "sdd/{change-name}/{artifact-type}", project: "{project}")
```

To list all artifacts for a change:

```
mem_search(query: "sdd/{change-name}/", project: "{project}")
```

## Project Isolation

Every `mem_save` and `mem_search` MUST include `project`. Observations are
scoped by project; omitting `project` breaks isolation and pollutes other
projects' recall.

## Concurrent Writes

Two concurrent saves of the same `(project, topic_key)` must not crash. The
upsert path handles this at the SQLite level (`ON CONFLICT DO UPDATE`). Do not
implement manual read-modify-write cycles; always use `mem_save` with the
topic_key above.

## Fallback When tonymem Is Unavailable

If `mem_save` or `mem_search` returns `available: false` or fails, degrade to
`none` mode for that operation: return the artifact inline in your response and
do not block the phase. Report the degraded path in the Section D return
envelope's `risks` field.
