import type { Plugin } from "@opencode-ai/plugin"
import { appendFileSync } from "node:fs"
import { join } from "node:path"

type TraceRecord = {
  ts: string
  event: string
  session?: string
  call?: string
  message?: string
  agent?: string
  model?: string
  phase?: string
  task?: string
  tool?: string
  result?: string
  reason?: string
  tokens?: {
    total?: number
    input?: number
    output?: number
    reasoning?: number
    cacheRead?: number
    cacheWrite?: number
  }
  durationMs?: number
}

function tokenSnapshot(value: unknown): TraceRecord["tokens"] | undefined {
  if (!value || typeof value !== "object") return undefined
  const tokens = value as Record<string, unknown>
  const cache = tokens.cache
  const cacheRecord = cache && typeof cache === "object" ? cache as Record<string, unknown> : undefined
  const out: NonNullable<TraceRecord["tokens"]> = {}
  if (typeof tokens.total === "number") out.total = tokens.total
  if (typeof tokens.input === "number") out.input = tokens.input
  if (typeof tokens.output === "number") out.output = tokens.output
  if (typeof tokens.reasoning === "number") out.reasoning = tokens.reasoning
  if (typeof cacheRecord?.read === "number") out.cacheRead = cacheRecord.read
  if (typeof cacheRecord?.write === "number") out.cacheWrite = cacheRecord.write
  return Object.keys(out).length ? out : undefined
}

function modelName(info: unknown): string | undefined {
  if (!info || typeof info !== "object") return undefined
  const value = info as Record<string, unknown>
  if (typeof value.providerID !== "string" || typeof value.modelID !== "string") return undefined
  return `${value.providerID}/${value.modelID}`
}

function assistantInfo(info: unknown): Record<string, unknown> | undefined {
  if (!info || typeof info !== "object") return undefined
  const value = info as Record<string, unknown>
  return value.role === "assistant" ? value : undefined
}

function phaseFromAgent(agent: unknown): string | undefined {
  if (typeof agent !== "string") return undefined
  if (agent.startsWith("sdd-")) return agent
  if (["explore", "general"].includes(agent)) return agent
  return undefined
}

function safeResult(output: unknown): string | undefined {
  if (!output || typeof output !== "object") return undefined
  const value = output as Record<string, unknown>
  if (typeof value.output === "string") {
    if (value.output.length === 0) return "empty"
    return "ok"
  }
  return undefined
}

