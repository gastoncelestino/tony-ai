---
description: List recent Judgment Day outcomes for the current project (or all projects)
agent: tony-orchestrator
subtask: true
---

Arguments (optional): $ARGUMENTS
Interpret `$ARGUMENTS` as an optional limit (integer) and/or `--all-projects`. Default limit is 10, default scope is the current project.

Call `jd_history` (judgment-memory MCP — `judgment-memory/server.py`) with those parameters. This reads the SQLite ledger directly (`judgment-memory/ledger.py`), so it always works even if Qdrant/Ollama are down — unlike `/memory-search`, it has no embedding dependency.

Return a table: execution_id, task, final, agreement, fix, lesson, created_at — most recent first. If empty, say the ledger has no entries for that scope yet.
