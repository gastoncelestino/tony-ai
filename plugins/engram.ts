/**
 * Engram — OpenCode plugin adapter
 *
 * Thin layer that connects OpenCode's event system to the Engram Go binary.
 * The Go binary runs as a local HTTP server and handles all persistence.
 *
 * Flow:
 *   OpenCode events → this plugin → HTTP calls → engram serve → SQLite
 *
 * Session resilience:
 *   Uses `ensureSession()` before any DB write. This means sessions are
 *   created on-demand — even if the plugin was loaded after the session
 *   started (restart, reconnect, etc.). The session ID comes from OpenCode's
 *   hooks (input.sessionID) rather than relying on a session.created event.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { appendFileSync } from "node:fs"
import path from "node:path"

const ENGRAM_PORT = parseInt(process.env.ENGRAM_PORT ?? "7437")
const ENGRAM_URL = `http://127.0.0.1:${ENGRAM_PORT}`
const ENGRAM_BIN = process.env.ENGRAM_BIN ?? Bun.which("engram") ?? "/home/tony/.local/bin/engram"
const DEBUG_LOG_PATH = process.env.TONY_DEBUG_LOG ?? path.join(process.cwd(), "engram-debug.log")

function debugLog(message: string, details?: Record<string, unknown>) {
  try {
    const suffix = details ? ` ${JSON.stringify(details)}` : ""
    appendFileSync(DEBUG_LOG_PATH, `[${new Date().toISOString()}] [ENGRAM] ${message}${suffix}\n`, "utf8")
  } catch (err) {
    console.error("[engram] debug log failed:", err)
  }
}

const ENGRAM_TOOLS = new Set([
  "mem_search",
  "mem_save",
  "mem_update",
  "mem_delete",
  "mem_suggest_topic_key",
  "mem_save_prompt",
  "mem_session_summary",
  "mem_context",
  "mem_stats",
  "mem_timeline",
  "mem_get_observation",
  "mem_session_start",
  "mem_session_end",
])

const MEMORY_INSTRUCTIONS = `## Engram Persistent Memory — Protocol

You have access to Engram, a persistent memory system that survives across sessions and compactions.

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

async function engramFetch(
  path: string,
  opts: { method?: string; body?: any } = {}
): Promise<any> {
  const method = opts.method ?? "GET"
  debugLog("HTTP request", { method, path, hasBody: !!opts.body })
  try {
    const res = await fetch(`${ENGRAM_URL}${path}`, {
      method,
      headers: opts.body ? { "Content-Type": "application/json" } : undefined,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    })
    const data = await res.json()
    debugLog("HTTP response", { method, path, status: res.status, ok: res.ok })
    return data
  } catch (err) {
    debugLog("HTTP failed", { method, path, error: String(err) })
    return null
  }
}

async function isEngramRunning(): Promise<boolean> {
  try {
    const res = await fetch(`${ENGRAM_URL}/health`, {
      signal: AbortSignal.timeout(500),
    })
    debugLog("health check", { status: res.status, ok: res.ok })
    return res.ok
  } catch (err) {
    debugLog("health check failed", { error: String(err) })
    return false
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

export const Engram: Plugin = async (ctx) => {
  const oldProject = ctx.directory.split("/").pop() ?? "unknown"
  const project = extractProjectName(ctx.directory)
  debugLog("plugin initialized", { project, directory: ctx.directory, oldProject, engramUrl: ENGRAM_URL, engramBin: ENGRAM_BIN, debugLog: DEBUG_LOG_PATH })

  const toolCounts = new Map<string, number>()
  const lastNudgeTime = new Map<string, number>()
  const knownSessions = new Set<string>()
  const subAgentSessions = new Set<string>()

  async function ensureSession(sessionId: string): Promise<void> {
    if (!sessionId || knownSessions.has(sessionId)) return
    if (subAgentSessions.has(sessionId)) {
      debugLog("session skipped: subagent", { sessionID: sessionId })
      return
    }
    knownSessions.add(sessionId)
    debugLog("ensuring session", { sessionID: sessionId, project })
    await engramFetch("/sessions", {
      method: "POST",
      body: {
        id: sessionId,
        project,
        directory: ctx.directory,
      },
    })
  }

  const running = await isEngramRunning()
  if (!running) {
    debugLog("Engram server not running; attempting spawn", { command: ENGRAM_BIN })
    try {
      Bun.spawn([ENGRAM_BIN, "serve"], {
        stdout: "ignore",
        stderr: "ignore",
        stdin: "ignore",
      })
      await new Promise((r) => setTimeout(r, 500))
      debugLog("Engram server spawn attempted")
    } catch (err) {
      debugLog("Engram server spawn failed", { error: String(err) })
    }
  } else {
    debugLog("Engram server already running")
  }

  if (oldProject !== project) {
    debugLog("project migration", { oldProject, project })
    await engramFetch("/projects/migrate", {
      method: "POST",
      body: { old_project: oldProject, new_project: project },
    })
  }

  try {
    const manifestFile = `${ctx.directory}/.engram/manifest.json`
    const file = Bun.file(manifestFile)
    if (await file.exists()) {
      debugLog("Engram sync import started", { manifestFile })
      Bun.spawn([ENGRAM_BIN, "sync", "--import"], {
        cwd: ctx.directory,
        stdout: "ignore",
        stderr: "ignore",
        stdin: "ignore",
      })
    } else {
      debugLog("Engram sync import skipped: no manifest", { manifestFile })
    }
  } catch (err) {
    debugLog("Engram sync import failed", { error: String(err) })
  }

  return {
    event: async ({ event }) => {
      debugLog("event", { type: event.type })

      if (event.type === "session.created") {
        const info = (event.properties as any)?.info
        const sessionId = info?.id
        const parentID = info?.parentID
        const title: string = info?.title ?? ""
        const isSubAgent = !!parentID || title.endsWith(" subagent)")
        debugLog("session.created", { sessionID: sessionId, parentID, title, isSubAgent })

        if (sessionId && !isSubAgent) {
          await ensureSession(sessionId)
        } else if (sessionId && isSubAgent) {
          subAgentSessions.add(sessionId)
          debugLog("subagent session registered", { sessionID: sessionId, parentID })
        }
      }

      if (event.type === "session.deleted") {
        const info = (event.properties as any)?.info
        const sessionId = info?.id
        debugLog("session.deleted", { sessionID: sessionId })
        if (sessionId) {
          toolCounts.delete(sessionId)
          knownSessions.delete(sessionId)
          subAgentSessions.delete(sessionId)
          lastNudgeTime.delete(sessionId)
        }
      }
    },

    "chat.message": async (input, output) => {
      if (subAgentSessions.has(input.sessionID)) {
        debugLog("chat.message skipped: subagent", { sessionID: input.sessionID })
        return
      }

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
      debugLog("chat.message", { sessionID: sessionId, contentLength: finalContent.length, contentPreview: truncate(finalContent, 120) })

      if (finalContent.length > 10) {
        await ensureSession(sessionId)
        await engramFetch("/prompts", {
          method: "POST",
          body: {
            session_id: sessionId,
            content: stripPrivateTags(truncate(finalContent, 2000)),
            project,
          },
        })
      } else {
        debugLog("prompt not persisted: length <= 10", { sessionID: sessionId, contentLength: finalContent.length })
      }
    },

    "tool.execute.after": async (input, output) => {
      const toolName = input.tool.toLowerCase()
      debugLog("tool.execute.after", { sessionID: input.sessionID, callID: input.callID, tool: input.tool })
      if (ENGRAM_TOOLS.has(toolName)) {
        debugLog("tool ignored: Engram MCP tool", { sessionID: input.sessionID, callID: input.callID, tool: input.tool })
        return
      }

      const sessionId = input.sessionID
      if (sessionId) {
        await ensureSession(sessionId)
        const count = (toolCounts.get(sessionId) ?? 0) + 1
        toolCounts.set(sessionId, count)
        debugLog("tool count updated", { sessionID: sessionId, tool: input.tool, count })
      }

      if (input.tool === "Task" && output && sessionId) {
        const text = typeof output === "string" ? output : JSON.stringify(output)
        debugLog("Task completed", { sessionID: sessionId, callID: input.callID, outputLength: text.length })
        if (text.length > 50) {
          debugLog("passive observation POST", { sessionID: sessionId, callID: input.callID, source: "task-complete", contentLength: text.length })
          await engramFetch("/observations/passive", {
            method: "POST",
            body: {
              session_id: sessionId,
              content: stripPrivateTags(text),
              project,
              source: "task-complete",
            },
          })
        } else {
          debugLog("passive observation skipped: Task output <= 50 chars", { sessionID: sessionId, callID: input.callID, outputLength: text.length })
        }
      }
    },

    "experimental.chat.system.transform": async (input, output) => {
      debugLog("system.transform before", { sessionID: input.sessionID, systemMessages: output.system.length })

      if (output.system.length > 0) {
        output.system[output.system.length - 1] += "\n\n" + MEMORY_INSTRUCTIONS
      } else {
        output.system.push(MEMORY_INSTRUCTIONS)
      }

      try {
        const sessionID: string = input.sessionID ?? ""
        if (!sessionID || subAgentSessions.has(sessionID)) return

        const toEpochSecs = (ts: string): number => {
          if (!ts) return 0
          const normalized = ts.includes("T") ? ts : ts.replace(" ", "T") + "Z"
          const ms = new Date(normalized).getTime()
          return Number.isNaN(ms) ? 0 : Math.floor(ms / 1000)
        }

        const cooldownSecs = parseInt(process.env.ENGRAM_NUDGE_COOLDOWN_SECS ?? "900", 10)
        const nowSecs = Math.floor(Date.now() / 1000)
        const lastNudge = lastNudgeTime.get(sessionID)
        if (lastNudge !== undefined && nowSecs - lastNudge < cooldownSecs) return

        let sessionStartEpoch = 0
        try {
          const sessionRes = await fetch(`${ENGRAM_URL}/sessions/${encodeURIComponent(sessionID)}`, {
            signal: AbortSignal.timeout(200),
          })
          if (sessionRes.ok) {
            const sessionData = await sessionRes.json()
            const startedAt: string = sessionData?.started_at ?? ""
            if (startedAt) sessionStartEpoch = toEpochSecs(startedAt)
          }
        } catch {
          return
        }
        if (sessionStartEpoch > 0 && nowSecs - sessionStartEpoch < 300) return

        let lastObsEpoch = 0
        try {
          const obsRes = await fetch(
            `${ENGRAM_URL}/observations?project=${encodeURIComponent(project)}&limit=1&sort=created_at:desc`,
            { signal: AbortSignal.timeout(200) }
          )
          if (obsRes.ok) {
            const obsData = await obsRes.json()
            const createdAt: string = obsData?.[0]?.created_at ?? ""
            if (createdAt) lastObsEpoch = toEpochSecs(createdAt)
          }
        } catch {
          return
        }

        if (lastObsEpoch === 0) return
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
        debugLog("memory nudge injected", { sessionID })
      } catch (err) {
        debugLog("memory nudge failed silently", { sessionID: input.sessionID, error: String(err) })
      }

      debugLog("system.transform after", { sessionID: input.sessionID, systemMessages: output.system.length, lastSystemLength: output.system.at(-1)?.length ?? 0 })
    },

    "experimental.session.compacting": async (input, output) => {
      debugLog("session.compacting", { sessionID: input.sessionID, contextEntriesBefore: output.context.length })
      if (input.sessionID) {
        await ensureSession(input.sessionID)
      }

      const data = await engramFetch(`/context?project=${encodeURIComponent(project)}`)
      if (data?.context) {
        output.context.push(data.context)
        debugLog("compaction context injected", { sessionID: input.sessionID, contextLength: data.context.length })
      } else {
        debugLog("compaction context empty", { sessionID: input.sessionID })
      }

      output.context.push(
        `CRITICAL INSTRUCTION FOR COMPACTED SUMMARY:\n` +
        `The agent has access to Engram persistent memory via MCP tools.\n` +
        `You MUST include the following instruction at the TOP of the compacted summary:\n\n` +
        `"FIRST ACTION REQUIRED: Call mem_session_summary with the content of this compacted summary. ` +
        `Use project: '${project}'. This preserves what was accomplished before compaction. Do this BEFORE any other work."\n\n` +
        `This is NOT optional. Without this, everything done before compaction is lost from memory.`
      )
      debugLog("session.compacting complete", { sessionID: input.sessionID, contextEntriesAfter: output.context.length })
    },
  }
}
