import type { Plugin } from "@opencode-ai/plugin"
import { appendFileSync } from "node:fs"
import { join } from "node:path"

type TraceEvent = Record<string, unknown> & { event: string; ts: string }
type Phase = { phase: string; taskID: string; callID: string; sessionID: string; startedAt: number }
type TokenSnapshot = { input: number; output: number; reasoning: number; cacheRead: number; cacheWrite: number }

const PHASES = new Set([
  "sdd-init", "sdd-explore", "sdd-propose", "sdd-spec", "sdd-design",
  "sdd-tasks", "sdd-apply", "sdd-verify", "sdd-archive", "sdd-onboard",
])
const REQUIRED_TASK_TRACE = [
  "TASK_CREATE", "MODEL_DECISION", "TOOL_REQUEST", "KERNEL_INTERCEPT", "KERNEL_DECISION",
  "TOOL_EXECUTE_START", "TOOL_EXECUTE_END", "TOOL_RESULT", "TASK_COMPLETE", "PHASE_ENTER", "PHASE_EXIT",
] as const

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined
}

function tokensOf(value: any): TokenSnapshot | undefined {
  const t = value?.tokens
  if (!t || typeof t !== "object") return undefined
  return {
    input: Number(t.input ?? 0),
    output: Number(t.output ?? 0),
    reasoning: Number(t.reasoning ?? 0),
    cacheRead: Number(t.cache?.read ?? 0),
    cacheWrite: Number(t.cache?.write ?? 0),
  }
}

function tokenDelta(previous: TokenSnapshot | undefined, current: TokenSnapshot): TokenSnapshot {
  return {
    input: Math.max(0, current.input - (previous?.input ?? 0)),
    output: Math.max(0, current.output - (previous?.output ?? 0)),
    reasoning: Math.max(0, current.reasoning - (previous?.reasoning ?? 0)),
    cacheRead: Math.max(0, current.cacheRead - (previous?.cacheRead ?? 0)),
    cacheWrite: Math.max(0, current.cacheWrite - (previous?.cacheWrite ?? 0)),
  }
}

function addTokens(a: TokenSnapshot, b: TokenSnapshot): TokenSnapshot {
  return {
    input: a.input + b.input,
    output: a.output + b.output,
    reasoning: a.reasoning + b.reasoning,
    cacheRead: a.cacheRead + b.cacheRead,
    cacheWrite: a.cacheWrite + b.cacheWrite,
  }
}

function zeroTokens(): TokenSnapshot {
  return { input: 0, output: 0, reasoning: 0, cacheRead: 0, cacheWrite: 0 }
}

function safeJson(value: unknown): string {
  try { return JSON.stringify(value) } catch { return "[unserializable]" }
}

function argKeys(args: unknown): string[] {
  if (!args || typeof args !== "object") return []
  return Object.keys(args as Record<string, unknown>).sort()
}

