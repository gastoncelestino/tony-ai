/**
 * TonyMem — OpenCode plugin adapter
 *
 * AI baseline: preserve the working OpenCode lifecycle integration from
 * tony-gentle/plugins/engram.ts, while replacing Engram with TonyMem.
 *
 * This first version intentionally does NOT inject memory instructions into
 * the model context. Memory policy, Kernel phases, authorization, evidence,
 * artifacts, and routing will be added in later steps.
 *
 * Flow:
 *   OpenCode events → this plugin → TonyMem SQLite → memory.db
 *
 * The plugin keeps the important lifecycle behavior from Gentle:
 *   - session.created / session.deleted
 *   - ensureSession() with reconnect/reload resilience
 *   - sub-agent session suppression
 *   - user prompt capture
 *   - Task passive capture
 *   - tool counting
 *   - compaction lifecycle hook
 *   - project-name migration
 *   - <private> redaction before persistence
 */

import type { Plugin } from "@opencode-ai/plugin"
import { Database } from "bun:sqlite"
import path from "path"
import { fileURLToPath } from "url"

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url))
const DB_PATH = process.env.LOCAL_MEMORY_DB ?? path.join(PLUGIN_DIR, "..", "local-memory", "memory.db")

const TONYMEM_TOOLS = new Set([
  "mem_search",
  "mem_save",
  "mem_update",
  "mem_get_observation",
  "mem_context",
  "mem_session_summary",
  "mem_suggest_topic_key",
  "mem_save_prompt",
  "mem_review",
])

let db: Database | null = null

function getDb(): Database | null {
  if (db) return db

  try {
    const instance = new Database(DB_PATH, { create: true })
    instance.exec("PRAGMA journal_mode = WAL;")
    instance.exec("PRAGMA busy_timeout = 5000;")
    instance.exec(`
      CREATE TABLE IF NOT EXISTS observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT NOT NULL DEFAULT 'default',
        scope TEXT NOT NULL DEFAULT 'project',
        title TEXT NOT NULL,
        topic_key TEXT,
        type TEXT NOT NULL DEFAULT 'manual',
        content TEXT NOT NULL,
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
        [opts.title, opts.content, opts.type, ts, existing.id],
      )
    } else {
      conn.run(
        "INSERT INTO observations (project, scope, title, topic_key, type, content, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        [opts.project, "project", opts.title, opts.topicKey, opts.type, opts.content, ts, ts],
      )
    }
  } catch (err) {
    console.error("[tonymem] upsert failed:", err)
  }
}

function insertObservation(opts: {
  project: string
  title: string
  content: string
  type: string
}): void {
  const conn = getDb()
  if (!conn) return

  try {
    const ts = nowIso()
    conn.run(
      "INSERT INTO observations (project, scope, title, topic_key, type, content, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
      [opts.project, "project", opts.title, null, opts.type, opts.content, ts, ts],
    )
  } catch (err) {
    console.error("[tonymem] insert failed:", err)
  }
}

function recentContext(project: string, limit = 3): string | null {
  const conn = getDb()
  if (!conn) return null

  try {
    const rows = conn
      .query(
        "SELECT title, content FROM observations WHERE project = ? AND type != 'prompt-capture' ORDER BY updated_at DESC LIMIT ?",
      )
      .all(project, limit) as { title: string; content: string }[]

    if (rows.length === 0) return null
    return rows.map((row) => `### ${row.title}\n${row.content}`).join("\n\n")
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

function extractProjectName(directory: string): string {
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

  try {
    const result = Bun.spawnSync(["git", "-C", directory, "rev-parse", "--show-toplevel"])
    if (result.exitCode === 0) {
      const root = result.stdout?.toString().trim()
      if (root) return root.split("/").pop() ?? "unknown"
    }
  } catch {}

  return directory.split("/").pop() ?? "unknown"
}

function truncate(str: string, max: number): string {
  if (!str) return ""
  return str.length > max ? str.slice(0, max) + "..." : str
}

function stripPrivateTags(str: string): string {
  if (!str) return ""
  return str.replace(/<private>[\s\S]*?<\/private>/gi, "[REDACTED]").trim()
}

export const TonyMem: Plugin = async (ctx) => {
  const oldProject = ctx.directory.split("/").pop() ?? "unknown"
  const project = extractProjectName(ctx.directory)

  const toolCounts = new Map<string, number>()
  const sessionStartTime = new Map<string, number>()
  const knownSessions = new Set<string>()
  const subAgentSessions = new Set<string>()

  function ensureSession(sessionId: string): void {
    if (!sessionId || knownSessions.has(sessionId)) return
    if (subAgentSessions.has(sessionId)) return

    knownSessions.add(sessionId)
    sessionStartTime.set(sessionId, Math.floor(Date.now() / 1000))
  }

  // Eager initialization keeps the first lifecycle event from racing DB setup.
  getDb()

  if (oldProject !== project) {
    migrateProject(oldProject, project)
  }

  return {
    event: async ({ event }) => {
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

      if (event.type === "session.deleted") {
        const info = (event.properties as any)?.info
        const sessionId = info?.id

        if (sessionId) {
          toolCounts.delete(sessionId)
          knownSessions.delete(sessionId)
          subAgentSessions.delete(sessionId)
          sessionStartTime.delete(sessionId)
        }
      }
    },

    "chat.message": async (input, output) => {
      if (subAgentSessions.has(input.sessionID)) return

      const sessionId = input.sessionID
      const content = output.parts
        .filter((part) => part.type === "text")
        .map((part) => (part as any).text ?? "")
        .join("\n")
        .trim()

      const fallback = !content && output.message.summary
        ? `${output.message.summary.title ?? ""}\n${output.message.summary.body ?? ""}`.trim()
        : ""

      const finalContent = content || fallback

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

    // Keep the compaction lifecycle hook from Gentle, but do not inject
    // memory instructions or large historical context into the model.
    "experimental.session.compacting": async (input, output) => {
      if (input.sessionID) {
        ensureSession(input.sessionID)
      }

      // Deliberately no context injection here. Tony Kernel/TonyMem will own
      // compact-context policy in a later step so the prompt stays small.
      void output
      void recentContext
    },
  }
}

export default TonyMem