export const TonyTrace: Plugin = async ({ directory, worktree }) => {
  const cwd = worktree || directory
  const logPath = process.env.TONY_TRACE_LOG ?? join(cwd, ".opencode", "tony-trace.jsonl")
  const starts = new Map<string, number>()
  const phases = new Map<string, string>()
  const tasks = new Map<string, string>()
  const seenStepTokens = new Set<string>()

  const write = (record: Omit<TraceRecord, "ts">) => {
    try {
      const line: TraceRecord = { ts: new Date().toISOString(), ...record }
      appendFileSync(logPath, JSON.stringify(line) + "\n", "utf8")
    } catch (error) {
      console.error("[TONY TRACE] unable to write trace", { logPath, error: String(error) })
    }
  }

  write({ event: "RUN_START" })

  return {
    event: async ({ event }) => {
      const properties = event.properties as Record<string, unknown> | undefined

      if (event.type === "session.created") {
        const info = properties?.info as Record<string, unknown> | undefined
        write({
          event: "SESSION_CREATE",
          session: typeof info?.id === "string" ? info.id : undefined,
          agent: typeof info?.agent === "string" ? info.agent : undefined,
        })
        return
      }

      if (event.type === "session.deleted") {
        const info = properties?.info as Record<string, unknown> | undefined
        const session = typeof info?.id === "string" ? info.id : undefined
        write({ event: "SESSION_DELETE", session })
        if (session) {
          phases.delete(session)
          starts.delete(session)
        }
        return
      }

      if (event.type === "session.status") {
        const session = typeof properties?.sessionID === "string" ? properties.sessionID : undefined
        const status = properties?.status as Record<string, unknown> | undefined
        write({ event: "SESSION_STATUS", session, result: typeof status?.type === "string" ? status.type : undefined })
        return
      }

      if (event.type === "session.error") {
        const session = typeof properties?.sessionID === "string" ? properties.sessionID : undefined
        write({ event: "SESSION_ERROR", session })
        return
      }

      if (event.type === "session.compacted") {
        const session = typeof properties?.sessionID === "string" ? properties.sessionID : undefined
        write({ event: "CONTEXT_COMPACTION", session })
        return
      }

      if (event.type === "permission.asked" || event.type === "permission.replied") {
        const session = typeof properties?.sessionID === "string" ? properties.sessionID : undefined
        write({ event: event.type === "permission.asked" ? "PERMISSION_ASK" : "PERMISSION_REPLY", session })
        return
      }

      if (event.type === "message.updated") {
        const info = properties?.info
        const assistant = assistantInfo(info)
        if (!assistant) return
        const session = typeof assistant.sessionID === "string" ? assistant.sessionID : undefined
        const agent = typeof assistant.agent === "string" ? assistant.agent : undefined
        const phase = phaseFromAgent(agent)
        if (session && phase) phases.set(session, phase)
        write({
          event: "MODEL_DECISION",
          session,
          message: typeof assistant.id === "string" ? assistant.id : undefined,
          agent,
          model: modelName(assistant),
          phase: phase ?? (session ? phases.get(session) : undefined),
          result: typeof assistant.finish === "string" ? assistant.finish : undefined,
          tokens: tokenSnapshot(assistant.tokens),
        })
        return
      }

      if (event.type === "message.part.updated") {
        const part = properties?.part as Record<string, unknown> | undefined
        if (!part) return
        const session = typeof part.sessionID === "string" ? part.sessionID : undefined
        const type = part.type
        if (type === "step-finish") {
          const id = typeof part.id === "string" ? part.id : undefined
          if (id && seenStepTokens.has(id)) return
          if (id) seenStepTokens.add(id)
          write({
            event: "MODEL_STEP",
            session,
            message: typeof part.messageID === "string" ? part.messageID : undefined,
            phase: session ? phases.get(session) : undefined,
            result: typeof part.reason === "string" ? part.reason : undefined,
            tokens: tokenSnapshot(part.tokens),
          })
        } else if (type === "subtask") {
          const agent = typeof part.agent === "string" ? part.agent : undefined
          const task = typeof part.id === "string" ? part.id : undefined
          if (session && agent) phases.set(session, phaseFromAgent(agent) ?? agent)
          write({
            event: "TASK_CREATE",
            session,
            message: typeof part.messageID === "string" ? part.messageID : undefined,
            task,
            agent,
            phase: phaseFromAgent(agent) ?? agent,
            model: modelName(part.model),
          })
          if (session && task) tasks.set(`${session}:${task}`, agent ?? "unknown")
        }
        return
      }
    },

    "tool.execute.before": async (input, output) => {
      const key = `${input.sessionID}:${input.callID}`
      starts.set(key, Date.now())
      const args = output.args as Record<string, unknown> | undefined
      const agent = typeof args?.subagent_type === "string" ? args.subagent_type : undefined
      const phase = phaseFromAgent(agent) ?? phases.get(input.sessionID)
      write({
        event: input.tool.toLowerCase() === "task" ? "TASK_DISPATCH" : "TOOL_REQUEST",
        session: input.sessionID,
        call: input.callID,
        tool: input.tool,
        agent,
        phase,
        task: typeof args?.description === "string" ? args.description.slice(0, 160) : undefined,
      })
    },

    "tool.execute.after": async (input, output) => {
      const key = `${input.sessionID}:${input.callID}`
      const started = starts.get(key)
      starts.delete(key)
      const durationMs = started === undefined ? undefined : Date.now() - started
      const isTask = input.tool.toLowerCase() === "task"
      write({
        event: isTask ? "TASK_COMPLETE" : "TOOL_RESULT",
        session: input.sessionID,
        call: input.callID,
        tool: input.tool,
        phase: phases.get(input.sessionID),
        result: safeResult(output),
        durationMs,
      })
    },
  }
}

export default TonyTrace