export const TonyTrace: Plugin = async ({ directory }) => {
  const logPath = join(directory, "tony-trace.jsonl")

  const phases = new Map<string, Phase>()
  const taskPhaseByCall = new Map<string, string>()
  const childSessionPhase = new Map<string, string>()
  const tokenByMessage = new Map<string, TokenSnapshot>()
  const sessionTokens = new Map<string, TokenSnapshot>()
  const taskEvents = new Map<string, Set<string>>()

  const emit = (event: string, details: Record<string, unknown> = {}) => {
    const record: TraceEvent = { ts: new Date().toISOString(), event, ...details }
    const callID = asString(details.callID)
    if (callID) {
      const events = taskEvents.get(callID) ?? new Set<string>()
      events.add(event)
      taskEvents.set(callID, events)
    }
    try { appendFileSync(logPath, safeJson(record) + "\n", "utf8") } catch (error) { console.error("[TONY TRACE] write failed", error) }
  }

  // Public bridge for the Tony Kernel. The Kernel emits KERNEL_INTERCEPT and
  // KERNEL_DECISION without depending on this plugin's implementation.
  const runtime = globalThis as typeof globalThis & {
    __tonyTraceEmit?: (event: string, details?: Record<string, unknown>) => void
  }
  runtime.__tonyTraceEmit = emit

  const closePhase = (callID: string, status: string, result: unknown, childSessionID?: string) => {
    const phase = phases.get(callID)
    if (!phase) return
    const sessionID = childSessionID ?? [...childSessionPhase.entries()].find(([, p]) => p === phase.phase)?.[0]
    const tokens = sessionID ? sessionTokens.get(sessionID) : undefined

    emit("PHASE_EXIT", {
      phase: phase.phase,
      taskID: phase.taskID,
      callID,
      sessionID: sessionID ?? phase.sessionID,
      status,
      durationMs: Date.now() - phase.startedAt,
      tokens: tokens ?? zeroTokens(),
      resultLength: typeof result === "string" ? result.length : undefined,
    })

    const observed = taskEvents.get(callID) ?? new Set<string>()
    const missing = REQUIRED_TASK_TRACE.filter((name) => !observed.has(name))
    if (missing.length === 0) {
      emit("TRACE_VALID", { callID, taskID: phase.taskID, phase: phase.phase, events: REQUIRED_TASK_TRACE.length })
    } else {
      emit("TRACE_INVALID", { callID, taskID: phase.taskID, phase: phase.phase, missing })
    }

    phases.delete(callID)
    taskPhaseByCall.delete(callID)
    taskEvents.delete(callID)
  }

  return {
    event: async ({ event }) => {
      const p: any = (event as any).properties ?? {}

      if (event.type === "session.created") {
        const info = p.info ?? {}
        const sessionID = asString(info.id)
        if (sessionID && !info.parentID) emit("RUN_START", { sessionID })
        return
      }

      if (event.type === "message.updated") {
        const info = p.info
        if (!info || info.role !== "assistant") return
        const sessionID = asString(info.sessionID)
        const messageID = asString(info.id)
        if (!sessionID || !messageID) return

        const current = tokensOf(info)
        if (current) {
          const delta = tokenDelta(tokenByMessage.get(messageID), current)
          tokenByMessage.set(messageID, current)
          sessionTokens.set(sessionID, addTokens(sessionTokens.get(sessionID) ?? zeroTokens(), delta))
        }

        if (info.time?.completed) {
          emit("MODEL_DECISION", {
            sessionID,
            messageID,
            action: info.finish === "tool-calls" ? "tool-calls" : "respond",
            model: `${info.providerID ?? "?"}/${info.modelID ?? "?"}`,
            finish: info.finish,
            tokens: current,
          })
        }
        return
      }

      if (event.type === "message.part.updated") {
        const part: any = p.part
        if (!part) return
        if (part.type === "tool" && part.state?.status === "pending") {
          emit("MODEL_DECISION", {
            sessionID: part.sessionID,
            messageID: part.messageID,
            callID: part.callID,
            action: "tool",
            tool: part.tool,
            inputKeys: argKeys(part.state.input),
          })
        }
        if (part.type === "step-finish") {
          emit("STEP_FINISH", {
            sessionID: part.sessionID,
            messageID: part.messageID,
            tokens: part.tokens,
            reason: part.reason,
          })
        }
        return
      }

      if (event.type === "permission.asked" || event.type === "permission.replied") {
        emit(event.type === "permission.asked" ? "PERMISSION_ASKED" : "PERMISSION_REPLIED", {
          sessionID: p.sessionID,
          callID: p.callID,
          permission: p.permission ?? p.type,
        })
        return
      }

      if (event.type === "session.compacted") {
        emit("COMPACTION", { sessionID: p.sessionID })
        return
      }
      if (event.type === "session.error") {
        emit("SESSION_ERROR", { sessionID: p.sessionID, error: p.error?.name ?? p.error?.message ?? String(p.error ?? "unknown") })
        return
      }
      if (event.type === "session.deleted") {
        emit("RUN_END", { sessionID: p.info?.id ?? p.sessionID })
      }
    },

    "tool.execute.before": async (input, output) => {
      const tool = input.tool.toLowerCase()
      const args: any = output.args ?? {}
      const subagent = asString(args.subagent_type)
      const taskID = asString(args.task_id) ?? asString(args.taskID) ?? asString(args.id)
      const phase = subagent && PHASES.has(subagent) ? subagent : undefined

      emit("TOOL_REQUEST", {
        sessionID: input.sessionID,
        callID: input.callID,
        tool: input.tool,
        inputKeys: argKeys(args),
        ...(subagent ? { subagent } : {}),
      })

      if (tool === "task" && subagent) {
        const phaseName = phase ?? subagent
        taskPhaseByCall.set(input.callID, phaseName)
        phases.set(input.callID, {
          phase: phaseName,
          taskID: taskID ?? input.callID,
          callID: input.callID,
          sessionID: input.sessionID,
          startedAt: Date.now(),
        })
        emit("TASK_CREATE", {
          sessionID: input.sessionID,
          callID: input.callID,
          taskID: taskID ?? input.callID,
          agent: subagent,
        })
        emit("PHASE_ENTER", {
          sessionID: input.sessionID,
          phase: phaseName,
          taskID: taskID ?? input.callID,
          callID: input.callID,
        })
      }

      emit("TOOL_EXECUTE_START", { sessionID: input.sessionID, callID: input.callID, tool: input.tool })
    },

    "tool.execute.after": async (input, output: any) => {
      const text = typeof output?.output === "string" ? output.output : typeof output === "string" ? output : undefined
      const metadata = output?.metadata
      const childSessionID = asString(metadata?.sessionId) ?? asString(metadata?.sessionID)
      const phase = taskPhaseByCall.get(input.callID)
      if (phase && childSessionID) childSessionPhase.set(childSessionID, phase)

      emit("TOOL_EXECUTE_END", {
        sessionID: input.sessionID,
        callID: input.callID,
        tool: input.tool,
        status: metadata?.status ?? "completed",
        outputLength: text?.length,
      })
      emit("TOOL_RESULT", {
        sessionID: input.sessionID,
        callID: input.callID,
        tool: input.tool,
        outputLength: text?.length,
        childSessionID,
      })

      if (phase) {
        const phaseInfo = phases.get(input.callID)
        const status = metadata?.status === "error" ? "error" : "completed"
        emit("TASK_COMPLETE", {
          sessionID: input.sessionID,
          callID: input.callID,
          taskID: phaseInfo?.taskID ?? input.callID,
          status,
        })
        closePhase(input.callID, status, text, childSessionID)
      }
    },
  }
}

export default TonyTrace
