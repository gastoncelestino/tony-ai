/**
 * TonyMem — OpenCode plugin adapter (Tony-AI fork of tonymem)
 *
 * Unlike tonymem (Go binary + HTTP daemon on 127.0.0.1:7437), TonyMem has no
 * server process to manage. This plugin talks directly to the same SQLite
 * file that `local-memory/server.py` (the MCP tool server) reads and writes,
 * using Bun's built-in `bun:sqlite` — no npm install, no extra process.
 *
 * Both processes open the DB in WAL mode, which is exactly the concurrency
 * mode SQLite is built for (one writer at a time, readers never block). This
 * removes an entire failure class tonymem had (daemon not running, port
 * conflicts, spawn races) at the cost of nothing — it's a straight
 * simplification, not a compromise.
 *
 * Flow:
 *   OpenCode events → this plugin → bun:sqlite → memory.db (same file
 *   local-memory/server.py uses, same `observations` table/schema)
 *
 * Feature parity with plugins/tonymem.ts:
 *   - session tracking (in-memory only — TonyMem doesn't need a `sessions`
 *     table; start time lives in a Map exactly like `knownSessions` did)
 *   - sub-agent session suppression (issue #116 fix, carried over verbatim)
 *   - user prompt capture (chat.message → mem_save_prompt equivalent)
 *   - passive capture from Task tool output (tool.execute.after)
 *   - always-on memory protocol injected into the system prompt
 *   - "it's been 15 minutes, save something" nudge
 *   - compaction hook: inject recent context + force a session summary
 *   - project rename migration (git remote changed → old project's rows
 *     get relabeled)
 *
 * Not carried over: the HTTP health check / spawn-the-binary dance. There is
 * no binary to spawn — the DB file is created on first use by whichever
 * process (plugin or MCP server) touches it first, via the same
 * `CREATE TABLE IF NOT EXISTS` schema.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { Database } from "bun:sqlite"
import path from "path"
import { fileURLToPath } from "url"

// ─── Configuration ───────────────────────────────────────────────────────────

// Same env var local-memory/server.py already uses — one source of truth
// for where the DB lives, so both processes always agree.
const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url))
const DB_PATH = process.env.LOCAL_MEMORY_DB ?? path.join(PLUGIN_DIR, "..", "local-memory", "memory.db")

// TonyMem's own tools — don't count these as "tool calls" for session stats
const TONYMEM_TOOLS = new Set([
  "mem_search",
  "mem_save",
  "mem_update",
  "mem_get_observation",
  "mem_context",
  "mem_session_summary",
  "mem_suggest_topic_key",
  "mem_save_prompt",
])

// ─── Memory Instructions ─────────────────────────────────────────────────────
// These get injected into the agent's context so it knows to call mem_save.
// Same triggers/policy as tonymem's — only the branding and the tool surface
// (no mem_judge, mem_review, mem_merge_projects — TonyMem doesn't have them,
// and no current prompt actually depends on them) changed.

const MEMORY_INSTRUCTIONS = `## TonyMem Persistent Memory — Protocol

You have access to TonyMem, a persistent memory system that survives across sessions and compactions.

### WHEN TO SAVE (mandatory — not optional)

Call \`mem_save\` IMMEDIATELY after any of these:
- Bug fix completed
- Architecture or design decision made
- Non-obvious discovery about the codebase
- Configuration change or environment setup
- Pattern established (naming, structure, convention)
- User preference or constraint learned

Format for \`mem_save\`:
- **title**: Verb + what — short, searchable (e.g. "Fixed N+1 query in UserList", "Chose Zustand over Redux")
- **type**: bugfix | decision | architecture | discovery | pattern | config | preference
- **scope**: \`project\` (default) | \`personal\`
- **topic_key** (optional, recommended for evolving decisions): stable key like \`architecture/auth-model\`
- **content**:
  **What**: One sentence — what was done
  **Why**: What motivated it (user request, bug, performance, etc.)
  **Where**: Files or paths affected
  **Learned**: Gotchas, edge cases, things that surprised you (omit if none)

Topic rules:
- Different topics must not overwrite each other (e.g. architecture vs bugfix)
- Reuse the same \`topic_key\` to update an evolving topic instead of creating new observations
- If unsure about the key, call \`mem_suggest_topic_key\` first and then reuse it
- Use \`mem_update\` when you have an exact observation ID to correct

### WHEN TO SEARCH MEMORY

When the user asks to recall something — any variation of "remember", "recall", "what did we do",
"how did we solve", or the equivalent in the user's language, or references to past work:
1. First call \`mem_context\` — checks recent session history (fast, cheap)
2. If not found, call \`mem_search\` with relevant keywords (FTS5 full-text search)
3. If you find a match, use \`mem_get_observation\` for full untruncated content

Also search memory PROACTIVELY when:
- Starting work on something that might have been done before
- The user mentions a topic you have no context on — check if past sessions covered it
- The user's FIRST message references the project, a feature, or a problem — call \`mem_search\` with keywords from their message to check for prior work before responding

### SESSION CLOSE PROTOCOL (mandatory)

Before ending a session or saying "done" / "that's it", you MUST:
1. Call \`mem_session_summary\` with this structure:

## Goal
[What we were working on this session]

## Instructions
[User preferences or constraints discovered — skip if none]

## Discoveries
- [Technical findings, gotchas, non-obvious learnings]

## Accomplished
- [Completed items with key details]

## Next Steps
- [What remains to be done — for the next session]

## Relevant Files
- path/to/file — [what it does or what changed]

This is NOT optional. If you skip this, the next session starts blind.

### AFTER COMPACTION

If you see a message about compaction or context reset, or if you see "FIRST ACTION REQUIRED" in your context:
1. IMMEDIATELY call \`mem_session_summary\` with the compacted summary content — this persists what was done before compaction
2. Then call \`mem_context\` to recover any additional context from previous sessions
3. Only THEN continue working

Do not skip step 1. Without it, everything done before compaction is lost from memory.
`

// ─── SQLite ──────────────────────────────────────────────────────────────────
// Same schema as local-memory/server.py's init_db(). Whichever process opens
// the file first creates it; both use IF NOT EXISTS so there's no race.

let db: Database | null = null

function getDb(): Database | null {
  if (db) return db
  try {
    const instance = new Database(DB_PATH, { create: true })
    instance.exec("PRAGMA journal_mode = WAL;")
    instance.exec(`
      CREATE TABLE IF NOT EXISTS observations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project    TEXT NOT NULL DEFAULT 'default',
          scope      TEXT NOT NULL DEFAULT 'project',
          title      TEXT NOT NULL,
          topic_key  TEXT,
          type       TEXT NOT NULL DEFAULT 'manual',
          content    TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
      );
      CREATE UNIQUE INDEX IF NOT EXISTS idx_project_topic
          ON observations(project, topic_key)
          WHERE topic_key IS NOT NULL;
      CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
          USING fts5(title, content, content='observations', content_rowid='id');
      CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
          INSERT INTO observations_fts(rowid, title, content)
          VALUES (new.id, new.title, new.content);
      END;
      CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
          INSERT INTO observations_fts(observations_fts, rowid, title, content)
          VALUES ('delete', old.id, old.title, old.content);
      END;
      CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
          INSERT INTO observations_fts(observations_fts, rowid, title, content)
          VALUES ('delete', old.id, old.title, old.content);
          INSERT INTO observations_fts(rowid, title, content)
          VALUES (new.id, new.title, new.content);
      END;
    `)
    db = instance
    return db
  } catch (err) {
    console.error("[tonymem] failed to open DB:", err)
    return null
  }
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d+Z$/, "Z")
}

/** Upsert into `observations` keyed by (project, topic_key) — same rule
 * mem_save in server.py follows. Used for prompt capture and passive
 * capture writes so the plugin and the MCP server never diverge in
 * behavior for the same kind of write. */
