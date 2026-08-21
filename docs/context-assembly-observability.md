# Context Assembly Observability

## Metric: `accepted_context_chars`

Context Assembly records the cumulative number of characters of assembled context accepted into a session's system context.

The metric is emitted through OpenCode structured logging with:

- `service`: `context-assembly`
- `level`: `info`
- `message`: `accepted context characters`
- `extra.sessionID`: the OpenCode session identifier
- `extra.accepted_context_chars`: cumulative accepted context characters for that session

The value is the length of the actual context block appended by Context Assembly. It therefore includes the assembly's provenance and section formatting and reflects the characters actually admitted to the system context, not merely the raw source payload size.

## Session semantics

The counter is maintained independently for each `sessionID`.

Each successful context assembly adds its accepted block length to the session total. A later assembly in the same session reports the cumulative value rather than resetting the counter.

When OpenCode emits `session.deleted`, the session counter and any pending context for that session are discarded.

## Existing decision statistics

The existing `ContextAssemblyStats` fields remain available for detailed decision analysis:

- documentation/code received;
- accepted items;
- deduplicated items;
- budget rejections;
- source characters used;
- total budget.

`accepted_context_chars` complements those fields by answering the session-level question: **how many characters were actually admitted into the assembled context during this session?**

## Privacy and logging

The metric does not log context content, source text, prompts, or code bodies. Only the session identifier and character count are emitted.

OpenCode logging failures are intentionally non-blocking: failure to record the metric must not prevent Context Assembly from delivering valid context to the agent.
