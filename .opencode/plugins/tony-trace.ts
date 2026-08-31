import type { Plugin } from "@opencode-ai/plugin"
import { appendFileSync } from "node:fs"
import { join } from "node:path"

type Tokens = { total?: number; input?: number; output?: number; reasoning?: number; cacheRead?: number; cacheWrite?: number }

type Trace = {
  ts: string
  event: string
  session?: string
  call?: string
  message?: string
  agent?: string
  model?: string
  phase?: string
  tool?: string
  task?: string
  result?: string
  durationMs?: number
  tokens?: Tokens
}

function tokens(value: unknown): Tokens | undefined {
  if (!value || typeof value !== "object") return undefined
  const v = value as Record<string, unknown>
  const c = v.cache && typeof v.cache === "object" ? v.cache as Record<string, unknown> : undefined
  const t: Tokens = {}
  if (typeof v.total === "number") t.total = v.total
  if (typeof v.input === "number") t.input = v.input
  if (typeof v.output === "number") t.output = v.output
  if (typeof v.reasoning === "number") t.reasoning = v.reasoning
  if (typeof c?.read === "number") t.cacheRead = c.read
  if (typeof c?.write === "number") t.cacheWrite = c.write
  return Object.keys(t).length ? t : undefined
}

function phase(agent: unknown): string | undefined {
  if (typeof agent !== "string") return undefined
  if (agent.startsWith("sdd-")) return agent
  if (agent === "explore" || agent === "general") return agent
  return undefined
}

function model(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined
  const v = value as Record<string, unknown>
  return typeof v.providerID === "string" && typeof v.modelID === "string" ? `${v.providerID}/${v.modelID}` : undefined
}

function result(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined
  const v = value as Record<string, unknown>
  if (typeof v.output !== "string") return undefined
  return v.output.length ? "ok" : "empty"
}

export const TonyTrace: Plugin = async ({ directory, worktree }) => {
  const cwd = worktree || directory
  const path = process.env.TONY_TRACE_LOG ?? join(cwd, ".opencode", "tony-trace.jsonl")
  const starts = new Map<string, number>()
  const phases = new Map<string, string>()
  const seen = new Set<string>()

  const log = (event: string, data: Omit<Trace, "ts" | "event"> = {}) => {
    try {
      const line: Trace = { ts: new Date().toISOString(), event, ...data }
      appendFileSync(path, JSON.stringify(line) + "\n", "utf8")
    } catch (error) {
      console.error("[TONY TRACE] write failed", String(error))
    }
  }

  log("RUN_START")

  return {
    event: async ({ event }) => {
      const p = event.properties as Record<string, unknown> | undefined

      if (event.type === "session.created") {
        const info = p?.info as Record<string, unknown> | undefined
        log("SESSION_CREATE", { session: typeof info?.id === "string" ? info.id : undefined, agent: typeof info?.agent === "string" ? info.agent : undefined })
        return
      }

      if (event.type === "session.deleted") {
        const info = p?.info as Record<string, unknown> | undefined
        const session = typeof info?.id === "string" ? info.id : undefined
        log("SESSION_DELETE", { session })
        if (session) { phases.delete(session); for (const key of starts.keys()) if (key.startsWith(session + ":")) starts.delete(key) }
        return
      }

      if (event.type === "session.status") {
        const session = typeof p?.sessionID === "string" ? p.sessionID : undefined
        const status = p?.status as Record<string, unknown> | undefined
        log("SESSION_STATUS", { session, result: typeof status?.type === "string" ? status.type : undefined })
        return
      }

      if (event.type === "session.error") {
        log("SESSION_ERROR", { session: typeof p?.sessionID === "string" ? p.sessionID : undefined })
        return
      }

      if (event.type === "session.compacted") {
        log("CONTEXT_COMPACTION", { session: typeof p?.sessionID === "string" ? p.sessionID : undefined })
        return
      }

      if (event.type === "permission.asked" || event.type === "permission.replied") {
        log(event.type === "permission.asked" ? "PERMISSION_ASK" : "PERMISSION_REPLY", { session: typeof p?.sessionID === "string" ? p.sessionID : undefined })
        return
      }

      if (event.type === "message.updated") {
        const info = p?.info as Record<string, unknown> | undefined
        if (info?.role !== "assistant") return
        const session = typeof info.sessionID === "string" ? info.sessionID : undefined
        const agent = typeof info.agent === "string" ? info.agent : undefined
        const currentPhase = phase(agent)
        if (session && currentPhase) phases.set(session, currentPhase)
        log("MODEL_DECISION", {
          session,
          message: typeof info.id === "string" ? info.id : undefined,
          agent,
          model: model(info),
          phase: currentPhase ?? (session ? phases.get(session) : undefined),
          result: typeof info.finish === "string" ? info.finish : undefined,
          tokens: tokens(info.tokens),
        })
        return
      }

      if (event.type === "message.part.updated") {
        const part = p?.part as Record<string, unknown> | undefined
        if (!part) return
        const session = typeof part.sessionID === "string" ? part.sessionID : undefined

        if (part.type === "step-finish") {
          const id = typeof part.id === "string" ? part.id : undefined
          if (id && seen.has(id)) return
          if (id) seen.add(id)
          log("MODEL_STEP", {
            session,
            message: typeof part.messageID === "string" ? part.messageID : undefined,
            phase: session ? phases.get(session) : undefined,
            result: typeof part.reason === "string" ? part.reason : undefined,
            tokens: tokens(part.tokens),
          })
        }

        if (part.type === "subtask") {
          const agent = typeof part.agent === "string" ? part.agent : undefined
          const currentPhase = phase(agent) ?? agent
          if (session && currentPhase) phases.set(session, currentPhase)
          log("TASK_CREATE", {
            session,
            message: typeof part.messageID === "string" ? part.messageID : undefined,
            task: typeof part.id === "string" ? part.id : undefined,
            agent,
            phase: currentPhase,
            model: model(part.model),
          })
        }
      }
    },

    "tool.execute.before": async (input, output) => {
      const key = `${input.sessionID}:${input.callID}`
      starts.set(key, Date.now())
      const args = output.args as Record<string, unknown> | undefined
      const agent = typeof args?.subagent_type === "string" ? args.subagent_type : undefined
      log(input.tool.toLowerCase() === "task" ? "TASK_DISPATCH" : "TOOL_REQUEST", {
        session: input.sessionID,
        call: input.callID,
        tool: input.tool,
        agent,
        phase: phase(agent) ?? phases.get(input.sessionID),
        task: typeof args?.description === "string" ? args.description.slice(0, 160) : undefined,
      })
    },

    "tool.execute.after": async (input, output) => {
      const key = `${input.sessionID}:${input.callID}`
      const start = starts.get(key)
      starts.delete(key)
      log(input.tool.toLowerCase() === "task" ? "TASK_COMPLETE" : "TOOL_RESULT", {
        session: input.sessionID,
        call: input.callID,
        tool: input.tool,
        phase: phases.get(input.sessionID),
        result: result(output),
        durationMs: start === undefined ? undefined : Date.now() - start,
      })
    },
  }
}

export default TonyTrace