function upsertObservation(opts: {
  project: string
  topicKey: string
  title: string
  content: string
  type: string
}): void {
  const conn = getDb()
  if (!conn) return
  try {
    const ts = nowIso()
    const existing = conn
      .query("SELECT id FROM observations WHERE project = ? AND topic_key = ?")
      .get(opts.project, opts.topicKey) as { id: number } | null

    if (existing) {
      conn.run(
        "UPDATE observations SET title=?, content=?, type=?, updated_at=? WHERE id=?",
        [opts.title, opts.content, opts.type, ts, existing.id]
      )
    } else {
      conn.run(
        "INSERT INTO observations (project, scope, title, topic_key, type, content, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        [opts.project, "project", opts.title, opts.topicKey, opts.type, opts.content, ts, ts]
      )
    }
  } catch (err) {
    console.error("[tonymem] upsert failed:", err)
  }
}

/** Plain insert (no upsert) — used for passive capture, where each Task
 * completion is its own discovery, not a running total to overwrite. */
function insertObservation(opts: { project: string; title: string; content: string; type: string }): void {
  const conn = getDb()
  if (!conn) return
  try {
    const ts = nowIso()
    conn.run(
      "INSERT INTO observations (project, scope, title, topic_key, type, content, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
      [opts.project, "project", opts.title, null, opts.type, opts.content, ts, ts]
    )
  } catch (err) {
    console.error("[tonymem] insert failed:", err)
  }
}

