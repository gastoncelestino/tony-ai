---
description: Show TonyMem observation and Judgment Day memory stats for the current project
agent: tony-orchestrator
subtask: true
---

Call, for the current project:

1. `mem_stats` (local-memory MCP) — observation counts by type, last-updated timestamp.
2. `jd_stats` (judgment-memory MCP) — total judgments, breakdown by `final` outcome and by `agreement`, and `contradiction_rate`.

Report both plainly as two short sections (Observations / Judgment Day). If `jd_stats` shows zero judgments, say the ledger is empty rather than omitting the section — this command is also how someone confirms `jd_record` calls are actually landing.
