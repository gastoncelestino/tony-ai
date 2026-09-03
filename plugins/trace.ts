import type { Plugin } from "@opencode-ai/plugin"
import { appendFileSync } from "node:fs"
import { join } from "node:path"
import { authorizeExecution, assertBootstrapToolAllowed, bootstrapStarted, completeBootstrap, completeSuccessfulTask, finishBootstrap, KernelBlockedError, rememberPrompt } from "../kernel/authorize-execution"
import { createExecutionObservationStore } from "../kernel/execution-observation"
import { createExecutionGraph } from "../kernel/execution-graph"
import { createEvidenceLedger, recordToolEvidence } from "../kernel/evidence-ledger"
import { evaluateEvidenceClaim, type EvidenceClaim, type EvidenceClaimType, type EvidenceGateResult } from "../kernel/evidence-gate"

const WORK_TOOLS = new Set(["read", "glob", "grep", "bash", "write", "edit", "apply_patch", "skill", "todowrite", "webfetch", "websearch"])
const REQUIRED_TRACE = ["TASK_CREATE", "MODEL_DECISION", "TOOL_REQUEST", "KERNEL_INTERCEPT", "KERNEL_DECISION", "TOOL_EXECUTE_START", "TOOL_EXECUTE_END", "TOOL_RESULT", "TASK_COMPLETE", "PHASE_ENTER", "PHASE_EXIT"] as const
const CLAIM_TYPES = new Set<EvidenceClaimType>(["file_discovery", "file_content", "search", "command", "modification"])

type TokenSnapshot = { input: number; output: number; reasoning: number; cacheRead: number; cacheWrite: number }
type Phase = { agent: string; phase: string; taskID: string; callID: string; sessionID: string; startedAt: number }
type Result = { title: string; output: string; metadata: unknown }
type StructuredClaim = { type: EvidenceClaimType; target?: string; statement?: string; evidenceIds?: string[] }
type EvidenceEvaluation = { allowed: boolean; results: EvidenceGateResult[] }

const asString = (value: unknown) => typeof value === "string" && value.length > 0 ? value : undefined
const argKeys = (value: unknown) => value && typeof value === "object" ? Object.keys(value as Record<string, unknown>).sort() : []
function tokensOf(value: any): TokenSnapshot | undefined {
  const t = value?.tokens
  if (!t || typeof t !== "object") return undefined
  return { input: Number(t.input ?? 0), output: Number(t.output ?? 0), reasoning: Number(t.reasoning ?? 0), cacheRead: Number(t.cache?.read ?? 0), cacheWrite: Number(t.cache?.write ?? 0) }
}
function tokenDelta(previous: TokenSnapshot | undefined, current: TokenSnapshot): TokenSnapshot {
  return { input: Math.max(0, current.input - (previous?.input ?? 0)), output: Math.max(0, current.output - (previous?.output ?? 0)), reasoning: Math.max(0, current.reasoning - (previous?.reasoning ?? 0)), cacheRead: Math.max(0, current.cacheRead - (previous?.cacheRead ?? 0)), cacheWrite: Math.max(0, current.cacheWrite - (previous?.cacheWrite ?? 0)) }
}
function addTokens(a: TokenSnapshot, b: TokenSnapshot): TokenSnapshot { return { input: a.input + b.input, output: a.output + b.output, reasoning: a.reasoning + b.reasoning, cacheRead: a.cacheRead + b.cacheRead, cacheWrite: a.cacheWrite + b.cacheWrite } }
const zeroTokens = (): TokenSnapshot => ({ input: 0, output: 0, reasoning: 0, cacheRead: 0, cacheWrite: 0 })
function normalizeResult(value: unknown): Result {
  if (value && typeof value === "object") {
    const result = value as Record<string, unknown>
    return { title: typeof result.title === "string" ? result.title : "Task", output: typeof result.output === "string" ? result.output : JSON.stringify(value), metadata: result.metadata ?? {} }
  }
  return { title: "Task", output: typeof value === "string" ? value : JSON.stringify(value), metadata: {} }
}
function failed(result: Result) { const metadata = result.metadata; return !!metadata && typeof metadata === "object" && ((metadata as any).status === "error" || (metadata as any).error === true || (metadata as any).failed === true) }
function extractPrompt(parts: unknown[]) { return parts.filter((p): p is { type?: string; text?: string } => !!p && typeof p === "object").filter((p) => p.type === "text" && typeof p.text === "string").map((p) => p.text!.trim()).filter(Boolean).join("\n").trim() }
function extractStructuredClaims(output: string): StructuredClaim[] {
  const match = output.match(/<evidence_claims>\s*([\s\S]*?)\s*<\/evidence_claims>/i)
  if (!match) return []
  try {
    const parsed = JSON.parse(match[1])
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is Record<string, unknown> => !!item && typeof item === "object").flatMap((item) => {
      const type = item.type
      if (typeof type !== "string" || !CLAIM_TYPES.has(type as EvidenceClaimType)) return []
      const target = typeof item.target === "string" && item.target.length > 0 ? item.target : undefined
      const statement = typeof item.statement === "string" && item.statement.length > 0 ? item.statement : undefined
      const evidenceIds = Array.isArray(item.evidenceIds) && item.evidenceIds.every((id) => typeof id === "string") ? item.evidenceIds as string[] : undefined
      return [{ type: type as EvidenceClaimType, target, statement, evidenceIds }]
    })
  } catch {
    return []
  }
}

