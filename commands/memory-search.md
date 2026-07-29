---
description: Search TonyMem observations and Judgment Day memory for a query
agent: gentle-orchestrator
subtask: true
---

Query: $ARGUMENTS

Run two lookups and merge the results, since they cover different stores:

1. `mem_search` (local-memory MCP — `local-memory/server.py`) — full-text FTS5 search over TonyMem's `observations` table for the current project.
2. `jd_recall` (judgment-memory MCP — `judgment-memory/server.py`) — semantic (Qdrant) search over past Judgment Day lessons for the current project. If it returns `available: false`, say so plainly (Ollama/Qdrant likely aren't running) rather than treating it as zero results.

Return a single merged list, each entry tagged with its source (`observation` or `judgment`), most relevant first. If both come back empty, say so — don't invent results.