function lastObservationEpoch(project: string): number {
  const conn = getDb()
  if (!conn) return 0
  try {
    const row = conn
      .query("SELECT updated_at FROM observations WHERE project = ? ORDER BY updated_at DESC LIMIT 1")
      .get(project) as { updated_at: string } | null
    if (!row?.updated_at) return 0
    const ms = new Date(row.updated_at).getTime()
    return Number.isNaN(ms) ? 0 : Math.floor(ms / 1000)
  } catch (err) {
    console.error("[tonymem] last-observation lookup failed:", err)
    return 0
  }
}

function recentContext(project: string, limit = 3): string | null {
  const conn = getDb()
  if (!conn) return null
  try {
    const rows = conn
      .query(
        "SELECT title, content FROM observations WHERE project = ? AND type != 'prompt-capture' ORDER BY updated_at DESC LIMIT ?"
      )
      .all(project, limit) as { title: string; content: string }[]
    if (rows.length === 0) return null
    return rows.map((r) => `### ${r.title}\n${r.content}`).join("\n\n")
  } catch (err) {
    console.error("[tonymem] recent-context lookup failed:", err)
    return null
  }
}

function migrateProject(oldProject: string, newProject: string): void {
  const conn = getDb()
  if (!conn) return
  try {
    conn.run("UPDATE observations SET project = ? WHERE project = ?", [newProject, oldProject])
  } catch (err) {
    console.error("[tonymem] project migration failed:", err)
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function extractProjectName(directory: string): string {
  // Try git remote origin URL
  try {
    const result = Bun.spawnSync(["git", "-C", directory, "remote", "get-url", "origin"])
    if (result.exitCode === 0) {
      const url = result.stdout?.toString().trim()
      if (url) {
        const name = url.replace(/\.git$/, "").split(/[/:]/).pop()
        if (name) return name
      }
    }
  } catch {}

  // Fallback: git root directory name (works in worktrees)
  try {
    const result = Bun.spawnSync(["git", "-C", directory, "rev-parse", "--show-toplevel"])
    if (result.exitCode === 0) {
      const root = result.stdout?.toString().trim()
      if (root) return root.split("/").pop() ?? "unknown"
    }
  } catch {}

  // Final fallback: cwd basename
  return directory.split("/").pop() ?? "unknown"
}

function truncate(str: string, max: number): string {
  if (!str) return ""
  return str.length > max ? str.slice(0, max) + "..." : str
}

/**
 * Strip <private>...</private> tags before persisting.
 */
function stripPrivateTags(str: string): string {
  if (!str) return ""
  return str.replace(/<private>[\s\S]*?<\/private>/gi, "[REDACTED]").trim()
}

// ─── Plugin Export ───────────────────────────────────────────────────────────

export const TonyMem: Plugin = async (ctx) => {
  const oldProject = ctx.directory.split("/").pop() ?? "unknown"
  const project = extractProjectName(ctx.directory)

  // Track tool counts per session (in-memory only, not critical)
  const toolCounts = new Map<string, number>()

  // Track last nudge time per session to debounce save reminders
  const lastNudgeTime = new Map<string, number>() // sessionID -> epoch seconds

  // Track session start time locally — replaces the HTTP round-trip tonymem
  // needed to ask its daemon "when did this session start".
  const sessionStartTime = new Map<string, number>() // sessionID -> epoch seconds

  // Track sub-agent session IDs so we can suppress their tool-hook registrations.
  // Sub-agents (Task() calls) have a parentID or a title ending in " subagent)".
  // We must not register them as top-level TonyMem sessions — they cause session
  // inflation (e.g. 170 sessions for 1 real conversation, carried over from
  // tonymem issue #116).
  const subAgentSessions = new Set<string>()
  const knownSessions = new Set<string>()

  function ensureSession(sessionId: string): void {
    if (!sessionId || knownSessions.has(sessionId)) return
    if (subAgentSessions.has(sessionId)) return
    knownSessions.add(sessionId)
    sessionStartTime.set(sessionId, Math.floor(Date.now() / 1000))
  }

  // Open (or create) the DB eagerly so a cold start doesn't lose the first
  // few writes to a lazy-init race.
  getDb()

  // Migrate project name if it changed (one-time, idempotent)
  if (oldProject !== project) {
    migrateProject(oldProject, project)
  }

  return {
    // ─── Event Listeners ───────────────────────────────────────────

    event: async ({ event }) => {
      // --- Session Created ---
      if (event.type === "session.created") {
        const info = (event.properties as any)?.info
        const sessionId = info?.id
        const parentID = info?.parentID
        const title: string = info?.title ?? ""

        const isSubAgent = !!parentID || title.endsWith(" subagent)")

        if (sessionId && !isSubAgent) {
          ensureSession(sessionId)
        } else if (sessionId && isSubAgent) {
          subAgentSessions.add(sessionId)
        }
      }

      // --- Session Deleted ---
      if (event.type === "session.deleted") {
        const info = (event.properties as any)?.info
        const sessionId = info?.id
        if (sessionId) {
          toolCounts.delete(sessionId)
          knownSessions.delete(sessionId)
          subAgentSessions.delete(sessionId)
          lastNudgeTime.delete(sessionId)
          sessionStartTime.delete(sessionId)
        }
      }
    },

    // ─── User Prompt Capture ──────────────────────────────────────
    // chat.message is called once per user message, before the LLM sees it.

    "chat.message": async (input, output) => {
      if (subAgentSessions.has(input.sessionID)) return

      const sessionId = input.sessionID

      const content = output.parts
        .filter((p) => p.type === "text")
        .map((p) => (p as any).text ?? "")
        .join("\n")
        .trim()

      const fallback = !content && output.message.summary
        ? `${output.message.summary.title ?? ""}\n${output.message.summary.body ?? ""}`.trim()
        : ""

      const finalContent = content || fallback

      // Only capture non-trivial prompts (>10 chars)
      if (finalContent.length > 10) {
        ensureSession(sessionId)
        upsertObservation({
          project,
          topicKey: `prompt/${project}/${sessionId}`,
          title: `Prompt capture — ${project}/${sessionId}`,
          content: stripPrivateTags(truncate(finalContent, 2000)),
          type: "prompt-capture",
        })
      }
    },

    // ─── Tool Execution Hook ─────────────────────────────────────
    // Count tool calls per session (for session end stats).
    // Passive capture: when a Task tool completes, save its output as a
    // discovery so it's searchable even if the sub-agent forgot to mem_save.

    "tool.execute.after": async (input, output) => {
      if (TONYMEM_TOOLS.has(input.tool.toLowerCase())) return

      const sessionId = input.sessionID
      if (sessionId) {
        ensureSession(sessionId)
        toolCounts.set(sessionId, (toolCounts.get(sessionId) ?? 0) + 1)
      }

      if (input.tool === "Task" && output && sessionId) {
        const text = typeof output === "string" ? output : JSON.stringify(output)
        if (text.length > 50) {
          insertObservation({
            project,
            title: `Task output — ${project}/${sessionId}`,
            content: stripPrivateTags(truncate(text, 4000)),
            type: "discovery",
          })
        }
      }
    },

    // ─── System Prompt: Always-on memory instructions ──────────
    // Injects MEMORY_INSTRUCTIONS into the system prompt of every message.
    //
    // We append to the last existing system entry instead of pushing a new one.
    // Some models (Qwen3.5, Mistral/Ministral via llama.cpp) reject multiple
    // system messages — their Jinja chat templates only allow a single system
    // block at the beginning. By concatenating, we avoid adding extra system
    // messages that would break these models.

    "experimental.chat.system.transform": async (input, output) => {
      if (output.system.length > 0) {
        output.system[output.system.length - 1] += "\n\n" + MEMORY_INSTRUCTIONS
      } else {
        output.system.push(MEMORY_INSTRUCTIONS)
      }

      // ── Save nudge ──────────────────────────────────────────────────────────
      try {
        const sessionID: string = input.sessionID ?? ""
        if (!sessionID || subAgentSessions.has(sessionID)) return

        const cooldownSecs = parseInt(process.env.TONYMEM_NUDGE_COOLDOWN_SECS ?? "900", 10)
        const nowSecs = Math.floor(Date.now() / 1000)

        const lastNudge = lastNudgeTime.get(sessionID)
        if (lastNudge !== undefined && nowSecs - lastNudge < cooldownSecs) return

        // Skip if the session is too young (< 5 minutes)
        const sessionStartEpoch = sessionStartTime.get(sessionID) ?? 0
        if (sessionStartEpoch > 0 && nowSecs - sessionStartEpoch < 300) return

        const lastObsEpoch = lastObservationEpoch(project)
        // No observations yet — nothing to nudge about
        if (lastObsEpoch === 0) return

        // Only nudge if last save was more than 15 minutes ago
        if (nowSecs - lastObsEpoch < 900) return

        const nudge =
          "\n\nMEMORY REMINDER: It's been over 15 minutes since your last memory save. " +
          "If you've made decisions, discoveries, completed significant work, or found non-obvious things, " +
          "call mem_save now."
        if (output.system.length > 0) {
          output.system[output.system.length - 1] += nudge
        } else {
          output.system.push(nudge)
        }
        lastNudgeTime.set(sessionID, nowSecs)
      } catch {
        // Any unexpected error — silently skip the nudge, never crash the hook
      }
    },

    // ─── Compaction Hook: Persist memory + inject context ──────────
    // Compaction is triggered by the system when context gets too long. The
    // old agent "dies" and a new one starts with the compacted summary.

    "experimental.session.compacting": async (input, output) => {
      if (input.sessionID) {
        ensureSession(input.sessionID)
      }

      const contextText = recentContext(project, 3)
      if (contextText) {
        output.context.push(contextText)
      }

      output.context.push(
        `CRITICAL INSTRUCTION FOR COMPACTED SUMMARY:\n` +
        `The agent has access to TonyMem persistent memory via MCP tools.\n` +
        `You MUST include the following instruction at the TOP of the compacted summary:\n\n` +
        `"FIRST ACTION REQUIRED: Call mem_session_summary with the content of this compacted summary. ` +
        `Use project: '${project}'. This preserves what was accomplished before compaction. Do this BEFORE any other work."\n\n` +
        `This is NOT optional. Without this, everything done before compaction is lost from memory.`
      )
    },
  }
}

export default TonyMem
