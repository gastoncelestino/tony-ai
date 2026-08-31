/**
 * TonyMem — OpenCode plugin adapter
 *
 * AI baseline: this plugin preserves the working OpenCode lifecycle integration
 * from tony-gentle/plugins/engram.ts. The memory backend is TonyMem via
 * Bun's built-in bun:sqlite.
 *
 * IMPORTANT: this is intentionally a lifecycle baseline. Do not add Kernel
 * phases, authorization, evidence, artifacts, reviewers, SDD, or memory-policy
 * prompts here yet. Those are subsequent incremental changes after the
 * lifecycle has been proven from a real OpenCode execution.
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

function truncate(str: string, max: number): string {
  if (!str) return ""
  return str.length > max ? str.slice(0, max) + "..." : str
}

function stripPrivateTags(str: string): string {
  if (!str) return ""
  return str.replace(/<private>[\s\S]*?<\/private>/gi, "[REDACTED]").trim()
}

function upsertObservation(opts: {
  project: string
  scope?: string
  title: string
  topicKey?: string | null
  type?: string
  content: string
}) {
  const database = getDb()
  if (!database) return
  const timestamp = nowIso()

  if (opts.topicKey) {
    database
      .prepare(`
        INSERT INTO observations
          (project, scope, title, topic_key, type, content, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project, topic_key) DO UPDATE SET
          scope = excluded.scope,
          title = excluded.title,
          type = excluded.type,
          content = excluded.content,
          updated_at = excluded.updated_at
      `)
      .run(
        opts.project,
        opts.scope ?? "project",
        opts.title,
        opts.topicKey,
        opts.type ?? "manual",
        opts.content,
        timestamp,
        timestamp,
      )
    return
  }

  database
    .prepare(`
      INSERT INTO observations
        (project, scope, title, topic_key, type, content, created_at, updated_at)
      VALUES (?, ?, ?, NULL, ?, ?, ?, ?)
    `)
    .run(
      opts.project,
      opts.scope ?? "project",
      opts.title,
      opts.type ?? "manual",
      opts.content,
      timestamp,
      timestamp,
    )
}

function extractProjectName(directory: string): string {
  const parts = directory.split("/").filter(Boolean)
  return parts.pop() ?? "unknown"
}

export const TonyMem: Plugin = async (ctx) => {
  const oldProject = ctx.directory.split("/").pop() ?? "unknown"
  const project = extractProjectName(ctx.directory)

  const toolCounts = new Map<string, number>()
  const lastNudgeTime = new Map<string, number>()
  const knownSessions = new Set<string>()
  const subAgentSessions = new Set<string>()

  async function ensureSession(sessionId: string): Promise<void> {
    if (!sessionId || knownSessions.has(sessionId)) return
    if (subAgentSessions.has(sessionId)) return
    knownSessions.add(sessionId)
    // TonyMem has no sessions table. Session tracking is intentionally kept
    // in-memory, matching the lifecycle role of the original Engram adapter.
  }

  getDb()

  if (oldProject !== project) {
    try {
      getDb()?.prepare("UPDATE observations SET project = ? WHERE project = ?").run(project, oldProject)
    } catch {
      // Memory must never break OpenCode startup.
    }
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
          await ensureSession(sessionId)
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
          lastNudgeTime.delete(sessionId)
        }
      }
    },

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

      if (finalContent.length > 10) {
        await ensureSession(sessionId)
        upsertObservation({
          project,
          title: "User prompt",
          type: "prompt",
          content: stripPrivateTags(truncate(finalContent, 2000)),
        })
      }
    },

    "tool.execute.after": async (input, output) => {
      if (TONYMEM_TOOLS.has(input.tool.toLowerCase())) return

      const sessionId = input.sessionID
      if (sessionId) {
        await ensureSession(sessionId)
        toolCounts.set(sessionId, (toolCounts.get(sessionId) ?? 0) + 1)
      }

      if (input.tool.toLowerCase() === "task") {
        const outputText = typeof output === "string"
          ? output
          : JSON.stringify(output ?? "")

        if (outputText.length > 10 && sessionId && !subAgentSessions.has(sessionId)) {
          upsertObservation({
            project,
            title: "Task result",
            type: "task_result",
            content: stripPrivateTags(truncate(outputText, 4000)),
          })
        }
      }
    },

    "experimental.chat.system.transform": async (_input, _output) => {
      // Intentionally empty in the lifecycle baseline. No memory instructions
      // are injected into model context. Kernel will own policy later.
    },

    "experimental.session.compacting": async (_input, _output) => {
      // Lifecycle hook intentionally preserved as a no-op baseline.
      // Context recovery/persistence will be added incrementally later.
    },
  }
}