export const TonyTrace: Plugin = async ({ directory }) => {
  const logPath = join(directory, "tony-trace.jsonl")
  const observations = createExecutionObservationStore()
  const graph = createExecutionGraph()
  const evidence = createEvidenceLedger()
  const phases = new Map<string, Phase>()
  const taskEvents = new Map<string, Set<string>>()
  const tokenByMessage = new Map<string, TokenSnapshot>()
  const sessionTokens = new Map<string, TokenSnapshot>()
  const rootSessionByDirectory = new Map<string, string>()

  const emit = (event: string, details: Record<string, unknown> = {}) => {
    const callID = asString(details.callID)
    if (callID) { const events = taskEvents.get(callID) ?? new Set<string>(); events.add(event); taskEvents.set(callID, events) }
    try { appendFileSync(logPath, JSON.stringify({ ts: new Date().toISOString(), event, ...details }) + "\n", "utf8") }
    catch (error) { console.error("[TONY TRACE] write failed", error) }
  }

  const emitEvidenceSnapshot = (sessionID: string, callID: string, taskID: string) => {
    const entries = evidence.list().filter((entry) => entry.sessionId === sessionID)
    emit("EVIDENCE_SNAPSHOT", {
      sessionID,
      callID,
      taskID,
      count: entries.length,
      evidence: entries.map((entry) => ({ id: entry.id, taskID, kind: entry.kind, tool: entry.tool, target: entry.target })),
    })
  }

  const evaluateTaskEvidence = (sessionID: string, callID: string, taskID: string, claims: EvidenceClaim[] = []): EvidenceEvaluation => {
    const results: EvidenceGateResult[] = []
    for (const claim of claims) {
      const result = evaluateEvidenceClaim(evidence, claim)
      results.push(result)
      emit("EVIDENCE_GATE_RESULT", {
        sessionID,
        callID,
        taskID,
        claimId: result.claimId,
        allowed: result.allowed,
        matchedEvidenceIds: result.matchedEvidenceIds,
        missing: result.missing,
        reason: result.reason,
      })
    }
    return { allowed: results.every((result) => result.allowed), results }
  }

  const emitTaskEvidenceSnapshot = (callID: string, taskID: string, resultOutput: string): EvidenceEvaluation | undefined => {
    const taskNode = graph.getByCallId(callID)
    if (!taskNode) return undefined
    const childSession = graph.getChildren(taskNode.id).find((node) => node.kind === "session")
    if (!childSession) return undefined
    emitEvidenceSnapshot(childSession.sessionId, callID, taskID)
    const structuredClaims = extractStructuredClaims(resultOutput).map((claim, index): EvidenceClaim => ({
      id: `task:${taskID}:claim:${index + 1}`,
      type: claim.type,
      statement: claim.statement,
      evidenceIds: claim.evidenceIds,
      requirements: claim.target ? [{ kind: ({ file_discovery: "FILE_DISCOVERED", file_content: "FILE_CONTENT_READ", search: "SEARCH_RESULT", command: "COMMAND_RESULT", modification: "FILE_MODIFIED" } as const)[claim.type], target: claim.target }] : undefined,
    }))
    emit("EVIDENCE_CLAIMS", { sessionID: childSession.sessionId, callID, taskID, count: structuredClaims.length, claims: structuredClaims })
    return evaluateTaskEvidence(childSession.sessionId, callID, taskID, structuredClaims)
  }

  const closePhase = (callID: string, status: string, result: unknown, childSessionID?: string) => {
    const phase = phases.get(callID); if (!phase) return
    const sessionID = childSessionID ?? phase.sessionID
    emit("PHASE_EXIT", { agent: phase.agent, phase: phase.phase, taskID: phase.taskID, callID, sessionID, status, durationMs: Date.now() - phase.startedAt, tokens: sessionTokens.get(sessionID) ?? zeroTokens(), resultLength: typeof result === "string" ? result.length : undefined })
    const observed = taskEvents.get(callID) ?? new Set<string>()

    if (status === "blocked") {
      emit("TRACE_BLOCKED", { callID, taskID: phase.taskID, phase: phase.phase })
    } else {
      const missing = REQUIRED_TRACE.filter((name) => !observed.has(name))
      emit(missing.length === 0 ? "TRACE_VALID" : "TRACE_INVALID", { callID, taskID: phase.taskID, phase: phase.phase, ...(missing.length ? { missing } : { events: REQUIRED_TRACE.length }) })
    }

    phases.delete(callID); taskEvents.delete(callID)
  }

  return {
    "chat.message": async (input, output) => {
      const prompt = extractPrompt(output.parts)
      if (prompt) rememberPrompt(directory, input.sessionID, prompt)
    },

    "tool.execute.before": async (input, output) => {
      const tool = input.tool.toLowerCase()
      const args = output.args ?? {}
      const subagent = asString(args.subagent_type)
      const taskID = asString(args.task_id) ?? asString(args.taskID) ?? asString(args.id) ?? input.callID

      if (!rootSessionByDirectory.has(directory)) rootSessionByDirectory.set(directory, input.sessionID)
      assertBootstrapToolAllowed(directory, input.tool)
      if (tool !== "task" && WORK_TOOLS.has(tool) && rootSessionByDirectory.get(directory) === input.sessionID && !observations.hasRunningSession(input.sessionID)) {
        emit("TOOL_BLOCKED", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, reason: "work tool blocked in orchestrator session" })
        throw new KernelBlockedError(`[Tony Kernel] Work tool '${input.tool}' is blocked in the orchestrator session; delegate work with task()`)
      }

      emit("TOOL_REQUEST", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, inputKeys: argKeys(args), ...(subagent ? { subagent } : {}) })
      if (tool !== "task") {
        graph.toolStarted({ sessionId: input.sessionID, callId: input.callID, tool: input.tool })
        emit("TOOL_EXECUTE_START", { sessionID: input.sessionID, callID: input.callID, tool: input.tool })
        return
      }

      phases.set(input.callID, { agent: subagent ?? "task", phase: subagent ?? "task", taskID, callID: input.callID, sessionID: input.sessionID, startedAt: Date.now() })
      graph.taskStarted({ sessionId: input.sessionID, callId: input.callID, taskId: taskID, agent: subagent })
      emit("TASK_CREATE", { sessionID: input.sessionID, callID: input.callID, taskID, ...(subagent ? { agent: subagent } : {}) })
      emit("PHASE_ENTER", { sessionID: input.sessionID, phase: subagent ?? "task", taskID, callID: input.callID })
      emit("KERNEL_INTERCEPT", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, taskID, ...(subagent ? { subagent } : {}) })

      try {
        const decision = await authorizeExecution({ directory, sessionID: input.sessionID, callID: input.callID, tool, args })
        const phase = phases.get(input.callID)
        if (!phase) throw new KernelBlockedError("[Tony Kernel] Execution phase disappeared during authorization")
        phase.phase = decision.order.phase || phase.phase
        phase.taskID = decision.order.task_id || taskID
        emit("KERNEL_DECISION", { sessionID: input.sessionID, callID: input.callID, taskID: phase.taskID, decision: "ALLOW", allowed: true, reason: decision.reason })
        observations.start({ projectId: directory, sessionId: input.sessionID, callId: input.callID, taskId: phase.taskID, phase: phase.phase })
      } catch (error) {
        graph.taskFinished({ callId: input.callID, status: "blocked" })
        emit("KERNEL_DECISION", { sessionID: input.sessionID, callID: input.callID, taskID, decision: "BLOCK", allowed: false, reason: error instanceof Error ? error.message : String(error) })
        closePhase(input.callID, "blocked", "")
        throw error
      }
      emit("TOOL_EXECUTE_START", { sessionID: input.sessionID, callID: input.callID, tool: input.tool })
    },

    "tool.execute.after": async (input, output) => {
      const result = normalizeResult(output)
      const phase = phases.get(input.callID)
      const childSessionID = asString((result.metadata as any)?.sessionId) ?? asString((result.metadata as any)?.sessionID)
      if (phase) {
        if (failed(result)) {
          const observation = observations.fail(input.callID, result)
          graph.taskFinished({ callId: input.callID, status: observation.status, result })
          emit("TOOL_EXECUTE_END", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, status: observation.status, outputLength: result.output.length })
          emit("TOOL_RESULT", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, outputLength: result.output.length, output: result.output, childSessionID })
          emit("TASK_COMPLETE", { sessionID: input.sessionID, callID: input.callID, taskID: phase.taskID, status: observation.status })
          closePhase(input.callID, observation.status, result.output, childSessionID)
          return
        }

        const evidenceEvaluation = emitTaskEvidenceSnapshot(input.callID, phase.taskID, result.output)
        if (evidenceEvaluation && !evidenceEvaluation.allowed) {
          const blocked = evidenceEvaluation.results.filter((item) => !item.allowed)
          const first = blocked[0]
          const reason = first?.reason ?? "Evidence requirements are not satisfied"
          const missing = blocked.flatMap((item) => item.missing)
          const missingText = missing.map((item) => `${item.kind}${item.target ? `: ${item.target}` : ""}${item.tool ? ` (tool=${item.tool})` : ""}${item.callId ? ` (callID=${item.callId})` : ""}`).join("\n- ")
          const blockedMessage = `[Tony Kernel] Evidence Gate blocked task '${phase.taskID}'.\nReason: ${reason}\nMissing evidence:\n- ${missingText || "unknown"}`
          output.output = blockedMessage
          output.title = "Evidence Gate blocked"
          if (!output.metadata || typeof output.metadata !== "object") output.metadata = {}
          ;(output.metadata as Record<string, unknown>).status = "error"
          ;(output.metadata as Record<string, unknown>).error = true
          ;(output.metadata as Record<string, unknown>).tonyEvidenceGate = "blocked"

          const observation = observations.incomplete(input.callID)
          graph.taskFinished({ callId: input.callID, status: "blocked", result: normalizeResult(output) })
          emit("EVIDENCE_GATE_BLOCKED", { sessionID: input.sessionID, callID: input.callID, taskID: phase.taskID, allowed: false, claimId: first?.claimId, missing, reason })
          emit("TOOL_EXECUTE_END", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, status: "blocked", outputLength: blockedMessage.length })
          emit("TOOL_RESULT", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, outputLength: blockedMessage.length, output: blockedMessage, childSessionID })
          closePhase(input.callID, "blocked", blockedMessage, childSessionID)
          return
        }

        const observation = observations.succeed(input.callID, result)
        graph.taskFinished({ callId: input.callID, status: observation.status, result })
        emit("TOOL_EXECUTE_END", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, status: observation.status, outputLength: result.output.length })
        emit("TOOL_RESULT", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, outputLength: result.output.length, output: result.output, childSessionID })
        emit("TASK_COMPLETE", { sessionID: input.sessionID, callID: input.callID, taskID: phase.taskID, status: observation.status })
        closePhase(input.callID, observation.status, result.output, childSessionID)

        const isBootstrap = bootstrapStarted(directory, input.sessionID)
        if (isBootstrap) {
          try {
            await completeBootstrap(directory, input.sessionID, result.output)
          } catch (error) {
            emit("BOOTSTRAP_FAILED", { sessionID: input.sessionID, callID: input.callID, reason: error instanceof Error ? error.message : String(error) })
            return
          }

          finishBootstrap(directory, input.sessionID)
        } else {
          await completeSuccessfulTask(directory, input.sessionID, phase.taskID, result)
        }
        return
      }

      const status = failed(result) ? "failed" : "completed"
      graph.toolFinished({ callId: input.callID, status, result })
      const evidenceEntries = recordToolEvidence(evidence, {
        sessionId: input.sessionID,
        callId: input.callID,
        tool: input.tool,
        args: input.args,
        output: result.output,
        metadata: result.metadata,
        failed: status === "failed",
      })
      emit("TOOL_EXECUTE_END", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, status, outputLength: result.output.length })
      emit("TOOL_RESULT", { sessionID: input.sessionID, callID: input.callID, tool: input.tool, outputLength: result.output.length, output: result.output, childSessionID, evidence: evidenceEntries.map((entry) => ({ id: entry.id, kind: entry.kind, target: entry.target })) })
    },

    event: async ({ event }) => {
      const p: any = (event as any).properties ?? {}
      if (event.type === "session.created") {
        const info = p.info ?? {}
        const sessionID = asString(info.id)
        if (sessionID) graph.sessionCreated({ sessionId: sessionID, parentSessionId: asString(info.parentID) })
        if (sessionID && !info.parentID) emit("RUN_START", { sessionID })
      } else if (event.type === "message.updated") {
        const info: any = p.info; if (!info || info.role !== "assistant") return
        const sessionID = asString(info.sessionID); const messageID = asString(info.id); if (!sessionID || !messageID) return
        const current = tokensOf(info)
        if (current) { const delta = tokenDelta(tokenByMessage.get(messageID), current); tokenByMessage.set(messageID, current); sessionTokens.set(sessionID, addTokens(sessionTokens.get(sessionID) ?? zeroTokens(), delta)) }
        if (info.time?.completed) emit("MODEL_DECISION", { sessionID, messageID, action: info.finish === "tool-calls" ? "tool-calls" : "respond", model: `${info.providerID ?? "?"}/${info.modelID ?? "?"}`, finish: info.finish, tokens: current })
      } else if (event.type === "message.part.updated") {
        const part: any = p.part; if (!part) return
        if (part.type === "tool" && part.state?.status === "pending") emit("MODEL_DECISION", { sessionID: part.sessionID, messageID: part.messageID, callID: part.callID, action: "tool", tool: part.tool, inputKeys: argKeys(part.state.input) })
        if (part.type === "step-finish") emit("STEP_FINISH", { sessionID: part.sessionID, messageID: part.messageID, tokens: part.tokens, reason: part.reason })
      } else if (event.type === "permission.asked" || event.type === "permission.replied") emit(event.type === "permission.asked" ? "PERMISSION_ASKED" : "PERMISSION_REPLIED", { sessionID: p.sessionID, callID: p.callID, permission: p.permission ?? p.type })
      else if (event.type === "session.compacted") emit("COMPACTION", { sessionID: p.sessionID })
      else if (event.type === "session.error") emit("SESSION_ERROR", { sessionID: p.sessionID, error: p.error?.name ?? p.error?.message ?? String(p.error ?? "unknown") })
      else if (event.type === "session.deleted") emit("RUN_END", { sessionID: p.info?.id ?? p.sessionID })
    },
  }
}

export default TonyTrace
